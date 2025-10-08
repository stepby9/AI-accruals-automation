#!/usr/bin/env python3
"""
Upload Invoice Extraction Results to Snowflake

This script uploads the CSV file with invoice extraction results to Snowflake.
Run this AFTER reviewing the CSV file to ensure all extractions are correct.

Usage:
    python upload_to_snowflake.py
"""

import sys
import os
from pathlib import Path

# Add src to Python path
sys.path.append(os.path.join(os.path.dirname(__file__)))
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.utils.logger import setup_logger
from config.settings import CSV_RESULTS_DIR

logger = setup_logger(__name__)


def upload_csv_to_snowflake():
    """Upload invoice extraction results CSV to Snowflake"""

    csv_path = CSV_RESULTS_DIR / "invoice_extraction_results.csv"

    print("=" * 60)
    print("📤 Snowflake Upload Tool")
    print("=" * 60)

    # Check if CSV exists
    if not csv_path.exists():
        print(f"\n❌ CSV file not found: {csv_path}")
        print(f"   Please run test_invoices.py first to generate results")
        logger.error(f"CSV file not found: {csv_path}")
        return

    print(f"\n📄 CSV file: {csv_path}")

    # Count rows in CSV
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            row_count = sum(1 for line in f) - 1  # Subtract header
        print(f"   Rows to upload: {row_count}")
    except Exception as e:
        print(f"❌ Error reading CSV: {str(e)}")
        return

    # Confirm upload
    print("\n" + "=" * 60)
    response = input(f"📋 Upload {row_count} rows to Snowflake? (yes/no): ").strip().lower()

    if response not in ['yes', 'y']:
        print("\n❌ Upload cancelled")
        logger.info("Upload cancelled by user")
        return

    # Connect to Snowflake and upload
    print("\n🔄 Connecting to Snowflake...")
    logger.info("Uploading CSV to Snowflake")

    try:
        from src.clients.snowflake_data_client import SnowflakeDataClient

        snowflake_client = SnowflakeDataClient()
        print("✅ Connected to Snowflake")

        print(f"\n📤 Uploading {csv_path.name}...")
        success = snowflake_client.upload_csv_to_snowflake(str(csv_path.absolute()))

        if success:
            print(f"\n✅ Successfully uploaded {row_count} rows to Snowflake!")
            print(f"   Table: PSEDM_FINANCE_PROD.EDM_GTM_FPA.ACCRUALS_AUTOMATION_EXTRACTED_INVOICES")
            logger.info(f"Successfully uploaded {row_count} rows to Snowflake")

            print("\n" + "=" * 60)
            print("🎉 Upload complete!")
            print("=" * 60)
        else:
            print(f"\n❌ Upload failed - check logs for details")
            logger.error("Upload to Snowflake failed")

    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        logger.error(f"Error uploading to Snowflake: {str(e)}")
        print("\nPlease check:")
        print("  1. Snowflake credentials in .env file")
        print("  2. Network connection")
        print("  3. Table permissions")
        print("  4. Log file for detailed error")


if __name__ == "__main__":
    upload_csv_to_snowflake()
