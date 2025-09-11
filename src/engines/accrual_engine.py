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

logger = setup_logger(__name__)

@dataclass
class AccrualDecision:
    po_id: str
    line_id: str
    bill_id: Optional[str]
    accrual_amount_usd: float
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
        
        openai.api_key = OpenAIConfig.API_KEY
        self.excluded_gl_accounts = set(AppConfig.EXCLUDED_GL_ACCOUNTS)
        self.min_accrual_amount_usd = AppConfig.MIN_ACCRUAL_AMOUNT_USD
        
        logger.info("Accrual engine initialized")

    def analyze_accrual_need(self, po_line: POLine, bills: List[Bill], 
                           invoice_data_list: List[InvoiceData]) -> AccrualDecision:
        try:
            logger.info(f"Analyzing accrual need for PO {po_line.po_id}:{po_line.line_id}")
            
            # Apply business rules first
            if self._should_exclude_by_gl_account(po_line.gl_account):
                return self._create_no_accrual_decision(
                    po_line, None, f"Excluded GL account: {po_line.gl_account}"
                )
            
            remaining_balance_usd = self._convert_to_usd(
                po_line.remaining_balance, po_line.currency
            )
            
            if remaining_balance_usd < self.min_accrual_amount_usd:
                return self._create_no_accrual_decision(
                    po_line, None, 
                    f"Remaining balance ${remaining_balance_usd:,.2f} USD < ${self.min_accrual_amount_usd:,.2f} USD threshold"
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

    def _convert_to_usd(self, amount: float, currency: str) -> float:
        """Convert amount to USD. For now, simplified conversion."""
        if currency.upper() == 'USD':
            return amount
        
        # TODO: Implement actual currency conversion using exchange rates
        # For now, use simplified rates
        conversion_rates = {
            'EUR': 1.1,
            'GBP': 1.25,
            'CAD': 0.75,
            'JPY': 0.007,
        }
        
        rate = conversion_rates.get(currency.upper(), 1.0)
        return amount * rate

    def _ai_analyze_accrual(self, po_line: POLine, bills: List[Bill], 
                          invoice_data_list: List[InvoiceData]) -> AccrualDecision:
        try:
            prompt = self._create_analysis_prompt(po_line, bills, invoice_data_list)
            
            response = openai.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a financial expert specializing in accrual accounting. Analyze the provided data and make accrual decisions based on accounting principles and business rules."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                max_tokens=1000,
                temperature=0.1
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Convert to AccrualDecision object
            return AccrualDecision(
                po_id=po_line.po_id,
                line_id=po_line.line_id,
                bill_id=result.get('bill_id'),
                accrual_amount_usd=float(result.get('accrual_amount_usd', 0)),
                reasoning=result.get('reasoning', ''),
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

    def _create_analysis_prompt(self, po_line: POLine, bills: List[Bill], 
                              invoice_data_list: List[InvoiceData]) -> str:
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        prompt = f"""
        Analyze whether an accrual is needed for this Purchase Order line as of {current_date}.

        PO LINE DETAILS:
        - PO ID: {po_line.po_id}
        - Line ID: {po_line.line_id}
        - Vendor: {po_line.vendor_name}
        - GL Account: {po_line.gl_account}
        - Description: {po_line.description}
        - Total Amount: {po_line.amount} {po_line.currency}
        - Remaining Balance: {po_line.remaining_balance} {po_line.currency}
        - Delivery Date: {po_line.delivery_date}
        - Prepaid Start: {po_line.prepaid_start_date}
        - Prepaid End: {po_line.prepaid_end_date}

        RELATED BILLS:
        """
        
        for bill in bills:
            prompt += f"""
        - Bill ID: {bill.bill_id}
        - Amount: {bill.amount} {bill.currency}
        - Status: {bill.payment_status}
        - Posting Period: {bill.posting_period}
        - Created: {bill.created_date}
        """
        
        prompt += "\nINVOICE DATA:\n"
        for invoice in invoice_data_list:
            prompt += f"""
        - Invoice: {invoice.invoice_number}
        - Service Description: {invoice.service_description}
        - Service Period: {invoice.service_period_start} to {invoice.service_period_end}
        - Amount: {invoice.total_amount} {invoice.currency}
        - Line Items: {json.dumps(invoice.line_items, indent=2)}
        """
        
        prompt += f"""

        BUSINESS RULES:
        1. No negative accruals for prepaid services
        2. Consider if services were provided but not yet paid
        3. Estimate monthly accrual amounts
        4. Check if we paid for previous months already
        5. Current month to accrue for: {current_date[:7]} (YYYY-MM)

        ANALYSIS INSTRUCTIONS:
        1. Determine if an accrual is needed based on:
           - Has the service been provided but not yet expensed?
           - Is there an unpaid portion that should be accrued?
           - For subscription services, calculate monthly accrual amount
        
        2. Calculate the accrual amount in USD for the current month only
        
        3. Consider payment history and previous accruals
        
        4. Provide detailed reasoning for the decision

        Return response as valid JSON:
        {{
            "bill_id": "string or null - which bill this relates to",
            "accrual_amount_usd": "number - amount to accrue in USD (0 if no accrual needed)",
            "reasoning": "string - detailed explanation of the decision",
            "confidence_score": "number between 0 and 1"
        }}
        """
        
        return prompt

    def _create_no_accrual_decision(self, po_line: POLine, bill_id: Optional[str], 
                                  reasoning: str) -> AccrualDecision:
        return AccrualDecision(
            po_id=po_line.po_id,
            line_id=po_line.line_id,
            bill_id=bill_id,
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