import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import json
import base64
import hmac
import hashlib
import time
import urllib.parse

from config.settings import NetSuiteConfig
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

@dataclass
class POLine:
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
    delivery_date: Optional[datetime]
    prepaid_start_date: Optional[datetime]
    prepaid_end_date: Optional[datetime]
    remaining_balance: float

@dataclass
class Bill:
    bill_id: str
    po_id: str
    vendor_name: str
    amount: float
    currency: str
    posting_period: str
    payment_status: str
    invoice_file_url: Optional[str]
    created_date: datetime
    due_date: Optional[datetime]

class NetSuiteClient:
    def __init__(self):
        self.account_id = NetSuiteConfig.ACCOUNT_ID
        self.token_id = NetSuiteConfig.TOKEN_ID
        self.token_secret = NetSuiteConfig.TOKEN_SECRET
        self.consumer_key = NetSuiteConfig.CONSUMER_KEY
        self.consumer_secret = NetSuiteConfig.CONSUMER_SECRET
        
        if not all([self.account_id, self.token_id, self.token_secret, 
                   self.consumer_key, self.consumer_secret]):
            raise ValueError("NetSuite credentials not properly configured")
        
        self.base_url = f"https://{self.account_id}.suitetalk.api.netsuite.com"
        logger.info(f"NetSuite client initialized for account: {self.account_id}")

    def _generate_oauth_header(self, url: str, method: str = "GET") -> str:
        timestamp = str(int(time.time()))
        nonce = base64.b64encode(hashlib.sha256(str(time.time()).encode()).digest()).decode()[:32]
        
        oauth_params = {
            'oauth_consumer_key': self.consumer_key,
            'oauth_nonce': nonce,
            'oauth_signature_method': 'HMAC-SHA256',
            'oauth_timestamp': timestamp,
            'oauth_token': self.token_id,
            'oauth_version': '1.0'
        }
        
        signature_base = self._create_signature_base(method, url, oauth_params)
        signing_key = f"{urllib.parse.quote(self.consumer_secret)}&{urllib.parse.quote(self.token_secret)}"
        signature = base64.b64encode(
            hmac.new(signing_key.encode(), signature_base.encode(), hashlib.sha256).digest()
        ).decode()
        
        oauth_params['oauth_signature'] = signature
        
        auth_header = 'OAuth ' + ', '.join([f'{k}="{urllib.parse.quote(str(v))}"' for k, v in oauth_params.items()])
        return auth_header

    def _create_signature_base(self, method: str, url: str, params: Dict) -> str:
        encoded_params = '&'.join([f'{urllib.parse.quote(str(k))}={urllib.parse.quote(str(v))}' 
                                  for k, v in sorted(params.items())])
        return f"{method}&{urllib.parse.quote(url)}&{urllib.parse.quote(encoded_params)}"

    def _make_request(self, endpoint: str, method: str = "GET", data: Dict = None) -> Dict:
        url = f"{self.base_url}{endpoint}"
        headers = {
            'Authorization': self._generate_oauth_header(url, method),
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        try:
            if method == "GET":
                response = requests.get(url, headers=headers)
            else:
                response = requests.post(url, headers=headers, json=data)
            
            response.raise_for_status()
            logger.debug(f"NetSuite API call successful: {method} {endpoint}")
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"NetSuite API call failed: {method} {endpoint} - {str(e)}")
            raise

    def get_po_line_details(self, po_id: str, line_id: str) -> Optional[POLine]:
        try:
            endpoint = f"/services/rest/record/v1/purchaseorder/{po_id}"
            response = self._make_request(endpoint)
            
            po_data = response.get('data', {})
            lines = po_data.get('item', [])
            
            for line in lines:
                if str(line.get('line')) == str(line_id):
                    return POLine(
                        po_id=po_id,
                        line_id=line_id,
                        vendor_name=po_data.get('entity', {}).get('name', ''),
                        requestor=po_data.get('employee', {}).get('name', ''),
                        legal_entity=po_data.get('subsidiary', {}).get('name', ''),
                        currency=po_data.get('currency', {}).get('name', ''),
                        memo=po_data.get('memo', ''),
                        gl_account=line.get('account', {}).get('name', ''),
                        description=line.get('description', ''),
                        amount=float(line.get('amount', 0)),
                        delivery_date=self._parse_date(line.get('expectedreceiptdate')),
                        prepaid_start_date=self._parse_date(line.get('custcol_prepaid_start')),
                        prepaid_end_date=self._parse_date(line.get('custcol_prepaid_end')),
                        remaining_balance=float(line.get('quantityremaining', 0)) * float(line.get('rate', 0))
                    )
            
            logger.warning(f"Line {line_id} not found in PO {po_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error fetching PO line details for {po_id}:{line_id} - {str(e)}")
            return None

    def get_bills_for_po(self, po_id: str) -> List[Bill]:
        try:
            endpoint = f"/services/rest/query/v1/suiteql"
            query = f"""
                SELECT b.id, b.tranid, b.entity, b.total, b.currency, 
                       b.postingperiod, b.status, b.trandate, b.duedate
                FROM transaction b
                WHERE b.type = 'VendBill' 
                AND b.createdfrom = '{po_id}'
                AND b.mainline = 'T'
            """
            
            data = {"q": query}
            response = self._make_request(endpoint, "POST", data)
            
            bills = []
            for item in response.get('items', []):
                bills.append(Bill(
                    bill_id=item.get('id'),
                    po_id=po_id,
                    vendor_name=item.get('entity'),
                    amount=float(item.get('total', 0)),
                    currency=item.get('currency'),
                    posting_period=item.get('postingperiod'),
                    payment_status=item.get('status'),
                    invoice_file_url=None,  # Will be populated by download_invoice_files
                    created_date=self._parse_date(item.get('trandate')),
                    due_date=self._parse_date(item.get('duedate'))
                ))
            
            logger.info(f"Found {len(bills)} bills for PO {po_id}")
            return bills
            
        except Exception as e:
            logger.error(f"Error fetching bills for PO {po_id} - {str(e)}")
            return []

    def download_invoice_files(self, bill_id: str) -> List[str]:
        try:
            endpoint = f"/services/rest/record/v1/vendorbill/{bill_id}/file"
            response = self._make_request(endpoint)
            
            file_urls = []
            for file_info in response.get('items', []):
                file_id = file_info.get('id')
                file_name = file_info.get('name')
                
                download_endpoint = f"/services/rest/record/v1/file/{file_id}/content"
                file_response = self._make_request(download_endpoint)
                
                # Save file locally and return path
                file_path = self._save_invoice_file(bill_id, file_name, file_response)
                file_urls.append(file_path)
            
            logger.info(f"Downloaded {len(file_urls)} files for bill {bill_id}")
            return file_urls
            
        except Exception as e:
            logger.error(f"Error downloading invoice files for bill {bill_id} - {str(e)}")
            return []

    def _save_invoice_file(self, bill_id: str, file_name: str, content: bytes) -> str:
        from config.settings import INVOICES_DIR
        
        bill_dir = INVOICES_DIR / bill_id
        bill_dir.mkdir(exist_ok=True)
        
        file_path = bill_dir / file_name
        with open(file_path, 'wb') as f:
            f.write(content)
        
        return str(file_path)

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str.split('T')[0], '%Y-%m-%d')
        except (ValueError, AttributeError):
            return None

    def get_new_bills_since(self, last_sync_date: datetime) -> List[Bill]:
        try:
            date_str = last_sync_date.strftime('%Y-%m-%d')
            endpoint = f"/services/rest/query/v1/suiteql"
            query = f"""
                SELECT b.id, b.tranid, b.createdfrom, b.entity, b.total, b.currency, 
                       b.postingperiod, b.status, b.trandate, b.duedate
                FROM transaction b
                WHERE b.type = 'VendBill' 
                AND b.datecreated >= '{date_str}'
                AND b.mainline = 'T'
            """
            
            data = {"q": query}
            response = self._make_request(endpoint, "POST", data)
            
            bills = []
            for item in response.get('items', []):
                bills.append(Bill(
                    bill_id=item.get('id'),
                    po_id=item.get('createdfrom'),
                    vendor_name=item.get('entity'),
                    amount=float(item.get('total', 0)),
                    currency=item.get('currency'),
                    posting_period=item.get('postingperiod'),
                    payment_status=item.get('status'),
                    invoice_file_url=None,
                    created_date=self._parse_date(item.get('trandate')),
                    due_date=self._parse_date(item.get('duedate'))
                ))
            
            logger.info(f"Found {len(bills)} new bills since {date_str}")
            return bills
            
        except Exception as e:
            logger.error(f"Error fetching new bills since {date_str} - {str(e)}")
            return []