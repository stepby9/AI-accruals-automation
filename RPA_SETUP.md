# NetSuite RPA File Download Setup

This document explains how to use the RPA (Robotic Process Automation) approach for downloading invoice files from NetSuite using browser automation via Playwright.

## Why RPA Instead of API?

The NetSuite API has limitations when it comes to downloading attached files. The RPA approach:
- Uses a real browser to navigate NetSuite
- Handles Okta SSO authentication seamlessly
- Downloads files exactly as a human would
- More reliable for file attachments

## Installation

### 1. Install Playwright

```bash
# Install Python package
pip install playwright

# Install browser binaries (only needed once)
playwright install chromium
```

### 2. Configure Environment Variables

Add these to your `.env` file:

```env
# NetSuite RPA Configuration
NETSUITE_OKTA_URL=https://your-company.okta.com/home/netsuite/xxx/xxx
NETSUITE_RPA_HEADLESS=true          # Set to 'false' for debugging
NETSUITE_USE_RPA_DOWNLOADS=true     # Enable RPA downloads
```

**Important**: Update `NETSUITE_OKTA_URL` with your company's Okta NetSuite SSO URL.

## Usage

### Option 1: Via NetSuiteClient (Recommended)

The RPA downloader is integrated into the existing `NetSuiteClient`. It will automatically use RPA when enabled:

```python
from src.clients.netsuite_client import NetSuiteClient

# Initialize client (RPA enabled by default)
client = NetSuiteClient(use_rpa_for_downloads=True)

# Download files for a bill
files = client.download_invoice_files("26358814")

print(f"Downloaded {len(files)} files:")
for file_path in files:
    print(f"  - {file_path}")
```

### Option 2: Direct RPA Downloader

You can also use the RPA downloader directly:

```python
from src.clients.netsuite_rpa_downloader import NetSuiteRPADownloader

# Initialize downloader
downloader = NetSuiteRPADownloader(headless=False, manual_login=True)

# Download files for a single bill
files = downloader.download_bill_invoices("26358814")

# Or download for multiple bills in one session
bill_ids = ["26358814", "26358815", "26358816"]
results = downloader.download_multiple_bills(bill_ids)
```

### Option 3: Test Script

Use the provided test script:

```bash
# Test connection only
python test_rpa_download.py --test-connection

# Download files for a single bill
python test_rpa_download.py 26358814

# Download files for multiple bills
python test_rpa_download.py 26358814 26358815 26358816

# Run with visible browser (for debugging)
python test_rpa_download.py 26358814 --headless=false

# Test via NetSuiteClient wrapper
python test_rpa_download.py 26358814 --use-client
```

## How It Works

### Authentication Flow

1. **Browser Launch**: Playwright launches a Chromium browser
2. **Navigate to Okta**: Goes to your company's Okta SSO page
3. **Manual Login**: You log in manually (for security)
4. **Auto-redirect**: After login, automatically redirects to NetSuite
5. **Session Reuse**: For batch downloads, login happens once

### Download Process

1. Navigates to the bill page in NetSuite
2. Finds the "Communication" section
3. Locates all attached files
4. Downloads each file
5. Saves files to `data/invoices/{bill_id}/`

### File Organization

Downloaded files are saved in:
```
data/
└── invoices/
    ├── 26358814/
    │   ├── invoice_001.pdf
    │   └── receipt_002.pdf
    ├── 26358815/
    │   └── invoice_003.xlsx
    └── ...
```

## Configuration Options

### Headless Mode

**Headless** (default): Browser runs in background, no window visible
```env
NETSUITE_RPA_HEADLESS=true
```

**Headed**: Browser window visible (useful for debugging)
```env
NETSUITE_RPA_HEADLESS=false
```

### Manual vs Automated Login

**Manual Login** (recommended for security):
- You log in through Okta manually
- Script waits for you to complete login
- More secure, no credentials stored

**Automated Login** (not yet implemented):
- Script logs in automatically
- Would require storing Okta credentials
- Less secure, not recommended

## Integration with Main Workflow

The RPA downloader is automatically used in the main accruals workflow:

```python
# In run_monthly_accruals.py
orchestrator = MonthlyAccrualsOrchestrator()
orchestrator.run_monthly_accruals(spreadsheet_id="YOUR_SHEET_ID")
```

The workflow will:
1. Fetch PO/PR data from Google Sheets
2. Get PO/bill data from NetSuite API
3. **Use RPA to download invoice files** (if enabled)
4. Process invoices with AI
5. Make accrual decisions
6. Update Google Sheets

## Troubleshooting

### Playwright Not Installed

```
Error: Playwright not available
```

**Solution**:
```bash
pip install playwright
playwright install chromium
```

### Login Timeout

```
Error: Login detection timed out
```

**Solution**: You have 5 minutes to log in manually. If you need more time, the timeout can be adjusted in `netsuite_rpa_downloader.py`:

```python
timeout = 300000  # 5 minutes in milliseconds
```

### Files Not Found

```
Warning: No files found in Communication section
```

**Possible causes**:
1. Bill has no attached files
2. Communication section has different structure
3. NetSuite page layout changed

**Solution**: Run with `headless=False` to see what's happening:
```bash
python test_rpa_download.py 26358814 --headless=false
```

### Browser Crashes

**Solution**:
1. Make sure Chromium is installed: `playwright install chromium`
2. Update Playwright: `pip install --upgrade playwright`
3. Check system resources (RAM, CPU)

### Slow Performance

**Tips**:
- Use `download_multiple_bills()` instead of individual downloads
- This reuses the browser session and login
- Much faster for batch operations

## Debugging

### Enable Debug Logging

In your `.env`:
```env
LOG_LEVEL=DEBUG
```

### Run with Visible Browser

```bash
python test_rpa_download.py 26358814 --headless=false
```

This shows you exactly what the browser is doing.

### Check Downloaded Files

Files are saved to:
```
data/invoices/{bill_id}/
```

Check this directory to verify downloads completed.

## Security Notes

1. **No Credentials Stored**: Manual login means your Okta password is never stored in code
2. **Session Timeout**: Browser session is temporary and closed after downloads
3. **Headless Mode**: In production, use headless mode for security
4. **Rate Limiting**: Add delays between downloads if needed to avoid triggering NetSuite rate limits

## Performance

### Single Bill Download
- Login: ~10-30 seconds (manual)
- Page load: ~3-5 seconds
- File download: ~1-3 seconds per file
- **Total**: ~15-40 seconds per bill

### Batch Download (10 bills)
- Login: ~10-30 seconds (once)
- Per bill: ~5-8 seconds
- **Total**: ~60-110 seconds for 10 bills

**Tip**: Always use batch downloads for multiple bills!

## Advanced Usage

### Custom Okta URL

If your Okta URL changes:

```python
downloader = NetSuiteRPADownloader(headless=True, manual_login=True)
downloader.okta_login_url = "https://new-url.okta.com/..."
```

### Custom Download Location

Files are saved to `config.settings.INVOICES_DIR` by default. To change:

1. Update `.env`:
```env
# Add custom path if needed
```

2. Or modify `config/settings.py`:
```python
INVOICES_DIR = Path("/custom/path/invoices")
```

### Session Persistence

For very large batches, you might want to persist the browser session:

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(accept_downloads=True)
    page = context.new_page()

    # Login once
    # ... login code ...

    # Download many bills using same session
    for bill_id in large_list_of_bills:
        # Download files...
        pass

    browser.close()
```

## Fallback to API

If RPA fails, the system can fall back to API downloads:

```python
# Disable RPA
client = NetSuiteClient(use_rpa_for_downloads=False)

# Or in .env
NETSUITE_USE_RPA_DOWNLOADS=false
```

## Future Enhancements

Potential improvements:
1. Automated Okta login (with secure credential storage)
2. Parallel browser sessions for faster batch processing
3. Screenshot capture for debugging
4. Error recovery and retry logic
5. Progress callbacks for long-running downloads

## Support

If you encounter issues:

1. Check logs in `logs/` directory
2. Run test script with visible browser
3. Verify Okta URL is correct
4. Ensure Playwright and Chromium are installed
5. Check NetSuite page structure hasn't changed
