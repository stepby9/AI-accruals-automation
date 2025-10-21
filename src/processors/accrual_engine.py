"""
Accrual Decision Engine - Uses AI to analyze if accruals are needed for PO lines
"""

import json
import yaml
from typing import Dict, List
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from openai import OpenAI

from config.settings import OpenAIConfig
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class AccrualDecision:
    """Result of accrual analysis for a PO line"""
    po_number: str
    needs_accrual: bool
    accrual_amount: float
    reasoning: str
    short_summary: str
    confidence_score: float
    analyzed_at: datetime
    processing_time_seconds: float = 0.0
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_total: int = 0


class AccrualEngine:
    """
    Analyzes PO lines to determine if accruals are needed
    Uses AI to apply business rules and make decisions

    Note: Business rules (GL account exclusions, minimum balance thresholds) are
    pre-applied in the Snowflake view ACCRUALS_AUTOMATION_PO_ANALYSIS_INPUT,
    so all data received here is already filtered and ready for AI analysis.
    """

    def __init__(self, current_month: str = None):
        """
        Initialize the accrual engine

        Args:
            current_month: The month we're analyzing for (e.g., "February 2025")
                          If not provided, uses current month
        """
        if not OpenAIConfig.API_KEY:
            raise ValueError("OpenAI API key not configured")

        self.client = OpenAI(api_key=OpenAIConfig.API_KEY)

        # Load prompt configuration from YAML
        self._load_prompt_config()

        if current_month is None:
            now = datetime.now()
            self.current_month = now.strftime("%B %Y")
        else:
            self.current_month = current_month

        logger.info(f"Accrual engine initialized for month: {self.current_month}")

    def _load_prompt_config(self):
        """Load prompt configuration from YAML file"""
        yaml_path = Path(__file__).parent.parent.parent / "prompts" / "accrual_analysis.yaml"

        if not yaml_path.exists():
            raise FileNotFoundError(f"Prompt config not found: {yaml_path}")

        with open(yaml_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        self.system_prompt = config['system_prompt']
        self.user_prompt_template = config['user_prompt_template']
        self.model = config.get('model', 'gpt-4o')
        self.temperature = config.get('temperature')  # None if not specified
        self.response_format = config.get('response_format')  # None if not specified

        logger.info(f"Loaded prompt config from {yaml_path.name}, model: {self.model}")

    def analyze_po_line(self, po_line: Dict, related_bills: List[Dict]) -> AccrualDecision:
        """
        Analyze a single PO line to determine if accrual is needed

        Args:
            po_line: Dict with PO line data from Snowflake
            related_bills: List of dicts with related bill and invoice data

        Returns:
            AccrualDecision with analysis result
        """
        import time

        po_number = po_line.get('PO_NUMBER')
        logger.info(f"Analyzing PO {po_number} for accrual...")

        start_time = time.time()

        try:
            # Prepare data for AI analysis
            analysis_data = self._prepare_data_for_ai(po_line, related_bills)

            # Get AI decision
            ai_response = self._get_ai_decision(analysis_data)

            processing_time = time.time() - start_time

            # Parse and return decision
            decision = AccrualDecision(
                po_number=po_number,
                needs_accrual=ai_response.get('needs_accrual', False),
                accrual_amount=float(ai_response.get('accrual_amount', 0)),
                reasoning=ai_response.get('reasoning', ''),
                short_summary=ai_response.get('short_summary', ''),
                confidence_score=float(ai_response.get('confidence', 0)),
                analyzed_at=datetime.now(),
                processing_time_seconds=processing_time,
                tokens_input=ai_response.get('tokens_input', 0),
                tokens_output=ai_response.get('tokens_output', 0),
                tokens_total=ai_response.get('tokens_total', 0)
            )

            logger.info(f"PO {po_number}: Accrual={'YES' if decision.needs_accrual else 'NO'}, "
                       f"Amount={decision.accrual_amount}, Confidence={decision.confidence_score:.2f}, "
                       f"Tokens={decision.tokens_total} (in:{decision.tokens_input}, out:{decision.tokens_output}), "
                       f"Time={processing_time:.1f}s")

            return decision

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Error analyzing PO {po_number}: {str(e)}")
            return AccrualDecision(
                po_number=po_number,
                needs_accrual=False,
                accrual_amount=0.0,
                reasoning=f"ERROR: {str(e)}",
                short_summary=f"ERROR: {str(e)}",
                confidence_score=0.0,
                analyzed_at=datetime.now(),
                processing_time_seconds=processing_time,
                tokens_input=0,
                tokens_output=0,
                tokens_total=0
            )

    def _prepare_data_for_ai(self, po_line: Dict, related_bills: List[Dict]) -> Dict:
        """
        Prepare structured data for AI analysis

        Args:
            po_line: PO line data
            related_bills: Related bills and invoices

        Returns:
            Dict with formatted data for AI
        """
        from decimal import Decimal

        # Convert datetime/date/Decimal objects to strings for JSON serialization
        def serialize_value(val):
            if isinstance(val, (datetime, date)):
                return val.isoformat()
            elif isinstance(val, Decimal):
                return float(val)
            elif val is None:
                return None
            return val

        po_data = {k: serialize_value(v) for k, v in po_line.items()}
        bills_data = [{k: serialize_value(v) for k, v in bill.items()} for bill in related_bills]

        return {
            "current_analysis_month": self.current_month,
            "po_line": po_data,
            "related_bills": bills_data,
            "bill_count": len(related_bills)
        }

    def _get_ai_decision(self, analysis_data: Dict) -> Dict:
        """
        Send data to AI for accrual decision

        Args:
            analysis_data: Prepared data dict

        Returns:
            Dict with AI decision
        """
        # Format user prompt with template variables
        user_prompt = self.user_prompt_template.format(
            analysis_data=json.dumps(analysis_data, indent=2),
            current_month=self.current_month
        )

        try:
            # Build API call parameters - only include optional params if specified in YAML
            api_params = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            }

            # Add optional parameters only if they exist
            if hasattr(self, 'response_format') and self.response_format:
                api_params["response_format"] = self.response_format

            if hasattr(self, 'temperature') and self.temperature is not None:
                api_params["temperature"] = self.temperature

            response = self.client.chat.completions.create(**api_params)

            # Extract token usage
            usage = response.usage
            tokens_input = usage.prompt_tokens if usage else 0
            tokens_output = usage.completion_tokens if usage else 0
            tokens_total = usage.total_tokens if usage else 0

            result = json.loads(response.choices[0].message.content)

            # Add token info to result
            result['tokens_input'] = tokens_input
            result['tokens_output'] = tokens_output
            result['tokens_total'] = tokens_total

            return result

        except Exception as e:
            logger.error(f"Error getting AI decision: {str(e)}")
            raise
