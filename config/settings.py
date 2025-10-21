import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
LOGS_DIR = BASE_DIR / "logs"

# Use Google Drive folder for invoices (configured via .env)
INVOICES_DIR_OVERRIDE = os.getenv("INVOICES_DIR")

if INVOICES_DIR_OVERRIDE:
    INVOICES_DIR = Path(INVOICES_DIR_OVERRIDE)
else:
    # Fallback to local folder if not configured (for testing)
    INVOICES_DIR = BASE_DIR / "data" / "invoices"

# Use Google Drive folder for CSV results (configured via .env)
CSV_RESULTS_DIR_OVERRIDE = os.getenv("CSV_RESULTS_DIR")

if CSV_RESULTS_DIR_OVERRIDE:
    CSV_RESULTS_DIR = Path(CSV_RESULTS_DIR_OVERRIDE)
else:
    # Fallback to local folder if not configured
    CSV_RESULTS_DIR = BASE_DIR

# Create required directories
LOGS_DIR.mkdir(exist_ok=True)

# Only create INVOICES_DIR if it's the local fallback or if specified path doesn't exist yet
if not INVOICES_DIR_OVERRIDE or not INVOICES_DIR.exists():
    INVOICES_DIR.mkdir(parents=True, exist_ok=True)

class NetSuiteConfig:
    ACCOUNT_ID = os.getenv("NETSUITE_ACCOUNT_ID")

    # RPA / Browser Automation settings
    OKTA_URL = os.getenv("NETSUITE_OKTA_URL")  # Okta SSO URL for NetSuite
    RPA_HEADLESS = os.getenv("NETSUITE_RPA_HEADLESS", "true").lower() == "true"

class OpenAIConfig:
    API_KEY = os.getenv("OPENAI_API_KEY")
    MODEL = "gpt-4-vision-preview"
    MAX_TOKENS = 4000

class SnowflakeConfig:
    ACCOUNT = os.getenv("SNOWFLAKE_ACCOUNT")
    USER = os.getenv("SNOWFLAKE_USER")
    PASSWORD = os.getenv("SNOWFLAKE_PASSWORD")
    DATABASE = os.getenv("SNOWFLAKE_DATABASE")
    SCHEMA = os.getenv("SNOWFLAKE_SCHEMA")
    WAREHOUSE = os.getenv("SNOWFLAKE_WAREHOUSE")
    ROLE = os.getenv("SNOWFLAKE_ROLE")

class AppConfig:
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")