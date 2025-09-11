#!/usr/bin/env python3
"""
Main orchestrator for monthly accruals processing.

This script coordinates the entire monthly accruals workflow:
1. Read PO/PR list from Google Sheets
2. Sync data from NetSuite (incremental)
3. Process invoices with AI (only new ones)
4. Analyze accruals using business rules and AI
5. Update Google Sheets with decisions
"""

import sys
import os
from datetime import datetime
from typing import Dict, List, Any
import argparse

# Add src to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.clients import NetSuiteClient, GoogleSheetsClient
from src.processors import InvoiceProcessor
from src.engines import AccrualEngine
from src.utils.data_sync import DataSyncManager
from src.utils.logger import setup_logger
from config.settings import AppConfig

logger = setup_logger(__name__)

class MonthlyAccrualsOrchestrator:
    def __init__(self):
        logger.info("Initializing Monthly Accruals Orchestrator")
        
        try:
            self.sheets_client = GoogleSheetsClient()
            self.data_sync_manager = DataSyncManager()
            self.accrual_engine = AccrualEngine()
            
            logger.info("All clients initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize orchestrator: {str(e)}")
            raise

    def run_monthly_accruals(self, spreadsheet_id: str, worksheet_name: str = "PO_PR_List", 
                           force_full_sync: bool = False) -> bool:
        """
        Run the complete monthly accruals process
        
        Args:
            spreadsheet_id: Google Sheets ID containing PO/PR list
            worksheet_name: Name of worksheet with PO/PR data
            force_full_sync: Whether to force a complete re-sync (expensive!)
        
        Returns:
            bool: Success status
        """
        try:
            start_time = datetime.now()
            logger.info(f"Starting monthly accruals processing at {start_time}")
            logger.info(f"Processing spreadsheet: {spreadsheet_id}")
            logger.info(f"Force full sync: {force_full_sync}")
            
            # Step 1: Create backup of original sheet
            logger.info("Step 1: Creating backup of original sheet")
            backup_name = self.sheets_client.backup_original_sheet(spreadsheet_id, worksheet_name)
            if backup_name:
                logger.info(f"Backup created: {backup_name}")
            else:
                logger.warning("Failed to create backup - continuing anyway")
            
            # Step 2: Read PO/PR list from Google Sheets
            logger.info("Step 2: Reading PO/PR list from Google Sheets")
            po_pr_data = self.sheets_client.read_po_pr_list(spreadsheet_id, worksheet_name)
            
            if not po_pr_data:
                logger.error("No PO/PR data found in Google Sheets")
                return False
            
            logger.info(f"Found {len(po_pr_data)} PO/PR items to process")
            
            # Step 3: Incremental data sync from NetSuite
            logger.info("Step 3: Syncing data from NetSuite")
            
            if force_full_sync:
                po_lines, all_bills_by_po, invoice_data_by_bill = self.data_sync_manager.force_full_sync(po_pr_data)
            else:
                po_lines, all_bills_by_po, invoice_data_by_bill = self.data_sync_manager.incremental_data_sync(po_pr_data)
            
            logger.info(f"Synced {len(po_lines)} PO lines")
            total_bills = sum(len(bills) for bills in all_bills_by_po.values())
            logger.info(f"Found {total_bills} total bills")
            total_invoices = sum(len(invoices) for invoices in invoice_data_by_bill.values())
            logger.info(f"Processed {total_invoices} invoice documents")
            
            # Step 4: Analyze accruals
            logger.info("Step 4: Analyzing accrual needs")
            
            # Prepare data for batch analysis
            po_data_for_analysis = []
            for po_key, po_line in po_lines.items():
                po_data_for_analysis.append({
                    'po_id': po_line.po_id,
                    'line_id': po_line.line_id,
                    'vendor_name': po_line.vendor_name,
                    'requestor': po_line.requestor,
                    'legal_entity': po_line.legal_entity,
                    'currency': po_line.currency,
                    'memo': po_line.memo,
                    'gl_account': po_line.gl_account,
                    'description': po_line.description,
                    'amount': po_line.amount,
                    'delivery_date': po_line.delivery_date,
                    'prepaid_start_date': po_line.prepaid_start_date,
                    'prepaid_end_date': po_line.prepaid_end_date,
                    'remaining_balance': po_line.remaining_balance
                })
            
            # Run batch analysis
            accrual_decisions = self.accrual_engine.batch_analyze_accruals(
                po_data_for_analysis, all_bills_by_po, invoice_data_by_bill
            )
            
            logger.info(f"Generated {len(accrual_decisions)} accrual decisions")
            
            # Step 5: Generate summary statistics
            logger.info("Step 5: Generating summary statistics")
            summary_data = self.accrual_engine.get_monthly_accrual_summary(accrual_decisions)
            
            logger.info(f"Total accrual amount: ${summary_data['total_accrual_amount_usd']:,.2f} USD")
            logger.info(f"Lines with accruals: {summary_data['lines_with_accruals']}")
            logger.info(f"Lines without accruals: {summary_data['lines_without_accruals']}")
            
            # Step 6: Update Google Sheets with decisions
            logger.info("Step 6: Updating Google Sheets with accrual decisions")
            
            update_success = self.sheets_client.update_accrual_decisions(
                spreadsheet_id, accrual_decisions, worksheet_name
            )
            
            if not update_success:
                logger.error("Failed to update Google Sheets with decisions")
                return False
            
            # Step 7: Create summary sheet
            logger.info("Step 7: Creating summary sheet")
            
            summary_success = self.sheets_client.create_accrual_summary_sheet(
                spreadsheet_id, accrual_decisions, summary_data
            )
            
            if not summary_success:
                logger.warning("Failed to create summary sheet - continuing anyway")
            
            # Log final results
            end_time = datetime.now()
            duration = end_time - start_time
            
            logger.info("=" * 60)
            logger.info("MONTHLY ACCRUALS PROCESSING COMPLETED SUCCESSFULLY")
            logger.info("=" * 60)
            logger.info(f"Start time: {start_time}")
            logger.info(f"End time: {end_time}")
            logger.info(f"Duration: {duration}")
            logger.info(f"PO/PR items processed: {len(po_pr_data)}")
            logger.info(f"PO lines analyzed: {len(po_lines)}")
            logger.info(f"Bills found: {total_bills}")
            logger.info(f"Invoices processed: {total_invoices}")
            logger.info(f"Accrual decisions made: {len(accrual_decisions)}")
            logger.info(f"Total accrual amount: ${summary_data['total_accrual_amount_usd']:,.2f} USD")
            logger.info(f"Lines requiring accruals: {summary_data['lines_with_accruals']}")
            logger.info("=" * 60)
            
            return True
            
        except Exception as e:
            logger.error(f"Error in monthly accruals processing: {str(e)}")
            return False

    def get_processing_statistics(self) -> Dict[str, Any]:
        """Get current processing statistics"""
        try:
            return self.data_sync_manager.get_sync_statistics()
        except Exception as e:
            logger.error(f"Error getting statistics: {str(e)}")
            return {}

    def validate_configuration(self) -> bool:
        """Validate that all required configurations are set"""
        try:
            logger.info("Validating configuration...")
            
            # Check NetSuite credentials
            netsuite_client = NetSuiteClient()
            
            # Check OpenAI configuration  
            if not os.getenv("OPENAI_API_KEY"):
                logger.error("OpenAI API key not configured")
                return False
            
            # Check Google Sheets configuration
            if not os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY"):
                logger.error("Google service account key not configured")
                return False
            
            # Check Snowflake configuration
            required_snowflake_vars = [
                "SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PASSWORD",
                "SNOWFLAKE_DATABASE", "SNOWFLAKE_SCHEMA", "SNOWFLAKE_WAREHOUSE"
            ]
            
            for var in required_snowflake_vars:
                if not os.getenv(var):
                    logger.error(f"Snowflake configuration missing: {var}")
                    return False
            
            logger.info("Configuration validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Configuration validation failed: {str(e)}")
            return False


def main():
    """Main entry point for the script"""
    parser = argparse.ArgumentParser(description="Run monthly accruals processing")
    parser.add_argument("spreadsheet_id", help="Google Sheets spreadsheet ID")
    parser.add_argument("--worksheet", default="PO_PR_List", help="Worksheet name (default: PO_PR_List)")
    parser.add_argument("--force-full-sync", action="store_true", help="Force complete data re-sync (expensive!)")
    parser.add_argument("--validate-only", action="store_true", help="Only validate configuration and exit")
    parser.add_argument("--stats", action="store_true", help="Show processing statistics and exit")
    
    args = parser.parse_args()
    
    try:
        # Initialize orchestrator
        orchestrator = MonthlyAccrualsOrchestrator()
        
        # Handle different modes
        if args.validate_only:
            success = orchestrator.validate_configuration()
            sys.exit(0 if success else 1)
        
        if args.stats:
            stats = orchestrator.get_processing_statistics()
            print("Processing Statistics:")
            for key, value in stats.items():
                print(f"  {key}: {value}")
            sys.exit(0)
        
        # Validate configuration before processing
        if not orchestrator.validate_configuration():
            logger.error("Configuration validation failed - exiting")
            sys.exit(1)
        
        # Run the main processing
        success = orchestrator.run_monthly_accruals(
            spreadsheet_id=args.spreadsheet_id,
            worksheet_name=args.worksheet,
            force_full_sync=args.force_full_sync
        )
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        logger.info("Processing interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()