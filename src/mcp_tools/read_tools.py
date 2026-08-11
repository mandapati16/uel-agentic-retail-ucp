from __future__ import annotations

from typing import Any, Dict, Optional
from mcp.server.fastmcp import FastMCP

# Import your UCP query logic and Pydantic schemas from ucp_tools
from uel_agents.mcp_server.ucp_tools import UcpProduct, get_product_by_id, get_price_by_sku, get_inventory_by_sku


def register_read_tools(server: FastMCP) -> None:
    """Register all shared data-access read tools."""

    @server.tool()
    def get_product(product_id: str) -> Dict[str, Any]:
        """Fetch customer-facing product details (UCP-shaped) from BigQuery."""
        product: Optional[UcpProduct] = get_product_by_id(product_id)
        if not product:
            return {"error": f"Product '{product_id}' not found."}
        return product.model_dump()

    @server.tool()
    def get_price(sku_id: str) -> Dict[str, Any]:
        """Get active UCP price point for a specific SKU."""
        return get_price_by_sku(sku_id)

    @server.tool()
    def get_inventory(sku_id: str, location_id: Optional[str] = None) -> Dict[str, Any]:
        """Get real-time stock availability and inventory positions across locations."""
        return get_inventory_by_sku(sku_id, location_id=location_id)