"""
Tests for the Retriever module.
Tests contract parsing and product catalog parsing functions.
"""

import pytest
from purchasing_alignment_monitor.agents.retriever import (
    parse_contract_terms,
    parse_product_catalog,
)


class TestParseContractTerms:
    """Tests for parse_contract_terms function."""

    def test_parse_tier1_thresholds(self):
        """Test parsing Tier 1 dollar thresholds."""
        contract_text = """
        Volume-Based Pricing Tiers
        Tier 1: For annual Net purchases between $800,000 and $900,000, 
        the pricing set forth in Schedule 4.1 shall apply.
        """
        terms = parse_contract_terms(contract_text)
        
        assert terms["tier1_min"] == 800000.0
        assert terms["tier1_max"] == 900000.0

    def test_parse_tier2_thresholds_and_discount(self):
        """Test parsing Tier 2 thresholds and discount percentage."""
        contract_text = """
        Tier 2: For annual Net purchases between $900,001 and $1,000,000, 
        Omnicare shall receive an additional 0.25% discount on all Generic Products.
        """
        terms = parse_contract_terms(contract_text)
        
        assert terms["tier2_min"] == 900001.0
        assert terms["tier2_max"] == 1000000.0
        assert terms["tier2_discount"] == 0.0025

    def test_parse_tier3_threshold_and_discount(self):
        """Test parsing Tier 3 threshold and discount percentage."""
        contract_text = """
        Tier 3: For annual Net purchases exceeding $1,000,000, 
        Omnicare shall receive an additional 0.50% discount on all Generic Products.
        """
        terms = parse_contract_terms(contract_text)
        
        # The regex extracts 1,000,000 from "exceeding $1,000,000"
        assert terms["tier3_min"] == 1000000.0
        assert terms["tier3_discount"] == 0.0050

    def test_parse_all_tiers(self):
        """Test parsing complete contract with all tiers."""
        contract_text = """
        2.4 Volume-Based Pricing Tiers

        2.4.1 Tier 1: For annual Net purchases between $800,000 and $900,000, 
        the pricing set forth in Schedule 4.1 shall apply.

        2.4.2 Tier 2: For annual Net purchases between $900,001 and $1,000,000, 
        Omnicare shall receive an additional 0.25% discount on all Generic Products.

        2.4.3 Tier 3: For annual Net purchases exceeding $1,000,000, 
        Omnicare shall receive an additional 0.50% discount on all Generic Products.
        """
        terms = parse_contract_terms(contract_text)
        
        assert terms["tier1_min"] == 800000.0
        assert terms["tier1_max"] == 900000.0
        assert terms["tier2_min"] == 900001.0
        assert terms["tier2_max"] == 1000000.0
        # tier3_min is extracted from "exceeding $1,000,000"
        assert terms["tier3_min"] == 1000000.0
        assert terms["tier2_discount"] == 0.0025
        assert terms["tier3_discount"] == 0.0050

    def test_default_values_on_empty_text(self):
        """Test that defaults are returned when contract text is empty."""
        terms = parse_contract_terms("")
        
        # Should return default values
        assert terms["tier1_min"] == 800000.0
        assert terms["tier1_max"] == 900000.0
        assert terms["tier2_discount"] == 0.0025
        assert terms["tier3_discount"] == 0.0050
        assert terms["formulary_coverage_requirement"] == 0.92

    def test_default_values_on_unparseable_text(self):
        """Test that defaults are returned when contract text cannot be parsed."""
        contract_text = "This is some random text without pricing information."
        terms = parse_contract_terms(contract_text)
        
        # Should return default values
        assert "tier1_min" in terms
        assert "tier2_discount" in terms


class TestParseProductCatalog:
    """Tests for parse_product_catalog function."""

    def test_parse_branded_products(self):
        """Test parsing Branded Rx products from catalog."""
        catalog_text = """product_type,drug_name,ndc,manufacturer,wac_price,contract_price,onestop_eligible
Branded Rx,Lipitor,00071-0155-23,Pfizer,12.50,11.25,N
Branded Rx,Crestor,00310-0755-90,AstraZeneca,14.80,13.32,N"""
        
        products = parse_product_catalog(catalog_text)
        
        assert len(products["branded"]) == 2
        assert products["branded"][0]["drug_name"] == "lipitor"
        assert products["branded"][0]["ndc"] == "00071-0155-23"
        assert products["branded"][1]["drug_name"] == "crestor"

    def test_parse_generic_products(self):
        """Test parsing Generic products from catalog."""
        catalog_text = """product_type,drug_name,ndc,manufacturer,wac_price,contract_price,onestop_eligible
Generic,Lisinopril,00093-1040-01,Teva,0.85,0.68,Y
Generic,Metformin,00093-1048-01,Teva,0.45,0.36,Y"""
        
        products = parse_product_catalog(catalog_text)
        
        assert len(products["generic"]) == 2
        assert products["generic"][0]["drug_name"] == "lisinopril"
        assert products["generic"][1]["drug_name"] == "metformin"

    def test_parse_onestop_products(self):
        """Test parsing OneStop products from catalog."""
        catalog_text = """product_type,drug_name,ndc,manufacturer,wac_price,contract_price,onestop_eligible
OneStop,Amoxicillin,65862-0015-01,Aurobindo,0.42,0.34,Y
OneStop,Azithromycin,65862-0024-01,Aurobindo,1.85,1.48,Y"""
        
        products = parse_product_catalog(catalog_text)
        
        assert len(products["onestop"]) == 2
        assert products["onestop"][0]["drug_name"] == "amoxicillin"
        assert products["onestop"][1]["drug_name"] == "azithromycin"

    def test_all_ndcs_collected(self):
        """Test that all NDCs are collected in all_ndcs list."""
        catalog_text = """product_type,drug_name,ndc,manufacturer,wac_price,contract_price,onestop_eligible
Branded Rx,Lipitor,00071-0155-23,Pfizer,12.50,11.25,N
Generic,Lisinopril,00093-1040-01,Teva,0.85,0.68,Y
OneStop,Amoxicillin,65862-0015-01,Aurobindo,0.42,0.34,Y"""
        
        products = parse_product_catalog(catalog_text)
        
        assert len(products["all_ndcs"]) == 3
        assert "00071-0155-23" in products["all_ndcs"]
        assert "00093-1040-01" in products["all_ndcs"]
        assert "65862-0015-01" in products["all_ndcs"]

    def test_mixed_product_types(self):
        """Test parsing catalog with all product types."""
        catalog_text = """product_type,drug_name,ndc,manufacturer,wac_price,contract_price,onestop_eligible
Branded Rx,Lipitor,00071-0155-23,Pfizer,12.50,11.25,N
Branded Rx,Crestor,00310-0755-90,AstraZeneca,14.80,13.32,N
Generic,Lisinopril,00093-1040-01,Teva,0.85,0.68,Y
Generic,Metformin,00093-1048-01,Teva,0.45,0.36,Y
OneStop,Amoxicillin,65862-0015-01,Aurobindo,0.42,0.34,Y"""
        
        products = parse_product_catalog(catalog_text)
        
        assert len(products["branded"]) == 2
        assert len(products["generic"]) == 2
        assert len(products["onestop"]) == 1
        assert len(products["all_ndcs"]) == 5

    def test_contract_price_parsing(self):
        """Test that contract prices are correctly parsed."""
        catalog_text = """product_type,drug_name,ndc,manufacturer,wac_price,contract_price,onestop_eligible
Branded Rx,Lipitor,00071-0155-23,Pfizer,12.50,11.25,N"""
        
        products = parse_product_catalog(catalog_text)
        
        assert products["branded"][0]["contract_price"] == 11.25

    def test_empty_catalog(self):
        """Test parsing empty catalog."""
        products = parse_product_catalog("")
        
        assert products["branded"] == []
        assert products["generic"] == []
        assert products["onestop"] == []
        assert products["all_ndcs"] == []
