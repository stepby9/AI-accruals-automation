import json
from typing import Dict, List, Optional, Any
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

from config.settings import GoogleConfig
from src.engines.accrual_engine import AccrualDecision
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

class GoogleSheetsClient:
    def __init__(self):
        if not GoogleConfig.SERVICE_ACCOUNT_KEY:
            raise ValueError("Google service account key not configured")
        
        # Set up credentials and client
        self.credentials = Credentials.from_service_account_file(
            GoogleConfig.SERVICE_ACCOUNT_KEY,
            scopes=[
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
        )
        
        self.client = gspread.authorize(self.credentials)
        logger.info("Google Sheets client initialized")

    def read_po_pr_list(self, spreadsheet_id: str, worksheet_name: str = "PO_PR_List") -> List[Dict[str, Any]]:
        """Read the monthly PO/PR list from Google Sheets"""
        try:
            logger.info(f"Reading PO/PR list from sheet: {spreadsheet_id}")
            
            # Open the spreadsheet
            spreadsheet = self.client.open_by_key(spreadsheet_id)
            worksheet = spreadsheet.worksheet(worksheet_name)
            
            # Get all records as list of dictionaries
            records = worksheet.get_all_records()
            
            # Clean up the data
            cleaned_records = []
            for record in records:
                # Skip empty rows
                if not any(str(v).strip() for v in record.values()):
                    continue
                
                # Clean up the record
                cleaned_record = {}
                for key, value in record.items():
                    # Convert keys to snake_case and clean them
                    clean_key = key.lower().replace(' ', '_').replace('/', '_').strip()
                    cleaned_record[clean_key] = str(value).strip() if value else ""
                
                cleaned_records.append(cleaned_record)
            
            logger.info(f"Read {len(cleaned_records)} PO/PR records from sheets")
            return cleaned_records
            
        except Exception as e:
            logger.error(f"Error reading PO/PR list from sheets: {str(e)}")
            return []

    def update_accrual_decisions(self, spreadsheet_id: str, decisions: List[AccrualDecision], 
                               worksheet_name: str = "PO_PR_List") -> bool:
        """Update the Google Sheet with accrual decisions"""
        try:
            logger.info(f"Updating {len(decisions)} accrual decisions in sheet")
            
            # Open the spreadsheet
            spreadsheet = self.client.open_by_key(spreadsheet_id)
            worksheet = spreadsheet.worksheet(worksheet_name)
            
            # Get current data to match rows
            current_data = worksheet.get_all_records()
            
            # Create lookup for decisions by PO:Line
            decisions_lookup = {}
            for decision in decisions:
                key = f"{decision.po_id}:{decision.line_id}"
                decisions_lookup[key] = decision
            
            # Find column indices for accrual data
            headers = worksheet.row_values(1)
            accrual_amount_col = self._find_or_create_column(worksheet, headers, "Accrual Amount USD")
            reasoning_col = self._find_or_create_column(worksheet, headers, "Accrual Reasoning")
            confidence_col = self._find_or_create_column(worksheet, headers, "Confidence Score")
            updated_at_col = self._find_or_create_column(worksheet, headers, "Last Updated")
            
            # Update rows in batches
            updates = []
            row_num = 2  # Start from row 2 (after headers)
            
            for record in current_data:
                try:
                    # Extract PO and line info from the record
                    po_id = str(record.get('po_id', record.get('PO ID', ''))).strip()
                    line_id = str(record.get('line_id', record.get('Line ID', ''))).strip()
                    
                    if not po_id or not line_id:
                        row_num += 1
                        continue
                    
                    key = f"{po_id}:{line_id}"
                    decision = decisions_lookup.get(key)
                    
                    if decision:
                        # Prepare updates for this row
                        updates.append({
                            'range': f'{self._col_num_to_letter(accrual_amount_col)}{row_num}',
                            'values': [[f"{decision.accrual_amount_usd:,.2f}"]]
                        })
                        updates.append({
                            'range': f'{self._col_num_to_letter(reasoning_col)}{row_num}',
                            'values': [[decision.reasoning]]
                        })
                        updates.append({
                            'range': f'{self._col_num_to_letter(confidence_col)}{row_num}',
                            'values': [[f"{decision.confidence_score:.2f}"]]
                        })
                        updates.append({
                            'range': f'{self._col_num_to_letter(updated_at_col)}{row_num}',
                            'values': [[datetime.now().strftime('%Y-%m-%d %H:%M:%S')]]
                        })
                        
                        logger.debug(f"Prepared update for {key}: ${decision.accrual_amount_usd:.2f}")
                    
                except Exception as e:
                    logger.warning(f"Error processing row {row_num}: {str(e)}")
                
                row_num += 1
            
            # Batch update the sheet
            if updates:
                worksheet.batch_update(updates)
                logger.info(f"Successfully updated {len(updates)//4} rows with accrual decisions")
            else:
                logger.warning("No matching rows found to update")
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating accrual decisions in sheets: {str(e)}")
            return False

    def _find_or_create_column(self, worksheet, headers: List[str], column_name: str) -> int:
        """Find column index or create new column if it doesn't exist"""
        try:
            # Try to find existing column (case insensitive)
            for i, header in enumerate(headers):
                if header.lower().replace(' ', '_') == column_name.lower().replace(' ', '_'):
                    return i + 1  # gspread uses 1-based indexing
            
            # Column doesn't exist, add it
            new_col_index = len(headers) + 1
            worksheet.update_cell(1, new_col_index, column_name)
            logger.info(f"Created new column: {column_name} at position {new_col_index}")
            return new_col_index
            
        except Exception as e:
            logger.error(f"Error finding/creating column {column_name}: {str(e)}")
            return len(headers) + 1  # Default to end

    def _col_num_to_letter(self, col_num: int) -> str:
        """Convert column number to letter (1 -> A, 26 -> Z, 27 -> AA, etc.)"""
        result = ""
        while col_num > 0:
            col_num -= 1
            result = chr(col_num % 26 + ord('A')) + result
            col_num //= 26
        return result

    def create_accrual_summary_sheet(self, spreadsheet_id: str, decisions: List[AccrualDecision], 
                                   summary_data: Dict[str, Any]) -> bool:
        """Create a summary sheet with accrual analysis results"""
        try:
            logger.info("Creating accrual summary sheet")
            
            # Open the spreadsheet
            spreadsheet = self.client.open_by_key(spreadsheet_id)
            
            # Create or get summary worksheet
            summary_sheet_name = f"Accrual_Summary_{datetime.now().strftime('%Y%m%d')}"
            
            try:
                worksheet = spreadsheet.worksheet(summary_sheet_name)
                worksheet.clear()  # Clear existing content
            except:
                worksheet = spreadsheet.add_worksheet(
                    title=summary_sheet_name, 
                    rows=1000, 
                    cols=20
                )
            
            # Prepare summary data
            summary_rows = [
                ["Accrual Analysis Summary", "", "", ""],
                ["Generated At:", summary_data.get('generated_at', ''), "", ""],
                ["Total Lines Analyzed:", summary_data.get('total_lines_analyzed', 0), "", ""],
                ["Lines with Accruals:", summary_data.get('lines_with_accruals', 0), "", ""],
                ["Lines without Accruals:", summary_data.get('lines_without_accruals', 0), "", ""],
                ["Total Accrual Amount (USD):", f"${summary_data.get('total_accrual_amount_usd', 0):,.2f}", "", ""],
                ["", "", "", ""],
                ["GL Account Summary", "", "", ""],
                ["GL Account", "Count", "Total Amount", ""],
            ]
            
            # Add GL account breakdown
            gl_summary = summary_data.get('gl_account_summary', {})
            for gl_account, data in gl_summary.items():
                if data['count'] > 0:
                    summary_rows.append([
                        gl_account,
                        data['count'],
                        f"${data['total_amount']:,.2f}",
                        ""
                    ])
            
            # Add detailed decisions
            summary_rows.extend([
                ["", "", "", ""],
                ["Detailed Accrual Decisions", "", "", ""],
                ["PO ID", "Line ID", "Vendor", "GL Account", "Accrual Amount", "Reasoning"]
            ])
            
            for decision in decisions:
                if decision.accrual_amount_usd > 0:
                    summary_rows.append([
                        decision.po_id,
                        decision.line_id,
                        decision.vendor_name,
                        decision.gl_account,
                        f"${decision.accrual_amount_usd:,.2f}",
                        decision.reasoning[:500]  # Limit reasoning length
                    ])
            
            # Update the sheet with all data
            worksheet.update(f'A1:F{len(summary_rows)}', summary_rows)
            
            # Format the header rows
            worksheet.format('A1:F1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}
            })
            
            worksheet.format('A8:F8', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.8, 'green': 0.8, 'blue': 1.0}
            })
            
            logger.info(f"Created summary sheet: {summary_sheet_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating summary sheet: {str(e)}")
            return False

    def backup_original_sheet(self, spreadsheet_id: str, worksheet_name: str = "PO_PR_List") -> str:
        """Create a backup of the original sheet before making changes"""
        try:
            spreadsheet = self.client.open_by_key(spreadsheet_id)
            original_worksheet = spreadsheet.worksheet(worksheet_name)
            
            # Create backup sheet name with timestamp
            backup_name = f"{worksheet_name}_Backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Copy the worksheet
            backup_worksheet = spreadsheet.add_worksheet(
                title=backup_name,
                rows=original_worksheet.row_count,
                cols=original_worksheet.col_count
            )
            
            # Copy all data
            all_values = original_worksheet.get_all_values()
            if all_values:
                backup_worksheet.update(f'A1:Z{len(all_values)}', all_values)
            
            logger.info(f"Created backup sheet: {backup_name}")
            return backup_name
            
        except Exception as e:
            logger.error(f"Error creating backup sheet: {str(e)}")
            return ""

    def get_spreadsheet_info(self, spreadsheet_id: str) -> Dict[str, Any]:
        """Get information about the spreadsheet"""
        try:
            spreadsheet = self.client.open_by_key(spreadsheet_id)
            
            worksheets_info = []
            for worksheet in spreadsheet.worksheets():
                worksheets_info.append({
                    'name': worksheet.title,
                    'rows': worksheet.row_count,
                    'cols': worksheet.col_count,
                    'id': worksheet.id
                })
            
            return {
                'title': spreadsheet.title,
                'id': spreadsheet.id,
                'worksheets': worksheets_info,
                'url': spreadsheet.url
            }
            
        except Exception as e:
            logger.error(f"Error getting spreadsheet info: {str(e)}")
            return {}