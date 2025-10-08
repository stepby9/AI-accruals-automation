# Finance Accruals Automation

Automates the manual monthly accruals process for finance teams by integrating NetSuite, OpenAI, and Google Sheets to analyze thousands of PO lines and determine accrual needs.

## Overview

This system replaces a manual process that involves:
1. Checking thousands of PO lines/PRs each month
2. Manually searching NetSuite for vendor details and bills
3. Opening and reading invoice PDFs to understand services
4. Applying business rules to determine accrual amounts
5. Recording decisions in Google Sheets

## Features

- **Incremental Data Sync**: Only processes new bills and invoices to save ~90% on API costs after first month
- **RPA File Downloads**: Uses browser automation (Playwright) to download invoice files from NetSuite reliably
- **Multi-format Invoice Processing**: Handles PDF, Excel, Word, and image invoices
- **AI-Powered Analysis**: Uses OpenAI GPT-4 Vision to extract invoice data and make accrual decisions
- **Business Rules Engine**: Implements complex accrual logic and GL account exclusions
- **Google Sheets Integration**: Reads PO/PR lists and updates with accrual decisions
- **Comprehensive Logging**: Full audit trail for debugging and compliance

## Architecture

```
Google Sheets (PO/PR list) 
→ NetSuite API (fetch PO/PR/Bill data)
→ Download Invoices
→ OpenAI API (extract invoice details)
→ Snowflake Database (store all data)
→ AI analyze and decide accruals
→ Update Google Sheets with decisions
```

## Setup

### 1. Environment Setup

1. Copy `.env.example` to `.env` and fill in your credentials:
   ```bash
   cp .env.example .env
   ```

2. Configure the following credentials in `.env`:
   - NetSuite account ID and Okta URL (for RPA downloads)
   - OpenAI API key
   - Snowflake database connection
   - Google Service Account JSON file path
   - Invoice storage location (Google Drive path)

### 2. Install Dependencies

```bash
pip install -r requirements.txt

# Install Playwright browser for RPA downloads
playwright install chromium
```

### 3. Google Service Account Setup

1. Create a service account in Google Cloud Console
2. Enable Google Sheets API and Google Drive API
3. Download the service account JSON file
4. Set the path in your `.env` file
5. Share your Google Sheets with the service account email

### 4. Configure Invoice Storage Location

Set the Google Drive path for invoice storage in `.env`:
```env
INVOICES_DIR=G:\.shortcut-targets-by-id\YOUR_ID\FP&A Internal\Automation\Accruals\Bills
```

All downloaded invoices will be saved to this Google Drive folder, organized by bill ID.

### 5. Database Initialization

The system will automatically create required Snowflake tables on first run:
- `bills` - NetSuite bill data
- `invoice_data` - AI-extracted invoice information
- `accrual_decisions` - Monthly accrual decisions
- `sync_tracking` - Incremental sync tracking

## Usage

### Basic Monthly Processing

```bash
python run_monthly_accruals.py YOUR_SPREADSHEET_ID
```

### Advanced Options

```bash
# Use custom worksheet name
python run_monthly_accruals.py YOUR_SPREADSHEET_ID --worksheet "Monthly_POs"

# Force complete data re-sync (expensive!)
python run_monthly_accruals.py YOUR_SPREADSHEET_ID --force-full-sync

# Validate configuration only
python run_monthly_accruals.py --validate-only

# Show processing statistics
python run_monthly_accruals.py --stats
```

## Business Rules

The system implements the following accrual rules:

1. **GL Account Exclusions**: No accruals for accounts 4550, 6080, 6090, 6092
2. **Minimum Threshold**: No accruals if remaining balance < $5,000 USD
3. **No Negative Accruals**: For prepaid services
4. **Monthly Calculation**: Estimates monthly accrual amounts
5. **Previous Payments**: Considers if we already paid for previous months

## Components

### Core Modules

- `src/clients/netsuite_client.py` - NetSuite API integration
- `src/clients/netsuite_rpa_downloader.py` - RPA browser automation for file downloads
- `src/clients/sheets_client.py` - Google Sheets integration
- `src/processors/invoice_processor.py` - AI-powered invoice processing
- `src/engines/accrual_engine.py` - Business rules and AI decision engine
- `src/utils/data_sync.py` - Incremental data synchronization
- `src/database/models.py` - Snowflake database models

### Main Orchestrator

- `run_monthly_accruals.py` - Main execution script

### Test Scripts

- `test_invoices.py` - Test invoice processing with OpenAI
- `test_rpa_download.py` - Test RPA file downloads from NetSuite

### Documentation

- `README.md` - Main project documentation
- `RPA_SETUP.md` - Detailed RPA setup and troubleshooting guide

## Logging

Logs are written to:
- Console (INFO level)
- Files in `logs/` directory (configurable level)

Log files are rotated daily with format: `{component}_{YYYYMMDD}.log`

## Cost Optimization

The system uses incremental processing to minimize API costs:

1. **NetSuite**: Only fetches new bills since last sync
2. **OpenAI**: Only processes new invoices, reuses existing analysis
3. **Database**: Tracks processing status to avoid duplicates

Expected cost savings: ~90% after first month of operation.

## Error Handling

The system includes comprehensive error handling:
- Individual PO line failures don't stop batch processing
- API failures are logged and retried where appropriate
- Database transactions ensure data consistency
- Backup sheets are created before making changes

## Monitoring

Use these commands to monitor the system:

```bash
# Check processing statistics
python run_monthly_accruals.py --stats

# Validate configuration
python run_monthly_accruals.py --validate-only

# View logs
tail -f logs/run_monthly_accruals_$(date +%Y%m%d).log
```

## Troubleshooting

### Common Issues

1. **NetSuite Authentication**: Ensure OAuth credentials are correct and token hasn't expired
2. **OpenAI Rate Limits**: System includes built-in retry logic for rate limits
3. **Google Sheets Permissions**: Service account must have edit access to spreadsheets
4. **Snowflake Connection**: Check warehouse is running and credentials are valid

### Debug Mode

Set `LOG_LEVEL=DEBUG` in `.env` for detailed logging.

## Development

### Project Structure

```
├── src/
│   ├── clients/          # External API clients
│   ├── processors/       # Document processing
│   ├── engines/          # Business logic
│   ├── database/         # Data models
│   └── utils/           # Utilities and sync logic
├── config/              # Configuration
├── logs/               # Log files
├── data/               # Data storage
└── tests/              # Test files
```

### Adding New Features

1. Follow the existing patterns for error handling and logging
2. Add new configuration options to `config/settings.py`
3. Update the database models if schema changes are needed
4. Add appropriate tests

## Security

- Never commit `.env` file or credentials to git
- Use environment variables for all sensitive data
- Service account has minimal required permissions
- API keys are validated on startup

## License

Internal use only.