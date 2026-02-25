# System Architecture - Purchasing Alignment Monitor

## 🖼️ Architecture Diagram

![Architecture Diagram](architecture_diagram.svg)

---

## 🏗️ High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Main Entry Point                         │
│                         (main.py)                               │
└────────────────────────────┬────────────────────────────────────┘
                             │
                    ┌────────▼─────────┐
                    │   LangGraph      │
                    │   Workflow       │
                    │   (workflow.py)  │
                    └────────┬─────────┘
                             │
    ┌────────────────────────┼────────────────────────────────────┐
    │            │           │           │            │           │
    ▼            ▼           ▼           ▼            ▼           ▼
┌────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐
│Contract│ │Product │ │   PO     │ │ Analyzer │ │    AI    │ │ Output │
│ Rules  │ │Catalog │ │  Data    │ │  (Risk)  │ │ Insights │ │Reports │
└────┬───┘ └────┬───┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬───┘
     │          │          │            │            │            │
     └──────────┴──────────┴────────────┴────────────┴────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
                    ▼                             ▼
              AWS Bedrock                  Local File System
            Knowledge Base              (CSV/TXT/Visualizations)
```

---

## 📦 Module Structure

### 1. **Main Entry Point** (`main.py`)
**Responsibilities:**
- Initialize and execute the entire workflow
- Validate AWS configuration
- Handle errors gracefully
- Generate human-readable reports
- Save output files (CSV, TXT, visualizations)

**Key Functions:**
```python
main()                    # Main execution orchestrator
generate_csv_report()     # Creates CSV output file
generate_text_report()    # Creates readable text report
```

**Output:**
- CSV file: `misaligned_hospitals_q[Q]_[YEAR].csv`
- Text report: `analysis_report_q[Q]_[YEAR].txt`
- Visualizations: `outputs/visualizations/*.png`

---

### 2. **Configuration Module** (`config/bedrock_config.py`)
**Responsibilities:**
- Manage AWS credentials and Bedrock settings
- Provide boto3 client instances
- Validate configuration completeness
- Extract model ID from MODEL_ARN

**Key Classes:**
```python
class BedrockConfig:
    get_bedrock_agent_runtime()  # Returns AWS SDK runtime client
    get_bedrock_client()         # Returns Bedrock client
    validate_config()            # Ensures all env vars are set
    model_id                     # Property: extracts model ID from ARN
```

**Environment Variables:**
```env
AWS_REGION              # AWS region (e.g., us-east-1)
AWS_ACCESS_KEY_ID       # AWS access key
AWS_SECRET_ACCESS_KEY   # AWS secret key
KNOWLEDGE_BASE_ID       # Bedrock KB identifier
MODEL_ARN              # Foundation model ARN (e.g., arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-pro-v1:0)
```

---

### 3. **Retriever Agent** (`agents/retriever.py`)
**Responsibilities:**
- Query Bedrock Knowledge Base for contract rules
- Query Bedrock Knowledge Base for product catalog
- Query Bedrock Knowledge Base for purchase order data (using `retrieve` API)
- Parse and reconstruct CSV data from chunks
- Return retrieved text chunks

**LangGraph Nodes:**

#### `retrieve_contract_rules(state)`
- **Input:** Empty state
- **Output:** `state['contract_rules']`, `state['contract_terms']`
- **API:** `retrieve_and_generate`
- **Query:** "What are the vendor contract pricing tiers..."

**Parsed Contract Terms:**
```python
{
    'tier1_min': 800000.0,
    'tier1_max': 900000.0,
    'tier2_min': 900001.0,
    'tier2_max': 1000000.0,
    'tier3_min': 1000001.0,
    'tier2_discount': 0.0025,  # 0.25%
    'tier3_discount': 0.005,   # 0.50%
    'formulary_coverage_requirement': 0.92,
    'price_increase_cap': 0.03,
    'price_protection_threshold': 0.10
}
```

#### `retrieve_product_catalog(state)`
- **Input:** State with contract rules
- **Output:** `state['product_catalog']`, `state['contracted_products']`
- **API:** `retrieve_and_generate`
- **Query:** "What products are available in the contract..."

**Contracted Products Structure:**
```python
{
    'branded': [{'drug_name': 'Lipitor', 'ndc': '00071-0155-23', ...}],
    'generic': [{'drug_name': 'Lisinopril', 'ndc': '00093-1040-01', ...}],
    'onestop': [{'drug_name': 'Amoxicillin', 'ndc': '65862-0015-01', ...}]
}
```

#### `retrieve_purchase_order_data(state)`
- **Input:** State with contract rules and product catalog
- **Output:** `state['purchase_order_data']` (CSV format)
- **API:** `retrieve` (raw chunks, no LLM processing)
- **Configuration:** `numberOfResults: 25` for complete data retrieval

**Why `retrieve` instead of `retrieve_and_generate`:**
- Returns raw data chunks without LLM summarization
- Prevents truncation of large CSV datasets
- Allows reconstruction of complete purchase order records

**Expected KB Content (CSV Format):**
```csv
hospital_id,hospital_name,vendor_name,drug_name,ndc,product_type,quantity,unit_price,order_date,contract_tier_applied
H001,City Medical Center,McKesson,Lisinopril,00093-1040-01,Generic,12000,0.68,2025-01-10,Tier1
H002,Valley Health,McKesson,Amlodipine,00093-3171-01,Generic,5000,0.74,2025-01-15,Tier1
```

---

### 4. **Analyzer Agent** (`agents/analyzer.py`)
**Responsibilities:**
- Parse purchase order CSV data
- Aggregate purchases by hospital
- Detect alignment violations (off-contract, pricing tier, spend thresholds)
- Assign risk levels
- Generate AI-powered insights using Amazon Nova Pro
- Generate visualizations (5 chart types)

**LangGraph Nodes:**

#### `analyze_alignment(state)`
- **Input:** `state['purchase_order_data']`, `state['contract_terms']`, `state['contracted_products']`
- **Output:** 
  - `state['hospital_analyses']` (list of dict)
  - `state['misaligned_hospitals']` (list of dict)

#### `generate_ai_insights(state)`
- **Input:** `state['hospital_analyses']`, `state['misaligned_hospitals']`
- **Output:**
  - `state['ai_insights']` (per-hospital recommendations)
  - `state['executive_summary']` (overall analysis)
  - `state['visualizations']` (chart file paths)
- **Model:** Amazon Nova Pro (`amazon.nova-pro-v1:0`)

**Analysis Logic:**

```python
# For each hospital:

1. Parse PO Records
   ├── Extract: hospital_id, hospital_name, drug, qty, price, product_type
   └── Convert: string → structured PurchaseRecord dataclass

2. Aggregate by Hospital
   ├── Sum quarterly spend
   ├── Count total purchases by product type (branded, generic, onestop)
   └── Categorize contracted vs off-contract

3. Detect Violations
   ├── Off-contract purchases?        → Issue + Risk ↑
   ├── Wrong pricing tier applied?    → Issue + Risk ↑
   ├── Below Tier 1 minimum spend?    → Issue + Risk ↑
   └── Price deviation >10%?          → Issue + Risk ↑

4. Assign Risk Level
   ├── HIGH:   Off-contract purchases present
   ├── MEDIUM: Spend below tier minimum or tier mismatch
   └── LOW:    All purchases aligned

5. Set Alignment Status
   ├── MISALIGNED: Any violations detected
   └── ALIGNED:    No violations
```

**Data Structures:**
```python
@dataclass
class PurchaseRecord:
    hospital_id: str
    hospital_name: str
    drug_name: str
    ndc: str
    product_type: str      # "Branded Rx", "Generic", "OneStop"
    quantity: int
    unit_price: float
    total_cost: float
    is_contracted: bool
    price_deviation: float

@dataclass
class HospitalAnalysis:
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
    pricing_tier: str          # "Tier 1", "Tier 2", "Tier 3", "Below Tier 1"
    alignment_status: str      # "ALIGNED" | "MISALIGNED"
    risk_level: str           # "LOW" | "MEDIUM" | "HIGH"
    issues: list[str]
```

---

### 5. **Workflow Orchestration** (`agents/workflow.py`)
**Responsibilities:**
- Define LangGraph state schema
- Construct workflow graph with 5 nodes
- Manage node connections
- Initialize workflow state

**Workflow State:**
```python
class WorkflowState(TypedDict):
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
    
    # AI Insights phase
    ai_insights: dict
    executive_summary: str
    visualizations: dict
```

**Workflow Graph:**
```
START
  │
  ├─→ retrieve_contract_rules
  │        │ (Bedrock KB - retrieve_and_generate)
  │        └─→ contract_rules, contract_terms
  │
  ├─→ retrieve_product_catalog
  │        │ (Bedrock KB - retrieve_and_generate)
  │        └─→ product_catalog, contracted_products
  │
  ├─→ retrieve_purchase_order_data
  │        │ (Bedrock KB - retrieve API, raw chunks)
  │        └─→ purchase_order_data (CSV)
  │
  ├─→ analyze_alignment
  │        │ (Risk Analysis)
  │        ├─→ hospital_analyses
  │        └─→ misaligned_hospitals
  │
  ├─→ generate_ai_insights
  │        │ (Amazon Nova Pro LLM)
  │        ├─→ ai_insights (per-hospital)
  │        ├─→ executive_summary
  │        └─→ visualizations (5 charts)
  │
  └─→ END
```

---

## 🤖 AI-Powered Insights

### Amazon Nova Pro Integration

The system uses **Amazon Nova Pro** (`amazon.nova-pro-v1:0`) for generating intelligent recommendations:

#### Per-Hospital Analysis
For each misaligned hospital, the AI generates:
1. Clear explanation of misalignment reasons
2. Specific, actionable recommendations (3-5 bullet points)
3. Estimated savings or benefits

#### Executive Summary
Overall analysis including:
1. Key findings summary
2. Organization-wide risk assessment
3. Top 3 priority actions
4. Projected cost savings

### Request Format (Nova Pro)
```python
bedrock_runtime.invoke_model(
    modelId=bedrock_config.model_id,  # amazon.nova-pro-v1:0
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
```

---

## 📊 Visualizations

The system generates 5 visualization charts using matplotlib:

| Chart | Type | Description |
|-------|------|-------------|
| `alignment_status_pie.png` | Pie | Aligned vs Misaligned hospitals |
| `risk_level_distribution.png` | Bar | Count by risk level (HIGH/MEDIUM/LOW) |
| `spend_by_risk_level.png` | Stacked Bar | Quarterly spend breakdown by risk |
| `product_type_distribution.png` | Grouped Bar | Purchases by product type per hospital |
| `contract_compliance.png` | Stacked Bar | Contracted vs off-contract purchases |

**Output Directory:** `purchasing_alignment_monitor/outputs/visualizations/`

---

## 🔄 Data Flow

### Phase 1: Retrieval (RAG)
```
Bedrock Knowledge Base (S3)
        │
        ├─→ Contract Rules (retrieve_and_generate)
        │   └──→ parse_contract_terms()
        │        ├── Pricing tier thresholds
        │        ├── Discount percentages
        │        └── Compliance requirements
        │
        ├─→ Product Catalog (retrieve_and_generate)
        │   └──→ parse_product_catalog()
        │        ├── Branded Rx products
        │        ├── Generic products
        │        └── OneStop products
        │
        └─→ Purchase Orders (retrieve - raw chunks)
            └──→ reconstruct_csv()
                 ├── Filter PO chunks
                 ├── Fix newlines
                 └── Deduplicate records
```

### Phase 2: Analysis
```
Purchase Order Records
        │
        ├─→ Parse CSV with pandas
        │   └── Convert to PurchaseRecord dataclass
        │
        ├─→ Group by Hospital
        │   ├── Sum quarterly spend
        │   ├── Count by product type
        │   └── Calculate annual projection (×4)
        │
        ├─→ Detect Violations
        │   ├── Check NDCs against contracted_products
        │   ├── Compare spend to tier thresholds
        │   └── Validate pricing tier applied
        │
        └─→ Risk Assessment
            ├── HIGH: Off-contract purchases
            ├── MEDIUM: Below tier minimum
            └── LOW: Fully aligned
```

### Phase 3: AI Insights Generation
```
Misaligned Hospitals
        │
        ├─→ For each hospital:
        │   └── Amazon Nova Pro
        │       ├── Analyze misalignment
        │       └── Generate recommendations
        │
        ├─→ Executive Summary
        │   └── Amazon Nova Pro
        │       ├── Overall risk assessment
        │       └── Priority actions
        │
        └─→ Visualizations
            └── matplotlib
                ├── Pie charts
                ├── Bar charts
                └── Stacked bar charts
```

### Phase 4: Output Generation
```
Analysis Results
        │
        ├─→ CSV Export
        │   └── misaligned_hospitals_q[Q]_[YEAR].csv
        │
        ├─→ Text Report
        │   └── analysis_report_q[Q]_[YEAR].txt
        │       ├── Summary statistics
        │       ├── Risk breakdown
        │       └── Hospital details
        │
        └─→ Visualizations
            └── outputs/visualizations/*.png
```

---

## 🎯 Risk Detection Algorithm

### Pricing Tier Thresholds
```python
contract_terms = {
    'tier1_min': 800000.0,   # $800K minimum for Tier 1
    'tier1_max': 900000.0,   # $900K maximum for Tier 1
    'tier2_min': 900001.0,   # Tier 2 starts above $900K
    'tier2_max': 1000000.0,  # Tier 2 up to $1M
    'tier3_min': 1000001.0,  # Tier 3 above $1M
    'tier2_discount': 0.0025,  # 0.25% discount
    'tier3_discount': 0.005,   # 0.50% discount
}
```

### Risk Scoring Algorithm
```
FOR each hospital:
    issues = []
    risk_level = "LOW"
    
    # 1. Check for off-contract purchases (HIGH RISK)
    FOR each purchase:
        IF drug_ndc NOT IN contracted_products:
            issues.append(f"Off-contract purchase: {drug_name}")
            risk_level = "HIGH"
    
    # 2. Calculate annual spend projection
    annual_spend = quarterly_spend × 4
    
    # 3. Determine pricing tier
    IF annual_spend < tier1_min:
        pricing_tier = "Below Tier 1"
        issues.append("Projected spend below minimum")
        IF risk_level != "HIGH":
            risk_level = "MEDIUM"
    ELIF annual_spend <= tier1_max:
        pricing_tier = "Tier 1"
    ELIF annual_spend <= tier2_max:
        pricing_tier = "Tier 2"
    ELSE:
        pricing_tier = "Tier 3"
    
    # 4. Set alignment status
    alignment_status = "MISALIGNED" if issues else "ALIGNED"
```

---

## 📊 CSV Output Schema

**Filename Format:** `misaligned_hospitals_q[QUARTER]_[YEAR].csv`

**Example:** `misaligned_hospitals_q1_2026.csv`

**Columns:**
| # | Column | Type | Example | Notes |
|---|--------|------|---------|-------|
| 1 | hospital_id | string | H001 | Unique identifier |
| 2 | hospital_name | string | City Medical Center | Official name |
| 3 | quarterly_spend | float | 72390.00 | Total USD spend |
| 4 | alignment_status | string | MISALIGNED | ALIGNED or MISALIGNED |
| 5 | risk_level | string | MEDIUM | LOW, MEDIUM, HIGH |
| 6 | issues | string | Off-contract: Drug X; Below min | Semicolon-separated |

**Sample Output:**
```csv
hospital_id,hospital_name,quarterly_spend,alignment_status,risk_level,issues
H001,City Medical Center,72390.0,MISALIGNED,MEDIUM,"Projected annual spend ($289,560.00) below Tier 1 minimum ($800,000.00)"
H002,Valley Health,31700.0,MISALIGNED,MEDIUM,"Off-contract purchase: Unapproved Drug X (NDC: 99999-999-99); Projected annual spend ($126,800.00) below Tier 1 minimum ($800,000.00)"
```

---

## 🔐 Error Handling

### Retrieval Errors
```python
try:
    response = bedrock_runtime.retrieve(...)
except Exception as e:
    state['retrieval_errors'].append(f"Bedrock KB error: {e}")
    state['purchase_order_data'] = ""
    # Continue with empty data
```

### AI Insights Errors
```python
try:
    response = bedrock_runtime.invoke_model(...)
except Exception as e:
    print(f"✗ Error generating AI insights: {str(e)}")
    state["ai_insights"] = {}
    state["executive_summary"] = ""
    # Workflow continues without AI insights
```

### CSV Parse Errors
```python
try:
    df = pd.read_csv(StringIO(csv_data))
except Exception as e:
    print(f"✗ Error parsing PO data: {str(e)}")
    return []  # Return empty records
```

### Invalid Record Handling
```python
try:
    quantity = int(record.get("quantity", 0))
    unit_price = float(record.get("unit_price", 0.0))
except (ValueError, TypeError) as e:
    print(f"⚠ Skipping invalid record: {record} - {str(e)}")
    continue  # Skip malformed records
```

---

## 🚀 Performance Characteristics

| Operation | Typical Time | Notes |
|-----------|--------------|-------|
| Contract Rules Retrieval | 2-3s | retrieve_and_generate |
| Product Catalog Retrieval | 2-3s | retrieve_and_generate |
| PO Data Retrieval | 1-2s | retrieve (raw chunks) |
| CSV Parsing | <100ms | For 100+ records |
| Hospital Analysis | <500ms | Per hospital |
| AI Insights (per hospital) | 3-5s | Amazon Nova Pro |
| Executive Summary | 3-5s | Amazon Nova Pro |
| Visualization Generation | <1s | 5 charts |
| CSV/Report Generation | <100ms | File I/O |
| **Total Execution** | **15-30s** | End-to-end with AI |

---

## 🔍 Bedrock Knowledge Base Setup

### Document Structure
```
Knowledge Base (S3 bucket)
├── VendorContractOmnicare/
│   └── vendor_contract_q1_2025.md
│       ├── Pricing Tier Thresholds
│       ├── Product Catalog (Branded/Generic/OneStop)
│       └── Compliance Requirements
│
└── S3DataCopy/
    └── po_data_q1_2025.csv
        ├── Hospital IDs and Names
        ├── Drug Purchases (NDC, quantity, price)
        └── Contract Tiers Applied
```

### Retrieval Configuration

**For Contract Rules & Product Catalog:**
```python
# Uses retrieve_and_generate for LLM-processed responses
response = bedrock_runtime.retrieve_and_generate(
    input={"text": query},
    retrieveAndGenerateConfiguration={
        "type": "KNOWLEDGE_BASE",
        "knowledgeBaseConfiguration": {
            "knowledgeBaseId": bedrock_config.knowledge_base_id,
            "modelArn": bedrock_config.model_arn,
        },
    },
)
```

**For Purchase Order Data:**
```python
# Uses retrieve for raw chunks (no LLM processing)
response = bedrock_runtime.retrieve(
    knowledgeBaseId=bedrock_config.knowledge_base_id,
    retrievalQuery={"text": query},
    retrievalConfiguration={
        "vectorSearchConfiguration": {
            "numberOfResults": 25  # Get all chunks
        }
    }
)
```

---

## 🧪 Testing Strategy

### Unit Tests (73 tests)
- CSV parsing with various formats
- Risk level assignment logic
- Hospital aggregation calculations
- Pricing tier determination
- Contract product matching
- Visualization generation

### Integration Tests
- Full workflow execution (mock Bedrock)
- CSV output validation
- Error handling paths
- AI insights with mocked responses

### Test Output Directory
```
tests/test_outputs/
├── visualizations/
│   ├── alignment_status_pie.png
│   ├── risk_level_distribution.png
│   └── ...
└── reports/
```

---

## 📝 Logging & Monitoring

### Log Levels
```
INFO:  "✓ Retrieved contract rules (1234 characters)"
INFO:  "✓ Parsed 23 purchase order records"
INFO:  "✓ Analyzed 5 hospitals"
INFO:  "✓ Generated insights for City Medical Center"
WARN:  "⚠ Skipping invalid record: {...}"
ERROR: "✗ Error retrieving contract rules: {exception}"
```

### Metrics Tracked
- Number of hospitals analyzed
- Number of misaligned hospitals detected
- Breakdown by risk level (HIGH/MEDIUM/LOW)
- Alignment rate percentage
- AI insights generation success/failure

---

## 🔄 Extension Points

### Implemented Enhancements
1. ✅ **AI-Powered Insights** - Amazon Nova Pro recommendations
2. ✅ **Visualizations** - 5 chart types with matplotlib
3. ✅ **Product Catalog Integration** - Branded/Generic/OneStop categorization
4. ✅ **Volume-Based Pricing Tiers** - Tier 1/2/3 thresholds

### Future Enhancements
1. **Multiple Vendor Support**
   - Track per-vendor compliance
   - Handle overlapping contracts

2. **Historical Analysis**
   - Compare quarter-over-quarter trends
   - Identify improving/declining hospitals

3. **Alerts & Notifications**
   - Email HIGH risk hospitals
   - Slack integration for real-time alerts

4. **Advanced Analytics**
   - Price trend analysis
   - Spend forecasting
   - Tier optimization recommendations

5. **API Integration**
   - REST API for report access
   - Webhook for ERP systems

---

## 📚 References

- [AWS Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)
- [AWS Bedrock Knowledge Bases](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html)
- [Amazon Nova Models](https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [Matplotlib Documentation](https://matplotlib.org/stable/contents.html)
- [Pandas DataFrame API](https://pandas.pydata.org/docs/)

---

**Last Updated:** February 2026  
**Version:** 0.2.0
