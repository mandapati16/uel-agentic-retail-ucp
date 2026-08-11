import json
import uuid
from src.bq_client import GuardedBigQueryClient
from src.mcp_tools.schemas import AgentActionSchema

bq = GuardedBigQueryClient()

def propose_action(sku_id: str, proposed_price: float, rationale: str, confidence: float) -> dict:
    """
    Proposes a price markdown on the canonical agent_actions bus.
    Enforces Rule A.5: Price changes are ALWAYS requires_human = True and status = PENDING.
    """
    action_id = str(uuid.uuid4())
    
    # 1. Instantiate the action schema
    action = AgentActionSchema(
        action_id=action_id,
        agent_name="agent_b_dynamic_pricing",
        action_type="propose_price_change",
        target_type="sku",
        target_ref=sku_id,
        payload={"proposed_price": proposed_price, "change_type": "markdown"},
        rationale=rationale,
        confidence=confidence,
        requires_human=True,
        status="PENDING"
    )
    
    # 2. Format payload for BigQuery insertion
    db_payload = {
        "action_id": action.action_id,
        "agent_name": action.agent_name,
        "action_type": action.action_type,
        "target_type": action.target_type,
        "target_ref": action.target_ref,
        "payload_json": json.dumps(action.payload),
        "rationale": action.rationale,
        "confidence": action.confidence,
        "status": action.status,
        "requires_human": action.requires_human
    }
    
    # 3. Write proposal to agent_actions BigQuery table
    bq.record_action_bus(db_payload)
    
    # 4. Return structured response to Gemini agent loop
    return {
        "status": "success",
        "action_id": action_id,
        "message": f"Price change proposal recorded for {sku_id} pending human approval."
    }