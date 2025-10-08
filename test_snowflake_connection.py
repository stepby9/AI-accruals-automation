#!/usr/bin/env python3
"""
Test Snowflake Connection

Quick script to verify Snowflake credentials are working
"""

import sys
import os

# Add src to Python path
sys.path.append(os.path.join(os.path.dirname(__file__)))
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.clients.snowflake_data_client import SnowflakeDataClient

print("=" * 60)
print("Testing Snowflake Connection")
print("=" * 60)

try:
    print("\n🔄 Initializing Snowflake client...")
    client = SnowflakeDataClient()
    print("✅ Client initialized")

    print("\n🔍 Testing connection...")
    success = client.test_connection()

    if success:
        print("\n✅ Connection successful!")

        # Try to query the table
        print("\n📋 Querying ACCRUALS_AUTOMATION_EXTRACTED_INVOICES table...")
        processed = client.get_processed_invoices()
        print(f"✅ Found {len(processed)} existing invoice records in Snowflake")

        if processed:
            print("\nSample records:")
            for i, (bill_id, file_name) in enumerate(list(processed)[:5]):
                print(f"  {i+1}. Bill: {bill_id}, File: {file_name}")
        else:
            print("  (Table is empty - ready for first upload)")

        print("\n" + "=" * 60)
        print("🎉 Snowflake is ready to use!")
        print("=" * 60)
    else:
        print("\n❌ Connection test failed")
        print("Check the logs for details")

except Exception as e:
    print(f"\n❌ Error: {str(e)}")
    print("\nPlease verify:")
    print("  1. Snowflake credentials in .env file")
    print("  2. Network access to purestorageit.snowflakecomputing.com")
    print("  3. Service account has access to PSEDM_FINANCE_PROD database")
    print("  4. Role FPAGTM_ANALYST_PROD has permissions")
