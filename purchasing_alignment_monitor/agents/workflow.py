"""
Workflow Module
LangGraph workflow orchestration for purchasing alignment analysis.
"""

from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END
from purchasing_alignment_monitor.agents.retriever import (
    retrieve_contract_rules,
    retrieve_product_catalog,
    retrieve_purchase_order_data,
)
from purchasing_alignment_monitor.agents.analyzer import (
    analyze_alignment,
    generate_ai_insights,
)


class WorkflowState(TypedDict):
    """Complete state for the alignment analysis workflow."""
    # Retrieval phase
    contract_rules: str
    contract_terms: dict
    product_catalog: str
    contracted_products: dict
    purchase_order_data: str
    retrieval_errors: list[str]
    
    # Analysis phase
    parsed_po_data: list[dict]
    hospital_analyses: list[dict]
    misaligned_hospitals: list[dict]
    
    # AI Insights
    ai_insights: dict
    executive_summary: str
    visualizations: dict  # Paths to generated chart images
    
    # Output
    csv_output: Optional[str]
    report: Optional[str]


def build_workflow(include_ai_insights: bool = True):
    """
    Build and compile the LangGraph workflow for purchasing alignment analysis.
    
    Workflow nodes:
    1. Retrieve Contract Rules
    2. Retrieve Product Catalog
    3. Retrieve Purchase Order Data
    4. Analyze Purchasing Alignment
    5. Generate AI Insights (optional)
    
    Args:
        include_ai_insights: Whether to include the AI insights generation node.
                            Set to False for faster execution or testing.
    
    Returns:
        Compiled workflow graph
    """
    workflow = StateGraph(WorkflowState)
    
    # Add nodes
    workflow.add_node("retrieve_contract_rules", retrieve_contract_rules)
    workflow.add_node("retrieve_product_catalog", retrieve_product_catalog)
    workflow.add_node("retrieve_po_data", retrieve_purchase_order_data)
    workflow.add_node("analyze_alignment", analyze_alignment)
    
    if include_ai_insights:
        workflow.add_node("generate_ai_insights", generate_ai_insights)
    
    # Define edges (workflow execution order)
    workflow.add_edge(START, "retrieve_contract_rules")
    workflow.add_edge("retrieve_contract_rules", "retrieve_product_catalog")
    workflow.add_edge("retrieve_product_catalog", "retrieve_po_data")
    workflow.add_edge("retrieve_po_data", "analyze_alignment")
    
    if include_ai_insights:
        workflow.add_edge("analyze_alignment", "generate_ai_insights")
        workflow.add_edge("generate_ai_insights", END)
    else:
        workflow.add_edge("analyze_alignment", END)
    
    # Compile the graph
    app = workflow.compile()
    
    return app


def initialize_state() -> WorkflowState:
    """Initialize the workflow state with empty/default values."""
    return {
        "contract_rules": "",
        "contract_terms": {},
        "product_catalog": "",
        "contracted_products": {},
        "purchase_order_data": "",
        "retrieval_errors": [],
        "parsed_po_data": [],
        "hospital_analyses": [],
        "misaligned_hospitals": [],
        "ai_insights": {},
        "executive_summary": "",
        "visualizations": {},
        "csv_output": None,
        "report": None,
    }
