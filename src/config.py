import os
from dataclasses import dataclass

@dataclass
class Config:
    PROJECT_ID: str = os.getenv("GCP_PROJECT", "xfuze-nextgen-poc")
    LOCATION: str = os.getenv("GCP_LOCATION", "us-central1")
    DATASET_ID: str = os.getenv("BQ_DATASET_ID", "xfuze_analytics")
    MODEL_NAME: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    
    # Guardrails from Xfuze Insights standard
    MAX_BYTES_PER_QUERY: int = 10_000_000_000  # 10 GB
    DAILY_BYTE_BUDGET: int = 100_000_000_000    # 100 GB
    DEFAULT_TENANT_ID: str = os.getenv("TENANT_ID", "tenant_default")

config = Config()