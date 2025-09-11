from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

from src.clients.netsuite_client import NetSuiteClient, POLine, Bill
from src.processors.invoice_processor import InvoiceProcessor, InvoiceData
from src.database.models import DatabaseManager
from src.utils.logger import setup_logger
from config.settings import AppConfig

logger = setup_logger(__name__)

class DataSyncManager:
    def __init__(self):
        self.netsuite_client = NetSuiteClient()
        self.invoice_processor = InvoiceProcessor()
        self.database = DatabaseManager()
        self.max_workers = AppConfig.MAX_WORKERS
        
        logger.info("Data sync manager initialized")


    def sync_new_bills_from_netsuite(self, last_sync_date: Optional[datetime] = None) -> List[Bill]:
        """Fetch only new bills from NetSuite since last sync"""
        try:
            if last_sync_date is None:
                last_sync_date = self._get_last_sync_date()
            
            logger.info(f"Syncing new bills since {last_sync_date}")
            
            # Get new bills from NetSuite
            new_bills = self.netsuite_client.get_new_bills_since(last_sync_date)
            
            if not new_bills:
                logger.info("No new bills found")
                return []
            
            # Save new bills to database
            saved_bills = []
            for bill in new_bills:
                try:
                    # Check if bill already exists
                    if not self.database.bill_exists(bill.bill_id):
                        self.database.save_bill(bill)
                        saved_bills.append(bill)
                        logger.debug(f"Saved new bill: {bill.bill_id}")
                    else:
                        logger.debug(f"Bill already exists: {bill.bill_id}")
                        
                except Exception as e:
                    logger.error(f"Error saving bill {bill.bill_id}: {str(e)}")
                    continue
            
            # Update last sync timestamp
            self._update_last_sync_date(datetime.now())
            
            logger.info(f"Synced {len(saved_bills)} new bills")
            return saved_bills
            
        except Exception as e:
            logger.error(f"Error syncing bills from NetSuite: {str(e)}")
            return []

    def process_new_invoices_only(self, bills: List[Bill]) -> Dict[str, List[InvoiceData]]:
        """Process invoices only for bills that haven't been processed before"""
        invoice_data_by_bill = {}
        bills_to_process = []
        
        # Filter bills that need invoice processing
        for bill in bills:
            if not self.database.invoices_processed_for_bill(bill.bill_id):
                bills_to_process.append(bill)
            else:
                # Load existing invoice data from database
                existing_data = self.database.get_invoice_data_for_bill(bill.bill_id)
                invoice_data_by_bill[bill.bill_id] = existing_data
                logger.debug(f"Using cached invoice data for bill {bill.bill_id}")
        
        if not bills_to_process:
            logger.info("No new invoices to process")
            return invoice_data_by_bill
        
        logger.info(f"Processing invoices for {len(bills_to_process)} bills")
        
        # Download and process invoices concurrently
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_bill = {
                executor.submit(self._download_and_process_bill_invoices, bill): bill
                for bill in bills_to_process
            }
            
            for future in as_completed(future_to_bill):
                bill = future_to_bill[future]
                try:
                    invoice_data = future.result()
                    if invoice_data:
                        invoice_data_by_bill[bill.bill_id] = invoice_data
                        # Save to database
                        for data in invoice_data:
                            self.database.save_invoice_data(data)
                        
                        logger.info(f"Processed {len(invoice_data)} invoices for bill {bill.bill_id}")
                    
                except Exception as e:
                    logger.error(f"Error processing invoices for bill {bill.bill_id}: {str(e)}")
                    invoice_data_by_bill[bill.bill_id] = []
        
        return invoice_data_by_bill

    def _download_and_process_bill_invoices(self, bill: Bill) -> List[InvoiceData]:
        """Download and process all invoices for a single bill"""
        try:
            # Download invoice files from NetSuite
            invoice_files = self.netsuite_client.download_invoice_files(bill.bill_id)
            
            if not invoice_files:
                logger.warning(f"No invoice files found for bill {bill.bill_id}")
                return []
            
            # Process each invoice file
            invoice_data_list = self.invoice_processor.process_multiple_invoices(
                invoice_files, bill.bill_id
            )
            
            return invoice_data_list
            
        except Exception as e:
            logger.error(f"Error downloading/processing invoices for bill {bill.bill_id}: {str(e)}")
            return []

    def get_po_data_from_sheets(self, po_pr_data: List[Dict]) -> Dict[str, POLine]:
        """Fetch detailed PO data for all PO lines from Google Sheets list"""
        po_lines = {}
        processed_pos = set()
        
        logger.info(f"Fetching PO details for {len(po_pr_data)} items")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_po = {}
            
            for item in po_pr_data:
                po_id = item.get('po_id')
                line_id = item.get('line_id')
                po_key = f"{po_id}:{line_id}"
                
                if po_key not in processed_pos:
                    future_to_po[executor.submit(
                        self.netsuite_client.get_po_line_details, po_id, line_id
                    )] = po_key
                    processed_pos.add(po_key)
            
            for future in as_completed(future_to_po):
                po_key = future_to_po[future]
                try:
                    po_line = future.result()
                    if po_line:
                        # Filter out PO lines with USD remaining balance below $5,000 threshold
                        if po_line.remaining_balance_usd >= AppConfig.MIN_ACCRUAL_AMOUNT_USD:
                            po_lines[po_key] = po_line
                            logger.debug(f"Fetched PO line details: {po_key} (${po_line.remaining_balance_usd:,.2f} USD)")
                        else:
                            logger.debug(f"Filtered out PO line {po_key}: remaining balance ${po_line.remaining_balance_usd:,.2f} USD < ${AppConfig.MIN_ACCRUAL_AMOUNT_USD:,.2f} USD threshold")
                    else:
                        logger.warning(f"No PO line data found for: {po_key}")
                        
                except Exception as e:
                    logger.error(f"Error fetching PO line {po_key}: {str(e)}")
        
        logger.info(f"Successfully fetched {len(po_lines)} PO line details")
        return po_lines

    def get_bills_for_pos(self, po_ids: Set[str]) -> Dict[str, List[Bill]]:
        """Get all bills for a set of PO IDs"""
        bills_by_po = {}
        
        logger.info(f"Fetching bills for {len(po_ids)} POs")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_po = {
                executor.submit(self.netsuite_client.get_bills_for_po, po_id): po_id
                for po_id in po_ids
            }
            
            for future in as_completed(future_to_po):
                po_id = future_to_po[future]
                try:
                    bills = future.result()
                    bills_by_po[po_id] = bills
                    logger.debug(f"Found {len(bills)} bills for PO {po_id}")
                    
                except Exception as e:
                    logger.error(f"Error fetching bills for PO {po_id}: {str(e)}")
                    bills_by_po[po_id] = []
        
        total_bills = sum(len(bills) for bills in bills_by_po.values())
        logger.info(f"Found total of {total_bills} bills across all POs")
        return bills_by_po

    def incremental_data_sync(self, po_pr_data: List[Dict]) -> tuple:
        """Perform incremental data synchronization"""
        try:
            logger.info("Starting incremental data sync")
            
            # Step 1: Sync only new bills from NetSuite
            new_bills = self.sync_new_bills_from_netsuite()
            
            # Step 2: Get PO line details (this data changes monthly, so always refresh)
            po_lines = self.get_po_data_from_sheets(po_pr_data)
            
            # Step 3: Get all bills for the POs (including existing ones)
            po_ids = {po_id.split(':')[0] for po_id in po_lines.keys()}
            all_bills_by_po = self.get_bills_for_pos(po_ids)
            
            # Step 4: Process invoices only for new bills
            all_bills = []
            for bills in all_bills_by_po.values():
                all_bills.extend(bills)
            
            invoice_data_by_bill = self.process_new_invoices_only(all_bills)
            
            logger.info("Incremental data sync completed successfully")
            
            return po_lines, all_bills_by_po, invoice_data_by_bill
            
        except Exception as e:
            logger.error(f"Error in incremental data sync: {str(e)}")
            raise

    def _get_last_sync_date(self) -> datetime:
        """Get the last sync date from database or default to 30 days ago"""
        try:
            last_sync = self.database.get_last_sync_date()
            if last_sync:
                return last_sync
        except:
            pass
        
        # Default to 30 days ago if no previous sync found
        return datetime.now() - timedelta(days=30)

    def _update_last_sync_date(self, sync_date: datetime):
        """Update the last sync date in database"""
        try:
            self.database.update_last_sync_date(sync_date)
        except Exception as e:
            logger.error(f"Error updating last sync date: {str(e)}")

    def get_sync_statistics(self) -> Dict:
        """Get statistics about the current sync status"""
        try:
            stats = {
                'last_sync_date': self.database.get_last_sync_date(),
                'total_bills_in_db': self.database.get_bills_count(),
                'total_invoices_processed': self.database.get_invoices_count(),
                'unique_pos_tracked': self.database.get_unique_pos_count(),
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting sync statistics: {str(e)}")
            return {}

    def force_full_sync(self, po_pr_data: List[Dict]) -> tuple:
        """Force a complete re-sync of all data (use sparingly)"""
        logger.warning("Performing FULL data sync - this will be expensive!")
        
        try:
            # Clear incremental tracking
            self._update_last_sync_date(datetime.now() - timedelta(days=90))
            
            # Run incremental sync which will now fetch everything
            return self.incremental_data_sync(po_pr_data)
            
        except Exception as e:
            logger.error(f"Error in full data sync: {str(e)}")
            raise