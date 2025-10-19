"""
Snowflake Data Client - Fetches PO/Bill data from Snowflake views
Replaces NetSuite API calls with Snowflake queries
"""

from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import snowflake.connector
from snowflake.connector import DictCursor

from config.settings import SnowflakeConfig
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class POLine:
    """PO Line data from Snowflake"""
    po_id: str
    line_id: str
    vendor_name: str
    requestor: str
    legal_entity: str
    currency: str
    memo: str
    gl_account: str
    description: str
    amount: float
    amount_usd: float
    delivery_date: Optional[datetime]
    prepaid_start_date: Optional[datetime]
    prepaid_end_date: Optional[datetime]
    remaining_balance: float
    remaining_balance_usd: float


@dataclass
class Bill:
    """Bill data from Snowflake"""
    bill_id: str
    po_id: str
    vendor_name: str
    amount: float
    currency: str
    posting_period: str
    payment_status: str
    created_date: datetime
    due_date: Optional[datetime]


class SnowflakeDataClient:
    """
    Client to fetch PO and Bill data from Snowflake views
    Replaces NetSuite API calls
    """

    def __init__(self):
        """Initialize Snowflake connection"""
        if not all([SnowflakeConfig.ACCOUNT, SnowflakeConfig.USER, SnowflakeConfig.PASSWORD,
                   SnowflakeConfig.DATABASE, SnowflakeConfig.SCHEMA, SnowflakeConfig.WAREHOUSE]):
            raise ValueError("Snowflake configuration incomplete")

        self.connection_params = {
            'account': SnowflakeConfig.ACCOUNT,
            'user': SnowflakeConfig.USER,
            'password': SnowflakeConfig.PASSWORD,
            'database': SnowflakeConfig.DATABASE,
            'schema': SnowflakeConfig.SCHEMA,
            'warehouse': SnowflakeConfig.WAREHOUSE
        }

        # Add role if specified
        if SnowflakeConfig.ROLE:
            self.connection_params['role'] = SnowflakeConfig.ROLE

        logger.info("Snowflake data client initialized")

    def _get_connection(self):
        """Get a Snowflake connection"""
        return snowflake.connector.connect(**self.connection_params)

    def get_po_line_details(self, po_id: str, line_id: str) -> Optional[POLine]:
        """
        Get PO line details from Snowflake view

        Args:
            po_id: Purchase Order ID
            line_id: Line ID

        Returns:
            POLine object or None if not found
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor(DictCursor)

                # TODO: Update with your actual Snowflake view name and column mappings
                query = """
                    SELECT
                        po_id,
                        line_id,
                        vendor_name,
                        requestor,
                        legal_entity,
                        currency,
                        memo,
                        gl_account,
                        description,
                        amount,
                        amount_usd,
                        delivery_date,
                        prepaid_start_date,
                        prepaid_end_date,
                        remaining_balance,
                        remaining_balance_usd
                    FROM YOUR_PO_LINES_VIEW
                    WHERE po_id = %s AND line_id = %s
                """

                cursor.execute(query, (po_id, line_id))
                row = cursor.fetchone()

                if not row:
                    logger.warning(f"PO line not found: {po_id}:{line_id}")
                    return None

                return POLine(
                    po_id=row['PO_ID'],
                    line_id=row['LINE_ID'],
                    vendor_name=row['VENDOR_NAME'],
                    requestor=row['REQUESTOR'],
                    legal_entity=row['LEGAL_ENTITY'],
                    currency=row['CURRENCY'],
                    memo=row['MEMO'],
                    gl_account=row['GL_ACCOUNT'],
                    description=row['DESCRIPTION'],
                    amount=float(row['AMOUNT']),
                    amount_usd=float(row['AMOUNT_USD']),
                    delivery_date=row['DELIVERY_DATE'],
                    prepaid_start_date=row['PREPAID_START_DATE'],
                    prepaid_end_date=row['PREPAID_END_DATE'],
                    remaining_balance=float(row['REMAINING_BALANCE']),
                    remaining_balance_usd=float(row['REMAINING_BALANCE_USD'])
                )

        except Exception as e:
            logger.error(f"Error fetching PO line {po_id}:{line_id} from Snowflake: {str(e)}")
            return None

    def get_bills_for_po(self, po_id: str) -> List[Bill]:
        """
        Get all bills for a PO from Snowflake view

        Args:
            po_id: Purchase Order ID

        Returns:
            List of Bill objects
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor(DictCursor)

                # TODO: Update with your actual Snowflake view name and column mappings
                query = """
                    SELECT
                        bill_id,
                        po_id,
                        vendor_name,
                        amount,
                        currency,
                        posting_period,
                        payment_status,
                        created_date,
                        due_date
                    FROM YOUR_BILLS_VIEW
                    WHERE po_id = %s
                """

                cursor.execute(query, (po_id,))
                rows = cursor.fetchall()

                bills = []
                for row in rows:
                    bills.append(Bill(
                        bill_id=row['BILL_ID'],
                        po_id=row['PO_ID'],
                        vendor_name=row['VENDOR_NAME'],
                        amount=float(row['AMOUNT']),
                        currency=row['CURRENCY'],
                        posting_period=row['POSTING_PERIOD'],
                        payment_status=row['PAYMENT_STATUS'],
                        created_date=row['CREATED_DATE'],
                        due_date=row['DUE_DATE']
                    ))

                logger.info(f"Found {len(bills)} bills for PO {po_id}")
                return bills

        except Exception as e:
            logger.error(f"Error fetching bills for PO {po_id} from Snowflake: {str(e)}")
            return []

    def get_po_lines_from_list(self, po_pr_data: List[Dict]) -> Dict[str, POLine]:
        """
        Fetch PO line details for a list of PO/PR items from Snowflake

        Args:
            po_pr_data: List of dicts with 'po_id' and 'line_id' keys

        Returns:
            Dictionary mapping "po_id:line_id" to POLine objects
        """
        po_lines = {}

        logger.info(f"Fetching {len(po_pr_data)} PO lines from Snowflake")

        for item in po_pr_data:
            po_id = item.get('po_id')
            line_id = item.get('line_id')
            po_key = f"{po_id}:{line_id}"

            po_line = self.get_po_line_details(po_id, line_id)
            if po_line:
                po_lines[po_key] = po_line

        logger.info(f"Successfully fetched {len(po_lines)} PO lines from Snowflake")
        return po_lines

    def get_bills_for_multiple_pos(self, po_ids: List[str]) -> Dict[str, List[Bill]]:
        """
        Get bills for multiple POs from Snowflake

        Args:
            po_ids: List of PO IDs

        Returns:
            Dictionary mapping po_id to list of Bill objects
        """
        bills_by_po = {}

        logger.info(f"Fetching bills for {len(po_ids)} POs from Snowflake")

        for po_id in po_ids:
            bills = self.get_bills_for_po(po_id)
            bills_by_po[po_id] = bills

        total_bills = sum(len(bills) for bills in bills_by_po.values())
        logger.info(f"Found total of {total_bills} bills from Snowflake")

        return bills_by_po

    def get_all_bills(self, limit: Optional[int] = None) -> List[Bill]:
        """
        Get all bills from Snowflake (useful for testing)

        Args:
            limit: Optional limit on number of bills to return

        Returns:
            List of Bill objects
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor(DictCursor)

                # TODO: Update with your actual Snowflake view name
                query = """
                    SELECT
                        bill_id,
                        po_id,
                        vendor_name,
                        amount,
                        currency,
                        posting_period,
                        payment_status,
                        created_date,
                        due_date
                    FROM YOUR_BILLS_VIEW
                """

                if limit:
                    query += f" LIMIT {limit}"

                cursor.execute(query)
                rows = cursor.fetchall()

                bills = []
                for row in rows:
                    bills.append(Bill(
                        bill_id=row['BILL_ID'],
                        po_id=row['PO_ID'],
                        vendor_name=row['VENDOR_NAME'],
                        amount=float(row['AMOUNT']),
                        currency=row['CURRENCY'],
                        posting_period=row['POSTING_PERIOD'],
                        payment_status=row['PAYMENT_STATUS'],
                        created_date=row['CREATED_DATE'],
                        due_date=row['DUE_DATE']
                    ))

                logger.info(f"Fetched {len(bills)} bills from Snowflake")
                return bills

        except Exception as e:
            logger.error(f"Error fetching bills from Snowflake: {str(e)}")
            return []

    def test_connection(self) -> bool:
        """
        Test Snowflake connection

        Returns:
            True if connection successful, False otherwise
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT CURRENT_VERSION()")
                version = cursor.fetchone()[0]
                logger.info(f"Snowflake connection successful. Version: {version}")
                return True

        except Exception as e:
            logger.error(f"Snowflake connection test failed: {str(e)}")
            return False

    def get_bills_to_download(self) -> list:
        """
        Get list of bill IDs that need invoice downloads from Snowflake view
        ACCRUALS_AUTOMATION_BILLS_TO_DOWNLOAD

        Returns:
            List of bill IDs (strings)
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                query = """
                    SELECT DISTINCT BILL_TRANSACTION_ID
                    FROM PSEDM_FINANCE_PROD.EDM_GTM_FPA.ACCRUALS_AUTOMATION_BILLS_TO_DOWNLOAD
                    WHERE BILL_TRANSACTION_ID IS NOT NULL
                    ORDER BY BILL_TRANSACTION_ID
                """

                cursor.execute(query)
                rows = cursor.fetchall()

                bill_ids = [str(row[0]) for row in rows]

                logger.info(f"Loaded {len(bill_ids)} bill IDs from Snowflake view")
                return bill_ids

        except Exception as e:
            logger.error(f"Error fetching bills to download from Snowflake: {str(e)}")
            return []

    def get_processed_invoices(self) -> set:
        """
        Get all (bill_id, file_name) pairs that have already been processed
        from Snowflake table ACCRUALS_AUTOMATION_EXTRACTED_INVOICES

        Returns:
            Set of tuples (bill_id, file_name) representing processed invoices
        """
        try:
            logger.info("Connecting to Snowflake to fetch processed invoices...")
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # First check if table has any data
                count_query = """
                    SELECT COUNT(*)
                    FROM PSEDM_FINANCE_PROD.EDM_GTM_FPA.ACCRUALS_AUTOMATION_EXTRACTED_INVOICES
                """

                logger.info("Checking table record count...")
                cursor.execute(count_query)
                count = cursor.fetchone()[0]
                logger.info(f"Table has {count} records")

                if count == 0:
                    logger.info("Table is empty, no processed invoices to load")
                    return set()

                # If table has data, fetch distinct bill_id and file_name pairs
                query = """
                    SELECT bill_id, file_name
                    FROM PSEDM_FINANCE_PROD.EDM_GTM_FPA.ACCRUALS_AUTOMATION_EXTRACTED_INVOICES
                """

                logger.info("Executing query to get processed invoices...")
                cursor.execute(query)

                logger.info("Fetching results...")
                rows = cursor.fetchall()

                processed_invoices = {(str(row[0]), str(row[1])) for row in rows}

                logger.info(f"Loaded {len(processed_invoices)} processed invoices from Snowflake")
                return processed_invoices

        except Exception as e:
            logger.error(f"Error fetching processed invoices from Snowflake: {str(e)}")
            return set()

    def upload_csv_to_snowflake(self, csv_file_path: str) -> bool:
        """
        APPEND CSV file to Snowflake table ACCRUALS_AUTOMATION_EXTRACTED_INVOICES
        (Does not replace existing data, only adds new records)

        Args:
            csv_file_path: Path to CSV file with NEW invoice extraction results

        Returns:
            True if upload successful, False otherwise
        """
        try:
            import csv as csv_module

            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Read CSV and insert rows directly
                logger.info(f"Reading CSV file: {csv_file_path}")

                with open(csv_file_path, 'r', encoding='utf-8-sig') as csvfile:
                    reader = csv_module.DictReader(csvfile)
                    rows = list(reader)

                if not rows:
                    logger.info("No rows to upload (CSV is empty)")
                    return True

                # Debug: print first row keys to verify column names
                logger.info(f"CSV columns: {list(rows[0].keys())}")
                logger.info(f"Inserting {len(rows)} rows into ACCRUALS_AUTOMATION_EXTRACTED_INVOICES table")

                # Prepare insert query
                insert_query = """
                    INSERT INTO PSEDM_FINANCE_PROD.EDM_GTM_FPA.ACCRUALS_AUTOMATION_EXTRACTED_INVOICES
                    (bill_id, file_name, is_invoice, invoice_number, invoice_date,
                     service_description, service_period, line_items_summary,
                     total_amount, tax_amount, net_amount, currency, confidence_score,
                     processing_time_seconds, file_path)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """

                # Insert each row
                for row in rows:
                    # Strip leading single quote from service_period if present (Excel text formatting)
                    service_period = row['service_period'] if row['service_period'] else None
                    if service_period and service_period.startswith("'"):
                        service_period = service_period[1:]

                    cursor.execute(insert_query, (
                        row['bill_id'],
                        row['file_name'],
                        row['is_invoice'].lower() == 'true',  # Convert to boolean
                        row['invoice_number'] if row['invoice_number'] else None,
                        row['invoice_date'] if row['invoice_date'] else None,
                        row['service_description'] if row['service_description'] else None,
                        service_period,
                        row['line_items_summary'] if row['line_items_summary'] else None,
                        float(row['total_amount']) if row['total_amount'] else None,
                        float(row['tax_amount']) if row['tax_amount'] else None,
                        float(row['net_amount']) if row['net_amount'] else None,
                        row['currency'] if row['currency'] else None,
                        float(row['confidence_score']) if row['confidence_score'] else None,
                        float(row['processing_time_seconds']) if row['processing_time_seconds'] else None,
                        row['file_path'] if row['file_path'] else None
                    ))

                conn.commit()

                logger.info(f"Successfully inserted {len(rows)} rows into Snowflake")
                return True

        except Exception as e:
            logger.error(f"Error uploading CSV to Snowflake: {str(e)}")
            return False
