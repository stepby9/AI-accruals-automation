# Installation Guide

Quick setup guide for the Finance Accruals Automation project.

## Prerequisites

- Python 3.8 or higher
- pip (Python package installer)
- Git (optional, for version control)

## Step-by-Step Installation

### 1. Clone or Download the Project

```bash
cd C:\Users\ssuprun\Desktop\script_testing\accruals
```

### 2. Create Virtual Environment (Recommended)

```bash
# Create virtual environment
python -m venv venv

# Activate on Windows
venv\Scripts\activate

# Activate on Mac/Linux
source venv/bin/activate
```

### 3. Install Python Dependencies

```bash
# Install all required packages
pip install -r requirements.txt
```

### 4. Install Playwright Browser

```bash
# Install Playwright browser for RPA downloads
playwright install chromium
```

This downloads the Chromium browser (~150MB) needed for browser automation.

### 5. Configure Environment Variables

```bash
# Copy the example file
copy .env.example .env

# Edit .env with your credentials
notepad .env
```

**Required configurations:**

```env
# NetSuite API (for data fetching)
NETSUITE_ACCOUNT_ID=3339715
NETSUITE_TOKEN_ID=your_token_id
NETSUITE_TOKEN_SECRET=your_token_secret
NETSUITE_CONSUMER_KEY=your_consumer_key
NETSUITE_CONSUMER_SECRET=your_consumer_secret

# NetSuite RPA (for file downloads)
NETSUITE_OKTA_URL=https://purestorage.okta.com/home/netsuite/0oa17egaalm4fLsk81d8/82
NETSUITE_RPA_HEADLESS=true
NETSUITE_USE_RPA_DOWNLOADS=true

# OpenAI (for invoice processing)
OPENAI_API_KEY=sk-...

# Snowflake (for data storage)
SNOWFLAKE_ACCOUNT=your_account
SNOWFLAKE_USER=your_user
SNOWFLAKE_PASSWORD=your_password
SNOWFLAKE_DATABASE=your_database
SNOWFLAKE_SCHEMA=your_schema
SNOWFLAKE_WAREHOUSE=your_warehouse

# Google Sheets (for input/output)
GOOGLE_SERVICE_ACCOUNT_KEY=path/to/service-account.json
GOOGLE_DRIVE_FOLDER_ID=your_folder_id
```

### 6. Verify Installation

Test each component individually:

#### Test OpenAI Connection
```bash
python test_invoices.py
```

#### Test NetSuite RPA Downloads
```bash
python test_rpa_download.py --test-connection
```

#### Test Full Workflow (with a small dataset)
```bash
python run_monthly_accruals.py YOUR_SPREADSHEET_ID --validate-only
```

## Common Issues

### Issue: `playwright` command not found

**Solution:**
```bash
pip install playwright
playwright install chromium
```

### Issue: OpenAI API errors

**Solution:** Verify your API key is correct:
```bash
# Test directly
python -c "import openai; print('OpenAI installed')"
```

### Issue: Snowflake connection fails

**Solution:** Check your credentials and network:
```bash
# Test connection
python -c "import snowflake.connector; print('Snowflake connector installed')"
```

### Issue: Google Sheets permission denied

**Solution:**
1. Make sure service account JSON file path is correct
2. Share the Google Sheet with the service account email
3. Grant "Editor" permissions

## Directory Structure After Installation

```
accruals/
├── venv/                          # Virtual environment (if created)
├── src/                           # Source code
│   ├── clients/                   # API clients
│   ├── processors/                # Document processors
│   ├── engines/                   # Business logic
│   ├── database/                  # Database models
│   └── utils/                     # Utilities
├── config/                        # Configuration
├── logs/                          # Log files (auto-created)
├── data/                          # Data storage (auto-created)
│   └── invoices/                  # Downloaded invoices
├── test_invoices/                 # Test invoice files
├── .env                           # Your credentials (DO NOT COMMIT)
├── .env.example                   # Example credentials template
├── requirements.txt               # Python dependencies
├── README.md                      # Main documentation
├── RPA_SETUP.md                   # RPA detailed guide
├── INSTALL.md                     # This file
└── run_monthly_accruals.py       # Main script
```

## Next Steps

1. **Read the documentation:**
   - [README.md](README.md) - Project overview and usage
   - [RPA_SETUP.md](RPA_SETUP.md) - RPA file download setup

2. **Test with sample data:**
   ```bash
   # Test invoice processing
   python test_invoices.py

   # Test RPA download with a single bill
   python test_rpa_download.py 26358814
   ```

3. **Run your first accruals analysis:**
   ```bash
   python run_monthly_accruals.py YOUR_SPREADSHEET_ID
   ```

## Getting Help

- Check [README.md](README.md) for usage instructions
- Check [RPA_SETUP.md](RPA_SETUP.md) for RPA troubleshooting
- Review logs in `logs/` directory for errors
- Run with `LOG_LEVEL=DEBUG` for detailed logging

## Uninstallation

To remove the project:

```bash
# Deactivate virtual environment
deactivate

# Delete the project folder
cd ..
rmdir /s accruals
```

To keep the project but clean up:

```bash
# Remove downloaded files
rmdir /s data\invoices

# Remove logs
rmdir /s logs

# Remove virtual environment
rmdir /s venv
```
