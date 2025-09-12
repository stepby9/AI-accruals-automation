#!/usr/bin/env python3
"""
Simple invoice processing test script without emoji characters
"""

import sys
import os
from pathlib import Path
import time

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

def test_invoices():
    """Test invoice processing functionality"""
    
    try:
        # Import required modules
        import openai
        from config.settings import OpenAIConfig
        
        # Check if OpenAI API key is configured
        if not OpenAIConfig.API_KEY:
            print("ERROR: OpenAI API key not found!")
            print("   Please set OPENAI_API_KEY in your .env file")
            return
        
        print("OpenAI API key found")
        print(f"OpenAI library version: {openai.__version__}")
        
        # Check if test folder exists
        folder_path = Path("test_invoices")
        if not folder_path.exists():
            print(f"ERROR: Folder not found: {folder_path}")
            print("   Please create a 'test_invoices' folder with some invoice files")
            return
        
        # Find invoice files
        invoice_files = []
        for ext in ['*.pdf', '*.png', '*.jpg', '*.jpeg']:
            invoice_files.extend(folder_path.glob(ext))
        
        if not invoice_files:
            print(f"ERROR: No invoice files found in: {folder_path}")
            print("   Supported formats: PDF, PNG, JPG, JPEG")
            return
        
        print("Files detected:")
        for file in invoice_files:
            print(f"   - {file.name}")
        
        # Initialize the invoice processor
        try:
            from processors.invoice_processor import InvoiceProcessor
            processor = InvoiceProcessor()
            print("InvoiceProcessor initialized successfully")
        except Exception as e:
            print(f"ERROR: Error initializing InvoiceProcessor: {str(e)}")
            return
        
        # Process each invoice
        print("\n" + "="*50)
        print("PROCESSING INVOICES")
        print("="*50)
        
        for invoice_file in invoice_files:
            print(f"\nProcessing: {invoice_file.name}")
            print("-" * 40)
            
            start_time = time.time()
            
            try:
                result = processor.process_invoice(str(invoice_file), "TEST_001")
                processing_time = time.time() - start_time
                
                if result:
                    print("SUCCESS!")
                    print(f"   Invoice Number: {result.invoice_number}")
                    print(f"   Invoice Date: {result.invoice_date}")
                    print(f"   Total Amount: {result.total_amount}")
                    print(f"   Currency: {result.currency}")
                    print(f"   Service Description: {result.service_description}")
                    print(f"   Service Period: {result.service_period}")
                    print(f"   Line Items Summary: {result.line_items_summary}")
                    print(f"   Confidence Score: {result.confidence_score}")
                    print(f"   Processing Time: {processing_time:.1f} seconds")
                else:
                    print("FAILED: No data extracted")
                    print(f"   Processing Time: {processing_time:.1f} seconds")
                
            except Exception as e:
                processing_time = time.time() - start_time
                print(f"ERROR: {str(e)}")
                print(f"   Processing Time: {processing_time:.1f} seconds")
        
    except ImportError as e:
        print(f"Import error: {str(e)}")
        print("Make sure all required packages are installed")
    except Exception as e:
        print(f"Unexpected error: {str(e)}")

if __name__ == "__main__":
    test_invoices()