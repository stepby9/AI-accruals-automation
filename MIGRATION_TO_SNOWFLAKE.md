# Migration Guide: NetSuite API → Snowflake Views

This guide explains the changes made to use Snowflake views for data queries instead of NetSuite API.

## What Changed

### Before (NetSuite API)
```
Google Sheets → NetSuite API (fetch PO/Bill data) → NetSuite RPA (download files) → Process
```

### After (Snowflake + RPA)
```
Google Sheets → Snowflake Views (fetch PO/Bill data) → NetSuite RPA (download files) → Process
```

## New Architecture

### Data Flow
1. **PO/PR List**: Still from Google Sheets
2. **PO/Bill Data**: Now from Snowflake views (was NetSuite API)
3. **Invoice Files**: NetSuite RPA downloads (unchanged)
4. **Storage**: Snowflake database (unchanged)

### Files Changed

**NEW FILES:**
- `src/clients/netsuite_client_simplified.py` - RPA downloads only
- `src/clients/snowflake_data_client.py` - Data queries from Snowflake

**KEPT (for reference):**
- `src/clients/netsuite_client.py` - Old API client (not used)

**UPDATED:**
- `src/clients/__init__.py` - Now imports simplified versions

## Setup Required

### 1. Create Snowflake Views

You need to create Snowflake views that replicate the NetSuite data structure:

#### View 1: PO Lines View
```sql
CREATE OR REPLACE VIEW YOUR_PO_LINES_VIEW AS
SELECT
    po_id,
    line_id,
    vendor_name,
    requestor,
    legal_entity,
    currency,
    memo,
    gl_account,
    description,
    amount,
    amount_usd,
    delivery_date,
    prepaid_start_date,
    prepaid_end_date,
    remaining_balance,
    remaining_balance_usd
FROM your_netsuite_po_data_table;
```

#### View 2: Bills View
```sql
CREATE OR REPLACE VIEW YOUR_BILLS_VIEW AS
SELECT
    bill_id,
    po_id,
    vendor_name,
    amount,
    currency,
    posting_period,
    payment_status,
    created_date,
    due_date
FROM your_netsuite_bills_data_table;
```

### 2. Update Code with Your View Names

Edit `src/clients/snowflake_data_client.py` and replace:

```python
# Line ~65
FROM YOUR_PO_LINES_VIEW

# Line ~140
FROM YOUR_BILLS_VIEW

# Line ~260
FROM YOUR_BILLS_VIEW
```

With your actual Snowflake view names.

### 3. Test Snowflake Connection

```python
from src.clients import SnowflakeDataClient

client = SnowflakeDataClient()
success = client.test_connection()
print(f"Snowflake connected: {success}")
```

## Code Changes Needed

### Old Code (NetSuite API)
```python
from src.clients import NetSuiteClient

netsuite = NetSuiteClient()

# Fetch PO data
po_line = netsuite.get_po_line_details(po_id, line_id)

# Fetch bills
bills = netsuite.get_bills_for_po(po_id)

# Download files
files = netsuite.download_invoice_files(bill_id)
```

### New Code (Snowflake + RPA)
```python
from src.clients import SnowflakeDataClient, NetSuiteClient

# Data from Snowflake
snowflake = SnowflakeDataClient()
po_line = snowflake.get_po_line_details(po_id, line_id)
bills = snowflake.get_bills_for_po(po_id)

# Files from NetSuite RPA
netsuite = NetSuiteClient()  # Now simplified - RPA only
files = netsuite.download_invoice_files(bill_id)
```

## Configuration Changes

### .env File

**Remove (no longer needed):**
```env
# NETSUITE_TOKEN_ID=your_token_id
# NETSUITE_TOKEN_SECRET=your_token_secret
# NETSUITE_CONSUMER_KEY=your_consumer_key
# NETSUITE_CONSUMER_SECRET=your_consumer_secret
```

**Keep (still needed):**
```env
# For RPA downloads
NETSUITE_ACCOUNT_ID=3339715
NETSUITE_OKTA_URL=https://purestorage.okta.com/home/netsuite/xxx/xxx
NETSUITE_RPA_HEADLESS=false
NETSUITE_USE_RPA_DOWNLOADS=true

# For Snowflake data
SNOWFLAKE_ACCOUNT=your_account
SNOWFLAKE_USER=your_user
SNOWFLAKE_PASSWORD=your_password
SNOWFLAKE_DATABASE=your_database
SNOWFLAKE_SCHEMA=your_schema
SNOWFLAKE_WAREHOUSE=your_warehouse
```

## Benefits of This Approach

### ✅ Advantages

1. **Single Source of Truth**: All data from Snowflake
2. **Better Performance**: Snowflake queries are faster than NetSuite API
3. **No API Limits**: No NetSuite API rate limiting
4. **Easier Queries**: SQL is simpler than NetSuite API
5. **Better Testing**: Can query Snowflake directly to verify data
6. **Reliable Downloads**: RPA still works perfectly for files

### ⚠️ Requirements

1. **Snowflake Views Must Be Updated**: Views need to contain current NetSuite data
2. **Data Sync Process**: You need a process to sync NetSuite → Snowflake
3. **View Maintenance**: Views must match expected schema

## Data Sync Considerations

### How to Keep Snowflake Views Current

**Option 1: Scheduled NetSuite → Snowflake ETL**
- Run daily/hourly ETL job
- Extracts data from NetSuite
- Loads into Snowflake tables
- Views always reflect latest data

**Option 2: NetSuite SuiteAnalytics**
- Use NetSuite's built-in data warehouse
- Connect to Snowflake
- Views pull from SuiteAnalytics

**Option 3: Real-time CDC (Change Data Capture)**
- Stream changes from NetSuite
- Real-time updates to Snowflake
- Most complex but most current

## Testing

### Test Snowflake Data Client

```python
from src.clients import SnowflakeDataClient

client = SnowflakeDataClient()

# Test connection
assert client.test_connection()

# Test PO line fetch
po_line = client.get_po_line_details("123456", "1")
print(f"PO Line: {po_line}")

# Test bills fetch
bills = client.get_bills_for_po("123456")
print(f"Bills: {len(bills)}")
```

### Test NetSuite RPA Downloads

```python
from src.clients import NetSuiteClient

client = NetSuiteClient()

# Test file download
files = client.download_invoice_files("26358814")
print(f"Downloaded: {len(files)} files")
```

### Test Integration

```python
from src.clients import SnowflakeDataClient, NetSuiteClient

# Get data from Snowflake
snowflake = SnowflakeDataClient()
bills = snowflake.get_bills_for_po("123456")

# Download files from NetSuite for each bill
netsuite = NetSuiteClient()
for bill in bills:
    files = netsuite.download_invoice_files(bill.bill_id)
    print(f"Bill {bill.bill_id}: {len(files)} files")
```

## Migration Steps

1. **Create Snowflake views** (see Setup section)
2. **Update `snowflake_data_client.py`** with your view names
3. **Test Snowflake connection** (`test_connection()`)
4. **Test data queries** (fetch PO/bills)
5. **Update `.env`** (remove unused NetSuite API credentials)
6. **Test RPA downloads** (should still work)
7. **Update `data_sync.py`** to use `SnowflakeDataClient` instead of `NetSuiteClient`
8. **Run end-to-end test** with a small dataset

## Rollback Plan

If you need to rollback:

1. Restore original `src/clients/__init__.py`:
```python
from .netsuite_client import NetSuiteClient, POLine, Bill
```

2. The old `netsuite_client.py` is still in the codebase for reference

## Next Steps

1. Create the Snowflake views
2. Update `snowflake_data_client.py` with your view names
3. Test the connection
4. Update `data_sync.py` to use the new clients
5. Run a test with a few PO lines

## Questions?

Check the files:
- `src/clients/snowflake_data_client.py` - Snowflake queries
- `src/clients/netsuite_client_simplified.py` - RPA downloads only
- `src/clients/netsuite_rpa_downloader.py` - RPA implementation
