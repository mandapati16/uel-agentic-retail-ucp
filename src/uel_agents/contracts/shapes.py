from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class UCPProductPriceRead(BaseModel):
    product_id: str
    sku_id: str
    current_price: float
    weeks_of_cover: float
    sales_velocity: float
    recommended_markdown_pct: Optional[float] = 0.0

class AgentActionSchema(BaseModel):
    action_id: str
    agent_name: str = "agent_b_dynamic_pricing"
    action_type: str = "propose_price_change"
    target_type: str = "sku"
    target_ref: str
    payload: Dict[str, Any]
    rationale: str
    confidence: float
    requires_human: bool = True  # Dynamic pricing changes ALWAYS require human approval (A.5)
    status: str = "PENDING"