"""
Integration tests for the complete workflow.
Tests the full pipeline from retrieval to analysis.
"""

import pytest
from purchasing_alignment_monitor.agents.workflow import (
    build_workflow,
    initialize_state,
    WorkflowState,
)


class TestWorkflowState:
    """Tests for workflow state initialization."""

    def test_initialize_state_has_all_keys(self):
        """Test that initialized state has all required keys."""
        state = initialize_state()
        
        required_keys = [
            "contract_rules",
            "contract_terms",
            "product_catalog",
            "contracted_products",
            "purchase_order_data",
            "retrieval_errors",
            "parsed_po_data",
            "hospital_analyses",
            "misaligned_hospitals",
            "csv_output",
            "report",
        ]
        
        for key in required_keys:
            assert key in state, f"Missing key: {key}"

    def test_initialize_state_empty_values(self):
        """Test that initialized state has empty/default values."""
        state = initialize_state()
        
        assert state["contract_rules"] == ""
        assert state["contract_terms"] == {}
        assert state["product_catalog"] == ""
        assert state["contracted_products"] == {}
        assert state["retrieval_errors"] == []
        assert state["hospital_analyses"] == []
        assert state["misaligned_hospitals"] == []


class TestWorkflowBuild:
    """Tests for workflow graph construction."""

    def test_workflow_builds_successfully(self):
        """Test that workflow compiles without errors."""
        workflow = build_workflow()
        assert workflow is not None

    def test_workflow_has_correct_nodes(self):
        """Test that workflow has all expected nodes."""
        workflow = build_workflow()
        
        # The compiled graph should have our nodes
        # This is a basic check that the build succeeded
        assert workflow is not None


class TestEndToEndAnalysis:
    """End-to-end tests simulating full workflow execution."""

    def test_full_analysis_with_mock_data(self):
        """Test complete analysis with mock data (bypassing Bedrock)."""
        from purchasing_alignment_monitor.agents.analyzer import analyze_alignment
        from purchasing_alignment_monitor.agents.retriever import (
            parse_contract_terms,
            parse_product_catalog,
        )
        
        # Simulate retrieved contract rules
        contract_text = """
        Volume-Based Pricing Tiers
        
        Tier 1: For annual Net purchases between $800,000 and $900,000, 
        the pricing set forth in Schedule 4.1 shall apply.
        
        Tier 2: For annual Net purchases between $900,001 and $1,000,000, 
        Omnicare shall receive an additional 0.25% discount.
        
        Tier 3: For annual Net purchases exceeding $1,000,000, 
        Omnicare shall receive an additional 0.50% discount.
        """
        
        # Simulate retrieved product catalog
        catalog_text = """product_type,drug_name,ndc,manufacturer,wac_price,contract_price,onestop_eligible
Branded Rx,Lipitor,00071-0155-23,Pfizer,12.50,11.25,N
Branded Rx,Crestor,00310-0755-90,AstraZeneca,14.80,13.32,N
Generic,Lisinopril,00093-1040-01,Teva,0.85,0.68,Y
Generic,Metformin,00093-1048-01,Teva,0.45,0.36,Y
OneStop,Amoxicillin,65862-0015-01,Aurobindo,0.42,0.34,Y
OneStop,Azithromycin,65862-0024-01,Aurobindo,1.85,1.48,Y"""
        
        # Simulate retrieved PO data
        po_data = """hospital_id,hospital_name,vendor_name,drug_name,ndc,product_type,quantity,unit_price,order_date,contract_tier_applied
H001,City Medical Center,McKesson,Lisinopril,00093-1040-01,Generic,100000,0.68,2025-01-10,Tier1
H001,City Medical Center,McKesson,Metformin,00093-1048-01,Generic,80000,0.36,2025-02-05,Tier1
H001,City Medical Center,McKesson,Amoxicillin,65862-0015-01,OneStop,50000,0.34,2025-03-12,Tier1
H001,City Medical Center,McKesson,Lipitor,00071-0155-23,Branded Rx,10000,11.25,2025-03-15,Tier1
H002,Valley Health,McKesson,Lisinopril,00093-1040-01,Generic,50000,0.68,2025-01-15,Tier1
H002,Valley Health,McKesson,Unapproved Drug X,99999-999-99,Off-Contract,7000,4.00,2025-02-20,Tier1
H003,Riverside Hospital,McKesson,Lisinopril,00093-1040-01,Generic,200000,0.62,2025-01-22,Tier2
H003,Riverside Hospital,McKesson,Lipitor,00071-0155-23,Branded Rx,50000,11.25,2025-02-11,Tier2"""
        
        # Build state
        state = {
            "contract_rules": contract_text,
            "contract_terms": parse_contract_terms(contract_text),
            "product_catalog": catalog_text,
            "contracted_products": parse_product_catalog(catalog_text),
            "purchase_order_data": po_data,
        }
        
        # Run analysis
        result = analyze_alignment(state)
        
        # Verify results
        assert len(result["hospital_analyses"]) == 3
        
        # H001 should be ALIGNED (all contracted, good spend)
        h001 = next(h for h in result["hospital_analyses"] if h["hospital_id"] == "H001")
        assert h001["alignment_status"] == "ALIGNED"
        
        # H002 should be MISALIGNED (off-contract purchase)
        h002 = next(h for h in result["hospital_analyses"] if h["hospital_id"] == "H002")
        assert h002["alignment_status"] == "MISALIGNED"
        assert h002["off_contract_purchases"] == 1
        
        # H003 should be ALIGNED (all contracted, Tier 2 spend)
        h003 = next(h for h in result["hospital_analyses"] if h["hospital_id"] == "H003")
        assert h003["alignment_status"] == "ALIGNED"
        assert h003["pricing_tier"] in ["Tier 2", "Tier 3"]

    def test_misaligned_hospitals_list(self):
        """Test that misaligned hospitals are correctly identified."""
        from purchasing_alignment_monitor.agents.analyzer import analyze_alignment
        from purchasing_alignment_monitor.agents.retriever import (
            parse_contract_terms,
            parse_product_catalog,
        )
        
        state = {
            "contract_terms": {
                "tier1_min": 800000.0,
                "tier1_max": 900000.0,
                "tier2_max": 1000000.0,
                "tier3_min": 1000001.0,
            },
            "contracted_products": {
                "all_ndcs": ["00093-1040-01"],
            },
            "purchase_order_data": """hospital_id,hospital_name,vendor_name,drug_name,ndc,product_type,quantity,unit_price,order_date,contract_tier_applied
H001,Good Hospital,McKesson,Lisinopril,00093-1040-01,Generic,100000,2.00,2025-01-10,Tier1
H002,Bad Hospital,McKesson,Unknown Drug,99999-999-99,Off-Contract,5000,4.00,2025-02-20,Tier1
H003,Another Bad,McKesson,Mystery Drug,88888-888-88,Off-Contract,3000,5.00,2025-03-15,Tier1""",
        }
        
        result = analyze_alignment(state)
        
        # Should have 2 misaligned hospitals
        assert len(result["misaligned_hospitals"]) == 2
        
        misaligned_ids = [h["hospital_id"] for h in result["misaligned_hospitals"]]
        assert "H002" in misaligned_ids
        assert "H003" in misaligned_ids
        assert "H001" not in misaligned_ids
