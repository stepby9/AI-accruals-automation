#!/usr/bin/env python3
"""
Upload Accrual Analysis Results to Snowflake

Reads accrual_analysis_results.csv and uploads to Snowflake table
ACCRUALS_AUTOMATION_ANALYSIS_RESULTS

Usage:
    python upload_accrual_analysis_to_snowflake.py
"""

import sys
import os
from pathlib import Path

# Add src to Python path
sys.path.append(os.path.join(os.path.dirname(__file__)))
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from config.settings import CSV_RESULTS_DIR
from src.clients.snowflake_data_client import SnowflakeDataClient
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


def main():
    """Upload accrual analysis results CSV to Snowflake"""
    try:
        print("=" * 80)
        print("📤 Snowflake Upload Tool - Accrual Analysis Results")
        print("=" * 80)

        # Get CSV file path
        csv_path = CSV_RESULTS_DIR / "accrual_analysis_results.csv"

        if not csv_path.exists():
            print(f"\n❌ CSV file not found: {csv_path}")
            print(f"   Run the accrual analysis first: python run_accrual_analysis.py")
            return

        print(f"\n📄 CSV file: {csv_path}")

        # Count rows in CSV (excluding header and empty lines)
        import csv
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            rows = [row for row in reader if any(row.values())]  # Filter out empty rows
            row_count = len(rows)

        if row_count == 0:
            print(f"\n⚠️  CSV file is empty (no data rows)")
            print(f"   Nothing to upload")
            return

        print(f"   Rows to upload: {row_count}")

        # Confirm upload
        print(f"\n🔍 Target Snowflake table:")
        print(f"   PSEDM_FINANCE_PROD.EDM_GTM_FPA.ACCRUALS_AUTOMATION_ANALYSIS_RESULTS")

        response = input(f"\n📤 Upload {row_count} rows to Snowflake? (yes/no): ").strip().lower()

        if response not in ['yes', 'y']:
            print("\n❌ Upload cancelled")
            return

        # Initialize Snowflake client
        print("\n🔄 Connecting to Snowflake...")
        snowflake_client = SnowflakeDataClient()

        # Upload to Snowflake
        print(f"📤 Uploading {csv_path.name}...")
        success = snowflake_client.upload_accrual_analysis_to_snowflake(str(csv_path))

        if success:
            print("\n" + "=" * 80)
            print("✅ SUCCESS!")
            print("=" * 80)
            print(f"   Uploaded {row_count} rows to Snowflake")
            print(f"   Table: ACCRUALS_AUTOMATION_ANALYSIS_RESULTS")
            print("=" * 80)
            logger.info(f"Successfully uploaded {row_count} accrual analysis results to Snowflake")
        else:
            print("\n" + "=" * 80)
            print("❌ UPLOAD FAILED")
            print("=" * 80)
            print("   Check the logs for details")
            logger.error("Failed to upload accrual analysis results to Snowflake")

    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        logger.error(f"Error in upload script: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
