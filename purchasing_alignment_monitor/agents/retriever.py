"""
Retriever Agent Module
Retrieves contract rules, product catalog, and purchase order data from Bedrock Knowledge Base.
"""

import re
from typing import TypedDict
from dataclasses import dataclass
from purchasing_alignment_monitor.config.bedrock_config import bedrock_config


@dataclass
class ContractTerms:
    """Parsed contract terms."""
    tier1_min: float = 800000.0
    tier1_max: float = 900000.0
    tier2_min: float = 900001.0
    tier2_max: float = 1000000.0
    tier3_min: float = 1000001.0
    tier2_discount: float = 0.0025  # 0.25%
    tier3_discount: float = 0.0050  # 0.50%
    formulary_coverage_requirement: float = 0.92  # 92%
    price_increase_cap: float = 0.03  # 3%
    price_protection_threshold: float = 0.10  # 10%


class RetrieverState(TypedDict):
    """State for retriever operations."""
    contract_rules: str
    contract_terms: dict
    product_catalog: str
    contracted_products: dict  # {"branded": [], "generic": [], "onestop": []}
    purchase_order_data: str
    retrieval_errors: list[str]


def parse_contract_terms(contract_text: str) -> dict:
    """
    Parse contract text to extract pricing tiers and thresholds.
    Returns a dictionary of contract terms.
    """
    terms = ContractTerms()
    
    # Parse Tier 1 thresholds
    tier1_match = re.search(
        r"Tier\s*1[:\s]+.*?\$([0-9,]+).*?and\s*\$([0-9,]+)", 
        contract_text, 
        re.IGNORECASE | re.DOTALL
    )
    if tier1_match:
        terms.tier1_min = float(tier1_match.group(1).replace(",", ""))
        terms.tier1_max = float(tier1_match.group(2).replace(",", ""))
    
    # Parse Tier 2 thresholds
    tier2_match = re.search(
        r"Tier\s*2[:\s]+.*?\$([0-9,]+).*?and\s*\$([0-9,]+).*?([0-9.]+)%",
        contract_text,
        re.IGNORECASE | re.DOTALL
    )
    if tier2_match:
        terms.tier2_min = float(tier2_match.group(1).replace(",", ""))
        terms.tier2_max = float(tier2_match.group(2).replace(",", ""))
        terms.tier2_discount = float(tier2_match.group(3)) / 100
    
    # Parse Tier 3 threshold
    tier3_match = re.search(
        r"Tier\s*3[:\s]+.*?exceeding\s*\$([0-9,]+).*?([0-9.]+)%",
        contract_text,
        re.IGNORECASE | re.DOTALL
    )
    if tier3_match:
        terms.tier3_min = float(tier3_match.group(1).replace(",", ""))
        terms.tier3_discount = float(tier3_match.group(2)) / 100
    
    # Parse formulary coverage requirement
    coverage_match = re.search(
        r"([0-9]+)\s*percent\s*\(([0-9]+)%\)\s*coverage",
        contract_text,
        re.IGNORECASE
    )
    if coverage_match:
        terms.formulary_coverage_requirement = float(coverage_match.group(2)) / 100
    
    return {
        "tier1_min": terms.tier1_min,
        "tier1_max": terms.tier1_max,
        "tier2_min": terms.tier2_min,
        "tier2_max": terms.tier2_max,
        "tier3_min": terms.tier3_min,
        "tier2_discount": terms.tier2_discount,
        "tier3_discount": terms.tier3_discount,
        "formulary_coverage_requirement": terms.formulary_coverage_requirement,
        "price_increase_cap": terms.price_increase_cap,
        "price_protection_threshold": terms.price_protection_threshold,
    }


def parse_product_catalog(catalog_text: str) -> dict:
    """
    Parse product catalog to extract contracted products by type.
    Returns a dictionary with branded, generic, and onestop product lists.
    """
    products = {
        "branded": [],
        "generic": [],
        "onestop": [],
        "all_ndcs": set(),
    }
    
    lines = catalog_text.strip().split("\n")
    for line in lines[1:]:  # Skip header
        parts = line.split(",")
        if len(parts) >= 4:
            product_type = parts[0].strip().lower()
            drug_name = parts[1].strip().lower()
            ndc = parts[2].strip()
            
            product_info = {
                "drug_name": drug_name,
                "ndc": ndc,
                "manufacturer": parts[3].strip() if len(parts) > 3 else "",
                "contract_price": float(parts[5]) if len(parts) > 5 else 0.0,
            }
            
            products["all_ndcs"].add(ndc)
            
            if "branded" in product_type:
                products["branded"].append(product_info)
            elif "generic" in product_type:
                products["generic"].append(product_info)
            elif "onestop" in product_type:
                products["onestop"].append(product_info)
    
    # Convert set to list for JSON serialization
    products["all_ndcs"] = list(products["all_ndcs"])
    
    return products


def retrieve_contract_rules(state: dict) -> dict:
    """
    Retrieve vendor contract rules from Bedrock Knowledge Base.
    
    Returns contract terms including:
    - Volume-based pricing tiers
    - Purchase commitment percentages
    - OneStop Program requirements
    - Price protection terms
    """
    print("\n=== NODE: Retrieve Contract Rules ===")
    
    try:
        bedrock_runtime = bedrock_config.get_bedrock_agent_runtime()
        
        response = bedrock_runtime.retrieve_and_generate(
            input={
                "text": "What are the volume-based pricing tiers including dollar thresholds, discount percentages, OneStop Program formulary coverage requirements, and price protection terms?"
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
        
        # Parse contract terms
        state["contract_terms"] = parse_contract_terms(contract_rules)
        print(f"✓ Parsed contract terms: {state['contract_terms']}")
        
    except Exception as e:
        error_msg = f"Error retrieving contract rules: {str(e)}"
        print(f"✗ {error_msg}")
        state["contract_rules"] = ""
        state["contract_terms"] = parse_contract_terms("")  # Use defaults
        state["retrieval_errors"].append(error_msg)
    
    return state


def retrieve_product_catalog(state: dict) -> dict:
    """
    Retrieve product catalog from Bedrock Knowledge Base.
    
    Returns contracted products including:
    - Branded Rx Products
    - Generic Products
    - OneStop Products
    """
    print("\n=== NODE: Retrieve Product Catalog ===")
    
    try:
        bedrock_runtime = bedrock_config.get_bedrock_agent_runtime()
        
        response = bedrock_runtime.retrieve_and_generate(
            input={
                "text": "Retrieve the complete product catalog with all Branded Rx Products, Generic Products, and OneStop Products including drug names, NDC codes, manufacturers, and contract prices. Format as CSV."
            },
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": bedrock_config.knowledge_base_id,
                    "modelArn": bedrock_config.model_arn,
                },
            },
        )
        
        catalog_text = response.get("output", {}).get("text", "")
        print(f"✓ Retrieved product catalog ({len(catalog_text)} characters)")
        state["product_catalog"] = catalog_text
        
        # Parse product catalog
        state["contracted_products"] = parse_product_catalog(catalog_text)
        print(f"✓ Parsed {len(state['contracted_products']['branded'])} branded, "
              f"{len(state['contracted_products']['generic'])} generic, "
              f"{len(state['contracted_products']['onestop'])} OneStop products")
        
    except Exception as e:
        error_msg = f"Error retrieving product catalog: {str(e)}"
        print(f"✗ {error_msg}")
        state["product_catalog"] = ""
        state["contracted_products"] = {"branded": [], "generic": [], "onestop": [], "all_ndcs": []}
        state["retrieval_errors"].append(error_msg)
    
    return state


def retrieve_purchase_order_data(state: dict) -> dict:
    """
    Retrieve quarterly purchase order data from Bedrock Knowledge Base.
    
    Uses the retrieve API (not retrieve_and_generate) to get raw data chunks
    without LLM summarization, ensuring all records are returned.
    
    Returns data including:
    - Hospital IDs and names
    - Drug purchases with product types
    - Quantities and prices
    - Contract tiers applied
    """
    print("\n=== NODE: Retrieve Purchase Order Data ===")
    
    try:
        bedrock_runtime = bedrock_config.get_bedrock_agent_runtime()
        
        # Use retrieve API to get raw chunks without LLM processing
        response = bedrock_runtime.retrieve(
            knowledgeBaseId=bedrock_config.knowledge_base_id,
            retrievalQuery={
                "text": "purchase order data CSV hospital drug NDC quantity price"
            },
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": 25  # Increase to get all chunks
                }
            }
        )
        
        # Combine all retrieved chunks
        chunks = response.get("retrievalResults", [])
        print(f"  Retrieved {len(chunks)} chunks from Knowledge Base")
        
        # Extract PO data chunks (filter out product catalog chunks)
        po_chunks = []
        csv_header = "hospital_id,hospital_name,vendor_name,drug_name,ndc,product_type,quantity,unit_price,order_date,contract_tier_applied"
        
        for chunk in chunks:
            text = chunk.get("content", {}).get("text", "")
            # Only include chunks with hospital IDs (H001, H002, etc.) - these are PO records
            if text and ("H001" in text or "H002" in text or "H003" in text or "H004" in text or "H005" in text):
                # Skip product catalog chunks
                if "wac_price" not in text.lower() and "contract_price" not in text.lower():
                    po_chunks.append(text)
        
        print(f"  Filtered to {len(po_chunks)} PO data chunks")
        
        # Reconstruct CSV from chunks
        # The KB returns data with spaces instead of newlines between rows
        all_rows = set()  # Use set to avoid duplicates
        
        for chunk in po_chunks:
            # Fix: KB returns rows separated by spaces instead of newlines
            # Pattern: data ends with Tier1/Tier2/Tier3, then next row starts with H00X
            import re
            fixed_chunk = re.sub(r'(Tier[123]) (H00[0-9])', r'\1\n\2', chunk)
            
            # Also handle header followed by first row
            fixed_chunk = re.sub(r'(contract_tier_applied) (H00[0-9])', r'\1\n\2', fixed_chunk)
            
            # Split into lines and add non-header lines
            for line in fixed_chunk.strip().split('\n'):
                line = line.strip()
                if line and line.startswith('H00'):
                    all_rows.add(line)
        
        # Build final CSV
        rows = sorted(list(all_rows))  # Sort for consistent order
        po_data = csv_header + "\n" + "\n".join(rows)
        
        print(f"  Reconstructed {len(rows)} PO records")
        print(f"✓ Retrieved purchase order data ({len(po_data)} characters)")
        state["purchase_order_data"] = po_data
        
    except Exception as e:
        error_msg = f"Error retrieving purchase order data: {str(e)}"
        print(f"✗ {error_msg}")
        state["purchase_order_data"] = ""
        state["retrieval_errors"].append(error_msg)
    
    return state
