import uuid
import os
from src.agent.pricing_agent import DynamicPricingAgent
from src.utils.logger import log_audit_event

def run_interactive_simulation():
    agent = DynamicPricingAgent()
    
    print("=" * 70)
    print("=== Initializing Agent B: Dynamic Pricing & Markdown (Interactive) ===")
    print("=" * 70)

    while True:
        # Prompt the user for a Product ID
        sku_id = input("\nEnter a Product ID to evaluate (or type 'exit' to quit): ").strip()
        
        if sku_id.lower() == 'exit':
            print("\nExiting simulation. Goodbye!")
            break
            
        if not sku_id:
            print("Please enter a valid Product ID.")
            continue

        correlation_id = str(uuid.uuid4())
        
        print(f"\n[{sku_id}] Starting evaluation... (Correlation ID: {correlation_id[:8]})")
        print("-" * 50)

        # Audit Event 1: Initiate SKU evaluation
        log_audit_event(
            event_type="EVALUATION_START",
            agent_id="agent_b_dynamic_pricing",
            action="evaluate_sku",
            status="INITIATED",
            payload={"product_id": sku_id},
            correlation_id=correlation_id
        )

        try:
            decision = agent.evaluate_sku(sku_id)
            
            print(f"\n[{sku_id}] Agent Final Decision:\n{decision}")
            
            # Audit Event 2: Log successful completion
            log_audit_event(
                event_type="EVALUATION_COMPLETE",
                agent_id="agent_b_dynamic_pricing",
                action="evaluate_sku",
                status="SUCCESS",
                payload={
                    "product_id": sku_id, 
                    "summary": decision[:150].replace("\n", " ") + "..."
                },
                correlation_id=correlation_id
            )
            
        except Exception as e:
            print(f"\n[{sku_id}] Error during evaluation: {str(e)}")
            
            # Audit Event 3: Log evaluation failure
            log_audit_event(
                event_type="EVALUATION_FAILED",
                agent_id="agent_b_dynamic_pricing",
                action="evaluate_sku",
                status="ERROR",
                payload={"product_id": sku_id},
                correlation_id=correlation_id,
                error=str(e)
            )
            
        print("=" * 70)

if __name__ == "__main__":
    run_interactive_simulation()