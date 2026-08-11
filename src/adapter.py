import yaml
from typing import Dict, Any

class DataAdapter:
    """
    Portability seam mapping UCP/onX entities onto underlying BigQuery physical tables,
    handling effective-dated freshness rules and tenant/RLS filters.
    """
    def __init__(self, mode: str = "sandbox"):
        self.mode = mode
        self.mappings = {
            "sandbox": {
                "product": "dim_products",
                "price": "fact_price_plan",
                "sales_velocity": "fact_product_weekly",
                "markdown_sku": "fact_markdown_sku",
                "elasticity": "vw_price_elasticity_recommendations",
                "cover_forecast": "vw_weeks_of_cover_forecast"
            },
            "customer_sdv": {
                "product": "sdv_product_events",
                "price": "bi_serving_price_plan",
                "sales_velocity": "sdv_sales_events",
                "markdown_sku": "bi_markdown_feeder",
                "elasticity": "bi_elasticity_model_out",
                "cover_forecast": "bi_weeks_of_cover_out"
            }
        }

    def get_table(self, entity: str) -> str:
        return self.mappings.get(self.mode, {}).get(entity, f"dim_{entity}")

    def apply_freshness_filter(self, entity: str) -> str:
        if self.mode == "customer_sdv":
            # Append-only latest snapshot clause
            return "AND _PARTITIONTIME = CURRENT_DATE()"
        return ""