"""
Contract validation script (Sprint 1, Story 1 — Shuchi's task)

Checks the live xfuze_analytics BigQuery dataset against the documented
contract in data_contracts.md. Fails loudly (non-zero exit, clear report)
on any drift — missing tables, missing/renamed columns, type mismatches,
or suspiciously empty tables — so Pairs 2 and 3 don't discover breakage
silently mid-build.

Run manually:
    python validate_contract.py

Or wire into a pre-flight check / CI step later. Exit code 0 = contract
matches; exit code 1 = drift detected, see printed report.
"""

import os
import sys
from dataclasses import dataclass, field

from google.cloud import bigquery, secretmanager
from google.oauth2 import service_account

PROJECT = os.environ["GCP_PROJECT"]
DATASET = os.environ["BQ_DATASET"]
SECRET_NAME = os.environ["SECRET_NAME"]

# Minimum sane row count — a table with fewer rows than this is likely
# empty/broken rather than legitimately small. Adjust per table if needed.
MIN_ROW_COUNT = 1


# ---------------------------------------------------------------------
# The contract, encoded from data_contracts.md
# Keep this in sync by hand whenever data_contracts.md changes, until/unless
# someone automates generating one from the other.
# ---------------------------------------------------------------------

@dataclass
class TableContract:
    columns: dict  # column_name -> data_type
    min_rows: int = MIN_ROW_COUNT


CONTRACT: dict[str, TableContract] = {
    "dim_products": TableContract(columns={
        "product_id": "STRING", "product_name": "STRING", "category": "STRING",
        "subcategory": "STRING", "base_price": "NUMERIC", "cogs": "NUMERIC",
        "elasticity_true": "FLOAT64", "base_weekly_demand": "INT64",
    }),
    "dim_stores": TableContract(columns={
        "store_id": "STRING", "store_name": "STRING", "region": "STRING",
        "region_id": "STRING", "lat": "FLOAT64", "lng": "FLOAT64",
    }),
    "dim_customers_analytics": TableContract(columns={
        "customer_id": "STRING", "customer_num": "INT64", "customer_name": "STRING",
        "email": "STRING", "region": "STRING", "current_segment": "STRING",
        "loyalty_tier": "STRING", "ltv": "FLOAT64", "roas": "FLOAT64",
        "total_orders": "INT64", "total_units": "INT64", "total_revenue": "FLOAT64",
        "total_refunds": "INT64", "total_refund_value": "FLOAT64",
        "avg_basket": "FLOAT64", "avg_discount_pct": "FLOAT64",
        "first_order_date": "DATE", "last_order_date": "DATE",
        "days_since_last_order": "INT64", "favourite_category": "STRING",
        "favourite_store": "STRING", "loyalty_points": "INT64",
        "favourite_product": "STRING", "persona": "STRING", "created_at": "TIMESTAMP",
    }),
    "fact_inventory_daily": TableContract(columns={
        "warehouse_id": "STRING", "warehouse_name": "STRING", "region": "STRING",
        "product_id": "STRING", "category": "STRING", "subcategory": "STRING",
        "supplier_name": "STRING", "date": "DATE", "units_on_hand": "INT64",
        "units_sold": "INT64", "units_received": "INT64", "cost_price": "NUMERIC",
        "selling_price": "NUMERIC",
    }),
    "fact_customer_orders": TableContract(columns={
        "order_id": "STRING", "customer_id": "STRING", "order_date": "DATE",
        "store_id": "STRING", "store_name": "STRING", "region": "STRING",
        "category": "STRING", "subcategory": "STRING", "product_id": "STRING",
        "product_name": "STRING", "order_amount": "FLOAT64", "item_count": "INT64",
        "discount_amount": "FLOAT64", "discount_pct": "FLOAT64",
        "return_amount": "FLOAT64", "return_reason": "STRING", "is_return": "BOOL",
    }),
    "fact_product_weekly": TableContract(columns={
        "product_id": "STRING", "product_name": "STRING", "subcategory": "STRING",
        "category": "STRING", "week_start": "DATE", "revenue": "NUMERIC",
        "budget": "NUMERIC", "cogs": "NUMERIC", "gross_margin": "NUMERIC",
        "discounts": "NUMERIC", "returns": "NUMERIC", "net_contribution": "NUMERIC",
        "units": "INT64",
    }),
    "fact_price_plan": TableContract(columns={
        "product_id": "STRING", "category": "STRING", "subcategory": "STRING",
        "week_start": "DATE", "list_price": "NUMERIC", "shelf_price": "NUMERIC",
        "is_promo": "BOOL", "promo_type": "STRING", "discount_pct": "FLOAT64",
    }),
    "fact_supply_chain": TableContract(columns={
        "po_id": "STRING", "line_item_id": "STRING", "supplier_id": "STRING",
        "supplier_name": "STRING", "warehouse_id": "STRING", "warehouse_name": "STRING",
        "store_id": "STRING", "category": "STRING", "product_id": "STRING",
        "product_name": "STRING", "sku": "STRING", "order_date": "DATE",
        "expected_date": "DATE", "actual_date": "DATE", "status": "STRING",
        "qty_ordered": "INT64", "qty_received": "INT64", "unit_cost": "NUMERIC",
        "line_value": "NUMERIC", "lead_days_promised": "INT64",
        "lead_days_actual": "INT64", "on_time": "BOOL", "quality_score": "NUMERIC",
        "defect_count": "INT64", "region": "STRING", "fill_rate_pct": "NUMERIC",
    }),
    "fact_bopis_events": TableContract(columns={
        "event_id": "STRING", "order_id": "STRING", "customer_id": "STRING",
        "store_id": "STRING", "store_name": "STRING", "region": "STRING",
        "date": "DATE", "fulfillment_type": "STRING", "status": "STRING",
        "prep_time_mins": "FLOAT64", "sla_target_mins": "INT64", "sla_met": "BOOL",
        "items": "INT64", "order_value": "FLOAT64", "created_at": "TIMESTAMP",
    }),
}


# ---------------------------------------------------------------------
# Auth — same pattern as server.py: pull SA key from Secret Manager
# ---------------------------------------------------------------------

def get_bq_client() -> bigquery.Client:
    sm = secretmanager.SecretManagerServiceClient()
    name = f"projects/{PROJECT}/secrets/{SECRET_NAME}/versions/latest"
    payload = sm.access_secret_version(name=name).payload.data.decode("utf-8")
    import json
    creds_info = json.loads(payload)
    creds = service_account.Credentials.from_service_account_info(creds_info)
    return bigquery.Client(project=PROJECT, credentials=creds)


# ---------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------

@dataclass
class Drift:
    table: str
    issues: list = field(default_factory=list)


def get_live_columns(bq: bigquery.Client) -> dict[str, dict[str, str]]:
    """table_name -> {column_name: data_type} for every table in the dataset."""
    rows = bq.query(
        f"SELECT table_name, column_name, data_type "
        f"FROM `{PROJECT}.{DATASET}.INFORMATION_SCHEMA.COLUMNS` "
        "ORDER BY table_name, ordinal_position"
    ).result()
    live: dict[str, dict[str, str]] = {}
    for r in rows:
        live.setdefault(r.table_name, {})[r.column_name] = r.data_type
    return live


def get_row_count(bq: bigquery.Client, table: str) -> int:
    rows = list(bq.query(
        f"SELECT COUNT(*) AS n FROM `{PROJECT}.{DATASET}.{table}`"
    ).result())
    return int(rows[0]["n"]) if rows else 0


def validate() -> list[Drift]:
    bq = get_bq_client()
    live = get_live_columns(bq)
    all_drifts: list[Drift] = []

    for table, contract in CONTRACT.items():
        drift = Drift(table=table)

        if table not in live:
            drift.issues.append("TABLE MISSING from dataset")
            all_drifts.append(drift)
            continue  # nothing else to check if the table doesn't exist

        live_cols = live[table]

        for col, expected_type in contract.columns.items():
            if col not in live_cols:
                drift.issues.append(f"COLUMN MISSING: '{col}' (expected {expected_type})")
            elif live_cols[col] != expected_type:
                drift.issues.append(
                    f"TYPE MISMATCH: '{col}' expected {expected_type}, "
                    f"found {live_cols[col]}"
                )

        extra_cols = set(live_cols) - set(contract.columns)
        if extra_cols:
            drift.issues.append(
                f"NEW COLUMNS not in contract (informational, not a failure): "
                f"{sorted(extra_cols)}"
            )

        try:
            row_count = get_row_count(bq, table)
            if row_count < contract.min_rows:
                drift.issues.append(
                    f"ROW COUNT SUSPICIOUSLY LOW: {row_count} rows "
                    f"(expected >= {contract.min_rows})"
                )
        except Exception as e:
            drift.issues.append(f"ROW COUNT CHECK FAILED: {e}")

        if drift.issues:
            all_drifts.append(drift)

    return all_drifts


def main():
    print(f"Validating contract for {PROJECT}.{DATASET} "
          f"({len(CONTRACT)} tables)...\n")

    drifts = validate()

    # Separate hard failures from informational-only findings (new columns)
    hard_failures = [
        d for d in drifts
        if any(not issue.startswith("NEW COLUMNS") for issue in d.issues)
    ]

    if not drifts:
        print("✅ Contract matches. No drift detected.")
        sys.exit(0)

    for d in drifts:
        print(f"--- {d.table} ---")
        for issue in d.issues:
            marker = "  ⚠️ " if issue.startswith("NEW COLUMNS") else "  ❌ "
            print(f"{marker}{issue}")
        print()

    if hard_failures:
        print(f"❌ DRIFT DETECTED in {len(hard_failures)} table(s). "
              f"Fix data_contracts.md and server.py, or investigate the source change.")
        sys.exit(1)
    else:
        print("⚠️  Only informational findings (new columns available). "
              "No hard failures.")
        sys.exit(0)


if __name__ == "__main__":
    main()
