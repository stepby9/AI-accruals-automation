"""
NetSuite RPA File Downloader using Playwright

This module uses browser automation to download invoice files from NetSuite
because the API approach has limitations. It handles Okta authentication
and navigates to bill pages to download attached files.
"""

from playwright.sync_api import sync_playwright, Page, Download
import time
import os
from pathlib import Path
from typing import List, Optional, Dict
from dataclasses import dataclass

from config.settings import NetSuiteConfig, INVOICES_DIR
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class DownloadedFile:
    """Represents a file downloaded from NetSuite"""
    file_path: str
    original_filename: str
    bill_id: str
    downloaded_at: str


class NetSuiteRPADownloader:
    """Downloads invoice files from NetSuite using browser automation"""

    def __init__(self, headless: bool = True, manual_login: bool = True):
        """
        Initialize the RPA downloader

        Args:
            headless: Whether to run browser in headless mode (False for debugging)
            manual_login: Whether to wait for manual Okta login (True for security)
        """
        self.headless = headless
        self.manual_login = manual_login
        self.base_url = f"https://{NetSuiteConfig.ACCOUNT_ID}.app.netsuite.com" if NetSuiteConfig.ACCOUNT_ID else None

        # Okta login URL - configure this in your .env
        self.okta_login_url = os.getenv(
            "NETSUITE_OKTA_URL",
            "https://purestorage.okta.com/home/netsuite/0oa17egaalm4fLsk81d8/82"
        )

        logger.info(f"NetSuite RPA Downloader initialized (headless={headless}, manual_login={manual_login})")

    def download_bill_invoices(self, bill_id: str, skip_if_exists: bool = True) -> List[str]:
        """
        Download all invoice files attached to a NetSuite bill

        Args:
            bill_id: The NetSuite bill ID
            skip_if_exists: If True, skip download if bill folder already exists with files

        Returns:
            List of file paths to downloaded files
        """
        try:
            # Check if bill folder already exists with files
            if skip_if_exists:
                bill_dir = INVOICES_DIR / bill_id
                if bill_dir.exists() and any(bill_dir.iterdir()):
                    logger.info(f"✓ Invoices for bill {bill_id} have already been downloaded")
                    logger.info(f"  Folder: {bill_dir}")
                    # Return existing files
                    existing_files = [str(f) for f in bill_dir.iterdir() if f.is_file()]
                    logger.info(f"  Found {len(existing_files)} existing file(s)")
                    return existing_files

            logger.info(f"Starting download process for bill {bill_id}")

            with sync_playwright() as p:
                # Launch browser
                browser = p.chromium.launch(headless=self.headless)
                context = browser.new_context(accept_downloads=True)
                page = context.new_page()

                # Login to NetSuite via Okta
                if not self._login_to_netsuite(page):
                    logger.error("Failed to login to NetSuite")
                    browser.close()
                    return []

                # Navigate to bill page
                bill_url = self._get_bill_url(bill_id)
                logger.info(f"Navigating to bill: {bill_url}")

                try:
                    page.goto(bill_url, wait_until="domcontentloaded", timeout=60000)
                except Exception as e:
                    logger.warning(f"Navigation issue (this is often normal with NetSuite): {e}")
                    logger.info("Attempting to continue anyway...")

                # Wait for page to stabilize
                time.sleep(2)

                # Wait for page to fully load
                page.wait_for_load_state("networkidle")

                # Download files from Communication section
                downloaded_files = self._download_files_from_page(page, bill_id)

                # Print summary
                if downloaded_files:
                    logger.info("=" * 60)
                    logger.info(f"✓ Successfully downloaded {len(downloaded_files)} file(s) to:")
                    logger.info(f"  {INVOICES_DIR / bill_id}")
                    logger.info("=" * 60)
                    for filepath in downloaded_files:
                        logger.info(f"  - {os.path.basename(filepath)}")
                else:
                    logger.warning("✗ No files were downloaded successfully")

                # Wait for user before closing browser
                logger.info("\nBrowser will stay open so you can inspect...")
                logger.info("Press ENTER when you want to close the browser...")
                input()

                browser.close()
                return downloaded_files

        except Exception as e:
            logger.error(f"Error downloading files for bill {bill_id}: {str(e)}")
            return []

    def download_multiple_bills(self, bill_ids: List[str], skip_if_exists: bool = True) -> Dict[str, List[str]]:
        """
        Download invoice files for multiple bills in a single browser session

        Args:
            bill_ids: List of NetSuite bill IDs
            skip_if_exists: If True, skip bills that already have downloaded files

        Returns:
            Dictionary mapping bill_id to list of downloaded file paths
        """
        results = {}
        bills_to_download = []
        skipped_bills = []

        try:
            logger.info(f"Starting batch download for {len(bill_ids)} bills")

            # Check which bills already have files
            if skip_if_exists:
                for bill_id in bill_ids:
                    bill_dir = INVOICES_DIR / bill_id
                    if bill_dir.exists() and any(bill_dir.iterdir()):
                        logger.info(f"✓ Invoices for bill {bill_id} already downloaded - skipping")
                        existing_files = [str(f) for f in bill_dir.iterdir() if f.is_file()]
                        results[bill_id] = existing_files
                        skipped_bills.append(bill_id)
                    else:
                        bills_to_download.append(bill_id)
            else:
                bills_to_download = bill_ids

            if not bills_to_download:
                logger.info("All bills already have downloaded files. No downloads needed.")
                return results

            logger.info(f"Downloading {len(bills_to_download)} new bills (skipped {len(skipped_bills)})")

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                context = browser.new_context(accept_downloads=True)
                page = context.new_page()

                # Login once for all bills
                if not self._login_to_netsuite(page):
                    logger.error("Failed to login to NetSuite")
                    browser.close()
                    return results

                # Download files for each bill that needs downloading
                for bill_id in bills_to_download:
                    try:
                        bill_url = self._get_bill_url(bill_id)
                        logger.info(f"Processing bill {bill_id}: {bill_url}")

                        page.goto(bill_url, wait_until="domcontentloaded", timeout=60000)
                        time.sleep(2)
                        page.wait_for_load_state("networkidle", timeout=30000)

                        downloaded_files = self._download_files_from_page(page, bill_id)
                        results[bill_id] = downloaded_files

                        logger.info(f"Downloaded {len(downloaded_files)} files for bill {bill_id}")

                    except Exception as e:
                        logger.error(f"Error processing bill {bill_id}: {str(e)}")
                        results[bill_id] = []
                        continue

                # Print summary
                total_files = sum(len(files) for files in results.values())
                new_downloads = sum(len(files) for bill_id, files in results.items() if bill_id in bills_to_download)
                logger.info("=" * 60)
                logger.info(f"Batch download completed:")
                logger.info(f"  Total bills: {len(bill_ids)}")
                logger.info(f"  Already downloaded (skipped): {len(skipped_bills)}")
                logger.info(f"  Newly downloaded: {len(bills_to_download)}")
                logger.info(f"  Total files: {total_files}")
                logger.info(f"  New files downloaded: {new_downloads}")
                logger.info("=" * 60)

                for bill_id, files in results.items():
                    status = "✓ Skipped" if bill_id in skipped_bills else "✓ Downloaded"
                    logger.info(f"\n{status} - Bill {bill_id}: {len(files)} file(s)")
                    for file_path in files:
                        logger.info(f"  - {os.path.basename(file_path)}")

                # Wait for user before closing browser
                logger.info("\nBrowser will stay open so you can inspect...")
                logger.info("Press ENTER when you want to close the browser...")
                input()

                browser.close()

            return results

        except Exception as e:
            logger.error(f"Error in batch download: {str(e)}")
            return results

    def _login_to_netsuite(self, page: Page) -> bool:
        """
        Handle NetSuite login via Okta

        Args:
            page: Playwright page object

        Returns:
            True if login successful, False otherwise
        """
        try:
            logger.info("Navigating to Okta login page")
            page.goto(self.okta_login_url)

            if self.manual_login:
                # Manual login mode - wait for user
                logger.info("=" * 60)
                logger.info("MANUAL LOGIN REQUIRED")
                logger.info("=" * 60)
                logger.info("Please log in through Okta in the browser window.")
                logger.info("After logging in, you'll be redirected to NetSuite.")
                logger.info("Press ENTER in this terminal once you're logged in and ready to proceed...")
                logger.info("=" * 60)

                # Wait for user to press Enter
                input()

                logger.info("Proceeding with automation...")
                time.sleep(3)  # Give NetSuite time to fully load

            else:
                # Automated login mode (requires credentials in env vars)
                # TODO: Implement automated Okta login if needed
                logger.warning("Automated login not yet implemented. Use manual_login=True")
                return False

            return True

        except Exception as e:
            logger.error(f"Error during login: {str(e)}")
            return False

    def _get_bill_url(self, bill_id: str) -> str:
        """Construct the NetSuite bill URL"""
        return f"{self.base_url}/app/accounting/transactions/vendbill.nl?whence=&id={bill_id}"

    def _download_files_from_page(self, page: Page, bill_id: str) -> List[str]:
        """
        Download all files from the Communication section of a bill page

        Args:
            page: Playwright page object
            bill_id: NetSuite bill ID

        Returns:
            List of downloaded file paths
        """
        downloaded_files = []

        try:
            # Navigate to Communication section
            if not self._navigate_to_communication_section(page):
                logger.warning(f"Could not access Communication section for bill {bill_id}")
                return []

            # Find all file download links
            file_selector = 'a[href*="/core/media/media.nl"]'

            try:
                file_elements = page.locator(file_selector).all()

                if not file_elements:
                    logger.info(f"No files found in Communication section for bill {bill_id}")
                    return []

                logger.info(f"Found {len(file_elements)} file(s) to download for bill {bill_id}")

                # Download each file
                for i, element in enumerate(file_elements):
                    try:
                        text = element.inner_text() or f"file_{i+1}"
                        href = element.get_attribute('href') or ''

                        logger.info(f"[{i+1}/{len(file_elements)}] Downloading: {text} | Link: {href[:80]}...")

                        # Trigger download
                        with page.expect_download(timeout=30000) as download_info:
                            element.click()

                        download = download_info.value

                        # Save the file
                        saved_path = self._save_download(download, bill_id)
                        if saved_path:
                            downloaded_files.append(saved_path)
                            filename = os.path.basename(saved_path)
                            logger.info(f"    ✓ Saved as: {filename}")

                        time.sleep(1)  # Small delay between downloads

                    except Exception as e:
                        logger.error(f"    ✗ Error downloading file {i+1}: {str(e)}")
                        continue

            except Exception as e:
                logger.error(f"Error finding files for bill {bill_id}: {str(e)}")

            return downloaded_files

        except Exception as e:
            logger.error(f"Error downloading files from page for bill {bill_id}: {str(e)}")
            return []

    def _navigate_to_communication_section(self, page: Page) -> bool:
        """
        Navigate to the Communication section of a NetSuite bill page

        Args:
            page: Playwright page object

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("Looking for Communication section...")

            # Try different selectors to find Communication section
            communication_selectors = [
                'a:has-text("Communication")',
                'span:has-text("Communication")',
                'div:has-text("Communication")',
                '[id*="communication"]',
                '[class*="communication"]',
                'a[href*="communication"]',
            ]

            clicked = False
            for selector in communication_selectors:
                try:
                    element = page.locator(selector).first
                    if element.is_visible():
                        logger.info(f"Found Communication section with selector: {selector}")
                        element.click()
                        clicked = True
                        time.sleep(1)  # Brief wait for content to appear
                        logger.info("Clicked Communication section")
                        return True
                except:
                    continue

            if not clicked:
                logger.warning("Could not automatically click Communication section.")
                logger.info("Please click it manually, then press ENTER to continue...")
                input()

            return True

        except Exception as e:
            logger.error(f"Error navigating to Communication section: {str(e)}")
            return False

    def _save_download(self, download: Download, bill_id: str) -> Optional[str]:
        """
        Save a downloaded file to the invoices directory

        Args:
            download: Playwright Download object
            bill_id: NetSuite bill ID

        Returns:
            Path to saved file, or None if failed
        """
        try:
            # Create bill-specific directory
            bill_dir = INVOICES_DIR / bill_id
            bill_dir.mkdir(exist_ok=True, parents=True)

            # Get original filename
            original_filename = download.suggested_filename

            # Save file
            file_path = bill_dir / original_filename
            download.save_as(str(file_path))

            logger.debug(f"Saved file to: {file_path}")
            return str(file_path)

        except Exception as e:
            logger.error(f"Error saving download for bill {bill_id}: {str(e)}")
            return None

    def test_connection(self) -> bool:
        """
        Test the RPA connection to NetSuite

        Returns:
            True if connection successful, False otherwise
        """
        try:
            logger.info("Testing NetSuite RPA connection...")

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                context = browser.new_context()
                page = context.new_page()

                success = self._login_to_netsuite(page)

                browser.close()

                if success:
                    logger.info("✓ NetSuite RPA connection test successful")
                else:
                    logger.error("✗ NetSuite RPA connection test failed")

                return success

        except Exception as e:
            logger.error(f"Error testing connection: {str(e)}")
            return False


# Convenience function for quick testing
def quick_download_test(bill_id: str, headless: bool = False):
    """
    Quick test function to download files from a single bill

    Args:
        bill_id: NetSuite bill ID
        headless: Whether to run browser in headless mode
    """
    downloader = NetSuiteRPADownloader(headless=headless, manual_login=True)
    files = downloader.download_bill_invoices(bill_id)

    print(f"\n{'='*60}")
    print(f"Downloaded {len(files)} files:")
    for file_path in files:
        print(f"  - {file_path}")
    print(f"{'='*60}\n")

    return files
