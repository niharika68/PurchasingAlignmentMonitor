"""
Workflow Module
LangGraph workflow orchestration for purchasing alignment analysis.
"""

from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END
from purchasing_alignment_monitor.agents.retriever import (
    retrieve_contract_rules,
    retrieve_purchase_order_data,
)
from purchasing_alignment_monitor.agents.analyzer import analyze_alignment


class WorkflowState(TypedDict):
    """Complete state for the alignment analysis workflow."""
    # Retrieval phase
    contract_rules: str
    purchase_order_data: str
    retrieval_errors: list[str]
    
    # Analysis phase
    parsed_po_data: list[dict]
    hospital_analyses: list[dict]
    misaligned_hospitals: list[dict]
    
    # Output
    csv_output: Optional[str]
    report: Optional[str]


def build_workflow():
    """
    Build and compile the LangGraph workflow for purchasing alignment analysis.
    
    Workflow nodes:
    1. Retrieve Contract Rules
    2. Retrieve Purchase Order Data
    3. Analyze Purchasing Alignment
    4. Export CSV Output
    
    Returns:
        Compiled workflow graph
    """
    workflow = StateGraph(WorkflowState)
    
    # Add nodes
    workflow.add_node("retrieve_contract_rules", retrieve_contract_rules)
    workflow.add_node("retrieve_po_data", retrieve_purchase_order_data)
    workflow.add_node("analyze_alignment", analyze_alignment)
    
    # Define edges (workflow execution order)
    workflow.add_edge(START, "retrieve_contract_rules")
    workflow.add_edge("retrieve_contract_rules", "retrieve_po_data")
    workflow.add_edge("retrieve_po_data", "analyze_alignment")
    workflow.add_edge("analyze_alignment", END)
    
    # Compile the graph
    app = workflow.compile()
    
    return app


def initialize_state() -> WorkflowState:
    """Initialize the workflow state with empty/default values."""
    return {
        "contract_rules": "",
        "purchase_order_data": "",
        "retrieval_errors": [],
        "parsed_po_data": [],
        "hospital_analyses": [],
        "misaligned_hospitals": [],
        "csv_output": None,
        "report": None,
    }
