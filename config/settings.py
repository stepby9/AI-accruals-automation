import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
LOGS_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"
INVOICES_DIR = DATA_DIR / "invoices"

LOGS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
INVOICES_DIR.mkdir(exist_ok=True)

class NetSuiteConfig:
    ACCOUNT_ID = os.getenv("NETSUITE_ACCOUNT_ID")
    TOKEN_ID = os.getenv("NETSUITE_TOKEN_ID")
    TOKEN_SECRET = os.getenv("NETSUITE_TOKEN_SECRET")
    CONSUMER_KEY = os.getenv("NETSUITE_CONSUMER_KEY")
    CONSUMER_SECRET = os.getenv("NETSUITE_CONSUMER_SECRET")

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

class GoogleConfig:
    SERVICE_ACCOUNT_KEY = os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY")
    DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

class AppConfig:
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    MAX_WORKERS = int(os.getenv("MAX_WORKERS", "4"))
    BATCH_SIZE = int(os.getenv("BATCH_SIZE", "50"))
    MIN_ACCRUAL_AMOUNT_USD = float(os.getenv("MIN_ACCRUAL_AMOUNT_USD", "5000"))
    
    EXCLUDED_GL_ACCOUNTS = ["4550", "6080", "6090", "6092"]