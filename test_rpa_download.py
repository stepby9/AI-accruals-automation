#!/usr/bin/env python3
"""
Test script for NetSuite RPA downloader

Usage:
    python test_rpa_download.py BILL_ID                    # Download files for a single bill
    python test_rpa_download.py BILL_ID1 BILL_ID2 ...     # Download files for multiple bills
    python test_rpa_download.py --test-connection          # Test connection only
"""

import sys
import os
from pathlib import Path

# Add src to Python path
sys.path.append(os.path.join(os.path.dirname(__file__)))
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))


def test_single_bill(bill_id: str, headless: bool = False):
    """Test downloading files for a single bill"""
    from src.clients.netsuite_rpa_downloader import NetSuiteRPADownloader

    print(f"\n{'='*60}")
    print(f"Testing RPA download for bill: {bill_id}")
    print(f"{'='*60}\n")

    downloader = NetSuiteRPADownloader(headless=headless, manual_login=True)
    files = downloader.download_bill_invoices(bill_id)

    print(f"\n{'='*60}")
    print(f"✓ Downloaded {len(files)} file(s):")
    print(f"{'='*60}")
    for file_path in files:
        print(f"  - {file_path}")
    print(f"{'='*60}\n")

    return files


def test_multiple_bills(bill_ids: list, headless: bool = False):
    """Test downloading files for multiple bills"""
    from src.clients.netsuite_rpa_downloader import NetSuiteRPADownloader

    print(f"\n{'='*60}")
    print(f"Testing RPA download for {len(bill_ids)} bills")
    print(f"{'='*60}\n")

    downloader = NetSuiteRPADownloader(headless=headless, manual_login=True)
    results = downloader.download_multiple_bills(bill_ids)

    print(f"\n{'='*60}")
    print(f"Download Results:")
    print(f"{'='*60}")

    total_files = 0
    for bill_id, files in results.items():
        print(f"\nBill {bill_id}: {len(files)} file(s)")
        for file_path in files:
            print(f"  - {os.path.basename(file_path)}")
        total_files += len(files)

    print(f"\n{'='*60}")
    print(f"✓ Total: {total_files} files downloaded from {len(bill_ids)} bills")
    print(f"{'='*60}\n")

    return results


def test_connection(headless: bool = False):
    """Test connection to NetSuite"""
    from src.clients.netsuite_rpa_downloader import NetSuiteRPADownloader

    print(f"\n{'='*60}")
    print(f"Testing NetSuite RPA Connection")
    print(f"{'='*60}\n")

    downloader = NetSuiteRPADownloader(headless=headless, manual_login=True)
    success = downloader.test_connection()

    if success:
        print("\n✓ Connection test successful!")
    else:
        print("\n✗ Connection test failed!")

    return success


def test_with_netsuite_client(bill_id: str):
    """Test using the NetSuiteClient wrapper"""
    from src.clients.netsuite_client import NetSuiteClient

    print(f"\n{'='*60}")
    print(f"Testing via NetSuiteClient for bill: {bill_id}")
    print(f"{'='*60}\n")

    # Initialize with RPA enabled
    client = NetSuiteClient(use_rpa_for_downloads=True)
    files = client.download_invoice_files(bill_id)

    print(f"\n{'='*60}")
    print(f"✓ Downloaded {len(files)} file(s) via NetSuiteClient:")
    print(f"{'='*60}")
    for file_path in files:
        print(f"  - {file_path}")
    print(f"{'='*60}\n")

    return files


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Test NetSuite RPA file downloader")
    parser.add_argument("bill_ids", nargs="*", help="NetSuite bill IDs to download")
    parser.add_argument("--test-connection", action="store_true", help="Test connection only")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--use-client", action="store_true", help="Test via NetSuiteClient wrapper")

    args = parser.parse_args()

    try:
        # Test connection
        if args.test_connection:
            test_connection(headless=args.headless)
            return

        # Validate bill IDs provided
        if not args.bill_ids:
            print("Error: Please provide at least one bill ID")
            print("\nUsage:")
            print("  python test_rpa_download.py BILL_ID")
            print("  python test_rpa_download.py BILL_ID1 BILL_ID2 BILL_ID3")
            print("  python test_rpa_download.py --test-connection")
            sys.exit(1)

        # Test with NetSuiteClient wrapper
        if args.use_client:
            if len(args.bill_ids) > 1:
                print("Warning: --use-client only supports single bill. Using first bill only.")
            test_with_netsuite_client(args.bill_ids[0])
            return

        # Download files
        if len(args.bill_ids) == 1:
            test_single_bill(args.bill_ids[0], headless=args.headless)
        else:
            test_multiple_bills(args.bill_ids, headless=args.headless)

    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nError: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
