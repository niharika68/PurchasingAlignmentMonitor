"""
Tests for the Analyzer module.
Tests purchase order parsing, tier determination, and alignment analysis.
"""

import os
import pytest
from purchasing_alignment_monitor.agents.analyzer import (
    parse_purchase_order_csv,
    determine_pricing_tier,
    check_product_contracted,
    analyze_alignment,
)


# Persistent test outputs directory
TEST_OUTPUTS_DIR = os.path.join(os.path.dirname(__file__), "test_outputs")


@pytest.fixture
def test_output_dir():
    """Fixture that provides a persistent test outputs directory."""
    os.makedirs(TEST_OUTPUTS_DIR, exist_ok=True)
    return TEST_OUTPUTS_DIR


class TestParsePurchaseOrderCSV:
    """Tests for parse_purchase_order_csv function."""

    def test_parse_basic_csv(self):
        """Test parsing basic CSV data."""
        csv_data = """hospital_id,hospital_name,vendor_name,drug_name,ndc,product_type,quantity,unit_price,order_date,contract_tier_applied
H001,City Medical Center,McKesson,Lisinopril,00093-1040-01,Generic,12000,0.68,2025-01-10,Tier1
H001,City Medical Center,McKesson,Metformin,00093-1048-01,Generic,8000,0.36,2025-02-05,Tier1"""
        
        records = parse_purchase_order_csv(csv_data)
        
        assert len(records) == 2
        assert records[0]["hospital_id"] == "H001"
        assert records[0]["drug_name"] == "Lisinopril"
        assert records[0]["quantity"] == 12000

    def test_parse_csv_with_markdown_formatting(self):
        """Test parsing CSV wrapped in markdown code blocks."""
        csv_data = """```csv
hospital_id,hospital_name,vendor_name,drug_name,ndc,product_type,quantity,unit_price,order_date,contract_tier_applied
H001,City Medical Center,McKesson,Lisinopril,00093-1040-01,Generic,12000,0.68,2025-01-10,Tier1
```"""
        
        records = parse_purchase_order_csv(csv_data)
        
        assert len(records) == 1
        assert records[0]["hospital_id"] == "H001"

    def test_parse_empty_csv(self):
        """Test parsing empty CSV returns empty list."""
        records = parse_purchase_order_csv("")
        assert records == []

    def test_column_names_normalized(self):
        """Test that column names are normalized to lowercase."""
        csv_data = """Hospital_ID,Hospital_Name,Vendor_Name,Drug_Name,NDC,Product_Type,Quantity,Unit_Price,Order_Date,Contract_Tier_Applied
H001,City Medical Center,McKesson,Lisinopril,00093-1040-01,Generic,12000,0.68,2025-01-10,Tier1"""
        
        records = parse_purchase_order_csv(csv_data)
        
        assert "hospital_id" in records[0]
        assert "drug_name" in records[0]


class TestDeterminePricingTier:
    """Tests for determine_pricing_tier function."""

    @pytest.fixture
    def contract_terms(self):
        """Sample contract terms for testing."""
        return {
            "tier1_min": 800000.0,
            "tier1_max": 900000.0,
            "tier2_min": 900001.0,
            "tier2_max": 1000000.0,
            "tier3_min": 1000001.0,
        }

    def test_below_tier1(self, contract_terms):
        """Test spend below Tier 1 minimum."""
        tier = determine_pricing_tier(500000.0, contract_terms)
        assert tier == "Below Tier 1"

    def test_tier1(self, contract_terms):
        """Test spend in Tier 1 range."""
        tier = determine_pricing_tier(850000.0, contract_terms)
        assert tier == "Tier 1"

    def test_tier2(self, contract_terms):
        """Test spend in Tier 2 range."""
        tier = determine_pricing_tier(950000.0, contract_terms)
        assert tier == "Tier 2"

    def test_tier3(self, contract_terms):
        """Test spend exceeding Tier 3 minimum."""
        tier = determine_pricing_tier(1500000.0, contract_terms)
        assert tier == "Tier 3"

    def test_tier1_boundary_min(self, contract_terms):
        """Test spend exactly at Tier 1 minimum."""
        tier = determine_pricing_tier(800000.0, contract_terms)
        assert tier == "Tier 1"

    def test_tier1_boundary_max(self, contract_terms):
        """Test spend exactly at Tier 1 maximum."""
        tier = determine_pricing_tier(900000.0, contract_terms)
        assert tier == "Tier 1"

    def test_tier2_boundary(self, contract_terms):
        """Test spend exactly at Tier 2 maximum."""
        tier = determine_pricing_tier(1000000.0, contract_terms)
        assert tier == "Tier 2"


class TestCheckProductContracted:
    """Tests for check_product_contracted function."""

    @pytest.fixture
    def contracted_products(self):
        """Sample contracted products for testing."""
        return {
            "branded": [{"drug_name": "lipitor", "ndc": "00071-0155-23"}],
            "generic": [{"drug_name": "lisinopril", "ndc": "00093-1040-01"}],
            "onestop": [{"drug_name": "amoxicillin", "ndc": "65862-0015-01"}],
            "all_ndcs": ["00071-0155-23", "00093-1040-01", "65862-0015-01"],
        }

    def test_contracted_by_ndc(self, contracted_products):
        """Test product is contracted when NDC matches."""
        is_contracted = check_product_contracted(
            "00093-1040-01", "Generic", contracted_products
        )
        assert is_contracted is True

    def test_contracted_by_product_type_branded(self, contracted_products):
        """Test Branded Rx products are considered contracted."""
        is_contracted = check_product_contracted(
            "unknown-ndc", "Branded Rx", contracted_products
        )
        assert is_contracted is True

    def test_contracted_by_product_type_generic(self, contracted_products):
        """Test Generic products are considered contracted."""
        is_contracted = check_product_contracted(
            "unknown-ndc", "Generic", contracted_products
        )
        assert is_contracted is True

    def test_contracted_by_product_type_onestop(self, contracted_products):
        """Test OneStop products are considered contracted."""
        is_contracted = check_product_contracted(
            "unknown-ndc", "OneStop", contracted_products
        )
        assert is_contracted is True

    def test_not_contracted_unknown_ndc(self, contracted_products):
        """Test product is not contracted when NDC and type unknown."""
        is_contracted = check_product_contracted(
            "99999-999-99", "Off-Contract", contracted_products
        )
        assert is_contracted is False

    def test_not_contracted_empty_catalog(self):
        """Test product is not contracted with empty catalog."""
        empty_products = {"branded": [], "generic": [], "onestop": [], "all_ndcs": []}
        is_contracted = check_product_contracted(
            "00093-1040-01", "", empty_products
        )
        assert is_contracted is False


class TestAnalyzeAlignment:
    """Tests for analyze_alignment function."""

    @pytest.fixture
    def base_state(self):
        """Base state with contract terms and products."""
        return {
            "contract_terms": {
                "tier1_min": 800000.0,
                "tier1_max": 900000.0,
                "tier2_min": 900001.0,
                "tier2_max": 1000000.0,
                "tier3_min": 1000001.0,
            },
            "contracted_products": {
                "branded": [{"drug_name": "lipitor", "ndc": "00071-0155-23"}],
                "generic": [{"drug_name": "lisinopril", "ndc": "00093-1040-01"}],
                "onestop": [{"drug_name": "amoxicillin", "ndc": "65862-0015-01"}],
                "all_ndcs": ["00071-0155-23", "00093-1040-01", "65862-0015-01"],
            },
            "purchase_order_data": "",
        }

    def test_aligned_hospital(self, base_state):
        """Test hospital with all contracted purchases is aligned."""
        base_state["purchase_order_data"] = """hospital_id,hospital_name,vendor_name,drug_name,ndc,product_type,quantity,unit_price,order_date,contract_tier_applied
H001,City Medical Center,McKesson,Lisinopril,00093-1040-01,Generic,100000,2.00,2025-01-10,Tier1
H001,City Medical Center,McKesson,Lipitor,00071-0155-23,Branded Rx,100000,2.00,2025-02-05,Tier1"""
        
        result = analyze_alignment(base_state)
        
        assert len(result["hospital_analyses"]) == 1
        assert result["hospital_analyses"][0]["alignment_status"] == "ALIGNED"
        assert result["hospital_analyses"][0]["risk_level"] == "LOW"
        assert len(result["misaligned_hospitals"]) == 0

    def test_misaligned_off_contract_purchase(self, base_state):
        """Test hospital with off-contract purchase is misaligned."""
        base_state["purchase_order_data"] = """hospital_id,hospital_name,vendor_name,drug_name,ndc,product_type,quantity,unit_price,order_date,contract_tier_applied
H002,Valley Health,McKesson,Lisinopril,00093-1040-01,Generic,100000,2.00,2025-01-15,Tier1
H002,Valley Health,McKesson,Unapproved Drug X,99999-999-99,Off-Contract,7000,4.00,2025-02-20,Tier1"""
        
        result = analyze_alignment(base_state)
        
        assert len(result["hospital_analyses"]) == 1
        assert result["hospital_analyses"][0]["alignment_status"] == "MISALIGNED"
        assert result["hospital_analyses"][0]["off_contract_purchases"] == 1
        assert len(result["misaligned_hospitals"]) == 1

    def test_misaligned_below_tier1_minimum(self, base_state):
        """Test hospital with spend below Tier 1 minimum is misaligned."""
        base_state["purchase_order_data"] = """hospital_id,hospital_name,vendor_name,drug_name,ndc,product_type,quantity,unit_price,order_date,contract_tier_applied
H004,Lakeside Clinic,McKesson,Lisinopril,00093-1040-01,Generic,1000,0.88,2025-01-05,Tier1"""
        
        result = analyze_alignment(base_state)
        
        # Quarterly spend = 1000 * 0.88 = $880
        # Annual projected = $880 * 4 = $3,520 (below $800K Tier 1 min)
        assert result["hospital_analyses"][0]["alignment_status"] == "MISALIGNED"
        assert "below Tier 1 minimum" in result["hospital_analyses"][0]["issues"]

    def test_multiple_hospitals(self, base_state):
        """Test analysis of multiple hospitals."""
        base_state["purchase_order_data"] = """hospital_id,hospital_name,vendor_name,drug_name,ndc,product_type,quantity,unit_price,order_date,contract_tier_applied
H001,City Medical Center,McKesson,Lisinopril,00093-1040-01,Generic,100000,2.00,2025-01-10,Tier1
H002,Valley Health,McKesson,Unapproved Drug X,99999-999-99,Off-Contract,7000,4.00,2025-02-20,Tier1
H003,Riverside Hospital,McKesson,Amoxicillin,65862-0015-01,OneStop,150000,2.00,2025-01-22,Tier2"""
        
        result = analyze_alignment(base_state)
        
        assert len(result["hospital_analyses"]) == 3
        
        # Find each hospital's analysis
        h001 = next(h for h in result["hospital_analyses"] if h["hospital_id"] == "H001")
        h002 = next(h for h in result["hospital_analyses"] if h["hospital_id"] == "H002")
        h003 = next(h for h in result["hospital_analyses"] if h["hospital_id"] == "H003")
        
        assert h001["alignment_status"] == "ALIGNED"
        assert h002["alignment_status"] == "MISALIGNED"
        assert h003["alignment_status"] == "ALIGNED"

    def test_product_type_counts(self, base_state):
        """Test that product type counts are tracked correctly."""
        base_state["purchase_order_data"] = """hospital_id,hospital_name,vendor_name,drug_name,ndc,product_type,quantity,unit_price,order_date,contract_tier_applied
H001,City Medical Center,McKesson,Lisinopril,00093-1040-01,Generic,50000,2.00,2025-01-10,Tier1
H001,City Medical Center,McKesson,Metformin,00093-1048-01,Generic,50000,2.00,2025-02-05,Tier1
H001,City Medical Center,McKesson,Lipitor,00071-0155-23,Branded Rx,50000,2.00,2025-03-01,Tier1
H001,City Medical Center,McKesson,Amoxicillin,65862-0015-01,OneStop,50000,2.00,2025-03-15,Tier1"""
        
        result = analyze_alignment(base_state)
        
        h001 = result["hospital_analyses"][0]
        assert h001["generic_purchases"] == 2
        assert h001["branded_purchases"] == 1
        assert h001["onestop_purchases"] == 1
        assert h001["total_purchases"] == 4

    def test_empty_purchase_data(self, base_state):
        """Test handling of empty purchase order data."""
        base_state["purchase_order_data"] = ""
        
        result = analyze_alignment(base_state)
        
        assert result["hospital_analyses"] == []
        assert result["misaligned_hospitals"] == []

    def test_risk_level_high_multiple_off_contract(self, base_state):
        """Test that multiple off-contract purchases result in HIGH risk."""
        base_state["purchase_order_data"] = """hospital_id,hospital_name,vendor_name,drug_name,ndc,product_type,quantity,unit_price,order_date,contract_tier_applied
H005,Mountain View,McKesson,Lisinopril,00093-1040-01,Generic,50000,4.00,2025-01-17,Tier1
H005,Mountain View,McKesson,Drug X,99999-999-99,Off-Contract,5000,3.80,2025-02-10,Tier1
H005,Mountain View,McKesson,Drug Y,88888-888-88,Off-Contract,5000,3.80,2025-02-15,Tier1
H005,Mountain View,McKesson,Drug Z,77777-777-77,Off-Contract,5000,3.80,2025-02-20,Tier1"""
        
        result = analyze_alignment(base_state)
        
        h005 = result["hospital_analyses"][0]
        assert h005["alignment_status"] == "MISALIGNED"
        assert h005["risk_level"] == "HIGH"
        assert h005["off_contract_purchases"] == 3

    def test_pricing_tier_assignment(self, base_state):
        """Test that pricing tier is correctly assigned based on spend."""
        # High spend hospital - should be Tier 2 or 3
        base_state["purchase_order_data"] = """hospital_id,hospital_name,vendor_name,drug_name,ndc,product_type,quantity,unit_price,order_date,contract_tier_applied
H003,Riverside Hospital,McKesson,Lisinopril,00093-1040-01,Generic,100000,2.50,2025-01-22,Tier2"""
        
        result = analyze_alignment(base_state)
        
        h003 = result["hospital_analyses"][0]
        # Quarterly spend = 100000 * 2.50 = $250,000
        # Annual projected = $1,000,000 -> Tier 2
        assert h003["pricing_tier"] == "Tier 2"
        assert h003["quarterly_spend"] == 250000.0
        assert h003["annual_spend_projected"] == 1000000.0


class TestGenerateAIInsights:
    """Tests for generate_ai_insights function with mocked Bedrock calls."""

    @pytest.fixture
    def sample_analysis_state(self):
        """State with hospital analyses for AI insight generation."""
        return {
            "hospital_analyses": [
                {
                    "hospital_id": "H001",
                    "hospital_name": "City Medical Center",
                    "quarterly_spend": 60000.0,
                    "annual_spend_projected": 240000.0,
                    "pricing_tier": "Below Tier 1 Minimum",
                    "alignment_status": "ALIGNED",
                    "risk_level": "LOW",
                    "issues": "No issues detected",
                    "total_purchases": 5,
                    "branded_purchases": 1,
                    "generic_purchases": 3,
                    "onestop_purchases": 1,
                    "off_contract_purchases": 0,
                },
                {
                    "hospital_id": "H002",
                    "hospital_name": "Memorial Hospital",
                    "quarterly_spend": 85000.0,
                    "annual_spend_projected": 340000.0,
                    "pricing_tier": "Below Tier 1 Minimum",
                    "alignment_status": "MISALIGNED",
                    "risk_level": "MEDIUM",
                    "issues": "Off-contract purchase: UnknownDrug (NDC: 99999-9999-99)",
                    "total_purchases": 4,
                    "branded_purchases": 1,
                    "generic_purchases": 2,
                    "onestop_purchases": 0,
                    "off_contract_purchases": 1,
                },
            ],
            "misaligned_hospitals": [
                {
                    "hospital_id": "H002",
                    "hospital_name": "Memorial Hospital",
                    "quarterly_spend": 85000.0,
                    "annual_spend_projected": 340000.0,
                    "pricing_tier": "Below Tier 1 Minimum",
                    "alignment_status": "MISALIGNED",
                    "risk_level": "MEDIUM",
                    "issues": "Off-contract purchase: UnknownDrug (NDC: 99999-9999-99)",
                    "total_purchases": 4,
                    "branded_purchases": 1,
                    "generic_purchases": 2,
                    "onestop_purchases": 0,
                    "off_contract_purchases": 1,
                },
            ],
            "contract_rules": "Sample contract with volume-based pricing tiers.",
        }

    def test_generate_ai_insights_returns_state_keys(self, sample_analysis_state, mocker, test_output_dir):
        """Test that generate_ai_insights returns required state keys."""
        from purchasing_alignment_monitor.agents.analyzer import generate_ai_insights
        
        # Mock the boto3 client
        mock_response = {
            "body": mocker.MagicMock()
        }
        mock_response["body"].read.return_value = b'{"content": [{"text": "Test AI insight for hospital."}]}'
        
        mock_client = mocker.MagicMock()
        mock_client.invoke_model.return_value = mock_response
        
        mocker.patch("boto3.client", return_value=mock_client)
        
        result = generate_ai_insights(sample_analysis_state, output_dir=test_output_dir)
        
        assert "ai_insights" in result
        assert "executive_summary" in result

    def test_generate_ai_insights_for_misaligned_hospitals(self, sample_analysis_state, mocker, test_output_dir):
        """Test that AI insights are generated for each misaligned hospital."""
        from purchasing_alignment_monitor.agents.analyzer import generate_ai_insights
        
        # Mock the boto3 client
        mock_response = {
            "body": mocker.MagicMock()
        }
        mock_response["body"].read.return_value = b'{"content": [{"text": "Detailed AI recommendation for compliance."}]}'
        
        mock_client = mocker.MagicMock()
        mock_client.invoke_model.return_value = mock_response
        
        mocker.patch("boto3.client", return_value=mock_client)
        
        result = generate_ai_insights(sample_analysis_state, output_dir=test_output_dir)
        
        # Should have insight for H002 (misaligned)
        assert "H002" in result["ai_insights"]
        assert result["ai_insights"]["H002"]["hospital_name"] == "Memorial Hospital"
        assert "ai_analysis" in result["ai_insights"]["H002"]

    def test_generate_ai_insights_calls_bedrock(self, sample_analysis_state, mocker, test_output_dir):
        """Test that generate_ai_insights calls Bedrock for each misaligned hospital and summary."""
        from purchasing_alignment_monitor.agents.analyzer import generate_ai_insights
        
        mock_response = {
            "body": mocker.MagicMock()
        }
        mock_response["body"].read.return_value = b'{"content": [{"text": "AI generated content."}]}'
        
        mock_client = mocker.MagicMock()
        mock_client.invoke_model.return_value = mock_response
        
        mocker.patch("boto3.client", return_value=mock_client)
        
        result = generate_ai_insights(sample_analysis_state, output_dir=test_output_dir)
        
        # Should call invoke_model twice: once for misaligned hospital, once for summary
        assert mock_client.invoke_model.call_count == 2

    def test_generate_ai_insights_handles_error(self, sample_analysis_state, mocker):
        """Test that generate_ai_insights handles Bedrock errors gracefully."""
        from purchasing_alignment_monitor.agents.analyzer import generate_ai_insights
        
        # Mock boto3 to raise an exception
        mocker.patch("boto3.client", side_effect=Exception("Bedrock connection failed"))
        
        result = generate_ai_insights(sample_analysis_state)
        
        # Should return empty insights with error message
        assert result["ai_insights"] == {}
        assert "unavailable" in result["executive_summary"].lower()

    def test_generate_ai_insights_empty_analyses(self):
        """Test that generate_ai_insights handles empty analyses."""
        from purchasing_alignment_monitor.agents.analyzer import generate_ai_insights
        
        empty_state = {
            "hospital_analyses": [],
            "misaligned_hospitals": [],
            "contract_rules": "",
        }
        
        result = generate_ai_insights(empty_state)
        
        assert result["ai_insights"] == {}
        assert result["executive_summary"] == ""


class TestGenerateHospitalReport:
    """Tests for generate_hospital_report function."""

    def test_generate_report_for_existing_hospital(self):
        """Test generating report for an existing hospital."""
        from purchasing_alignment_monitor.agents.analyzer import generate_hospital_report
        
        state = {
            "hospital_analyses": [
                {
                    "hospital_id": "H001",
                    "hospital_name": "City Medical Center",
                    "quarterly_spend": 60000.0,
                    "annual_spend_projected": 240000.0,
                    "pricing_tier": "Below Tier 1 Minimum",
                    "alignment_status": "ALIGNED",
                    "risk_level": "LOW",
                    "issues": "No issues detected",
                    "total_purchases": 5,
                    "branded_purchases": 1,
                    "generic_purchases": 3,
                    "onestop_purchases": 1,
                    "off_contract_purchases": 0,
                }
            ],
            "ai_insights": {},
        }
        
        report = generate_hospital_report(state, "H001")
        
        assert "City Medical Center" in report
        assert "H001" in report
        assert "60,000.00" in report
        assert "ALIGNED" in report
        assert "LOW" in report

    def test_generate_report_with_ai_insights(self):
        """Test generating report that includes AI insights."""
        from purchasing_alignment_monitor.agents.analyzer import generate_hospital_report
        
        state = {
            "hospital_analyses": [
                {
                    "hospital_id": "H002",
                    "hospital_name": "Memorial Hospital",
                    "quarterly_spend": 85000.0,
                    "annual_spend_projected": 340000.0,
                    "pricing_tier": "Below Tier 1 Minimum",
                    "alignment_status": "MISALIGNED",
                    "risk_level": "MEDIUM",
                    "issues": "Off-contract purchase detected",
                    "total_purchases": 4,
                    "branded_purchases": 1,
                    "generic_purchases": 2,
                    "onestop_purchases": 0,
                    "off_contract_purchases": 1,
                }
            ],
            "ai_insights": {
                "H002": {
                    "hospital_name": "Memorial Hospital",
                    "risk_level": "MEDIUM",
                    "ai_analysis": "This hospital should switch to contracted products to achieve compliance.",
                }
            },
        }
        
        report = generate_hospital_report(state, "H002")
        
        assert "Memorial Hospital" in report
        assert "MISALIGNED" in report
        assert "AI-POWERED ANALYSIS" in report
        assert "switch to contracted products" in report

    def test_generate_report_hospital_not_found(self):
        """Test generating report for non-existent hospital."""
        from purchasing_alignment_monitor.agents.analyzer import generate_hospital_report
        
        state = {
            "hospital_analyses": [],
            "ai_insights": {},
        }
        
        report = generate_hospital_report(state, "H999")
        
        assert "not found" in report


class TestGenerateVisualizations:
    """Tests for generate_visualizations function."""

    @pytest.fixture
    def sample_hospital_analyses(self):
        """Sample hospital analyses for visualization testing."""
        return [
            {
                "hospital_id": "H001",
                "hospital_name": "City Medical Center",
                "quarterly_spend": 60000.0,
                "annual_spend_projected": 240000.0,
                "pricing_tier": "Below Tier 1 Minimum",
                "alignment_status": "ALIGNED",
                "risk_level": "LOW",
                "issues": "No issues detected",
                "total_purchases": 5,
                "branded_purchases": 1,
                "generic_purchases": 3,
                "onestop_purchases": 1,
                "off_contract_purchases": 0,
            },
            {
                "hospital_id": "H002",
                "hospital_name": "Memorial Hospital",
                "quarterly_spend": 85000.0,
                "annual_spend_projected": 340000.0,
                "pricing_tier": "Below Tier 1 Minimum",
                "alignment_status": "MISALIGNED",
                "risk_level": "MEDIUM",
                "issues": "Off-contract purchase detected",
                "total_purchases": 4,
                "branded_purchases": 1,
                "generic_purchases": 2,
                "onestop_purchases": 0,
                "off_contract_purchases": 1,
            },
            {
                "hospital_id": "H003",
                "hospital_name": "Regional Health Center",
                "quarterly_spend": 120000.0,
                "annual_spend_projected": 480000.0,
                "pricing_tier": "Below Tier 1 Minimum",
                "alignment_status": "MISALIGNED",
                "risk_level": "HIGH",
                "issues": "Multiple off-contract purchases",
                "total_purchases": 6,
                "branded_purchases": 2,
                "generic_purchases": 2,
                "onestop_purchases": 0,
                "off_contract_purchases": 3,
            },
        ]

    @pytest.fixture
    def sample_misaligned(self, sample_hospital_analyses):
        """Misaligned hospitals subset."""
        return [h for h in sample_hospital_analyses if h["alignment_status"] == "MISALIGNED"]

    def test_generate_visualizations_creates_files(self, sample_hospital_analyses, sample_misaligned, test_output_dir):
        """Test that generate_visualizations creates chart files."""
        from purchasing_alignment_monitor.agents.analyzer import generate_visualizations
        
        result = generate_visualizations(sample_hospital_analyses, sample_misaligned, test_output_dir)
        
        # Should return dictionary with file paths
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_generate_visualizations_creates_alignment_pie(self, sample_hospital_analyses, sample_misaligned, test_output_dir):
        """Test that alignment status pie chart is created."""
        from purchasing_alignment_monitor.agents.analyzer import generate_visualizations
        
        result = generate_visualizations(sample_hospital_analyses, sample_misaligned, test_output_dir)
        
        assert "alignment_status_pie" in result
        assert os.path.exists(result["alignment_status_pie"])
        assert result["alignment_status_pie"].endswith(".png")

    def test_generate_visualizations_creates_spend_bar(self, sample_hospital_analyses, sample_misaligned, test_output_dir):
        """Test that hospital spend bar chart is created."""
        from purchasing_alignment_monitor.agents.analyzer import generate_visualizations
        
        result = generate_visualizations(sample_hospital_analyses, sample_misaligned, test_output_dir)
        
        assert "hospital_spend_bar" in result
        assert os.path.exists(result["hospital_spend_bar"])

    def test_generate_visualizations_creates_risk_distribution(self, sample_hospital_analyses, sample_misaligned, test_output_dir):
        """Test that risk level distribution chart is created."""
        from purchasing_alignment_monitor.agents.analyzer import generate_visualizations
        
        result = generate_visualizations(sample_hospital_analyses, sample_misaligned, test_output_dir)
        
        assert "risk_distribution" in result
        assert os.path.exists(result["risk_distribution"])

    def test_generate_visualizations_creates_product_type_chart(self, sample_hospital_analyses, sample_misaligned, test_output_dir):
        """Test that product type distribution chart is created."""
        from purchasing_alignment_monitor.agents.analyzer import generate_visualizations
        
        result = generate_visualizations(sample_hospital_analyses, sample_misaligned, test_output_dir)
        
        assert "product_type_distribution" in result
        assert os.path.exists(result["product_type_distribution"])

    def test_generate_visualizations_creates_contract_compliance_chart(self, sample_hospital_analyses, sample_misaligned, test_output_dir):
        """Test that contract compliance chart is created."""
        from purchasing_alignment_monitor.agents.analyzer import generate_visualizations
        
        result = generate_visualizations(sample_hospital_analyses, sample_misaligned, test_output_dir)
        
        assert "contract_compliance" in result
        assert os.path.exists(result["contract_compliance"])

    def test_generate_visualizations_empty_analyses(self, test_output_dir):
        """Test that empty analyses returns empty dict."""
        from purchasing_alignment_monitor.agents.analyzer import generate_visualizations
        
        result = generate_visualizations([], [], test_output_dir)
        
        assert result == {}

    def test_generate_visualizations_all_charts_created(self, sample_hospital_analyses, sample_misaligned, test_output_dir):
        """Test that all 5 charts are created."""
        from purchasing_alignment_monitor.agents.analyzer import generate_visualizations
        
        result = generate_visualizations(sample_hospital_analyses, sample_misaligned, test_output_dir)
        
        expected_charts = [
            "alignment_status_pie",
            "hospital_spend_bar",
            "risk_distribution",
            "product_type_distribution",
            "contract_compliance",
        ]
        
        for chart in expected_charts:
            assert chart in result, f"Missing chart: {chart}"
