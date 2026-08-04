"""
xfuze-data-access MCP server
Sprint 1 — Foundations & Hello-Agent (onX/UCP)
Owners: Shuchi Patel & Abdul

Read-only data-access layer over xfuze_analytics, plus the
propose_action / commit_action write path into agent_actions.

IMPORTANT: this server does NOT hold platform-operations tools
(workflows, pipelines, deployments) — that's xfuze-ai / Project Quokka.
This is data discovery + the shared action bus, per Appendix A.
"""
from dotenv import load_dotenv
load_dotenv()
import os
import json
import uuid
from datetime import datetime, timezone

from google.cloud import bigquery, secretmanager
from google.oauth2 import service_account
from fastmcp import FastMCP
from pydantic import BaseModel

# ---------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------

PROJECT = os.environ["GCP_PROJECT"]
DATASET = os.environ["BQ_DATASET"]              # xfuze_analytics
ACTIONS_DATASET = os.environ.get("BQ_ACTIONS_DATASET", DATASET)  # agent_actions may live separately
SECRET_NAME = os.environ["SECRET_NAME"]         # data-access-mcp-json-key

# TODO: replace with the real table set once INFORMATION_SCHEMA is introspected.
# Do not hand-guess columns beyond this — this is just the allow-list gate.
ALLOWED_TABLES = {
    "dim_products", "dim_categories", "dim_subcategories",
    "dim_customers_analytics", "dim_stores", "dim_warehouses",
    "dim_suppliers", "dim_calendar",
    "fact_customer_orders", "fact_orders",
    "fact_inventory_daily", "fact_stock_snapshot",
    "fact_product_weekly", "fact_product_monthly",
    "fact_price_plan", "fact_markdown_sku",
    "fact_supply_chain", "fact_bopis_events",
}

# Human-in-the-loop gate rules (Appendix A.5)
MAX_AUTO_REFUND = float(os.environ.get("MAX_AUTO_REFUND", "50.0"))
CONFIDENCE_GATE = float(os.environ.get("CONFIDENCE_GATE", "0.7"))
MONEY_ACTION_TYPES = {"price_change", "return_refund", "purchase_order"}



# Auth: pull SA key from Secret Manager, never from a local file


def get_bq_client() -> bigquery.Client:
    sm = secretmanager.SecretManagerServiceClient()
    name = f"projects/{PROJECT}/secrets/{SECRET_NAME}/versions/latest"
    payload = sm.access_secret_version(name=name).payload.data.decode("utf-8")
    creds_info = json.loads(payload)
    creds = service_account.Credentials.from_service_account_info(creds_info)
    return bigquery.Client(project=PROJECT, credentials=creds)


bq = get_bq_client()
mcp = FastMCP("xfuze-data-access")



# Query guardrails (Story: onX Hello-Agent proof — "adopt from day one")


def _safe_query(sql: str, params: list = None, max_rows: int = 500):
    if not sql.strip().upper().startswith("SELECT"):
        raise ValueError("Only SELECT statements are permitted")

    referenced = {t for t in ALLOWED_TABLES if t in sql}
    if not referenced:
        raise ValueError("Query does not reference an allow-listed table")

    if "LIMIT" not in sql.upper():
        sql = f"{sql}\nLIMIT {max_rows}"

    job_config = bigquery.QueryJobConfig(query_parameters=params or [])
    return list(bq.query(sql, job_config=job_config).result())


def _param(name: str, value, type_hint: str = "STRING"):
    return bigquery.ScalarQueryParameter(name, type_hint, value)


# ---------------------------------------------------------------------
# Tool-return shapes (Appendix A.3)
# Keep these small; derive field names from INFORMATION_SCHEMA, not memory.
# ---------------------------------------------------------------------


class Sku(BaseModel):
    product_id: str
    product_name: str
    category: str | None = None
    subcategory: str | None = None
    base_price: float | None = None
    cogs: float | None = None
    elasticity_true: float | None = None
    base_weekly_demand: int | None = None



class InventoryPosition(BaseModel):
    product_id: str
    warehouse_id: str
    warehouse_name: str | None = None
    region: str | None = None
    date: str
    units_on_hand: int
    units_sold: int | None = None
    units_received: int | None = None


class OrderLine(BaseModel):
    order_id: str
    customer_id: str
    order_date: str
    store_id: str | None = None
    store_name: str | None = None
    region: str | None = None
    product_id: str
    product_name: str | None = None
    order_amount: float
    item_count: int | None = None
    discount_amount: float | None = None
    discount_pct: float | None = None
    is_return: bool = False
    return_amount: float | None = None
    return_reason: str | None = None
    # NOTE: fact_customer_orders has no lifecycle/status or carrier fields.
    # For WISMO carrier-exception detection, join fact_bopis_events /
    # fact_supply_chain separately — see data_contracts.md.

class VelocityStats(BaseModel):
    product_id: str
    window_days: int
    units_sold: int
    avg_daily_velocity: float
    revenue: float | None = None
    gross_margin: float | None = None


class PricePoint(BaseModel):
    product_id: str
    list_price: float
    shelf_price: float
    is_promo: bool = False
    promo_type: str | None = None
    discount_pct: float | None = None
    week_start: str | None = None

class Policy(BaseModel):
    ref_id: str
    ref_type: str  # sku | order
    return_window_days: int
    max_auto_refund: float


#--------------------------------------------------------------------
# Read tools — any agent may call any of these
# ---------------------------------------------------------------------

@mcp.tool()
def get_sku(product_id: str) -> Sku:
    rows = _safe_query(
        "SELECT product_id, product_name, category, subcategory, "
        "base_price, cogs, elasticity_true, base_weekly_demand "
        f"FROM `{PROJECT}.{DATASET}.dim_products` "
        "WHERE product_id = @product_id",
        params=[_param("product_id", product_id)],
    )
    if not rows:
        raise ValueError(f"Product {product_id} not found")
    return Sku(**dict(rows[0]))

@mcp.tool()
def get_inventory(product_id: str, warehouse_id: str | None = None) -> list[InventoryPosition]:
    # Most recent date per warehouse — this is a daily snapshot table, not a
    # single current-state table.
    sql = (
        "SELECT warehouse_id, warehouse_name, region, product_id, "
        "date, units_on_hand, units_sold, units_received "
        f"FROM `{PROJECT}.{DATASET}.fact_inventory_daily` "
        "WHERE product_id = @product_id "
        "QUALIFY ROW_NUMBER() OVER ("
        "  PARTITION BY warehouse_id ORDER BY date DESC"
        ") = 1"
    )
    params = [_param("product_id", product_id)]
    if warehouse_id:
        sql += " AND warehouse_id = @warehouse_id"
        params.append(_param("warehouse_id", warehouse_id))
    rows = _safe_query(sql, params=params)
    out = []
    for r in rows:
        row = dict(r)
        row["date"] = str(row["date"])
        out.append(InventoryPosition(**row))
    return out


@mcp.tool()
def get_order(order_id: str) ->list[OrderLine]:
    """fact_customer_orders is line-level (one row per product per order),
    so this returns all lines for the order, not a single header row."""
    rows = _safe_query(
        "SELECT order_id, customer_id, order_date, store_id, store_name, "
        "region, product_id, product_name, order_amount, item_count, "
        "discount_amount, discount_pct, is_return, return_amount, return_reason "
        f"FROM `{PROJECT}.{DATASET}.fact_customer_orders` "
        "WHERE order_id = @order_id",
        params=[_param("order_id", order_id)],
    )
    if not rows:
        raise ValueError(f"Order {order_id} not found")
    out = []
    for r in rows:
        row = dict(r)
        row["order_date"] = str(row["order_date"])
        out.append(OrderLine(**row))
    return out


@mcp.tool()
def get_sales_velocity(product_id: str, window_days: int = 30) -> VelocityStats:
    # fact_product_weekly is a weekly aggregate (no daily grain), so "window_days"
    # is converted to a week count and summed across that many recent weeks.
    rows = _safe_query(
        "SELECT SUM(units) AS units_sold, SUM(revenue) AS revenue, "
        "SUM(gross_margin) AS gross_margin "
        f"FROM `{PROJECT}.{DATASET}.fact_product_weekly` "
        "WHERE product_id = @product_id "
        "AND week_start >= DATE_SUB(CURRENT_DATE(), INTERVAL @window_days DAY)",
        params=[_param("product_id", product_id), _param("window_days", window_days, "INT64")],
    )
    row = dict(rows[0]) if rows else {}
    units = int(row.get("units_sold") or 0)
    avg_daily = units / window_days if window_days else 0.0
    return VelocityStats(
        product_id=product_id,
        window_days=window_days,
        units_sold=units,
        avg_daily_velocity=round(avg_daily, 2),
        revenue=float(row["revenue"]) if row.get("revenue") is not None else None,
        gross_margin=float(row["gross_margin"]) if row.get("gross_margin") is not None else None,
    )


@mcp.tool()
def get_price(product_id: str) -> PricePoint:
    rows = _safe_query(
        "SELECT product_id, list_price, shelf_price, is_promo, promo_type, "
        "discount_pct, week_start "
        f"FROM `{PROJECT}.{DATASET}.fact_price_plan` "
        "WHERE product_id = @product_id "
        "ORDER BY week_start DESC "
        "LIMIT 1",
        params=[_param("product_id", product_id)],
    )
    if not rows:
        raise ValueError(f"No price found for {product_id}")
    row = dict(rows[0])
    row["week_start"] = str(row["week_start"]) if row.get("week_start") else None
    return PricePoint(**row)


@mcp.tool()
def get_returns_policy(ref_id: str, ref_type: str = "sku") -> Policy:
    # RESOLVED (was Appendix A.1 "gap to confirm"): fact_customer_orders DOES
    # carry is_return / return_amount / return_reason per line — see get_order
    # and data_contracts.md. This tool is still a policy stub though — the
    # eligibility RULES (return window, max auto-refund) aren't in the data
    # contract, they're business policy. Confirm with the data/product team
    # whether a real policy table exists, or if this threshold stays
    # hardcoded per Brief A.
    return Policy(
        ref_id=ref_id,
        ref_type=ref_type,
        return_window_days=30,
        max_auto_refund=MAX_AUTO_REFUND,
    )


# ---------------------------------------------------------------------
# Write tools — governed (Appendix A.4 / A.5)
# ---------------------------------------------------------------------

class AgentAction(BaseModel):
    agent_name: str
    action_type: str
    target_type: str
    target_ref: str
    payload: dict
    rationale: str
    confidence: float
    correlation_id: str | None = None
    source_action_id: str | None = None


def _requires_human(action: AgentAction) -> bool:
    if action.action_type in MONEY_ACTION_TYPES:
        if action.action_type == "return_refund":
            refund = action.payload.get("refund_amount", 0)
            if refund > MAX_AUTO_REFUND:
                return True
        else:
            return True
    if action.confidence < CONFIDENCE_GATE:
        return True
    return False


@mcp.tool()
def propose_action(action: AgentAction) -> str:
    """Inserts into agent_actions with status=PENDING, or auto-APPROVED
    if the action doesn't require a human gate. Never mutates a business
    record directly — that only happens in commit_action."""
    action_id = str(uuid.uuid4())
    requires_human = _requires_human(action)
    status = "PENDING" if requires_human else "APPROVED"
    now = datetime.now(timezone.utc).isoformat()

    row = {
        "action_id": action_id,
        "agent_name": action.agent_name,
        "action_type": action.action_type,
        "target_type": action.target_type,
        "target_ref": action.target_ref,
        "payload": json.dumps(action.payload),
        "rationale": action.rationale,
        "confidence": action.confidence,
        "requires_human": requires_human,
        "status": status,
        "correlation_id": action.correlation_id or action_id,
        "source_action_id": action.source_action_id,
        "created_at": now,
        "decided_by": "auto" if not requires_human else None,
        "decided_at": now if not requires_human else None,
        "committed_at": None,
    }

    table_ref = f"{PROJECT}.{ACTIONS_DATASET}.agent_actions"
    errors = bq.insert_rows_json(table_ref, [row])
    if errors:
        raise RuntimeError(f"Failed to insert agent_action: {errors}")

    return action_id


@mcp.tool()
def commit_action(action_id: str) -> str:
    """Performs the real write-back for an APPROVED action and marks it
    COMMITTED. Idempotent on action_id. Refuses to run on PENDING actions."""
    table = f"{PROJECT}.{ACTIONS_DATASET}.agent_actions"

    rows = list(bq.query(
        f"SELECT action_type, status, payload, target_ref FROM `{table}` "
        "WHERE action_id = @action_id",
        job_config=bigquery.QueryJobConfig(
            query_parameters=[_param("action_id", action_id)]
        ),
    ).result())

    if not rows:
        raise ValueError(f"Action {action_id} not found")

    action = dict(rows[0])
    if action["status"] == "COMMITTED":
        return "COMMITTED"  # idempotent no-op
    if action["status"] != "APPROVED":
        raise ValueError(
            f"Action {action_id} is {action['status']}, must be APPROVED before commit"
        )

    # TODO: dispatch on action_type to the real write-back
    # (e.g. update fact_inventory_daily, insert into fact_price_plan, etc.)
    # This is per-agent logic that Pairs 1–3 fill in as each agent lands.

    now = datetime.now(timezone.utc).isoformat()
    bq.query(
        f"UPDATE `{table}` SET status = 'COMMITTED', committed_at = @now "
        "WHERE action_id = @action_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            _param("now", now, "TIMESTAMP"),
            _param("action_id", action_id),
        ]),
    ).result()

    return "COMMITTED"


if __name__ == "__main__":
    mcp.run()
