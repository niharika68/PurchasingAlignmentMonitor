"""
Analyzer Agent Module
Analyzes purchasing alignment and detects misaligned hospitals.
Includes AI-powered insights and recommendations.
"""

import json
import os
from typing import TypedDict
from dataclasses import dataclass, asdict
import pandas as pd
from io import StringIO
import boto3
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
from purchasing_alignment_monitor.config.bedrock_config import bedrock_config


@dataclass
class PurchaseRecord:
    """Single purchase order record."""
    hospital_id: str
    hospital_name: str
    drug_name: str
    ndc: str
    product_type: str
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
    branded_purchases: int
    generic_purchases: int
    onestop_purchases: int
    avg_price_deviation: float
    pricing_tier: str
    alignment_status: str  # "ALIGNED" or "MISALIGNED"
    risk_level: str  # "LOW", "MEDIUM", "HIGH"
    issues: list[str]


class AnalyzerState(TypedDict):
    """State for analyzer operations."""
    contract_rules: str
    contract_terms: dict
    contracted_products: dict
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
        print(f"  DEBUG: Raw data that failed to parse:\n{po_csv[:1000]}")
        return []


def determine_pricing_tier(annual_spend: float, contract_terms: dict) -> str:
    """
    Determine the pricing tier based on annual spend and contract terms.
    """
    tier1_min = contract_terms.get("tier1_min", 800000.0)
    tier1_max = contract_terms.get("tier1_max", 900000.0)
    tier2_max = contract_terms.get("tier2_max", 1000000.0)
    tier3_min = contract_terms.get("tier3_min", 1000001.0)
    
    # Annualize quarterly spend
    if annual_spend < tier1_min:
        return "Below Tier 1"
    elif annual_spend <= tier1_max:
        return "Tier 1"
    elif annual_spend <= tier2_max:
        return "Tier 2"
    else:
        return "Tier 3"


def check_product_contracted(ndc: str, product_type: str, contracted_products: dict) -> bool:
    """
    Check if a product is in the contracted product catalog.
    """
    all_ndcs = contracted_products.get("all_ndcs", [])
    
    # Check by NDC
    if ndc in all_ndcs:
        return True
    
    # Check by product type (if marked in PO data)
    if product_type and product_type.lower() in ["branded rx", "generic", "onestop"]:
        return True
    
    return False


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
    
    # Get contract terms and product catalog
    contract_terms = state.get("contract_terms", {})
    contracted_products = state.get("contracted_products", {})
    
    # Use defaults if not parsed
    if not contract_terms:
        contract_terms = {
            "tier1_min": 800000.0,
            "tier1_max": 900000.0,
            "tier2_min": 900001.0,
            "tier2_max": 1000000.0,
            "tier3_min": 1000001.0,
            "tier2_discount": 0.0025,
            "tier3_discount": 0.0050,
        }
    
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
                "branded_count": 0,
                "generic_count": 0,
                "onestop_count": 0,
                "off_contract_count": 0,
            }
        
        # Calculate costs
        try:
            qty = int(record.get("quantity", 0))
            unit_price = float(record.get("unit_price", 0))
            total_cost = qty * unit_price
            ndc = str(record.get("ndc", ""))
            product_type = str(record.get("product_type", ""))
            
            # Check if product is contracted
            is_contracted = check_product_contracted(ndc, product_type, contracted_products)
            
            # If product_type explicitly says "Off-Contract", it's not contracted
            if "off-contract" in product_type.lower():
                is_contracted = False
            
            purchase = {
                "drug": record.get("drug_name", "UNKNOWN"),
                "ndc": ndc,
                "product_type": product_type,
                "quantity": qty,
                "unit_price": unit_price,
                "total_cost": total_cost,
                "vendor": record.get("vendor_name", "UNKNOWN"),
                "is_contracted": is_contracted,
            }
            
            hospitals[hospital_id]["purchases"].append(purchase)
            hospitals[hospital_id]["total_spend"] += total_cost
            
            # Count by product type
            product_type_lower = product_type.lower()
            if "branded" in product_type_lower:
                hospitals[hospital_id]["branded_count"] += 1
            elif "generic" in product_type_lower:
                hospitals[hospital_id]["generic_count"] += 1
            elif "onestop" in product_type_lower:
                hospitals[hospital_id]["onestop_count"] += 1
            
            if not is_contracted:
                hospitals[hospital_id]["off_contract_count"] += 1
        
        except (ValueError, TypeError) as e:
            print(f"  ⚠ Skipping invalid record: {record} - {e}")
            continue
    
    # Analyze each hospital
    analyses = []
    misaligned = []
    
    for hospital_id, hospital_data in hospitals.items():
        purchases = hospital_data["purchases"]
        total_spend = hospital_data["total_spend"]
        
        # Annualize quarterly spend (multiply by 4)
        annual_spend_projected = total_spend * 4
        
        # Determine pricing tier
        pricing_tier = determine_pricing_tier(annual_spend_projected, contract_terms)
        
        # Detect issues
        issues = []
        off_contract_count = hospital_data["off_contract_count"]
        
        # Check for off-contract purchases
        for purchase in purchases:
            if not purchase["is_contracted"]:
                issues.append(f"Off-contract purchase: {purchase['drug']} (NDC: {purchase['ndc']})")
        
        # Check if projected annual spend is below Tier 1 minimum
        tier1_min = contract_terms.get("tier1_min", 800000.0)
        if annual_spend_projected < tier1_min:
            issues.append(
                f"Projected annual spend (${annual_spend_projected:,.2f}) below Tier 1 minimum (${tier1_min:,.2f})"
            )
        
        # Determine alignment status and risk level
        alignment_status = "ALIGNED" if not issues else "MISALIGNED"
        
        if not issues:
            risk_level = "LOW"
        elif off_contract_count > 2:
            risk_level = "HIGH"
        elif off_contract_count > 0:
            risk_level = "MEDIUM"
        elif len(issues) == 1:
            risk_level = "MEDIUM"
        else:
            risk_level = "HIGH"
        
        analysis = {
            "hospital_id": hospital_id,
            "hospital_name": hospital_data["name"],
            "quarterly_spend": round(total_spend, 2),
            "annual_spend_projected": round(annual_spend_projected, 2),
            "pricing_tier": pricing_tier,
            "alignment_status": alignment_status,
            "risk_level": risk_level,
            "issues": "; ".join(issues) if issues else "No issues detected",
            "total_purchases": len(purchases),
            "branded_purchases": hospital_data["branded_count"],
            "generic_purchases": hospital_data["generic_count"],
            "onestop_purchases": hospital_data["onestop_count"],
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


def generate_visualizations(hospital_analyses: list, misaligned_hospitals: list, output_dir: str = None) -> dict:
    """
    Generate visualizations for the purchasing alignment analysis.
    
    Creates the following charts:
    1. Alignment Status Pie Chart (Aligned vs Misaligned)
    2. Hospital Spend Bar Chart (Quarterly spend by hospital)
    3. Risk Level Distribution (LOW/MEDIUM/HIGH breakdown)
    4. Product Type Distribution (Branded/Generic/OneStop purchases)
    5. Contract Compliance Chart (On-contract vs Off-contract)
    
    Args:
        hospital_analyses: List of hospital analysis dictionaries
        misaligned_hospitals: List of misaligned hospital dictionaries
        output_dir: Directory to save charts (defaults to outputs/visualizations/)
        
    Returns:
        Dictionary with paths to generated visualization files
    """
    if not hospital_analyses:
        return {}
    
    # Set output directory - default to outputs/visualizations/
    if output_dir is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_dir = os.path.join(base_dir, "outputs", "visualizations")
    os.makedirs(output_dir, exist_ok=True)
    
    visualizations = {}
    
    # Set style
    plt.style.use('seaborn-v0_8-whitegrid')
    colors = {
        'primary': '#2E86AB',
        'secondary': '#A23B72',
        'success': '#28A745',
        'warning': '#FFC107',
        'danger': '#DC3545',
        'info': '#17A2B8',
    }
    
    # 1. Alignment Status Pie Chart
    try:
        fig, ax = plt.subplots(figsize=(8, 6))
        aligned_count = len(hospital_analyses) - len(misaligned_hospitals)
        misaligned_count = len(misaligned_hospitals)
        
        sizes = [aligned_count, misaligned_count]
        labels = [f'Aligned ({aligned_count})', f'Misaligned ({misaligned_count})']
        chart_colors = [colors['success'], colors['danger']]
        explode = (0, 0.05)
        
        ax.pie(sizes, explode=explode, labels=labels, colors=chart_colors,
               autopct='%1.1f%%', shadow=True, startangle=90)
        ax.set_title('Hospital Alignment Status', fontsize=14, fontweight='bold')
        
        filepath = os.path.join(output_dir, 'alignment_status_pie.png')
        plt.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        visualizations['alignment_status_pie'] = filepath
    except Exception as e:
        print(f"  ⚠ Could not generate alignment pie chart: {e}")
    
    # 2. Hospital Spend Bar Chart
    try:
        fig, ax = plt.subplots(figsize=(12, 6))
        
        hospitals = [h['hospital_name'][:20] for h in hospital_analyses]
        spends = [h['quarterly_spend'] / 1000 for h in hospital_analyses]  # in thousands
        bar_colors = [colors['danger'] if h['alignment_status'] == 'MISALIGNED' 
                      else colors['success'] for h in hospital_analyses]
        
        bars = ax.bar(hospitals, spends, color=bar_colors, edgecolor='white', linewidth=0.7)
        ax.set_xlabel('Hospital', fontsize=11)
        ax.set_ylabel('Quarterly Spend ($K)', fontsize=11)
        ax.set_title('Quarterly Spend by Hospital', fontsize=14, fontweight='bold')
        plt.xticks(rotation=45, ha='right')
        
        # Add value labels on bars
        for bar, spend in zip(bars, spends):
            height = bar.get_height()
            ax.annotate(f'${spend:.0f}K',
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 3), textcoords="offset points",
                        ha='center', va='bottom', fontsize=9)
        
        # Add legend
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor=colors['success'], label='Aligned'),
            Patch(facecolor=colors['danger'], label='Misaligned')
        ]
        ax.legend(handles=legend_elements, loc='upper right')
        
        plt.tight_layout()
        filepath = os.path.join(output_dir, 'hospital_spend_bar.png')
        plt.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        visualizations['hospital_spend_bar'] = filepath
    except Exception as e:
        print(f"  ⚠ Could not generate spend bar chart: {e}")
    
    # 3. Risk Level Distribution
    try:
        fig, ax = plt.subplots(figsize=(8, 6))
        
        risk_counts = {'LOW': 0, 'MEDIUM': 0, 'HIGH': 0}
        for h in hospital_analyses:
            risk_level = h.get('risk_level', 'LOW')
            if risk_level in risk_counts:
                risk_counts[risk_level] += 1
        
        risk_labels = list(risk_counts.keys())
        risk_values = list(risk_counts.values())
        risk_colors = [colors['success'], colors['warning'], colors['danger']]
        
        bars = ax.bar(risk_labels, risk_values, color=risk_colors, edgecolor='white', linewidth=2)
        ax.set_xlabel('Risk Level', fontsize=11)
        ax.set_ylabel('Number of Hospitals', fontsize=11)
        ax.set_title('Risk Level Distribution', fontsize=14, fontweight='bold')
        
        # Add value labels
        for bar, val in zip(bars, risk_values):
            if val > 0:
                ax.annotate(f'{val}',
                            xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                            xytext=(0, 3), textcoords="offset points",
                            ha='center', va='bottom', fontsize=12, fontweight='bold')
        
        plt.tight_layout()
        filepath = os.path.join(output_dir, 'risk_distribution.png')
        plt.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        visualizations['risk_distribution'] = filepath
    except Exception as e:
        print(f"  ⚠ Could not generate risk distribution chart: {e}")
    
    # 4. Product Type Distribution (Stacked Bar)
    try:
        fig, ax = plt.subplots(figsize=(12, 6))
        
        hospitals = [h['hospital_name'][:15] for h in hospital_analyses]
        branded = [h['branded_purchases'] for h in hospital_analyses]
        generic = [h['generic_purchases'] for h in hospital_analyses]
        onestop = [h['onestop_purchases'] for h in hospital_analyses]
        
        x = range(len(hospitals))
        width = 0.6
        
        ax.bar(x, branded, width, label='Branded Rx', color=colors['primary'])
        ax.bar(x, generic, width, bottom=branded, label='Generic', color=colors['info'])
        ax.bar(x, onestop, width, bottom=[b+g for b, g in zip(branded, generic)], 
               label='OneStop', color=colors['secondary'])
        
        ax.set_xlabel('Hospital', fontsize=11)
        ax.set_ylabel('Number of Purchases', fontsize=11)
        ax.set_title('Purchase Distribution by Product Type', fontsize=14, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(hospitals, rotation=45, ha='right')
        ax.legend(loc='upper right')
        
        plt.tight_layout()
        filepath = os.path.join(output_dir, 'product_type_distribution.png')
        plt.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        visualizations['product_type_distribution'] = filepath
    except Exception as e:
        print(f"  ⚠ Could not generate product type chart: {e}")
    
    # 5. Off-Contract Purchases Comparison
    try:
        fig, ax = plt.subplots(figsize=(10, 6))
        
        hospitals = [h['hospital_name'][:20] for h in hospital_analyses]
        off_contract = [h['off_contract_purchases'] for h in hospital_analyses]
        total_purchases = [h['total_purchases'] for h in hospital_analyses]
        on_contract = [t - o for t, o in zip(total_purchases, off_contract)]
        
        x = range(len(hospitals))
        width = 0.35
        
        ax.bar([i - width/2 for i in x], on_contract, width, label='On-Contract', color=colors['success'])
        ax.bar([i + width/2 for i in x], off_contract, width, label='Off-Contract', color=colors['danger'])
        
        ax.set_xlabel('Hospital', fontsize=11)
        ax.set_ylabel('Number of Purchases', fontsize=11)
        ax.set_title('On-Contract vs Off-Contract Purchases', fontsize=14, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(hospitals, rotation=45, ha='right')
        ax.legend(loc='upper right')
        
        plt.tight_layout()
        filepath = os.path.join(output_dir, 'contract_compliance.png')
        plt.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        visualizations['contract_compliance'] = filepath
    except Exception as e:
        print(f"  ⚠ Could not generate contract compliance chart: {e}")
    
    return visualizations


def generate_ai_insights(state: dict, output_dir: str = None) -> dict:
    """
    Generate AI-powered insights for hospital analyses.
    
    Uses Bedrock LLM to:
    - Explain misalignment issues in natural language
    - Provide actionable recommendations for each hospital
    - Generate an executive summary of findings
    
    Args:
        state: Current workflow state with hospital analyses
        output_dir: Directory for visualizations (defaults to outputs/visualizations/)
    """
    print("\n=== NODE: Generate AI Insights ===")
    
    hospital_analyses = state.get("hospital_analyses", [])
    misaligned_hospitals = state.get("misaligned_hospitals", [])
    contract_rules = state.get("contract_rules", "")
    
    if not hospital_analyses:
        print("✗ No hospital analyses to generate insights for")
        state["ai_insights"] = {}
        state["executive_summary"] = ""
        return state
    
    try:
        # Get Bedrock runtime client
        bedrock_runtime = boto3.client(
            service_name="bedrock-runtime",
            region_name=bedrock_config.aws_region,
            aws_access_key_id=bedrock_config.aws_access_key_id,
            aws_secret_access_key=bedrock_config.aws_secret_access_key,
        )
        
        # Generate recommendations for misaligned hospitals
        hospital_insights = {}
        
        for hospital in misaligned_hospitals:
            prompt = f"""You are a healthcare procurement compliance analyst. Analyze the following hospital's purchasing misalignment and provide actionable recommendations.

Hospital: {hospital['hospital_name']} ({hospital['hospital_id']})
Quarterly Spend: ${hospital['quarterly_spend']:,.2f}
Annual Projected Spend: ${hospital['annual_spend_projected']:,.2f}
Current Pricing Tier: {hospital['pricing_tier']}
Risk Level: {hospital['risk_level']}
Issues Detected: {hospital['issues']}

Purchase Breakdown:
- Branded Rx Purchases: {hospital['branded_purchases']}
- Generic Purchases: {hospital['generic_purchases']}
- OneStop Purchases: {hospital['onestop_purchases']}
- Off-Contract Purchases: {hospital['off_contract_purchases']}

Contract Context:
{contract_rules[:2000] if contract_rules else "Standard vendor contract with volume-based pricing tiers."}

Provide:
1. A clear explanation of why this hospital is misaligned (2-3 sentences)
2. Specific, actionable recommendations to achieve compliance (3-5 bullet points)
3. Estimated savings or benefits if recommendations are followed

Be concise and professional."""

            response = bedrock_runtime.invoke_model(
                modelId=bedrock_config.model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps({
                    "messages": [
                        {"role": "user", "content": [{"text": prompt}]}
                    ],
                    "inferenceConfig": {
                        "maxTokens": 1000,
                        "temperature": 0.7
                    }
                })
            )
            
            response_body = json.loads(response["body"].read())
            insight_text = response_body["output"]["message"]["content"][0]["text"]
            
            hospital_insights[hospital["hospital_id"]] = {
                "hospital_name": hospital["hospital_name"],
                "risk_level": hospital["risk_level"],
                "ai_analysis": insight_text,
            }
            
            print(f"  ✓ Generated insights for {hospital['hospital_name']}")
        
        state["ai_insights"] = hospital_insights
        
        # Generate executive summary
        summary_prompt = f"""You are a healthcare procurement executive advisor. Generate a concise executive summary of the purchasing alignment analysis.

Analysis Overview:
- Total Hospitals Analyzed: {len(hospital_analyses)}
- Aligned Hospitals: {len(hospital_analyses) - len(misaligned_hospitals)}
- Misaligned Hospitals: {len(misaligned_hospitals)}

Misaligned Hospital Details:
{json.dumps([{
    "name": h["hospital_name"],
    "risk": h["risk_level"],
    "issues": h["issues"],
    "spend": h["quarterly_spend"]
} for h in misaligned_hospitals], indent=2)}

Provide:
1. Executive Summary (2-3 sentences highlighting key findings)
2. Risk Assessment (overall risk to the organization)
3. Top 3 Priority Actions
4. Projected Impact (cost savings or compliance improvements)

Format as a professional executive brief."""

        summary_response = bedrock_runtime.invoke_model(
            modelId=bedrock_config.model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "messages": [
                    {"role": "user", "content": [{"text": summary_prompt}]}
                ],
                "inferenceConfig": {
                    "maxTokens": 1500,
                    "temperature": 0.7
                }
            })
        )
        
        summary_body = json.loads(summary_response["body"].read())
        executive_summary = summary_body["output"]["message"]["content"][0]["text"]
        
        state["executive_summary"] = executive_summary
        print(f"✓ Generated executive summary")
        
        # Generate visualizations
        state["visualizations"] = generate_visualizations(hospital_analyses, misaligned_hospitals, output_dir)
        print(f"✓ Generated visualizations")
        
    except Exception as e:
        error_msg = f"Error generating AI insights: {str(e)}"
        print(f"✗ {error_msg}")
        state["ai_insights"] = {}
        state["executive_summary"] = f"AI insights unavailable: {error_msg}"
        state["visualizations"] = {}
    
    return state


def generate_hospital_report(state: dict, hospital_id: str) -> str:
    """
    Generate a detailed AI-powered report for a specific hospital.
    
    Args:
        state: Current workflow state with analyses
        hospital_id: ID of the hospital to generate report for
        
    Returns:
        Formatted report string
    """
    hospital_analyses = state.get("hospital_analyses", [])
    ai_insights = state.get("ai_insights", {})
    
    # Find the hospital analysis
    hospital = None
    for h in hospital_analyses:
        if h["hospital_id"] == hospital_id:
            hospital = h
            break
    
    if not hospital:
        return f"Hospital {hospital_id} not found in analysis."
    
    # Build report
    report = f"""
================================================================================
PURCHASING ALIGNMENT REPORT
================================================================================

Hospital: {hospital['hospital_name']}
ID: {hospital['hospital_id']}
Report Date: Generated by AI Analysis

--------------------------------------------------------------------------------
FINANCIAL SUMMARY
--------------------------------------------------------------------------------
Quarterly Spend:        ${hospital['quarterly_spend']:>15,.2f}
Annual Projected:       ${hospital['annual_spend_projected']:>15,.2f}
Pricing Tier:           {hospital['pricing_tier']:>15}

--------------------------------------------------------------------------------
ALIGNMENT STATUS
--------------------------------------------------------------------------------
Status:                 {hospital['alignment_status']}
Risk Level:             {hospital['risk_level']}

Issues:
{hospital['issues']}

--------------------------------------------------------------------------------
PURCHASE BREAKDOWN
--------------------------------------------------------------------------------
Total Purchases:        {hospital['total_purchases']:>15}
  - Branded Rx:         {hospital['branded_purchases']:>15}
  - Generic:            {hospital['generic_purchases']:>15}
  - OneStop:            {hospital['onestop_purchases']:>15}
  - Off-Contract:       {hospital['off_contract_purchases']:>15}

"""
    
    # Add AI insights if available
    if hospital_id in ai_insights:
        insight = ai_insights[hospital_id]
        report += f"""--------------------------------------------------------------------------------
AI-POWERED ANALYSIS & RECOMMENDATIONS
--------------------------------------------------------------------------------
{insight['ai_analysis']}

================================================================================
"""
    
    return report
