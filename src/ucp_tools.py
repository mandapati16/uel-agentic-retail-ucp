import os
import logging
from typing import Optional, List
from pydantic import BaseModel, Field
from google.cloud import bigquery

from src.config import config

logger = logging.getLogger("ucp_tools")

# --------------------------------------------------------------------
# 1. TYPED UCP PROTOCOL RESPONSE MODELS
# --------------------------------------------------------------------

class UcpProduct(BaseModel):
    product_id: str
    product_name: str
    category: str
    base_price: float
    cogs: float
    base_weekly_demand: int
    elasticity_true: float

class UcpInventory(BaseModel):
    product_id: str
    location_id: str
    stock_on_hand: int
    weekly_sales_velocity: float
    cover_weeks: float

class UcpPricePlan(BaseModel):
    product_id: str
    list_price: float
    shelf_price: float
    is_promo: bool
    discount_pct: float
    week_start: str


# --------------------------------------------------------------------
# 2. GUARDED UCP READ TOOLS (BigQuery + Fallback)
# --------------------------------------------------------------------

def get_product(product_id: str) -> UcpProduct:
    """Fetches master product attributes from dim_products or fallback mock."""
    try:
        client = bigquery.Client(project=config.PROJECT_ID)
        query = f"""
            SELECT product_id, product_name, category, base_price, cogs, base_weekly_demand, elasticity_true
            FROM `{config.PROJECT_ID}.{config.DATASET_ID}.dim_products`
            WHERE product_id = @product_id
            LIMIT 1
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("product_id", "STRING", product_id)]
        )
        query_job = client.query(query, job_config=job_config)
        results = list(query_job.result())

        if results:
            row = results[0]
            return UcpProduct(
                product_id=row.product_id,
                product_name=row.product_name,
                category=row.category,
                base_price=float(row.base_price),
                cogs=float(row.cogs),
                base_weekly_demand=int(row.base_weekly_demand),
                elasticity_true=float(row.elasticity_true)
            )
    except Exception as e:
        logger.warning(f"BigQuery fetch failed for product {product_id}, using fallback: {e}")

    # Fallback typed mock response for testing/resilience
    if "SHOES" in product_id:
        return UcpProduct(
            product_id=product_id,
            product_name="Running Shoes",
            category="Footwear",
            base_price=120.0,
            cogs=45.0,
            base_weekly_demand=150,
            elasticity_true=-1.8
        )
    return UcpProduct(
        product_id=product_id,
        product_name="Winter Trench Coat",
        category="Apparel",
        base_price=250.0,
        cogs=90.0,
        base_weekly_demand=80,
        elasticity_true=-1.2
    )


def get_inventory(product_id: str, location_id: Optional[str] = "WH_CENTRAL") -> UcpInventory:
    """Fetches inventory availability and stock cover weeks from fact_inventory_daily."""
    try:
        client = bigquery.Client(project=config.PROJECT_ID)
        query = f"""
            SELECT product_id, location_id, stock_on_hand, weekly_sales_velocity
            FROM `{config.PROJECT_ID}.{config.DATASET_ID}.fact_inventory_daily`
            WHERE product_id = @product_id AND location_id = @location_id
            ORDER BY snapshot_date DESC
            LIMIT 1
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("product_id", "STRING", product_id),
                bigquery.ScalarQueryParameter("location_id", "STRING", location_id)
            ]
        )
        query_job = client.query(query, job_config=job_config)
        results = list(query_job.result())

        if results:
            row = results[0]
            stock = int(row.stock_on_hand)
            velocity = float(row.weekly_sales_velocity) or 1.0
            return UcpInventory(
                product_id=row.product_id,
                location_id=row.location_id,
                stock_on_hand=stock,
                weekly_sales_velocity=velocity,
                cover_weeks=round(stock / velocity, 2)
            )
    except Exception as e:
        logger.warning(f"BigQuery fetch failed for inventory {product_id}, using fallback: {e}")

    # Fallback mock calculations based on SKU type
    stock = 850 if "SHOES" in product_id else 480
    velocity = 150.0 if "SHOES" in product_id else 80.0
    return UcpInventory(
        product_id=product_id,
        location_id=location_id or "WH_CENTRAL",
        stock_on_hand=stock,
        weekly_sales_velocity=velocity,
        cover_weeks=round(stock / velocity, 2)
    )


def get_price(product_id: str) -> UcpPricePlan:
    """Fetches active shelf pricing and promotional flags from fact_price_plan."""
    try:
        client = bigquery.Client(project=config.PROJECT_ID)
        query = f"""
            SELECT product_id, list_price, shelf_price, is_promo, discount_pct, week_start
            FROM `{config.PROJECT_ID}.{config.DATASET_ID}.fact_price_plan`
            WHERE product_id = @product_id
            ORDER BY week_start DESC
            LIMIT 1
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("product_id", "STRING", product_id)]
        )
        query_job = client.query(query, job_config=job_config)
        results = list(query_job.result())

        if results:
            row = results[0]
            return UcpPricePlan(
                product_id=row.product_id,
                list_price=float(row.list_price),
                shelf_price=float(row.shelf_price),
                is_promo=bool(row.is_promo),
                discount_pct=float(row.discount_pct),
                week_start=str(row.week_start)
            )
    except Exception as e:
        logger.warning(f"BigQuery fetch failed for price {product_id}, using fallback: {e}")

    # Fallback mock price plan
    base = 120.0 if "SHOES" in product_id else 250.0
    return UcpPricePlan(
        product_id=product_id,
        list_price=base,
        shelf_price=base,
        is_promo=False,
        discount_pct=0.0,
        week_start="2026-08-01"
    )