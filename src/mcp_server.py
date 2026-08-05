"""
FastMCP server wrapper for UCP tools.
Exposes guardrailed BigQuery tools as MCP endpoints.
"""

from fastmcp import FastMCP

# TODO: import ucp_tools once ucp_tools.py exists and is in src/
# from src.ucp_tools import get_product

mcp = FastMCP("ucp-data-access")

@mcp.tool()
def ucp_get_product(product_id: str) -> dict:
    """
    UCP-shaped product read: product_id -> {id, name, category, price, availability}.
    Guardrails: SELECT-only, parameterised, LIMIT-injected, byte-capped.
    """
    # Once IAM is fixed and ucp_tools is ready:
    # result = get_product(product_id)
    # return result.dict()
    
    # For now, return a mock response to prove the MCP structure works
    return {
        "product_id": product_id,
        "name": f"Product {product_id}",
        "category": "Electronics",
        "price": 99.99,
        "available": True,
        "description": "Mock product for Sprint 1 MCP proof",
    }

@mcp.tool()
def ucp_get_inventory(product_id: str, location_id: str = None) -> list:
    """
    UCP-shaped inventory read: multi-location stock availability.
    """
    return [
        {
            "product_id": product_id,
            "location_id": location_id or "all",
            "stock_level": 42,
            "available_to_promise": 40,
            "status": "in_stock",
        }
    ]

@mcp.tool()
def ucp_get_price(product_id: str) -> dict:
    """
    UCP-shaped price read: current price + markdown history.
    """
    return {
        "product_id": product_id,
        "price": 99.99,
        "currency": "GBP",
        "markdown_percentage": 0,
        "effective_price": 99.99,
    }

if __name__ == "__main__":
    import uvicorn
    # For local testing
    # uvicorn.run(mcp, host="0.0.0.0", port=8000)
    mcp.run()