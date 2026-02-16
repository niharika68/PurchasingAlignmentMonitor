"""
Retriever Agent Module
Retrieves contract rules and purchase order data from Bedrock Knowledge Base.
"""

from typing import TypedDict
from purchasing_alignment_monitor.config.bedrock_config import bedrock_config


class RetrieverState(TypedDict):
    """State for retriever operations."""
    contract_rules: str
    purchase_order_data: str
    retrieval_errors: list[str]


def retrieve_contract_rules(state: dict) -> dict:
    """
    Retrieve vendor contract rules from Bedrock Knowledge Base.
    
    Returns contract terms including:
    - Contracted drug lists
    - Price tiers
    - Minimum commitments
    - Eligible hospital classifications
    """
    print("\n=== NODE: Retrieve Contract Rules ===")
    
    try:
        bedrock_runtime = bedrock_config.get_bedrock_agent_runtime()
        
        response = bedrock_runtime.retrieve_and_generate(
            input={
                "text": "What are the vendor contract rules including: contracted drugs, pricing tiers, minimum quarterly commitments, and hospital eligibility classifications?"
            },
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": bedrock_config.knowledge_base_id,
                    "modelArn": bedrock_config.model_arn,
                },
            },
        )
        
        contract_rules = response.get("output", {}).get("text", "")
        print(f"✓ Retrieved contract rules ({len(contract_rules)} characters)")
        state["contract_rules"] = contract_rules
        
    except Exception as e:
        error_msg = f"Error retrieving contract rules: {str(e)}"
        print(f"✗ {error_msg}")
        state["contract_rules"] = ""
        state["retrieval_errors"].append(error_msg)
    
    return state


def retrieve_purchase_order_data(state: dict) -> dict:
    """
    Retrieve quarterly purchase order data from Bedrock Knowledge Base.
    
    Returns data including:
    - Hospital IDs and names
    - Drug purchases (contracted/non-contracted)
    - Quantities and prices
    - Dates and vendors
    """
    print("\n=== NODE: Retrieve Purchase Order Data ===")
    
    try:
        bedrock_runtime = bedrock_config.get_bedrock_agent_runtime()
        
        response = bedrock_runtime.retrieve_and_generate(
            input={
                "text": "Retrieve all quarterly purchase order data including: hospital ID, hospital name, drug name, quantity, unit price, total cost, purchase date, and vendor. Format as CSV."
            },
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": bedrock_config.knowledge_base_id,
                    "modelArn": bedrock_config.model_arn,
                },
            },
        )
        
        po_data = response.get("output", {}).get("text", "")
        print(f"✓ Retrieved purchase order data ({len(po_data)} characters)")
        state["purchase_order_data"] = po_data
        
    except Exception as e:
        error_msg = f"Error retrieving purchase order data: {str(e)}"
        print(f"✗ {error_msg}")
        state["purchase_order_data"] = ""
        state["retrieval_errors"].append(error_msg)
    
    return state
