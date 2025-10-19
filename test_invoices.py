#!/usr/bin/env python3
"""
Simple Invoice Processing Test Script

Usage:
    python test_invoices.py                           # Uses Google Drive Bills folder (from .env)
    python test_invoices.py 26358814                  # Tests specific bill folder
    python test_invoices.py path/to/invoice/folder    # Uses specified folder
"""

import sys
import os
import csv
import time
from pathlib import Path
from datetime import datetime

# Add src to Python path
sys.path.append(os.path.join(os.path.dirname(__file__)))
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.utils.logger import setup_logger

logger = setup_logger(__name__)

def test_invoices():
    # Start timing
    script_start_time = time.time()

    try:
        # Import and validate OpenAI first
        import openai
        from config.settings import OpenAIConfig
        
        # Check if OpenAI API key is configured
        if not OpenAIConfig.API_KEY:
            print("ERROR: OpenAI API key not found!")
            print("   Please set OPENAI_API_KEY in your .env file")
            return
        
        print("OpenAI API key found")
        
        # Check OpenAI version and initialize appropriately
        print(f"OpenAI library version: {openai.__version__}")
        
        try:
            # Try new OpenAI v1.x initialization
            test_client = openai.OpenAI(api_key=OpenAIConfig.API_KEY)
            print("OpenAI client (v1.x) initialized")
        except Exception as e:
            print(f"❌ OpenAI v1.x client error: {str(e)}")
            print("🔧 Trying legacy initialization...")
            try:
                # Try older OpenAI v0.x initialization
                openai.api_key = OpenAIConfig.API_KEY
                print("🤖 Using legacy OpenAI (v0.x) setup ✅")
            except Exception as e2:
                print(f"❌ Legacy OpenAI setup also failed: {str(e2)}")
                print("💡 You may need to update your OpenAI library:")
                print("   pip install --upgrade openai")
                return
        
        # Get folder path
        from config.settings import INVOICES_DIR

        if len(sys.argv) > 1:
            arg = sys.argv[1]
            # Check if argument is a bill ID (numeric) or a path
            if arg.isdigit():
                # Argument is a bill ID - use Google Drive folder
                folder_path = INVOICES_DIR / arg
                print(f"Testing bill {arg} from Google Drive")
            else:
                # Argument is a custom path
                folder_path = Path(arg)
                print(f"Testing custom folder: {folder_path}")
        else:
            # No argument - use the main Google Drive Bills folder
            folder_path = INVOICES_DIR
            print(f"Testing all bills from Google Drive")

        if not folder_path.exists():
            print(f"❌ Folder not found: {folder_path}")
            if len(sys.argv) > 1 and sys.argv[1].isdigit():
                print(f"   Bill {sys.argv[1]} has no downloaded invoices yet")
                print(f"   Download files first: python test_rpa_download.py {sys.argv[1]}")
            else:
                print(f"   Make sure INVOICES_DIR is configured in .env")
            return
        
        # Find invoice files
        invoice_extensions = ['.pdf', '.xlsx', '.xls', '.docx', '.doc', '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.txt']
        invoice_files = set()  # Use set to avoid duplicates

        # Check if we're in a specific bill folder or the main Bills folder
        if folder_path == INVOICES_DIR and len(sys.argv) <= 1:
            # Main Bills folder - search all bill subdirectories
            print(f"Searching all bill folders in {folder_path}...")
            for ext in invoice_extensions:
                invoice_files.update(folder_path.glob(f"*/*{ext}"))
                invoice_files.update(folder_path.glob(f"*/*{ext.upper()}"))
        else:
            # Specific bill folder or custom path - search just this folder
            for ext in invoice_extensions:
                invoice_files.update(folder_path.glob(f"*{ext}"))
                invoice_files.update(folder_path.glob(f"*{ext.upper()}"))

        invoice_files = list(invoice_files)  # Convert back to list
        
        if not invoice_files:
            print(f"❌ No invoice files found in: {folder_path}")
            print(f"   Supported formats: {', '.join(invoice_extensions)}")
            return
        
        print(f"📁 Found {len(invoice_files)} files in {folder_path}")
        logger.info(f"Found {len(invoice_files)} files in {folder_path}")
        print("📄 Files detected:")
        for file in invoice_files:
            # Show bill ID if scanning all bills
            if folder_path == INVOICES_DIR and len(sys.argv) <= 1:
                bill_id = file.parent.name
                print(f"   - Bill {bill_id}: {file.name} ({file.suffix})")
                logger.info(f"File detected - Bill {bill_id}: {file.name} ({file.suffix})")
            else:
                print(f"   - {file.name} ({file.suffix})")
                logger.info(f"File detected: {file.name} ({file.suffix})")
        print("=" * 60)
        
        # Initialize processor 
        try:
            from src.processors.invoice_processor import InvoiceProcessor
            processor = InvoiceProcessor()
        except Exception as e:
            print(f"❌ Error initializing InvoiceProcessor: {str(e)}")
            return
        
        # Prepare CSV output
        from config.settings import CSV_RESULTS_DIR
        csv_path = CSV_RESULTS_DIR / "invoice_extraction_results.csv"
        results_data = []
        newly_processed_count = 0

        # Clear CSV file at start of each run (fresh start)
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
            fieldnames = ['bill_id', 'file_name', 'is_invoice', 'invoice_number', 'invoice_date',
                         'service_description', 'service_period', 'line_items_summary',
                         'total_amount', 'tax_amount', 'net_amount', 'currency', 'confidence_score',
                         'processing_time_seconds', 'file_path']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
        logger.info("Cleared CSV file for fresh run")

        # Load existing processed invoices from Snowflake (single query at startup)
        print("🔍 Checking Snowflake for already processed invoices...")
        logger.info("Querying Snowflake for processed invoices")

        try:
            from src.clients.snowflake_data_client import SnowflakeDataClient
            snowflake_client = SnowflakeDataClient()
            processed_invoices = snowflake_client.get_processed_invoices()
            print(f"📋 Loaded {len(processed_invoices)} already processed invoices from Snowflake")
            logger.info(f"Loaded {len(processed_invoices)} processed invoices from Snowflake")
        except Exception as e:
            print(f"⚠️  Could not connect to Snowflake: {str(e)}")
            print(f"   Falling back to local CSV check only")
            logger.warning(f"Could not load from Snowflake, using empty set: {str(e)}")
            processed_invoices = set()
            snowflake_client = None

        # Process each file
        for i, file_path in enumerate(invoice_files, 1):
            # Determine bill ID
            if folder_path == INVOICES_DIR and len(sys.argv) <= 1:
                bill_id = file_path.parent.name
                print(f"\n🧾 [{i}/{len(invoice_files)}] Processing Bill {bill_id}: {file_path.name}")
            else:
                bill_id = folder_path.name if len(sys.argv) > 1 and sys.argv[1].isdigit() else f"TEST_{i:03d}"
                print(f"\n🧾 [{i}/{len(invoice_files)}] Processing: {file_path.name}")
            print("-" * 40)

            # Check if already processed in Snowflake
            record_key = (bill_id, file_path.name)
            if record_key in processed_invoices:
                print("✓ Invoice has already been processed and can be found in Snowflake. Skipping")
                logger.info(f"Skipping already processed invoice: Bill {bill_id}, File: {file_path.name}")
                continue

            start_time = time.time()

            try:
                # Process invoice
                result = processor.process_invoice(str(file_path), bill_id)

                processing_time = time.time() - start_time

                if result:
                    # Check if document is actually an invoice
                    if not result.is_invoice:
                        print("⚠️  NOT AN INVOICE!")
                        print(f"   This document is not an invoice - deleting file")
                        print(f"   Processing Time: {processing_time:.1f} seconds")

                        logger.warning(f"Document is not an invoice: Bill {bill_id}, File: {file_path.name}")
                        logger.info(f"Deleting non-invoice file: {file_path}")

                        # Delete the non-invoice file
                        try:
                            file_path.unlink()
                            print(f"   ✓ File deleted: {file_path.name}")
                            logger.info(f"Successfully deleted non-invoice file: {file_path.name}")
                        except Exception as delete_error:
                            print(f"   ❌ Could not delete file: {str(delete_error)}")
                            logger.error(f"Failed to delete non-invoice file {file_path.name}: {str(delete_error)}")

                        # Do NOT add to CSV/database
                        logger.info(f"Skipping database insertion for non-invoice: Bill {bill_id}, File: {file_path.name}")
                        continue

                    print("✅ SUCCESS!")
                    print(f"   Is invoice: {result.is_invoice}")
                    print(f"   Invoice #: {result.invoice_number or 'N/A'}")
                    print(f"   Date: {result.invoice_date or 'N/A'}")
                    print(f"   Total (incl. tax): {result.total_amount or 'N/A'} {result.currency or 'N/A'}")
                    print(f"   Tax: {result.tax_amount or 'N/A'} {result.currency or 'N/A'}")
                    print(f"   Net (excl. tax): {result.net_amount or 'N/A'} {result.currency or 'N/A'}")
                    print(f"   Description: {result.service_description or 'N/A'}")
                    print(f"   Service Period: {result.service_period or 'N/A'}")
                    print(f"   Line Items: {result.line_items_summary or 'N/A'}")
                    print(f"   Confidence: {result.confidence_score:.2f}")
                    print(f"   Processing Time: {processing_time:.1f} seconds")
                    print(f"   File: {result.file_path}")

                    # Log successful extraction
                    logger.info(f"Successfully processed invoice: Bill {bill_id}, File: {file_path.name}, Invoice#: {result.invoice_number}, Amount: {result.net_amount} {result.currency}, Confidence: {result.confidence_score:.2f}")

                    # Add to CSV results (only if is_invoice = True)
                    newly_processed_count += 1

                    # Add tab prefix to service_period to force Excel to treat it as text
                    service_period_value = result.service_period or ''
                    if service_period_value:
                        service_period_value = f"'{service_period_value}"

                    results_data.append({
                        'bill_id': result.bill_id,
                        'file_name': file_path.name,
                        'is_invoice': result.is_invoice,
                        'invoice_number': result.invoice_number or '',
                        'invoice_date': result.invoice_date or '',
                        'service_description': result.service_description or '',
                        'service_period': service_period_value,
                        'line_items_summary': result.line_items_summary or '',
                        'total_amount': result.total_amount or '',
                        'tax_amount': result.tax_amount or '',
                        'net_amount': result.net_amount or '',
                        'currency': result.currency or '',
                        'confidence_score': result.confidence_score,
                        'processing_time_seconds': round(processing_time, 1),
                        'file_path': result.file_path
                    })
                else:
                    print("❌ FAILED: No data extracted")
                    print(f"   Processing Time: {processing_time:.1f} seconds")
                    logger.error(f"Failed to extract data from invoice: Bill {bill_id}, File: {file_path.name}")

                    # Add failed result to CSV
                    results_data.append({
                        'bill_id': bill_id,
                        'file_name': file_path.name,
                        'is_invoice': 'FAILED',
                        'invoice_number': '',
                        'invoice_date': '',
                        'service_description': '',
                        'service_period': '',
                        'line_items_summary': '',
                        'total_amount': '',
                        'tax_amount': '',
                        'net_amount': '',
                        'currency': '',
                        'confidence_score': 0,
                        'processing_time_seconds': round(processing_time, 1),
                        'file_path': str(file_path)
                    })

            except Exception as e:
                print(f"❌ ERROR: {str(e)}")
                logger.error(f"Exception during invoice processing: Bill {bill_id}, File: {file_path.name}, Error: {str(e)}")

                # Add error result to CSV
                results_data.append({
                    'bill_id': bill_id,
                    'file_name': file_path.name,
                    'is_invoice': 'ERROR',
                    'invoice_number': '',
                    'invoice_date': '',
                    'service_description': '',
                    'service_period': '',
                    'line_items_summary': str(e),
                    'total_amount': '',
                    'tax_amount': '',
                    'net_amount': '',
                    'currency': '',
                    'confidence_score': 0,
                    'processing_time_seconds': 0,
                    'file_path': str(file_path)
                })

        # Calculate and display total execution time
        total_execution_time = time.time() - script_start_time
        minutes = int(total_execution_time // 60)
        seconds = int(total_execution_time % 60)

        # Calculate summary stats
        total_files_found = len(invoice_files)
        skipped_count = total_files_found - newly_processed_count

        # Write results to CSV only if there are new results
        if newly_processed_count > 0:
            with open(csv_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
                fieldnames = ['bill_id', 'file_name', 'is_invoice', 'invoice_number', 'invoice_date',
                             'service_description', 'service_period', 'line_items_summary',
                             'total_amount', 'tax_amount', 'net_amount', 'currency', 'confidence_score',
                             'processing_time_seconds', 'file_path']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(results_data)

            print("\n" + "=" * 60)
            print(f"📊 Processing Summary:")
            print(f"  Total files found: {total_files_found}")
            print(f"  Already processed (skipped): {skipped_count}")
            print(f"  Newly processed: {newly_processed_count}")
            print(f"  Total execution time: {minutes}m {seconds}s")
            print("=" * 60)
            print(f"\n✓ Results saved to CSV: {csv_path.absolute()}")
            print(f"\n💡 Next step: Review the CSV and then upload to Snowflake using:")
            print(f"   python upload_to_snowflake.py")
            logger.info(f"Summary: {total_files_found} files found, {skipped_count} skipped, {newly_processed_count} newly processed in {minutes}m {seconds}s")

        else:
            print("\n" + "=" * 60)
            print(f"📊 Processing Summary:")
            print(f"  Total files found: {total_files_found}")
            print(f"  Already processed (skipped): {skipped_count}")
            print(f"  Newly processed: {newly_processed_count}")
            print(f"  Total execution time: {minutes}m {seconds}s")
            print("=" * 60)
            print(f"\n✓ All invoices already in Snowflake database")
            logger.info(f"Summary: {total_files_found} files found, all already in Snowflake, completed in {minutes}m {seconds}s")

        print("🎯 Test completed!")
        
    except ImportError as e:
        print(f"❌ Import error: {str(e)}")
        print("   Make sure you have all dependencies installed:")
        print("   pip install -r requirements.txt")
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")

if __name__ == "__main__":
    test_invoices()