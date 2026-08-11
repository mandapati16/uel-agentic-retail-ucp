import uuid
import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from mcp.server.fastmcp import FastMCP

from src.ucp_tools import (
    get_product,
    get_inventory,
    get_price,
    UcpProduct,
    UcpInventory,
    UcpPricePlan,
)
from src.utils.logger import log_audit_event

logger = logging.getLogger("mcp_server")

# --------------------------------------------------------------------
# 1. ACTION MODEL DEFINITION
# --------------------------------------------------------------------

class AgentAction(BaseModel):
    agent_name: str
    action_type: str
    target_type: str
    target_ref: str
    payload: Dict[str, Any]
    rationale: str
    confidence: float
    requires_human: bool = True
    correlation_id: Optional[str] = None


# --------------------------------------------------------------------
# 2. FASTMCP SERVER INITIALIZATION
# --------------------------------------------------------------------

mcp = FastMCP("UCP-Data-Access-MCP")

@mcp.tool()
def ucp_get_product(product_id: str) -> Dict[str, Any]:
    """Fetches master product attributes from dim_products."""
    product: UcpProduct = get_product(product_id)
    return product.model_dump()

@mcp.tool()
def ucp_get_inventory(product_id: str, location_id: Optional[str] = "WH_CENTRAL") -> Dict[str, Any]:
    """Fetches real-time stock levels and velocity from fact_inventory_daily."""
    inventory: UcpInventory = get_inventory(product_id, location_id)
    return inventory.model_dump()

@mcp.tool()
def ucp_get_price(product_id: str) -> Dict[str, Any]:
    """Fetches active shelf pricing from fact_price_plan."""
    price: UcpPricePlan = get_price(product_id)
    return price.model_dump()

@mcp.tool()
def propose_action(
    agent_name: str,
    action_type: str,
    target_type: str,
    target_ref: str,
    payload: Dict[str, Any],
    rationale: str,
    confidence: float,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Proposes a business action on the agent_actions bus."""
    action_id = str(uuid.uuid4())
    requires_human = True if action_type == "price_change" or confidence < 0.7 else False

    action_record = {
        "action_id": action_id,
        "agent_name": agent_name,
        "action_type": action_type,
        "target_type": target_type,
        "target_ref": target_ref,
        "payload": payload,
        "rationale": rationale,
        "confidence": confidence,
        "status": "PENDING" if requires_human else "APPROVED",
        "requires_human": requires_human,
        "correlation_id": correlation_id or "N/A",
    }

    log_audit_event(
        event_type="ACTION_PROPOSED",
        agent_id=agent_name,
        action=action_type,
        status="PENDING" if requires_human else "APPROVED",
        payload=action_record,
        correlation_id=correlation_id,
    )

    return {
        "action_id": action_id,
        "status": action_record["status"],
        "requires_human": action_record["requires_human"],
    }

if __name__ == "__main__":
    mcp.run()
