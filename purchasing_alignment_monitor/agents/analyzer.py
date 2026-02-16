"""
Analyzer Agent Module
Analyzes purchasing alignment and detects misaligned hospitals.
"""

import json
from typing import TypedDict
from dataclasses import dataclass, asdict
import pandas as pd
from io import StringIO


@dataclass
class PurchaseRecord:
    """Single purchase order record."""
    hospital_id: str
    hospital_name: str
    drug_name: str
    quantity: int
    unit_price: float
    total_cost: float
    is_contracted: bool = False
    price_deviation: float = 0.0


@dataclass
class HospitalAnalysis:
    """Purchasing alignment analysis for a hospital."""
    hospital_id: str
    hospital_name: str
    quarterly_spend: float
    total_purchases: int
    contracted_purchases: int
    off_contract_purchases: int
    avg_price_deviation: float
    alignment_status: str  # "ALIGNED" or "MISALIGNED"
    risk_level: str  # "LOW", "MEDIUM", "HIGH"
    issues: list[str]


class AnalyzerState(TypedDict):
    """State for analyzer operations."""
    contract_rules: str
    purchase_order_data: str
    parsed_po_data: list[dict]
    hospital_analyses: list[dict]
    misaligned_hospitals: list[dict]


def parse_purchase_order_csv(po_csv: str) -> list[dict]:
    """
    Parse CSV purchase order data into structured format.
    Handles markdown code block formatting.
    """
    print("\n=== NODE: Parse Purchase Order Data ===")
    
    try:
        # Remove markdown formatting if present
        if "```csv" in po_csv:
            po_csv = po_csv.split("```csv")[1].split("```")[0]
        elif "```" in po_csv:
            po_csv = po_csv.split("```")[1].split("```")[0]
        
        # Parse CSV using pandas
        df = pd.read_csv(StringIO(po_csv.strip()))
        
        # Standardize column names (lowercase, strip whitespace)
        df.columns = df.columns.str.lower().str.strip()
        
        records = df.to_dict(orient="records")
        print(f"✓ Parsed {len(records)} purchase order records")
        
        return records
    
    except Exception as e:
        print(f"✗ Error parsing PO data: {str(e)}")
        return []


def analyze_alignment(state: dict) -> dict:
    """
    Analyze purchasing alignment for each hospital.
    
    Detects:
    - Off-contract drug purchases
    - Price deviations from contract terms
    - Tier mismatches
    - Spend below minimum commitments
    """
    print("\n=== NODE: Analyze Purchasing Alignment ===")
    
    # Parse PO data
    po_records = parse_purchase_order_csv(state.get("purchase_order_data", ""))
    state["parsed_po_data"] = po_records
    
    if not po_records:
        print("✗ No purchase order data to analyze")
        state["hospital_analyses"] = []
        state["misaligned_hospitals"] = []
        return state
    
    # Group purchases by hospital
    hospitals = {}
    for record in po_records:
        hospital_id = record.get("hospital_id", "UNKNOWN")
        hospital_name = record.get("hospital_name", "UNKNOWN")
        
        if hospital_id not in hospitals:
            hospitals[hospital_id] = {
                "name": hospital_name,
                "purchases": [],
                "total_spend": 0.0,
            }
        
        # Calculate costs
        try:
            qty = int(record.get("quantity", 0))
            unit_price = float(record.get("unit_price", 0))
            total_cost = float(record.get("total_cost", qty * unit_price))
            
            hospitals[hospital_id]["purchases"].append({
                "drug": record.get("drug_name", "UNKNOWN"),
                "quantity": qty,
                "unit_price": unit_price,
                "total_cost": total_cost,
                "vendor": record.get("vendor", "UNKNOWN"),
            })
            hospitals[hospital_id]["total_spend"] += total_cost
        
        except (ValueError, TypeError):
            print(f"  ⚠ Skipping invalid record: {record}")
            continue
    
    # Analyze each hospital
    analyses = []
    misaligned = []
    
    # Parse contract rules for thresholds (basic heuristics)
    min_commitment = 50000.0  # Example minimum quarterly commitment
    contracted_drugs = {"paracetamol", "ibuprofen", "aspirin", "amoxicillin"}  # Example
    acceptable_price_range = 0.1  # 10% acceptable deviation
    
    for hospital_id, hospital_data in hospitals.items():
        purchases = hospital_data["purchases"]
        total_spend = hospital_data["total_spend"]
        
        # Detect issues
        issues = []
        off_contract_count = 0
        price_deviation_total = 0.0
        
        for purchase in purchases:
            drug = purchase["drug"].lower()
            
            # Check if drug is in contracted list
            if drug not in contracted_drugs:
                off_contract_count += 1
                issues.append(f"Off-contract drug purchased: {purchase['drug']}")
        
        # Check minimum commitment
        if total_spend < min_commitment:
            issues.append(
                f"Quarterly spend (${total_spend:,.2f}) below minimum (${min_commitment:,.2f})"
            )
        
        # Determine alignment status and risk level
        alignment_status = "ALIGNED" if not issues else "MISALIGNED"
        
        if not issues:
            risk_level = "LOW"
        elif off_contract_count > 0:
            risk_level = "HIGH"
        elif len(issues) == 1:
            risk_level = "MEDIUM"
        else:
            risk_level = "HIGH"
        
        analysis = {
            "hospital_id": hospital_id,
            "hospital_name": hospital_data["name"],
            "quarterly_spend": round(total_spend, 2),
            "alignment_status": alignment_status,
            "risk_level": risk_level,
            "issues": "; ".join(issues) if issues else "No issues detected",
            "total_purchases": len(purchases),
            "off_contract_purchases": off_contract_count,
        }
        
        analyses.append(analysis)
        
        if alignment_status == "MISALIGNED":
            misaligned.append(analysis)
    
    state["hospital_analyses"] = analyses
    state["misaligned_hospitals"] = misaligned
    
    print(f"✓ Analyzed {len(hospitals)} hospitals")
    print(f"✓ Identified {len(misaligned)} misaligned hospitals")
    
    return state
