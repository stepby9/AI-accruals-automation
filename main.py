#!/usr/bin/env python3
"""
Accruals Automation - Main Menu
Production-ready entry point for all automation functions

Usage:
    python main.py
"""

import sys
import os
from pathlib import Path

# Add src to Python path
sys.path.append(os.path.join(os.path.dirname(__file__)))
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))


def print_header():
    """Print application header"""
    print("\n" + "=" * 80)
    print("📊 ACCRUALS AUTOMATION - MAIN MENU")
    print("=" * 80)


def print_menu():
    """Print main menu options"""
    print("\n🔹 INVOICE PROCESSING")
    print("  1. Download invoices from NetSuite (RPA)")
    print("  2. Extract invoice data with AI")
    print("  3. Upload extracted invoices to Snowflake")

    print("\n🔹 ACCRUAL ANALYSIS")
    print("  4. Run accrual analysis for a month")
    print("  5. Upload accrual analysis results to Snowflake")

    print("\n🔹 UTILITIES")
    print("  6. Test NetSuite connection")
    print("  7. View logs")
    print("  8. Check Snowflake connection")

    print("\n🔹 EXIT")
    print("  0. Exit application")

    print("\n" + "=" * 80)


def download_invoices():
    """Run RPA invoice download"""
    print("\n" + "=" * 80)
    print("📥 INVOICE DOWNLOAD")
    print("=" * 80)

    print("\nThis will download invoices from NetSuite for bills in the Snowflake view.")
    print("Already-downloaded bills will be skipped automatically.")
    print("\n💡 Note: Downloads are sequential (single browser session).")

    response = input("\n▶ Continue? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("❌ Cancelled")
        return

    try:
        from run_invoice_download import download_from_snowflake

        print(f"\n🚀 Starting RPA download...")
        download_from_snowflake(headless=True)

    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        print("   Check logs for details")


def extract_invoices():
    """Run AI invoice extraction"""
    print("\n" + "=" * 80)
    print("🤖 INVOICE EXTRACTION")
    print("=" * 80)

    print("\nThis will extract data from downloaded invoices using AI.")
    print("Already-processed invoices will be skipped automatically.")

    response = input("\n▶ Continue? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("❌ Cancelled")
        return

    # Ask for worker count
    workers_input = input("▶ Number of parallel workers (default: 3, press Enter for default): ").strip()

    try:
        from run_invoice_extraction import run_invoice_extraction

        if workers_input:
            workers = int(workers_input)
            print(f"\n🚀 Starting extraction with {workers} workers...")
            run_invoice_extraction(max_workers=workers)
        else:
            print(f"\n🚀 Starting extraction with default settings...")
            run_invoice_extraction()

    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        print("   Check logs for details")


def upload_invoices():
    """Upload extracted invoices to Snowflake"""
    print("\n" + "=" * 80)
    print("📤 UPLOAD INVOICES TO SNOWFLAKE")
    print("=" * 80)

    try:
        from upload_to_snowflake import upload_csv_to_snowflake
        upload_csv_to_snowflake()

    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        print("   Check logs for details")


def run_accrual_analysis():
    """Run accrual analysis"""
    print("\n" + "=" * 80)
    print("📊 ACCRUAL ANALYSIS")
    print("=" * 80)

    print("\nThis will analyze PO lines to determine if accruals are needed.")
    print("Already-analyzed PO lines for the selected month will be skipped automatically.")

    response = input("\n▶ Continue? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("❌ Cancelled")
        return

    # Ask for worker count
    workers_input = input("▶ Number of parallel workers (default: 3, press Enter for default): ").strip()

    try:
        from run_accrual_analysis import run_accrual_analysis

        if workers_input:
            workers = int(workers_input)
            print(f"\n🚀 Starting analysis with {workers} workers...")
            run_accrual_analysis(max_workers=workers)
        else:
            print(f"\n🚀 Starting analysis with default settings...")
            run_accrual_analysis()

    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        print("   Check logs for details")


def upload_accrual_analysis():
    """Upload accrual analysis results to Snowflake"""
    print("\n" + "=" * 80)
    print("📤 UPLOAD ACCRUAL ANALYSIS TO SNOWFLAKE")
    print("=" * 80)

    try:
        from upload_accrual_analysis_to_snowflake import main as upload_main
        upload_main()

    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        print("   Check logs for details")


def test_netsuite_connection():
    """Test NetSuite RPA connection"""
    print("\n" + "=" * 80)
    print("🔌 TEST NETSUITE CONNECTION")
    print("=" * 80)

    try:
        from run_invoice_download import test_connection
        test_connection(headless=False)

    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        print("   Check logs for details")


def view_logs():
    """View recent logs"""
    print("\n" + "=" * 80)
    print("📋 VIEW LOGS")
    print("=" * 80)

    log_dir = Path("logs")

    if not log_dir.exists():
        print("\n❌ No logs directory found")
        return

    log_files = sorted(log_dir.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True)

    if not log_files:
        print("\n❌ No log files found")
        return

    print(f"\n📁 Recent log files:")
    for i, log_file in enumerate(log_files[:5], 1):
        size_kb = log_file.stat().st_size / 1024
        print(f"  {i}. {log_file.name} ({size_kb:.1f} KB)")

    print("\n💡 Tip: Open log files with a text editor to view details")
    print(f"   Log directory: {log_dir.absolute()}")


def check_snowflake_connection():
    """Test Snowflake connection"""
    print("\n" + "=" * 80)
    print("🔌 TEST SNOWFLAKE CONNECTION")
    print("=" * 80)

    try:
        from src.clients.snowflake_data_client import SnowflakeDataClient

        print("\n🔄 Connecting to Snowflake...")
        client = SnowflakeDataClient()

        print("✅ Connection successful!")
        print(f"   Database: PSEDM_FINANCE_PROD")
        print(f"   Schema: EDM_GTM_FPA")

    except Exception as e:
        print(f"\n❌ Connection failed: {str(e)}")
        print("\n   Please check:")
        print("     1. Snowflake credentials in .env file")
        print("     2. Network connection")
        print("     3. VPN connection (if required)")


def main():
    """Main menu loop"""
    while True:
        print_header()
        print_menu()

        try:
            choice = input("▶ Select an option (0-8): ").strip()

            if choice == "0":
                print("\n👋 Goodbye!")
                print("=" * 80)
                break

            elif choice == "1":
                download_invoices()

            elif choice == "2":
                extract_invoices()

            elif choice == "3":
                upload_invoices()

            elif choice == "4":
                run_accrual_analysis()

            elif choice == "5":
                upload_accrual_analysis()

            elif choice == "6":
                test_netsuite_connection()

            elif choice == "7":
                view_logs()

            elif choice == "8":
                check_snowflake_connection()

            else:
                print(f"\n❌ Invalid option: {choice}")
                print("   Please select a number from 0-8")

            # Pause before returning to menu
            if choice != "0":
                input("\n⏸️  Press Enter to return to main menu...")

        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            print("=" * 80)
            break

        except Exception as e:
            print(f"\n❌ Unexpected error: {str(e)}")
            import traceback
            traceback.print_exc()
            input("\n⏸️  Press Enter to return to main menu...")


if __name__ == "__main__":
    main()
