# Accruals Automation - Technical Documentation

## Architecture Overview

This is a Python-based automation system that uses AI (GPT-4o) to process invoices and make accrual decisions for finance operations.

### High-Level Data Flow

```
┌─────────────────┐
│  Snowflake DB   │ (Input: Pre-filtered PO lines & bill data)
└────────┬────────┘
         │
         ├─→ NetSuite RPA ──→ Download Invoice Files ──→ Google Drive
         │
         ├─→ Invoice Processor (AI) ──→ Extract Data ──→ CSV ──→ Snowflake
         │
         └─→ Accrual Engine (AI) ──→ Analyze & Decide ──→ CSV ──→ Snowflake
```

## Technology Stack

- **Language**: Python 3.8+
- **AI**: OpenAI GPT-4o (vision + text)
- **Browser Automation**: Playwright (for NetSuite RPA)
- **Database**: Snowflake (data warehouse)
- **Storage**: Google Drive (invoice files)
- **Async**: ThreadPoolExecutor (parallel processing)
- **Config**: YAML (AI prompts), .env (credentials)

## Project Structure

```
accruals/
├── main.py                              # Interactive menu (entry point)
├── run_invoice_download.py              # RPA download script
├── run_invoice_extraction.py            # AI extraction script
├── run_accrual_analysis.py              # AI analysis script
├── upload_to_snowflake.py               # Upload invoices to DB
├── upload_accrual_analysis_to_snowflake.py  # Upload analysis to DB
│
├── config/
│   └── settings.py                      # Configuration classes from .env
│
├── prompts/
│   ├── invoice_extraction.yaml          # AI prompts for invoice processing
│   └── accrual_analysis.yaml            # AI prompts for accrual decisions
│
└── src/
    ├── clients/
    │   ├── netsuite_rpa_downloader.py   # Playwright browser automation
    │   └── snowflake_data_client.py     # Snowflake queries & uploads
    │
    ├── processors/
    │   ├── invoice_processor.py         # AI invoice extraction
    │   └── accrual_engine.py            # AI accrual decision logic
    │
    └── utils/
        ├── logger.py                    # Centralized logging
        └── prompt_manager.py            # YAML prompt loader
```

## Core Components

### 1. NetSuite RPA Downloader
**File**: `src/clients/netsuite_rpa_downloader.py`

**Purpose**: Downloads invoice files from NetSuite using browser automation.

**Why RPA?**: NetSuite API has limitations for file downloads. RPA is more reliable.

**Key Features**:
- Playwright-based browser automation
- Manual Okta SSO login (security)
- Batch download with single login session
- Automatic skip for already-downloaded bills
- Retry logic (3 attempts per bill)

**Flow**:
```python
1. Launch Chromium browser
2. Navigate to Okta SSO URL
3. Wait for manual login (or timeout)
4. For each bill:
   - Navigate to bill page
   - Find "Communication" section
   - Download all attached files
   - Save to: INVOICES_DIR/{bill_id}/
5. Close browser
```

**Usage**:
```python
from src.clients.netsuite_rpa_downloader import NetSuiteRPADownloader

downloader = NetSuiteRPADownloader(headless=True, manual_login=True)
files = downloader.download_bill_invoices("26358814")
```

---

### 2. Snowflake Data Client
**File**: `src/clients/snowflake_data_client.py`

**Purpose**: All Snowflake interactions (read from views, write to tables).

**Key Methods**:

#### Read Operations (from views):
- `get_bills_to_download()` - Bills needing invoice download
- `get_po_lines_for_month(month)` - PO lines to analyze
- `get_related_bills(po_number)` - Related bills for PO line
- `get_already_processed_bills()` - Skip logic for invoices
- `get_already_analyzed_po_lines(month)` - Skip logic for analysis

#### Write Operations (to tables):
- `upload_csv_to_snowflake(csv_path)` - Bulk insert invoice data
- `upload_accrual_analysis_to_snowflake(csv_path)` - Bulk insert analysis

**Snowflake Views (Input - Read-Only)**:
```sql
PSEDM_FINANCE_PROD.EDM_GTM_FPA.ACCRUALS_AUTOMATION_BILLS_TO_DOWNLOAD
PSEDM_FINANCE_PROD.EDM_GTM_FPA.ACCRUALS_AUTOMATION_PO_ANALYSIS_INPUT
PSEDM_FINANCE_PROD.EDM_GTM_FPA.ACCRUALS_AUTOMATION_RELATED_BILLS_FOR_ANALYSIS_INPUT
```

**Snowflake Tables (Output - Append)**:
```sql
PSEDM_FINANCE_PROD.EDM_GTM_FPA.ACCRUALS_AUTOMATION_EXTRACTED_INVOICES
PSEDM_FINANCE_PROD.EDM_GTM_FPA.ACCRUALS_AUTOMATION_ANALYSIS_RESULTS
```

**Important**: Input views pre-filter data:
- Excluded GL accounts: 4550, 6080, 6090, 6092
- Minimum unbilled amount: $5,000 USD
- Only active/relevant PO lines

---

### 3. Invoice Processor
**File**: `src/processors/invoice_processor.py`

**Purpose**: Extract structured data from invoice files using GPT-4o Vision.

**Supports**: PDF, Excel (.xlsx), Word (.docx), Images (PNG, JPG)

**Key Features**:
- Multi-format document processing
- YAML-based prompt configuration
- Automatic language detection/translation
- Confidence scoring
- Incremental processing (skip already-processed)

**Flow**:
```python
1. Check if bill already processed (Snowflake query)
2. Find invoice files in INVOICES_DIR/{bill_id}/
3. For each file:
   - Convert to base64 (for vision API)
   - Load YAML prompt (invoice_extraction.yaml)
   - Call GPT-4o vision API
   - Parse JSON response
   - Save to CSV
4. Return InvoiceData objects
```

**Data Extracted**:
- Invoice number, date
- Service description & period
- Line items summary
- Total/tax/net amounts
- Currency
- Confidence score

**Usage**:
```python
from src.processors.invoice_processor import InvoiceProcessor

processor = InvoiceProcessor()
invoice_data = processor.extract_from_bill("26358814")
```

**Token Usage**: ~3,700 tokens/invoice (3,300 input + 400 output)

---

### 4. Accrual Engine
**File**: `src/processors/accrual_engine.py`

**Purpose**: Analyze PO lines and decide if accruals are needed using GPT-4o.

**Key Features**:
- YAML-based prompt configuration
- Combines PO line data + related bills + invoice extractions
- Structured JSON output with confidence scores
- Token/time tracking per decision

**Flow**:
```python
1. Receive PO line data from Snowflake
2. Receive related bills data from Snowflake
3. Prepare structured data for AI:
   - PO details (amount, GL account, dates, etc.)
   - All related bills (amounts, posting periods)
   - All invoice extractions (service periods, descriptions)
4. Load YAML prompt (accrual_analysis.yaml)
5. Call GPT-4o API with all context
6. Parse JSON response:
   - needs_accrual (bool)
   - accrual_amount (float)
   - reasoning (string)
   - confidence_score (float)
7. Return AccrualDecision object
```

**Important**: Business rules are NOT in Python code. They are:
- Pre-applied in Snowflake view (GL exclusions, min balance)
- Embedded in AI system prompt (YAML file)

**Usage**:
```python
from src.processors.accrual_engine import AccrualEngine

engine = AccrualEngine(current_month="October 2025")
decision = engine.analyze_po_line(po_line, related_bills)
```

**Token Usage**: ~5,500 tokens/PO line (5,000 input + 500 output)

---

### 5. Prompt Manager
**File**: `src/utils/prompt_manager.py`

**Purpose**: Load and manage AI prompts from YAML files.

**Key Features**:
- Loads all YAML files from `prompts/` directory
- Template variable substitution
- Model configuration (model, temperature, etc.)
- Handles different API parameters (max_tokens vs max_completion_tokens)

**YAML Structure**:
```yaml
model: "gpt-4o"
temperature: 0.1  # Optional
response_format: "json_object"  # Optional

system_prompt: |
  You are an expert financial analyst...

user_prompt_template: |
  Analyze this PO line:
  PO Number: {po_number}
  Amount: {amount}
  ...
```

**Usage**:
```python
from src.utils.prompt_manager import PromptManager

pm = PromptManager()
system = pm.get_system_prompt("invoice_extraction")
user = pm.get_user_prompt("invoice_extraction", bill_id="12345")
config = pm.get_model_config("invoice_extraction")
```

---

### 6. Logger
**File**: `src/utils/logger.py`

**Purpose**: Centralized logging with file + console output.

**Features**:
- LOG_LEVEL from .env (INFO, DEBUG, WARNING, ERROR)
- Daily log files: `logs/{module}_{YYYYMMDD}.log`
- UTF-8 encoding (handles foreign languages)
- Console + file handlers

**Usage**:
```python
from src.utils.logger import setup_logger

logger = setup_logger(__name__)
logger.info("Processing started")
logger.error(f"Failed to process: {error}")
```

---

## Workflow Scripts

### 1. Invoice Download (`run_invoice_download.py`)

**Purpose**: Download invoice files from NetSuite for bills in Snowflake view.

**Flow**:
```python
1. Get bill IDs from Snowflake view (BILLS_TO_DOWNLOAD)
2. Filter out already-downloaded bills (check INVOICES_DIR)
3. Ask user for confirmation
4. Initialize RPA downloader
5. Manual Okta login (one-time)
6. For each bill (sequential):
   - Navigate to bill page
   - Download files
   - Save to INVOICES_DIR/{bill_id}/
7. Save failed_downloads.csv (if any failures)
```

**Usage**:
```bash
python run_invoice_download.py                    # Auto from Snowflake
python run_invoice_download.py 26358814           # Single bill
python run_invoice_download.py --test-connection  # Test only
```

---

### 2. Invoice Extraction (`run_invoice_extraction.py`)

**Purpose**: Extract data from downloaded invoices using AI.

**Flow**:
```python
1. Get list of bills with downloaded files (scan INVOICES_DIR)
2. Check Snowflake for already-processed bills
3. Filter to only new bills
4. Ask user for worker count (default: 3)
5. Process bills in parallel using ThreadPoolExecutor:
   - For each bill:
     - Read invoice files
     - Call GPT-4o vision API
     - Extract structured data
     - Track tokens/time
6. Save results to CSV (invoice_extraction_results.csv)
7. Print summary statistics
```

**Parallel Processing**:
```python
with ThreadPoolExecutor(max_workers=3) as executor:
    futures = [executor.submit(process_bill, bill_id) for bill_id in bills]
    for future in as_completed(futures):
        result = future.result()
```

**Usage**:
```bash
python run_invoice_extraction.py              # All bills
python run_invoice_extraction.py --workers 10 # 10 parallel workers
python run_invoice_extraction.py 26358814     # Single bill
```

**Output**: `invoice_extraction_results.csv` in CSV_RESULTS_DIR

---

### 3. Accrual Analysis (`run_accrual_analysis.py`)

**Purpose**: Analyze PO lines and decide accruals using AI.

**Flow**:
```python
1. Ask user for month to analyze (interactive)
2. Get PO lines from Snowflake view (for that month)
3. Get already-analyzed PO lines from Snowflake (skip logic)
4. Filter to only new/unanalyzed PO lines
5. Get related bills for each PO line
6. Ask user for worker count (default: 3)
7. Process PO lines in parallel using ThreadPoolExecutor:
   - For each PO line:
     - Get related bills data
     - Get invoice extractions for those bills
     - Call GPT-4o API with all context
     - Parse AI decision
     - Track tokens/time
8. Save results to CSV (accrual_analysis_results.csv)
9. Print summary statistics
```

**Incremental Processing**:
- Checks Snowflake table for PO lines already analyzed for the selected month
- Only processes new/unanalyzed PO lines
- Safe to re-run without duplicating work

**Usage**:
```bash
python run_accrual_analysis.py                   # Interactive month selection
python run_accrual_analysis.py --month "Oct 2025"  # Specific month
python run_accrual_analysis.py --workers 10      # 10 parallel workers
```

**Output**: `accrual_analysis_results.csv` in CSV_RESULTS_DIR

---

### 4. Upload Scripts

**Purpose**: Upload CSV results to Snowflake tables.

**upload_to_snowflake.py**:
```python
1. Read invoice_extraction_results.csv
2. Count rows
3. Ask user for confirmation
4. Connect to Snowflake
5. Bulk INSERT into ACCRUALS_AUTOMATION_EXTRACTED_INVOICES
6. APPEND mode (doesn't replace existing data)
```

**upload_accrual_analysis_to_snowflake.py**:
```python
1. Read accrual_analysis_results.csv
2. Count rows
3. Ask user for confirmation
4. Connect to Snowflake
5. Bulk INSERT into ACCRUALS_AUTOMATION_ANALYSIS_RESULTS
6. APPEND mode (doesn't replace existing data)
```

**Usage**:
```bash
python upload_to_snowflake.py
python upload_accrual_analysis_to_snowflake.py
```

---

## Configuration

### Environment Variables (.env)

```env
# Snowflake
SNOWFLAKE_USER=username
SNOWFLAKE_PASSWORD=password
SNOWFLAKE_ACCOUNT=account
SNOWFLAKE_WAREHOUSE=warehouse
SNOWFLAKE_DATABASE=PSEDM_FINANCE_PROD
SNOWFLAKE_SCHEMA=EDM_GTM_FPA
SNOWFLAKE_ROLE=role

# OpenAI
OPENAI_API_KEY=sk-...

# NetSuite (for RPA)
NETSUITE_ACCOUNT_ID=3339715
NETSUITE_OKTA_URL=https://company.okta.com/home/netsuite/xxx/xxx
NETSUITE_RPA_HEADLESS=true

# Application
LOG_LEVEL=INFO

# Storage (Google Drive paths)
INVOICES_DIR=G:\...\Bills
CSV_RESULTS_DIR=G:\...\Results
```

### Settings Classes (config/settings.py)

```python
class NetSuiteConfig:
    ACCOUNT_ID = os.getenv("NETSUITE_ACCOUNT_ID")
    OKTA_URL = os.getenv("NETSUITE_OKTA_URL")
    RPA_HEADLESS = os.getenv("NETSUITE_RPA_HEADLESS", "true").lower() == "true"

class OpenAIConfig:
    API_KEY = os.getenv("OPENAI_API_KEY")
    MODEL = "gpt-4-vision-preview"
    MAX_TOKENS = 4000

class SnowflakeConfig:
    ACCOUNT = os.getenv("SNOWFLAKE_ACCOUNT")
    USER = os.getenv("SNOWFLAKE_USER")
    PASSWORD = os.getenv("SNOWFLAKE_PASSWORD")
    # ... etc

class AppConfig:
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
```

---

## Performance Characteristics

### Processing Times
- **Invoice extraction**: ~10 seconds per invoice
- **Accrual analysis**: ~10 seconds per PO line

### Throughput (with parallel workers)
- **3 workers**: ~18 items/minute
- **10 workers**: ~60 items/minute
- **20 workers**: ~120 items/minute (diminishing returns)

### Token Usage (GPT-4o)
- **Invoice extraction**: ~3,700 tokens/invoice (3,300 input + 400 output)
- **Accrual analysis**: ~5,500 tokens/PO line (5,000 input + 500 output)

### Costs (GPT-4o: $2.50/1M input, $10.00/1M output)
- **Invoice extraction**: $0.0123 per invoice
- **Accrual analysis**: $0.0175 per PO line
- **Monthly example** (500 + 500): ~$14.90/month

### OpenAI Rate Limits (Tier 3)
- **RPM**: 10,000 requests/minute
- **TPM**: 10,000,000 tokens/minute
- **With 10 workers**: ~60 requests/min, ~330K tokens/min (well under limits)

---

## Error Handling & Resilience

### Skip Logic (Incremental Processing)
All components check before processing:
- **Invoice download**: Check if `INVOICES_DIR/{bill_id}/` exists with files
- **Invoice extraction**: Query Snowflake for processed bills
- **Accrual analysis**: Query Snowflake for analyzed PO lines (per month)

### Retry Logic
- **RPA downloads**: 3 retries per bill (network issues, page load timeouts)
- **No retries for AI**: Failed items logged, processing continues

### Failed Items Tracking
- **Failed downloads**: Saved to `failed_downloads_{timestamp}.csv`
- **Failed extractions**: Logged with error message
- **Failed analysis**: Logged with error message

### Parallel Processing Error Handling
```python
try:
    result = process_item(item)
    results.append(result)
except Exception as e:
    logger.error(f"Failed to process {item}: {str(e)}")
    # Continue with next item
```

---

## Key Design Decisions

### Why Snowflake Views Instead of NetSuite API?
- **Faster**: Snowflake queries are faster than NetSuite API
- **No rate limits**: NetSuite API has strict rate limiting
- **Pre-filtered**: Business rules applied once in SQL, not in Python
- **Single source of truth**: All data flows through Snowflake

### Why RPA for Downloads Instead of API?
- **NetSuite API limitations**: File download API is unreliable
- **More robust**: Browser automation works like a human user
- **Handles Okta SSO**: Manual login for security compliance

### Why CSV Instead of Direct Database Inserts?
- **Review before upload**: Users can inspect CSV results
- **Easier debugging**: Can see exact data being uploaded
- **Rollback friendly**: Can delete CSV and re-run
- **Simple bulk upload**: Snowflake INSERT FROM CSV is fast

### Why YAML for Prompts?
- **Hot reload**: Change prompts without code changes
- **Non-technical edits**: Finance team can adjust prompts
- **Version control**: Track prompt changes in git
- **Template variables**: Dynamic prompt construction

### Why Parallel Processing with Threads (not async)?
- **Simplicity**: ThreadPoolExecutor is simple and reliable
- **I/O bound**: Waiting on API responses (not CPU bound)
- **OpenAI SDK**: Uses requests library (blocking I/O)
- **Good enough**: 10-60 items/minute is sufficient

---

## Development Guide

### Adding a New AI Processor

1. **Create YAML prompt** in `prompts/`:
```yaml
model: "gpt-4o"
system_prompt: |
  You are an expert...
user_prompt_template: |
  Analyze: {data}
```

2. **Create processor class**:
```python
from src.utils.prompt_manager import PromptManager

class MyProcessor:
    def __init__(self):
        self.pm = PromptManager()
        self.client = OpenAI(api_key=OpenAIConfig.API_KEY)

    def process(self, data):
        system = self.pm.get_system_prompt("my_prompt")
        user = self.pm.get_user_prompt("my_prompt", data=data)
        response = self.client.chat.completions.create(...)
        return response
```

3. **Add logging**:
```python
from src.utils.logger import setup_logger
logger = setup_logger(__name__)
```

### Adding a New Snowflake View/Table

1. **Create view in Snowflake** with required filters
2. **Add query method** to `SnowflakeDataClient`:
```python
def get_my_data(self):
    query = """
        SELECT * FROM PSEDM_FINANCE_PROD.EDM_GTM_FPA.MY_VIEW
    """
    with self._get_connection() as conn:
        cursor = conn.cursor(DictCursor)
        cursor.execute(query)
        return cursor.fetchall()
```

3. **Update README** with table/view name and purpose

### Testing

**Manual testing approach** (no unit tests):
1. Test with single item first: `python run_script.py ITEM_ID`
2. Check logs for errors: `logs/script_name_YYYYMMDD.log`
3. Verify CSV output before uploading to Snowflake
4. Test with small batch (10-50 items) before full run

---

## Debugging Tips

### Enable Debug Logging
```env
LOG_LEVEL=DEBUG
```

### Check Token Usage
Look for these log lines:
```
Token usage - Input: 3300, Output: 400, Total: 3700
Tokens=5500 (in:5000, out:500), Time=10.2s
```

### Check Skip Logic
Look for these log lines:
```
✓ Invoices for bill 26358814 have already been downloaded
Skipping already processed bill: 26358814
Skipping already analyzed PO line: PO123456 for month Oct 2025
```

### Inspect AI Responses
Enable debug logging to see full API responses in logs.

### Test RPA Without Headless
```bash
export NETSUITE_RPA_HEADLESS=false
python run_invoice_download.py --test-connection
```

---

## Common Issues

### Issue: RPA Login Times Out
- **Cause**: Didn't complete Okta login within 5 minutes
- **Solution**: Login faster, or increase timeout in code

### Issue: OpenAI Rate Limit Error
- **Cause**: Too many workers for your tier
- **Solution**: Reduce worker count or upgrade OpenAI tier

### Issue: Snowflake Connection Failed
- **Cause**: Credentials, network, or VPN
- **Solution**: Check .env, test with `python main.py` → option 8

### Issue: Invoice Files Not Found
- **Cause**: INVOICES_DIR path incorrect
- **Solution**: Check .env INVOICES_DIR points to Google Drive

### Issue: CSV Upload Failed
- **Cause**: Column mismatch or data type error
- **Solution**: Check CSV columns match Snowflake table schema

---

## Security Considerations

### Credentials Storage
- ✅ All credentials in `.env` (git-ignored)
- ✅ Never hardcode credentials in code
- ❌ Never commit `.env` to git

### Okta Login
- ✅ Manual login (no password storage)
- ✅ Session is temporary (closed after downloads)
- ❌ Never use `--no-verify` flags

### API Keys
- ✅ OpenAI API key from environment variable
- ✅ Snowflake credentials from environment variable
- ❌ Never log API keys or passwords

### File Permissions
- Invoice files stored on Google Drive (company-controlled)
- CSV results stored on Google Drive (company-controlled)
- Logs may contain sensitive data (don't share publicly)

---

## Future Improvements

### Potential Enhancements
1. **Web UI**: React/Next.js frontend instead of CLI
2. **Real-time monitoring**: Dashboard showing processing status
3. **Automated scheduling**: Cron job for monthly runs
4. **Error notifications**: Slack/email alerts for failures
5. **Batch size optimization**: Dynamic worker count based on load
6. **Model switching**: Support GPT-4o-mini for cost savings
7. **Caching**: Cache Snowflake queries to reduce redundant calls
8. **Metrics tracking**: Store processing times/costs in database

### Not Recommended
- ❌ Automated Okta login (security risk)
- ❌ Parallel RPA downloads (single browser session is optimal)
- ❌ Move business rules to Python (keep in Snowflake views)

---

## Appendix: Data Models

### InvoiceData (Dataclass)
```python
@dataclass
class InvoiceData:
    bill_id: str
    is_invoice: bool
    invoice_number: Optional[str]
    invoice_date: Optional[date]
    service_description: Optional[str]
    service_period: Optional[str]
    line_items_summary: Optional[str]
    total_amount: Optional[float]
    tax_amount: Optional[float]
    net_amount: Optional[float]
    currency: Optional[str]
    confidence_score: float
    extracted_at: datetime
    file_path: str
```

### AccrualDecision (Dataclass)
```python
@dataclass
class AccrualDecision:
    po_number: str
    needs_accrual: bool
    accrual_amount: float
    reasoning: str
    short_summary: str
    confidence_score: float
    analyzed_at: datetime
    processing_time_seconds: float
    tokens_input: int
    tokens_output: int
    tokens_total: int
```

---

## Contact & Support

For technical issues:
1. Check logs in `logs/` directory
2. Review this technical documentation
3. Check user-facing README.md for common issues
4. Contact development team

---

**Last Updated**: October 2025
**Version**: 1.0 (Production)