import os
import uuid
import logging
from google import genai
from google.genai import types

# Setup Logging
logger = logging.getLogger("ucp-hello-agent")
logger.setLevel(logging.INFO)

# Initialize Vertex AI Client (EU Region)
client = genai.Client(
    vertexai=True,
    project=os.getenv("GCP_PROJECT", "xfuze-nextgen-poc"),
    location=os.getenv("GCP_REGION", "europe-west1")
)

# Define mock functions matching MCP signatures for Vertex Tool calling
def get_product(product_id: str) -> dict:
    # In full deployment, this routes to the MCP server via client libraries
    from mcp_server import get_product as mcp_get_product
    return mcp_get_product(product_id)

def get_price(product_id: str) -> dict:
    from mcp_server import get_price as mcp_get_price
    return mcp_get_price(product_id)

SYSTEM_INSTRUCTION = """
You are a UCP-compliant retail agent for Xfuze Insights.
Your task is to fetch requested product and pricing information using your available tools.
Always begin or end your response with the phrase 'Hello Agent'.
"""

def run_ucp_hello_agent(prompt: str, product_id: str):
    trace_id = str(uuid.uuid4())
    logger.info(f"[TRACE:{trace_id}] Processing prompt: '{prompt}' for SKU: {product_id}")

    # Bind tools to Gemini
    tools = [get_product, get_price]
    
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        temperature=0.2,
        tools=tools
    )

    # Agent Loop: Perceive & Reason
    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=f"{prompt} (Product ID: {product_id})",
        config=config
    )

    logger.info(f"[TRACE:{trace_id}] Execution complete.")
    return response.text

if __name__ == "__main__":
    # Test execution locally
    sample_prompt = "Can you retrieve the current pricing details and say hello agent?"
    output = run_ucp_hello_agent(sample_prompt, product_id="SKU-10024")
    print("\n--- Agent Response ---")
    print(output)