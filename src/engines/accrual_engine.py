import openai
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal
import json

from config.settings import OpenAIConfig, AppConfig
from src.clients.netsuite_client import POLine, Bill
from src.processors.invoice_processor import InvoiceData
from src.utils.logger import setup_logger
from src.utils.prompt_manager import get_system_prompt, get_user_prompt, get_model_config

logger = setup_logger(__name__)

@dataclass
class AccrualDecision:
    po_id: str
    line_id: str
    bill_id: Optional[str]
    accrual_amount_local: float  # Accrual amount in PO's local currency
    accrual_amount_usd: float    # Converted to USD for reporting
    reasoning: str
    confidence_score: float
    created_at: datetime
    gl_account: str
    vendor_name: str
    remaining_balance: float
    currency: str

class AccrualEngine:
    def __init__(self):
        if not OpenAIConfig.API_KEY:
            raise ValueError("OpenAI API key not configured")
        
        # Use legacy OpenAI initialization (compatible with v1.3.5)
        openai.api_key = OpenAIConfig.API_KEY
        self.excluded_gl_accounts = set(AppConfig.EXCLUDED_GL_ACCOUNTS)
        self.min_accrual_amount_usd = AppConfig.MIN_ACCRUAL_AMOUNT_USD
        
        logger.info("Accrual engine initialized")

    def _convert_accrual_to_usd(self, accrual_local: float, po_line: POLine) -> float:
        """Convert accrual amount from local currency to USD using PO's exchange rate"""
        if po_line.currency.upper() == 'USD' or po_line.amount == 0:
            return accrual_local
        
        # Use the PO's own USD/local currency ratio
        po_exchange_rate = po_line.amount_usd / po_line.amount if po_line.amount != 0 else 1.0
        accrual_usd = accrual_local * po_exchange_rate
        
        logger.debug(f"Converted accrual {accrual_local} {po_line.currency} to ${accrual_usd:,.2f} USD (rate: {po_exchange_rate:.4f})")
        return accrual_usd

    def analyze_accrual_need(self, po_line: POLine, bills: List[Bill], 
                           invoice_data_list: List[InvoiceData]) -> AccrualDecision:
        try:
            logger.info(f"Analyzing accrual need for PO {po_line.po_id}:{po_line.line_id}")
            
            # Apply business rules first
            if self._should_exclude_by_gl_account(po_line.gl_account):
                return self._create_no_accrual_decision(
                    po_line, None, f"Excluded GL account: {po_line.gl_account}"
                )
            
            # Note: USD remaining balance filtering is already done in data sync manager
            # This is just a safety check
            if po_line.remaining_balance_usd < self.min_accrual_amount_usd:
                return self._create_no_accrual_decision(
                    po_line, None, 
                    f"Remaining balance ${po_line.remaining_balance_usd:,.2f} USD < ${self.min_accrual_amount_usd:,.2f} USD threshold"
                )
            
            # Use AI to analyze complex scenarios
            return self._ai_analyze_accrual(po_line, bills, invoice_data_list)
            
        except Exception as e:
            logger.error(f"Error analyzing accrual for PO {po_line.po_id}:{po_line.line_id} - {str(e)}")
            return self._create_no_accrual_decision(
                po_line, None, f"Error in analysis: {str(e)}"
            )

    def _should_exclude_by_gl_account(self, gl_account: str) -> bool:
        if not gl_account:
            return False
        
        # Extract account number from account string (format might be "4550 - Account Name")
        account_number = gl_account.split(' ')[0].strip()
        return account_number in self.excluded_gl_accounts


    def _ai_analyze_accrual(self, po_line: POLine, bills: List[Bill], 
                          invoice_data_list: List[InvoiceData]) -> AccrualDecision:
        try:
            # Prepare template variables
            template_vars = self._prepare_prompt_variables(po_line, bills, invoice_data_list)
            
            # Get prompts and model config from prompt manager
            system_prompt = get_system_prompt("accrual_analysis")
            user_prompt = get_user_prompt("accrual_analysis", **template_vars)
            model_config = get_model_config("accrual_analysis")
            
            # Build API parameters dynamically based on model requirements
            api_params = {
                'model': model_config['model'],
                'messages': [
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user", 
                        "content": user_prompt
                    }
                ]
            }
            
            # Add token limit parameter (varies by model)
            if 'max_completion_tokens' in model_config:
                api_params['max_completion_tokens'] = model_config['max_completion_tokens']
            elif 'max_tokens' in model_config:
                api_params['max_tokens'] = model_config['max_tokens']
            
            # Add temperature if supported
            if 'temperature' in model_config:
                api_params['temperature'] = model_config['temperature']
            
            response = openai.chat.completions.create(**api_params)
            
            result = json.loads(response.choices[0].message.content)
            
            # Get accrual amount in local currency from AI response
            accrual_amount_local = float(result.get('accrual_amount_local', 0))
            
            # Convert to USD using PO's exchange rate for threshold check
            accrual_amount_usd = self._convert_accrual_to_usd(accrual_amount_local, po_line)
            
            # Apply USD threshold - if converted amount < $5,000 USD, set to 0
            if accrual_amount_usd < self.min_accrual_amount_usd and accrual_amount_local > 0:
                logger.info(f"Accrual ${accrual_amount_usd:,.2f} USD < ${self.min_accrual_amount_usd:,.2f} threshold, setting to $0")
                accrual_amount_local = 0
                accrual_amount_usd = 0
                reasoning = result.get('reasoning', '') + f" [Adjusted to $0: calculated accrual ${accrual_amount_usd:,.2f} USD < ${self.min_accrual_amount_usd:,.2f} USD threshold]"
            else:
                reasoning = result.get('reasoning', '')
            
            # Convert to AccrualDecision object
            return AccrualDecision(
                po_id=po_line.po_id,
                line_id=po_line.line_id,
                bill_id=result.get('bill_id'),
                accrual_amount_local=accrual_amount_local,
                accrual_amount_usd=accrual_amount_usd,
                reasoning=reasoning,
                confidence_score=float(result.get('confidence_score', 0.5)),
                created_at=datetime.now(),
                gl_account=po_line.gl_account,
                vendor_name=po_line.vendor_name,
                remaining_balance=po_line.remaining_balance,
                currency=po_line.currency
            )
            
        except Exception as e:
            logger.error(f"Error in AI analysis: {str(e)}")
            return self._create_no_accrual_decision(
                po_line, None, f"AI analysis failed: {str(e)}"
            )

    def _prepare_prompt_variables(self, po_line: POLine, bills: List[Bill], 
                                invoice_data_list: List[InvoiceData]) -> Dict[str, Any]:
        """Prepare all template variables needed for the accrual analysis prompt"""
        current_date = datetime.now().strftime('%Y-%m-%d')
        current_month = current_date[:7]
        
        # Prepare bills section
        bills_section = ""
        for bill in bills:
            bills_section += f"""
        - Bill ID: {bill.bill_id}
        - Amount: {bill.amount} {bill.currency}
        - Status: {bill.payment_status}
        - Posting Period: {bill.posting_period}
        - Created: {bill.created_date}
        """
        
        if not bills_section.strip():
            bills_section = "No related bills found."
        
        # Prepare invoices section
        invoices_section = ""
        for invoice in invoice_data_list:
            invoices_section += f"""
        - Invoice: {invoice.invoice_number}
        - Service Description: {invoice.service_description}
        - Service Period: {invoice.service_period_start} to {invoice.service_period_end}
        - Amount: {invoice.total_amount} {invoice.currency}
        - Line Items: {json.dumps(invoice.line_items, indent=2)}
        """
        
        if not invoices_section.strip():
            invoices_section = "No invoice data available."
        
        # Return all template variables
        return {
            'current_date': current_date,
            'current_month': current_month,
            'po_id': po_line.po_id,
            'line_id': po_line.line_id,
            'vendor_name': po_line.vendor_name,
            'gl_account': po_line.gl_account,
            'description': po_line.description,
            'amount': po_line.amount,
            'amount_usd': po_line.amount_usd,
            'remaining_balance': po_line.remaining_balance,
            'remaining_balance_usd': po_line.remaining_balance_usd,
            'currency': po_line.currency,
            'delivery_date': po_line.delivery_date or 'Not specified',
            'prepaid_start_date': po_line.prepaid_start_date or 'Not specified',
            'prepaid_end_date': po_line.prepaid_end_date or 'Not specified',
            'bills_section': bills_section.strip(),
            'invoices_section': invoices_section.strip()
        }

    def _create_no_accrual_decision(self, po_line: POLine, bill_id: Optional[str], 
                                  reasoning: str) -> AccrualDecision:
        return AccrualDecision(
            po_id=po_line.po_id,
            line_id=po_line.line_id,
            bill_id=bill_id,
            accrual_amount_local=0.0,
            accrual_amount_usd=0.0,
            reasoning=reasoning,
            confidence_score=1.0,
            created_at=datetime.now(),
            gl_account=po_line.gl_account,
            vendor_name=po_line.vendor_name,
            remaining_balance=po_line.remaining_balance,
            currency=po_line.currency
        )

    def batch_analyze_accruals(self, po_data: List[Dict[str, Any]], 
                              all_bills: Dict[str, List[Bill]], 
                              all_invoice_data: Dict[str, List[InvoiceData]]) -> List[AccrualDecision]:
        """Analyze accruals for a batch of PO lines"""
        decisions = []
        
        for po_info in po_data:
            try:
                po_line = POLine(**po_info)
                bills = all_bills.get(po_line.po_id, [])
                invoice_data = []
                
                # Collect invoice data for all bills related to this PO
                for bill in bills:
                    invoice_data.extend(all_invoice_data.get(bill.bill_id, []))
                
                decision = self.analyze_accrual_need(po_line, bills, invoice_data)
                decisions.append(decision)
                
            except Exception as e:
                logger.error(f"Error processing PO data: {str(e)}")
                continue
        
        logger.info(f"Completed batch analysis of {len(decisions)} PO lines")
        return decisions

    def get_monthly_accrual_summary(self, decisions: List[AccrualDecision]) -> Dict[str, Any]:
        """Generate summary statistics for monthly accruals"""
        total_accrual = sum(d.accrual_amount_usd for d in decisions)
        accrual_count = sum(1 for d in decisions if d.accrual_amount_usd > 0)
        
        # Group by GL account
        gl_summary = {}
        for decision in decisions:
            gl_account = decision.gl_account
            if gl_account not in gl_summary:
                gl_summary[gl_account] = {
                    'count': 0,
                    'total_amount': 0,
                    'decisions': []
                }
            
            if decision.accrual_amount_usd > 0:
                gl_summary[gl_account]['count'] += 1
                gl_summary[gl_account]['total_amount'] += decision.accrual_amount_usd
                gl_summary[gl_account]['decisions'].append(decision)
        
        return {
            'total_accrual_amount_usd': total_accrual,
            'total_lines_analyzed': len(decisions),
            'lines_with_accruals': accrual_count,
            'lines_without_accruals': len(decisions) - accrual_count,
            'gl_account_summary': gl_summary,
            'generated_at': datetime.now().isoformat()
        }