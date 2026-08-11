"""
UCP Hello-Agent: perceive -> reason -> propose -> gate -> commit loop.
"""

from typing import Optional
from pydantic import BaseModel
import vertexai
from vertexai.generative_models import GenerativeModel

PROJECT = "xfuze-nextgen-poc"
REGION = "europe-west4"

vertexai.init(project=PROJECT, location=REGION)

class AgentAction(BaseModel):
    """Proposed action from the agent."""
    action_type: str
    target_ref: str
    rationale: str
    confidence: float
    requires_human: bool = False

def hello_agent_ucp(prompt: str) -> str:
    """
    Hello-Agent proof: take a prompt, call a UCP tool, return grounded response.
    
    Example:
        Input: "What's the price of product XYZ?"
        -> Calls ucp_get_price("XYZ")
        -> Returns: "Product XYZ is £99.99"
    """
    model = GenerativeModel("gemini-1.5-flash-002")
    
    # For now, just respond to text
    # Once ucp_tools are ready, add tool-calling logic here
    response = model.generate_content(f"Answer this retail question concisely: {prompt}")
    
    return response.text

if __name__ == "__main__":
    # Test the agent
    result = hello_agent_ucp("What are typical product categories in retail?")
    print(result)