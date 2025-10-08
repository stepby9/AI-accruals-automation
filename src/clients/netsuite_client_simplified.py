"""
Simplified NetSuite Client - RPA downloads only
Data comes from Snowflake views instead of NetSuite API
"""

from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime
import os

from config.settings import NetSuiteConfig
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

# Import RPA downloader for file downloads
try:
    from src.clients.netsuite_rpa_downloader import NetSuiteRPADownloader
    RPA_AVAILABLE = True
except ImportError:
    RPA_AVAILABLE = False
    logger.warning("Playwright not available - RPA downloads will not work. Install with: pip install playwright && playwright install")


@dataclass
class Bill:
    """Bill data structure - populated from Snowflake views"""
    bill_id: str
    po_id: str
    vendor_name: str
    amount: float
    currency: str
    posting_period: str
    payment_status: str
    created_date: datetime
    due_date: Optional[datetime]


class NetSuiteClient:
    """
    Simplified NetSuite client that only handles RPA file downloads.
    All data queries come from Snowflake views instead of NetSuite API.
    """

    def __init__(self):
        """Initialize NetSuite client with RPA downloader"""
        self.account_id = NetSuiteConfig.ACCOUNT_ID

        if not self.account_id:
            raise ValueError("NETSUITE_ACCOUNT_ID not configured in .env")

        # Initialize RPA downloader
        try:
            headless = os.getenv("NETSUITE_RPA_HEADLESS", "false").lower() == "true"
            self.rpa_downloader = NetSuiteRPADownloader(headless=headless, manual_login=True)
            logger.info(f"NetSuite RPA client initialized (headless={headless})")
        except Exception as e:
            logger.error(f"Failed to initialize RPA downloader: {e}")
            raise

    def download_invoice_files(self, bill_id: str, skip_if_exists: bool = True) -> List[str]:
        """
        Download invoice files for a bill using RPA

        Args:
            bill_id: NetSuite bill ID
            skip_if_exists: If True, skip download if files already exist

        Returns:
            List of file paths to downloaded files
        """
        try:
            logger.info(f"Downloading files for bill {bill_id} using RPA")
            return self.rpa_downloader.download_bill_invoices(bill_id, skip_if_exists=skip_if_exists)

        except Exception as e:
            logger.error(f"Error downloading invoice files for bill {bill_id}: {str(e)}")
            return []

    def download_multiple_bills(self, bill_ids: List[str], skip_if_exists: bool = True) -> dict:
        """
        Download invoice files for multiple bills in a single browser session

        Args:
            bill_ids: List of NetSuite bill IDs
            skip_if_exists: If True, skip bills that already have files

        Returns:
            Dictionary mapping bill_id to list of downloaded file paths
        """
        try:
            logger.info(f"Downloading files for {len(bill_ids)} bills using RPA")
            return self.rpa_downloader.download_multiple_bills(bill_ids, skip_if_exists=skip_if_exists)

        except Exception as e:
            logger.error(f"Error in batch download: {str(e)}")
            return {}

    def test_connection(self) -> bool:
        """
        Test RPA connection to NetSuite

        Returns:
            True if connection successful, False otherwise
        """
        try:
            return self.rpa_downloader.test_connection()
        except Exception as e:
            logger.error(f"Connection test failed: {str(e)}")
            return False
