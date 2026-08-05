import os
import time
import json
from datetime import datetime
from typing import Optional
from google.cloud import bigquery
from pydantic import BaseModel

PROJECT = "xfuze-nextgen-poc"
DATASET = "xfuze_analytics"
ALLOWED_TABLES = {"dim_products"}
MAX_BYTES_PER_QUERY = 50_000_000

class UcpProduct(BaseModel):
    """Product entity, UCP-shaped."""
    product_id: str
    name: str
    category: Optional[str] = None
    subcategory: Optional[str] = None
    price: Optional[float] = None
    available: bool = True
    description: Optional[str] = None

def get_product(product_id: str, environment: str = "sandbox") -> UcpProduct:
    """Guarded get_product tool."""
    client = bigquery.Client(project=PROJECT)
    start_time = time.time()
    
    query = f"""
        SELECT 
            product_id,
            product_name,
            category,
            subcategory,
            retail_price as price,
            description
        FROM `{PROJECT}.{DATASET}.dim_products`
        WHERE product_id = @product_id
        LIMIT 1
    """
    
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("product_id", "STRING", product_id)
        ],
        maximum_bytes_billed=MAX_BYTES_PER_QUERY,
        dry_run=False,
        use_query_cache=True,
    )
    
    try:
        query_job = client.query(query, job_config=job_config)
        rows = list(query_job.result())
        latency_ms = (time.time() - start_time) * 1000
        bytes_scanned = query_job.total_bytes_processed or 0
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "environment": environment,
            "tool": "get_product",
            "product_id": product_id,
            "bytes_scanned": bytes_scanned,
            "latency_ms": round(latency_ms, 2),
            "trace_id": query_job.job_id,
            "status": "success",
        }
        print(f"[AUDIT] {json.dumps(log_entry)}")
        
        if not rows:
            raise ValueError(f"Product {product_id} not found")
        
        row = rows[0]
        return UcpProduct(
            product_id=row.product_id,
            name=row.product_name or "Unknown",
            category=row.category,
            subcategory=row.subcategory,
            price=float(row.price) if row.price else None,
            available=True,
            description=row.description,
        )
    
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "environment": environment,
            "tool": "get_product",
            "product_id": product_id,
            "latency_ms": round(latency_ms, 2),
            "trace_id": "unknown",
            "status": "error",
            "error": str(e),
        }
        print(f"[AUDIT] {json.dumps(log_entry)}")
        raise

if __name__ == "__main__":
    import sys
    
    print("=" * 70)
    print("Task #3: Minimal UCP-shaped tool call against sandbox contract")
    print("=" * 70)
    
    client = bigquery.Client(project=PROJECT)
    
    discovery_query = f"""
        SELECT product_id, product_name
        FROM `{PROJECT}.{DATASET}.dim_products`
        LIMIT 5
    """
    
    discovery_rows = list(client.query(discovery_query).result())
    
    if not discovery_rows:
        print("ERROR: No products found in dim_products.")
        sys.exit(1)
    
    print(f"\nFound {len(discovery_rows)} products. Using first one:")
    test_product_id = discovery_rows[0].product_id
    test_product_name = discovery_rows[0].product_name
    print(f"  product_id: {test_product_id}")
    print(f"  product_name: {test_product_name}")
    
    print(f"\nCalling get_product('{test_product_id}')...")
    result = get_product(test_product_id, environment="sandbox")
    
    print(f"\nResult (UCP-shaped):")
    print(result.json(indent=2))
    
    print("\n" + "=" * 70)
    print("✅ Task #3 complete!")
    print("=" * 70)