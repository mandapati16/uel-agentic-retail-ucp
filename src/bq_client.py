import google.cloud.bigquery as bigquery
from typing import List, Dict, Any
from src.config import config
from src.adapter import DataAdapter

class GuardedBigQueryClient:
    def __init__(self, mode: str = "sandbox"):
        # Initializing client without hardcoding project_id allows 
        # BigQuery to run compute jobs under your local ADC/Cloud Shell billing context.
        self.client = bigquery.Client()
        self.adapter = DataAdapter(mode=mode)
        
        # Explicit dataset path points queries to the target project & dataset
        self.dataset_ref = f"{config.PROJECT_ID}.{config.DATASET_ID}"

    def safe_read_query(self, query: str, tenant_id: str = config.DEFAULT_TENANT_ID) -> List[Dict[str, Any]]:
        # Enforce SELECT-only guardrail
        clean_query = query.strip()
        if not clean_query.upper().startswith("SELECT"):
            raise ValueError("Guardrail Violation: Data-access MCP tools are SELECT-only.")

        # Execute query with byte-cap dry-run or limit
        job_config = bigquery.QueryJobConfig(
            maximum_bytes_billed=config.MAX_BYTES_PER_QUERY
        )
        query_job = self.client.query(clean_query, job_config=job_config)
        return [dict(row) for row in query_job.result()]

    def record_action_bus(self, action_payload: dict):
        """Inserts action proposal directly into agent_actions table."""
        dml = f"""
        INSERT INTO `{self.dataset_ref}.agent_actions` 
        (action_id, agent_name, action_type, target_type, target_ref, payload, rationale, confidence, status, requires_human, created_at)
        VALUES (@action_id, @agent_name, @action_type, @target_type, @target_ref, PARSE_JSON(@payload), @rationale, @confidence, @status, @requires_human, CURRENT_TIMESTAMP())
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("action_id", "STRING", action_payload["action_id"]),
                bigquery.ScalarQueryParameter("agent_name", "STRING", action_payload.get("agent_name", "agent_b_dynamic_pricing")),
                bigquery.ScalarQueryParameter("action_type", "STRING", action_payload["action_type"]),
                bigquery.ScalarQueryParameter("target_type", "STRING", action_payload.get("target_type", "sku")),
                bigquery.ScalarQueryParameter("target_ref", "STRING", action_payload["target_ref"]),
                bigquery.ScalarQueryParameter("payload", "STRING", action_payload["payload_json"]),
                bigquery.ScalarQueryParameter("rationale", "STRING", action_payload["rationale"]),
                bigquery.ScalarQueryParameter("confidence", "FLOAT64", action_payload["confidence"]),
                bigquery.ScalarQueryParameter("status", "STRING", action_payload["status"]),
                bigquery.ScalarQueryParameter("requires_human", "BOOL", action_payload["requires_human"]),
            ]
        )
        self.client.query(dml, job_config=job_config).result()