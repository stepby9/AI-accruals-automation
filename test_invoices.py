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
from pathlib import Path

# Add src to Python path
sys.path.append(os.path.join(os.path.dirname(__file__)))
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

def test_invoices():
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
        print("📄 Files detected:")
        for file in invoice_files:
            # Show bill ID if scanning all bills
            if folder_path == INVOICES_DIR and len(sys.argv) <= 1:
                bill_id = file.parent.name
                print(f"   - Bill {bill_id}: {file.name} ({file.suffix})")
            else:
                print(f"   - {file.name} ({file.suffix})")
        print("=" * 60)
        
        # Initialize processor 
        try:
            from src.processors.invoice_processor import InvoiceProcessor
            processor = InvoiceProcessor()
        except Exception as e:
            print(f"❌ Error initializing InvoiceProcessor: {str(e)}")
            return
        
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

            import time
            start_time = time.time()

            try:
                # Process invoice
                result = processor.process_invoice(str(file_path), bill_id)
                
                processing_time = time.time() - start_time
                
                if result:
                    print("✅ SUCCESS!")
                    print(f"   Is invoice: {result.is_invoice}")
                    print(f"   Invoice #: {result.invoice_number or 'N/A'}")
                    print(f"   Date: {result.invoice_date or 'N/A'}")
                    print(f"   Amount: {result.total_amount or 'N/A'} {result.currency or 'N/A'}")
                    print(f"   Description: {result.service_description or 'N/A'}")
                    print(f"   Service Period: {result.service_period or 'N/A'}")
                    print(f"   Line Items: {result.line_items_summary or 'N/A'}")
                    print(f"   Confidence: {result.confidence_score:.2f}")
                    print(f"   Processing Time: {processing_time:.1f} seconds")
                    print(f"   File: {result.file_path}")
                else:
                    print("❌ FAILED: No data extracted")
                    print(f"   Processing Time: {processing_time:.1f} seconds")
                    
            except Exception as e:
                print(f"❌ ERROR: {str(e)}")
        
        print("\n" + "=" * 60)
        print("🎯 Test completed!")
        
    except ImportError as e:
        print(f"❌ Import error: {str(e)}")
        print("   Make sure you have all dependencies installed:")
        print("   pip install -r requirements.txt")
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")

if __name__ == "__main__":
    test_invoices()