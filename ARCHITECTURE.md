# System Architecture - Purchasing Alignment Monitor

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
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
    ┌─────────┐      ┌──────────────┐      ┌───────────┐
    │Retriever│      │  Analyzer    │      │ CSV Export│
    │ (RAG)   │      │ (Risk Logic) │      │ (Output)  │
    └────┬────┘      └──────┬───────┘      └─────┬─────┘
         │                  │                     │
         └──────────────────┼─────────────────────┘
                            │
                ┌───────────┴────────────┐
                │                        │
                ▼                        ▼
           AWS Bedrock            Local File System
         Knowledge Base           (CSV/TXT Reports)
```

## 📦 Module Structure

### 1. **Main Entry Point** (`main.py`)
**Responsibilities:**
- Initialize and execute the entire workflow
- Validate AWS configuration
- Handle errors gracefully
- Generate human-readable reports
- Save output files

**Key Functions:**
```python
main()                    # Main execution orchestrator
generate_csv_report()     # Creates CSV output file
generate_text_report()    # Creates readable text report
```

**Output:**
- CSV file: `misaligned_hospitals_q[Q]_[YEAR].csv`
- Text report: `analysis_report_q[Q]_[YEAR].txt`

---

### 2. **Configuration Module** (`config/bedrock_config.py`)
**Responsibilities:**
- Manage AWS credentials and Bedrock settings
- Provide boto3 client instances
- Validate configuration completeness

**Key Classes:**
```python
class BedrockConfig:
    get_bedrock_agent_runtime()  # Returns AWS SDK runtime client
    get_bedrock_client()         # Returns Bedrock client
    validate_config()            # Ensures all env vars are set
```

**Environment Variables:**
```env
AWS_REGION              # AWS region (e.g., us-east-1)
AWS_ACCESS_KEY_ID       # AWS access key
AWS_SECRET_ACCESS_KEY   # AWS secret key
KNOWLEDGE_BASE_ID       # Bedrock KB identifier
MODEL_ARN              # Foundation model ARN
```

---

### 3. **Retriever Agent** (`agents/retriever.py`)
**Responsibilities:**
- Query Bedrock Knowledge Base for contract rules
- Query Bedrock Knowledge Base for purchase order data
- Return retrieved text chunks

**LangGraph Nodes:**

#### `retrieve_contract_rules(state)`
- **Input:** Empty state
- **Output:** `state['contract_rules']` (str)
- **Query:** "What are the vendor contract rules including: contracted drugs, pricing tiers, minimum quarterly commitments, and hospital eligibility classifications?"

**Expected KB Content:**
```
- Contracted Drug List: Paracetamol, Ibuprofen, Aspirin, Amoxicillin
- Pricing Tiers: Standard ($X), Advanced ($Y), Premium ($Z)
- Minimum Quarterly Commitment: $50,000
- Hospital Classifications: Tier A (Standard), Tier B (Advanced)
```

#### `retrieve_purchase_order_data(state)`
- **Input:** State with contract rules
- **Output:** `state['purchase_order_data']` (CSV format)
- **Query:** "Retrieve all quarterly purchase order data including: hospital ID, hospital name, drug name, quantity, unit price, total cost, purchase date, and vendor. Format as CSV."

**Expected KB Content (CSV Format):**
```csv
hospital_id,hospital_name,drug_name,quantity,unit_price,total_cost,purchase_date,vendor
HOSP001,St. Mary,Paracetamol,1000,0.50,500.00,2025-01-15,PharmaCorp
HOSP001,St. Mary,Ciprofloxacin,200,5.00,1000.00,2025-01-20,OtherVendor
```

---

### 4. **Analyzer Agent** (`agents/analyzer.py`)
**Responsibilities:**
- Parse purchase order CSV data
- Aggregate purchases by hospital
- Detect alignment violations
- Assign risk levels

**LangGraph Node:**

#### `analyze_alignment(state)`
- **Input:** `state['purchase_order_data']` (CSV)
- **Output:** 
  - `state['hospital_analyses']` (list of dict)
  - `state['misaligned_hospitals']` (list of dict)

**Analysis Logic:**

```python
# For each hospital:

1. Parse PO Records
   ├── Extract: hospital_id, hospital_name, drug, qty, price, total
   └── Convert: string → structured data

2. Aggregate by Hospital
   ├── Sum quarterly spend
   ├── Count total purchases
   └── Categorize contracted vs off-contract

3. Detect Violations
   ├── Off-contract drugs?           → Issue + Risk ↑
   ├── Price deviation >10%?         → Issue + Risk ↑
   ├── Below minimum spend?          → Issue + Risk ↑
   └── Tier mismatch?                → Issue + Risk ↑

4. Assign Risk Level
   ├── HIGH:   Off-contract purchases present
   ├── MEDIUM: Minimum spend violation or tier mismatch
   └── LOW:    Only minor deviations

5. Set Alignment Status
   ├── MISALIGNED: Any violations detected
   └── ALIGNED:    No violations
```

**Data Structures:**
```python
@dataclass
class HospitalAnalysis:
    hospital_id: str
    hospital_name: str
    quarterly_spend: float
    total_purchases: int
    contracted_purchases: int
    off_contract_purchases: int
    avg_price_deviation: float
    alignment_status: str      # "ALIGNED" | "MISALIGNED"
    risk_level: str           # "LOW" | "MEDIUM" | "HIGH"
    issues: list[str]         # Violation descriptions
```

---

### 5. **Workflow Orchestration** (`agents/workflow.py`)
**Responsibilities:**
- Define LangGraph state schema
- Construct workflow graph
- Manage node connections
- Initialize workflow state

**Workflow State:**
```python
class WorkflowState(TypedDict):
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
```

**Workflow Graph:**
```
START
  │
  ├─→ retrieve_contract_rules
  │        │ (Bedrock Query)
  │        └─→ contract_rules: str
  │
  ├─→ retrieve_po_data
  │        │ (Bedrock Query)
  │        └─→ purchase_order_data: str
  │
  ├─→ analyze_alignment
  │        │ (Risk Analysis)
  │        ├─→ hospital_analyses: list
  │        └─→ misaligned_hospitals: list
  │
  └─→ END
```

---

## 🔄 Data Flow

### Phase 1: Retrieval (RAG)
```
Bedrock Knowledge Base
        │
        ├─→ Contract Rules
        │   └──→ parse_csv_metrics()
        │        ├── Drug lists
        │        ├── Price tiers
        │        └── Min commitments
        │
        └─→ Purchase Orders (CSV)
            └──→ parse_purchase_order_csv()
                 ├── Hospital ID
                 ├── Drug names
                 ├── Quantities
                 └── Prices
```

### Phase 2: Analysis
```
Purchase Order Records
        │
        ├─→ Group by Hospital
        │   ├── Sum quarterly spend
        │   ├── Count purchases
        │   └── Categorize contracts
        │
        ├─→ Detect Violations
        │   ├── Off-contract drugs?
        │   ├── Price deviations?
        │   ├── Below minimum?
        │   └── Tier mismatch?
        │
        └─→ Risk Assessment
            ├── HIGH Risk
            ├── MEDIUM Risk
            └── LOW Risk
```

### Phase 3: Output Generation
```
Hospital Analyses
        │
        ├─→ Filter Misaligned
        │   │
        │   ├─→ CSV Export
        │   │   └── misaligned_hospitals_q[Q]_[Y].csv
        │   │
        │   └─→ Text Report
        │       ├── Summary statistics
        │       ├── Risk breakdown
        │       └── analysis_report_q[Q]_[Y].txt
        │
        └─→ Return Final State
```

---

## 🎯 Risk Detection Algorithm

### Threshold Configuration
```python
thresholds = {
    'contracted_drugs': ['paracetamol', 'ibuprofen', 'aspirin', 'amoxicillin'],
    'min_quarterly_commitment': 50000.00,
    'acceptable_price_deviation': 0.10,  # 10%
    'hospital_tiers': {
        'Tier A': 'Standard coverage',
        'Tier B': 'Advanced coverage',
        'Tier C': 'Premium coverage',
    }
}
```

### Risk Scoring Algorithm
```
FOR each hospital:
    risk_score = 0
    violations = []
    
    # Off-contract drugs (HIGH RISK)
    IF off_contract_count > 0:
        risk_score += 30
        violations.append("Off-contract drugs purchased")
    
    # Below minimum spend (MEDIUM RISK)
    IF quarterly_spend < min_commitment:
        risk_score += 15
        violations.append("Spend below minimum")
    
    # Price deviation (MEDIUM RISK)
    IF avg_price_deviation > threshold:
        risk_score += 10
        violations.append("Price deviations detected")
    
    # Determine risk level
    IF risk_score >= 30:
        risk_level = "HIGH"
    ELIF risk_score >= 15:
        risk_level = "MEDIUM"
    ELSE:
        risk_level = "LOW"
    
    alignment_status = "MISALIGNED" if violations else "ALIGNED"
```

---

## 📊 CSV Output Schema

**Filename Format:** `misaligned_hospitals_q[QUARTER]_[YEAR].csv`

**Example:** `misaligned_hospitals_q1_2025.csv`

**Columns:**
| # | Column | Type | Example | Notes |
|---|--------|------|---------|-------|
| 1 | hospital_id | string | HOSP001 | Unique identifier |
| 2 | hospital_name | string | St. Mary Medical | Official name |
| 3 | quarterly_spend | float | 45000.00 | Total USD spend |
| 4 | alignment_status | string | MISALIGNED | ALIGNED or MISALIGNED |
| 5 | risk_level | string | HIGH | LOW, MEDIUM, HIGH |
| 6 | issues | string | Off-contract drug: X; Below min | Semicolon-separated |

**Sample Output:**
```csv
hospital_id,hospital_name,quarterly_spend,alignment_status,risk_level,issues
HOSP001,St. Mary Medical,45000.00,MISALIGNED,HIGH,Off-contract drug purchased: Ciprofloxacin; Quarterly spend ($45,000.00) below minimum ($50,000.00)
HOSP003,Community Health,48500.00,MISALIGNED,MEDIUM,Quarterly spend ($48,500.00) below minimum ($50,000.00)
```

---

## 🔐 Error Handling

### Retrieval Errors
```python
try:
    response = bedrock_runtime.retrieve_and_generate(...)
except Exception as e:
    state['retrieval_errors'].append(f"Bedrock KB error: {e}")
    state['contract_rules'] = ""  # Empty fallback
    # Continue with analysis (will use defaults)
```

### CSV Parse Errors
```python
try:
    df = pd.read_csv(StringIO(csv_data))
except Exception as e:
    print(f"CSV parse error: {e}")
    return []  # Return empty records
```

### Missing Fields
```python
hospital_id = record.get("hospital_id", "UNKNOWN")
hospital_name = record.get("hospital_name", "UNKNOWN")
# Safe access prevents KeyError crashes
```

---

## 🚀 Performance Characteristics

| Operation | Typical Time | Notes |
|-----------|--------------|-------|
| Bedrock KB Retrieval | 2-5s | Per query |
| CSV Parsing | <100ms | For 100+ records |
| Hospital Analysis | <500ms | Per hospital |
| CSV Generation | <100ms | Per 100 records |
| **Total Execution** | **5-10s** | End-to-end |

---

## 🔍 Bedrock Knowledge Base Setup

### Document Structure
```
Knowledge Base (S3 bucket)
├── Contract Rules/
│   ├── vendor_1_contracts.txt
│   ├── vendor_2_contracts.txt
│   └── pricing_tiers.txt
│
├── Purchase Orders/
│   ├── q1_2025_po_data.csv
│   ├── q2_2025_po_data.csv
│   └── hospital_master_list.csv
│
└── Reference/
    ├── hospital_classifications.txt
    └── drug_catalog.txt
```

### Retrieval Configuration
```python
retrieveAndGenerateConfiguration={
    'type': 'KNOWLEDGE_BASE',
    'knowledgeBaseConfiguration': {
        'knowledgeBaseId': 'kb-xxxxx',
        'modelArn': 'arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-pro-v1:0',
        'retrievalConfiguration': {
            'vectorSearchConfiguration': {
                'numberOfResults': 10
            }
        }
    }
}
```

---

## 🧪 Testing Strategy

### Unit Tests
- CSV parsing with various formats
- Risk level assignment logic
- Hospital aggregation calculations

### Integration Tests
- Full workflow execution (mock Bedrock)
- CSV output validation
- Error handling paths

### End-to-End Tests
- Real Bedrock KB retrieval (with test data)
- Complete workflow with sample hospitals
- Output file verification

---

## 📝 Logging & Monitoring

### Log Levels
```
INFO:  "✓ Retrieved contract rules (1234 characters)"
WARN:  "⚠ Skipping invalid record: {...}"
ERROR: "✗ Error retrieving contract rules: {exception}"
```

### Metrics Tracked
- Number of hospitals analyzed
- Number of misaligned hospitals detected
- Breakdown by risk level (HIGH/MEDIUM/LOW)
- Alignment rate percentage

---

## 🔄 Extension Points

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
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Pandas DataFrame API](https://pandas.pydata.org/docs/)

---

**Last Updated:** February 2025  
**Version:** 0.1.0
