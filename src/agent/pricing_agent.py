import vertexai
from vertexai.generative_models import GenerativeModel, Tool, FunctionDeclaration, Part
from src.config import config
import src.mcp_server as mcp_server
from src.utils.logger import log_audit_event

# ---------------------------------------------------------------------
# 1. Enhanced Tool Declarations
# ---------------------------------------------------------------------
ucp_get_product_decl = FunctionDeclaration(
    name="ucp_get_product",
    description="Fetches product details including base_price, cogs, elasticity_true, and base_weekly_demand.",
    parameters={
        "type": "object",
        "properties": {"product_id": {"type": "string", "description": "The SKU ID to query"}},
        "required": ["product_id"]
    }
)

ucp_get_inventory_decl = FunctionDeclaration(
    name="ucp_get_inventory",
    description="Fetches multi-location stock availability, units on hand, and weeks of cover.",
    parameters={
        "type": "object",
        "properties": {
            "product_id": {"type": "string"},
            "location_id": {"type": "string", "description": "Optional warehouse filter"}
        },
        "required": ["product_id"]
    }
)

ucp_get_price_decl = FunctionDeclaration(
    name="ucp_get_price",
    description="Fetches current list price, promo status, competitor pricing, and elasticity recommendations.",
    parameters={
        "type": "object",
        "properties": {"product_id": {"type": "string", "description": "The SKU ID"}},
        "required": ["product_id"]
    }
)

# Added to align with Brief B requirement to read sales velocity
ucp_get_sales_velocity_decl = FunctionDeclaration(
    name="ucp_get_sales_velocity",
    description="Fetches current sales velocity over a specific window of days.",
    parameters={
        "type": "object",
        "properties": {
            "product_id": {"type": "string"},
            "window_days": {"type": "integer", "description": "Lookback window for velocity (e.g., 7 or 30)"}
        },
        "required": ["product_id"]
    }
)

propose_action_decl = FunctionDeclaration(
    name="propose_action",
    description="Proposes a pricing action on the agent_actions bus with human gate enforcement.",
    parameters={
        "type": "object",
        "properties": {
            "agent_name": {"type": "string"},
            "action_type": {"type": "string", "description": "Must be 'price_change'"},
            "target_type": {"type": "string", "description": "Must be 'sku'"},
            "target_ref": {"type": "string", "description": "The target SKU ID"},
            "payload": {"type": "object", "description": "JSON containing proposed_price, discount_percent, and projected_clearance_days"},
            "rationale": {"type": "string", "description": "Detailed chain-of-thought justification using elasticity, cover, and margin analysis"},
            "confidence": {"type": "number", "description": "Confidence score between 0.0 and 1.0"}
        },
        "required": ["agent_name", "action_type", "target_type", "target_ref", "payload", "rationale", "confidence"]
    }
)

def call_mcp_tool(func, *args, **kwargs):
    if hasattr(func, "fn"):
        return func.fn(*args, **kwargs)
    return func(*args, **kwargs)

# ---------------------------------------------------------------------
# 2. Production-Grade Agent Implementation
# ---------------------------------------------------------------------
class DynamicPricingAgent:
    def __init__(self):
        vertexai.init(project=config.PROJECT_ID, location=config.LOCATION)
        
        self.tools = Tool(function_declarations=[
            ucp_get_product_decl, 
            ucp_get_inventory_decl, 
            ucp_get_price_decl, 
            ucp_get_sales_velocity_decl, # Added velocity tool
            propose_action_decl
        ])
        
        self.model = GenerativeModel(
            model_name=config.MODEL_NAME,
            tools=[self.tools],
            system_instruction="""
            You are the Lead Dynamic Pricing Agent for Xiatech (UK Retail Platform).
            Your objective is to optimize gross margin and stock clearance across UK retail inventory.

            CURRENCY RULES:
            - All financial metrics (base_price, cogs, proposed_price) are in British Pounds (£).
            - Always use the '£' symbol in every user-facing rationale and summary.

            DECISION LOGIC & PRICING RULES:
            1. PERCEIVE: Retrieve product metrics using ucp_get_product, ucp_get_inventory, ucp_get_sales_velocity, and ucp_get_price.
            2. ANALYZE TRADING SIGNALS:
               - Stock Cover >= 6 weeks AND Elasticity <= -1.0 (Elastic): Overstocked slow-mover. Recommend a calculated markdown (10% to 25%) to accelerate sell-through.
               - Stock Cover >= 6 weeks AND Elasticity > -1.0 (Inelastic): Overstocked but demand is inelastic. DO NOT discount heavily as volume won't lift. Maintain price or propose a minimal promo.
               - Stock Cover < 3 weeks: Scarcity risk. Hold price at full base_price or recommend price recovery. Do not markdown.
               - Velocity Drop: If current sales velocity is significantly below base_weekly_demand, prioritize a markdown to stimulate demand.
            3. MARGIN GUARDRAIL (CRITICAL):
               - Proposed Price MUST ALWAYS BE STRICTLY GREATER THAN COGS (Cost of Goods Sold).
               - Minimum Gross Margin Threshold = COGS + 15%. Never propose a price below this floor.
            4. ACTION PROPOSAL & QUEUE MANAGEMENT:
               - ONLY call 'propose_action' if you are recommending a tangible price change (i.e., a markdown > 0%).
               - DO NOT call 'propose_action' if maintaining the current price. We do not want to clutter the human approval queue with 0% discount approvals. Simply state the price hold in your text response.
               - When proposing an action, use action_type='price_change', agent_name='agent_b_dynamic_pricing', and target_type='sku'.
               - Include detailed chain-of-thought rationale covering: Current Price, COGS, Weeks Cover, Elasticity, and Margin Impact.
            """
        )

    def evaluate_sku(self, product_id: str, correlation_id: str = None) -> str:
        chat = self.model.start_chat()
        prompt = f"Perform a dynamic pricing evaluation for SKU '{product_id}'."
        
        print(f"\n[System] Initiating Gemini evaluation for SKU '{product_id}'...")
        log_audit_event(
            event_type="EVALUATION_START",
            agent_id="agent_b_dynamic_pricing",
            action="evaluate_sku",
            status="SUCCESS",
            payload={"product_id": product_id},
            correlation_id=correlation_id
        )

        try:
            response = chat.send_message(prompt)

            while response.candidates and response.candidates[0].function_calls:
                function_responses = []
                
                for function_call in response.candidates[0].function_calls:
                    name = function_call.name
                    args = {key: val for key, val in function_call.args.items()}
                    
                    print(f"  [Agent Tool Request]: {name}({args})")
                    
                    try:
                        if name == "ucp_get_product":
                            result = call_mcp_tool(mcp_server.ucp_get_product, **args)
                        elif name == "ucp_get_inventory":
                            result = call_mcp_tool(mcp_server.ucp_get_inventory, **args)
                        elif name == "ucp_get_price":
                            result = call_mcp_tool(mcp_server.ucp_get_price, **args)
                        elif name == "ucp_get_sales_velocity":
                            result = call_mcp_tool(mcp_server.ucp_get_sales_velocity, **args)
                        elif name == "propose_action":
                            if correlation_id and "correlation_id" not in args:
                                args["correlation_id"] = correlation_id
                            result = call_mcp_tool(mcp_server.propose_action, **args)
                        else:
                            result = {"error": f"Unknown tool {name}"}
                    except Exception as e:
                        result = {"error": str(e)}
                    
                    print(f"  [System Tool Output]: {result}")
                    
                    function_responses.append(
                        Part.from_function_response(
                            name=name,
                            response={"content": result}
                        )
                    )

                response = chat.send_message(function_responses)

            final_text = response.text
            log_audit_event(
                event_type="EVALUATION_COMPLETE",
                agent_id="agent_b_dynamic_pricing",
                action="evaluate_sku",
                status="SUCCESS",
                payload={"product_id": product_id, "summary": final_text[:150]},
                correlation_id=correlation_id
            )
            return final_text

        except Exception as err:
            log_audit_event(
                event_type="EVALUATION_FAILED",
                agent_id="agent_b_dynamic_pricing",
                action="evaluate_sku",
                status="ERROR",
                payload={"product_id": product_id},
                error=str(err),
                correlation_id=correlation_id
            )
            raise err