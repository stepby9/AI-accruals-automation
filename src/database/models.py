from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
import json
import snowflake.connector
from snowflake.connector import DictCursor

from config.settings import SnowflakeConfig
from src.clients.netsuite_client import Bill
from src.processors.invoice_processor import InvoiceData
from src.engines.accrual_engine import AccrualDecision
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

class DatabaseManager:
    def __init__(self):
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
        
        # Initialize tables
        self._ensure_tables_exist()
        logger.info("Database manager initialized")

    def _get_connection(self):
        """Get a database connection"""
        return snowflake.connector.connect(**self.connection_params)

    def _ensure_tables_exist(self):
        """Create tables if they don't exist"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Bills table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS bills (
                        bill_id VARCHAR(50) PRIMARY KEY,
                        po_id VARCHAR(50),
                        vendor_name VARCHAR(500),
                        amount DECIMAL(15,2),
                        currency VARCHAR(10),
                        posting_period VARCHAR(50),
                        payment_status VARCHAR(100),
                        invoice_file_url VARCHAR(1000),
                        created_date TIMESTAMP,
                        due_date TIMESTAMP,
                        synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
                    )
                """)
                
                # Invoice data table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS invoice_data (
                        id VARCHAR(100) PRIMARY KEY,
                        bill_id VARCHAR(50),
                        vendor_name VARCHAR(500),
                        invoice_number VARCHAR(200),
                        invoice_date TIMESTAMP,
                        service_description TEXT,
                        service_period_start TIMESTAMP,
                        service_period_end TIMESTAMP,
                        line_items VARIANT,
                        total_amount DECIMAL(15,2),
                        currency VARCHAR(10),
                        language VARCHAR(10),
                        confidence_score DECIMAL(3,2),
                        extracted_at TIMESTAMP,
                        file_path VARCHAR(1000),
                        FOREIGN KEY (bill_id) REFERENCES bills(bill_id)
                    )
                """)
                
                # Accrual decisions table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS accrual_decisions (
                        id VARCHAR(100) PRIMARY KEY,
                        po_id VARCHAR(50),
                        line_id VARCHAR(50),
                        bill_id VARCHAR(50),
                        accrual_amount_usd DECIMAL(15,2),
                        reasoning TEXT,
                        confidence_score DECIMAL(3,2),
                        created_at TIMESTAMP,
                        gl_account VARCHAR(200),
                        vendor_name VARCHAR(500),
                        remaining_balance DECIMAL(15,2),
                        currency VARCHAR(10),
                        UNIQUE (po_id, line_id, created_at)
                    )
                """)
                
                # Sync tracking table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sync_tracking (
                        id INTEGER IDENTITY(1,1) PRIMARY KEY,
                        sync_type VARCHAR(50),
                        last_sync_date TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
                    )
                """)
                
                # Insert default sync tracking record
                cursor.execute("""
                    MERGE INTO sync_tracking AS target
                    USING (SELECT 'bills_sync' as sync_type) AS source
                    ON target.sync_type = source.sync_type
                    WHEN NOT MATCHED THEN
                        INSERT (sync_type, last_sync_date)
                        VALUES ('bills_sync', CURRENT_TIMESTAMP() - INTERVAL '30 DAYS')
                """)
                
                logger.info("Database tables ensured to exist")
                
        except Exception as e:
            logger.error(f"Error ensuring tables exist: {str(e)}")
            raise

    def save_bill(self, bill: Bill) -> bool:
        """Save a bill to the database"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO bills (
                        bill_id, po_id, vendor_name, amount, currency,
                        posting_period, payment_status, invoice_file_url,
                        created_date, due_date
                    ) VALUES (
                        %(bill_id)s, %(po_id)s, %(vendor_name)s, %(amount)s, %(currency)s,
                        %(posting_period)s, %(payment_status)s, %(invoice_file_url)s,
                        %(created_date)s, %(due_date)s
                    )
                """, {
                    'bill_id': bill.bill_id,
                    'po_id': bill.po_id,
                    'vendor_name': bill.vendor_name,
                    'amount': bill.amount,
                    'currency': bill.currency,
                    'posting_period': bill.posting_period,
                    'payment_status': bill.payment_status,
                    'invoice_file_url': bill.invoice_file_url,
                    'created_date': bill.created_date,
                    'due_date': bill.due_date
                })
                
                return True
                
        except Exception as e:
            logger.error(f"Error saving bill {bill.bill_id}: {str(e)}")
            return False

    def bill_exists(self, bill_id: str) -> bool:
        """Check if a bill exists in the database"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM bills WHERE bill_id = %s", (bill_id,))
                return cursor.fetchone() is not None
                
        except Exception as e:
            logger.error(f"Error checking if bill exists {bill_id}: {str(e)}")
            return False

    def save_invoice_data(self, invoice_data: InvoiceData) -> bool:
        """Save invoice data to the database"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Generate unique ID
                invoice_id = f"{invoice_data.bill_id}_{invoice_data.invoice_number}_{int(invoice_data.extracted_at.timestamp())}"
                
                cursor.execute("""
                    INSERT INTO invoice_data (
                        id, bill_id, vendor_name, invoice_number, invoice_date,
                        service_description, service_period_start, service_period_end,
                        line_items, total_amount, currency, language, confidence_score,
                        extracted_at, file_path
                    ) VALUES (
                        %(id)s, %(bill_id)s, %(vendor_name)s, %(invoice_number)s, %(invoice_date)s,
                        %(service_description)s, %(service_period_start)s, %(service_period_end)s,
                        %(line_items)s, %(total_amount)s, %(currency)s, %(language)s, %(confidence_score)s,
                        %(extracted_at)s, %(file_path)s
                    )
                """, {
                    'id': invoice_id,
                    'bill_id': invoice_data.bill_id,
                    'vendor_name': invoice_data.vendor_name,
                    'invoice_number': invoice_data.invoice_number,
                    'invoice_date': invoice_data.invoice_date,
                    'service_description': invoice_data.service_description,
                    'service_period_start': invoice_data.service_period_start,
                    'service_period_end': invoice_data.service_period_end,
                    'line_items': json.dumps(invoice_data.line_items),
                    'total_amount': invoice_data.total_amount,
                    'currency': invoice_data.currency,
                    'language': invoice_data.language,
                    'confidence_score': invoice_data.confidence_score,
                    'extracted_at': invoice_data.extracted_at,
                    'file_path': invoice_data.file_path
                })
                
                return True
                
        except Exception as e:
            logger.error(f"Error saving invoice data for bill {invoice_data.bill_id}: {str(e)}")
            return False

    def invoices_processed_for_bill(self, bill_id: str) -> bool:
        """Check if invoices have been processed for a bill"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM invoice_data WHERE bill_id = %s", (bill_id,))
                return cursor.fetchone() is not None
                
        except Exception as e:
            logger.error(f"Error checking invoice processing for bill {bill_id}: {str(e)}")
            return False

    def get_invoice_data_for_bill(self, bill_id: str) -> List[InvoiceData]:
        """Get all invoice data for a bill"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor(DictCursor)
                cursor.execute("""
                    SELECT * FROM invoice_data WHERE bill_id = %s
                """, (bill_id,))
                
                results = cursor.fetchall()
                invoice_data_list = []
                
                for row in results:
                    invoice_data = InvoiceData(
                        bill_id=row['BILL_ID'],
                        vendor_name=row['VENDOR_NAME'],
                        invoice_number=row['INVOICE_NUMBER'],
                        invoice_date=row['INVOICE_DATE'],
                        service_description=row['SERVICE_DESCRIPTION'],
                        service_period_start=row['SERVICE_PERIOD_START'],
                        service_period_end=row['SERVICE_PERIOD_END'],
                        line_items=json.loads(row['LINE_ITEMS']) if row['LINE_ITEMS'] else [],
                        total_amount=float(row['TOTAL_AMOUNT']),
                        currency=row['CURRENCY'],
                        language=row['LANGUAGE'],
                        confidence_score=float(row['CONFIDENCE_SCORE']),
                        extracted_at=row['EXTRACTED_AT'],
                        file_path=row['FILE_PATH']
                    )
                    invoice_data_list.append(invoice_data)
                
                return invoice_data_list
                
        except Exception as e:
            logger.error(f"Error getting invoice data for bill {bill_id}: {str(e)}")
            return []

    def save_accrual_decision(self, decision: AccrualDecision) -> bool:
        """Save an accrual decision to the database"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                decision_id = f"{decision.po_id}_{decision.line_id}_{int(decision.created_at.timestamp())}"
                
                cursor.execute("""
                    INSERT INTO accrual_decisions (
                        id, po_id, line_id, bill_id, accrual_amount_usd,
                        reasoning, confidence_score, created_at, gl_account,
                        vendor_name, remaining_balance, currency
                    ) VALUES (
                        %(id)s, %(po_id)s, %(line_id)s, %(bill_id)s, %(accrual_amount_usd)s,
                        %(reasoning)s, %(confidence_score)s, %(created_at)s, %(gl_account)s,
                        %(vendor_name)s, %(remaining_balance)s, %(currency)s
                    )
                """, {
                    'id': decision_id,
                    'po_id': decision.po_id,
                    'line_id': decision.line_id,
                    'bill_id': decision.bill_id,
                    'accrual_amount_usd': decision.accrual_amount_usd,
                    'reasoning': decision.reasoning,
                    'confidence_score': decision.confidence_score,
                    'created_at': decision.created_at,
                    'gl_account': decision.gl_account,
                    'vendor_name': decision.vendor_name,
                    'remaining_balance': decision.remaining_balance,
                    'currency': decision.currency
                })
                
                return True
                
        except Exception as e:
            logger.error(f"Error saving accrual decision for {decision.po_id}:{decision.line_id}: {str(e)}")
            return False

    def get_last_sync_date(self) -> Optional[datetime]:
        """Get the last sync date for bills"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT last_sync_date FROM sync_tracking 
                    WHERE sync_type = 'bills_sync'
                """)
                
                result = cursor.fetchone()
                return result[0] if result else None
                
        except Exception as e:
            logger.error(f"Error getting last sync date: {str(e)}")
            return None

    def update_last_sync_date(self, sync_date: datetime):
        """Update the last sync date"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE sync_tracking 
                    SET last_sync_date = %s, updated_at = CURRENT_TIMESTAMP()
                    WHERE sync_type = 'bills_sync'
                """, (sync_date,))
                
        except Exception as e:
            logger.error(f"Error updating last sync date: {str(e)}")
            raise

    def get_bills_count(self) -> int:
        """Get total number of bills in database"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM bills")
                result = cursor.fetchone()
                return result[0] if result else 0
                
        except Exception as e:
            logger.error(f"Error getting bills count: {str(e)}")
            return 0

    def get_invoices_count(self) -> int:
        """Get total number of processed invoices"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM invoice_data")
                result = cursor.fetchone()
                return result[0] if result else 0
                
        except Exception as e:
            logger.error(f"Error getting invoices count: {str(e)}")
            return 0

    def get_unique_pos_count(self) -> int:
        """Get number of unique POs tracked"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(DISTINCT po_id) FROM bills")
                result = cursor.fetchone()
                return result[0] if result else 0
                
        except Exception as e:
            logger.error(f"Error getting unique POs count: {str(e)}")
            return 0

    def get_accrual_history(self, po_id: str, line_id: str, days: int = 30) -> List[Dict]:
        """Get accrual decision history for a PO line"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor(DictCursor)
                cursor.execute("""
                    SELECT * FROM accrual_decisions 
                    WHERE po_id = %s AND line_id = %s
                    AND created_at >= CURRENT_TIMESTAMP() - INTERVAL '%s DAYS'
                    ORDER BY created_at DESC
                """, (po_id, line_id, days))
                
                return cursor.fetchall()
                
        except Exception as e:
            logger.error(f"Error getting accrual history for {po_id}:{line_id}: {str(e)}")
            return []

    def cleanup_old_data(self, days: int = 90):
        """Clean up old data beyond specified days"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Clean up old accrual decisions (keep last 90 days by default)
                cursor.execute("""
                    DELETE FROM accrual_decisions 
                    WHERE created_at < CURRENT_TIMESTAMP() - INTERVAL '%s DAYS'
                """, (days,))
                
                decisions_deleted = cursor.rowcount
                
                # Clean up orphaned invoice data
                cursor.execute("""
                    DELETE FROM invoice_data 
                    WHERE bill_id NOT IN (SELECT bill_id FROM bills)
                """)
                
                invoices_deleted = cursor.rowcount
                
                logger.info(f"Cleanup completed: {decisions_deleted} old decisions, {invoices_deleted} orphaned invoices")
                
        except Exception as e:
            logger.error(f"Error cleaning up old data: {str(e)}")
            raise