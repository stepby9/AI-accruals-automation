import openai
import base64
import mimetypes
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import json
import fitz  # PyMuPDF
from PIL import Image
import io

from config.settings import OpenAIConfig
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

@dataclass
class InvoiceData:
    bill_id: str
    vendor_name: str
    invoice_number: str
    invoice_date: Optional[datetime]
    service_description: str
    service_period_start: Optional[datetime]
    service_period_end: Optional[datetime]
    line_items: List[Dict[str, Any]]
    total_amount: float
    currency: str
    language: str
    confidence_score: float
    extracted_at: datetime
    file_path: str

class InvoiceProcessor:
    def __init__(self):
        if not OpenAIConfig.API_KEY:
            raise ValueError("OpenAI API key not configured")
        
        openai.api_key = OpenAIConfig.API_KEY
        self.model = OpenAIConfig.MODEL
        self.max_tokens = OpenAIConfig.MAX_TOKENS
        
        logger.info("Invoice processor initialized with OpenAI API")

    def process_invoice(self, file_path: str, bill_id: str) -> Optional[InvoiceData]:
        try:
            logger.info(f"Processing invoice: {file_path} for bill {bill_id}")
            
            file_type = self._get_file_type(file_path)
            
            if file_type == 'pdf':
                return self._process_pdf(file_path, bill_id)
            elif file_type in ['jpg', 'jpeg', 'png', 'gif', 'bmp']:
                return self._process_image(file_path, bill_id)
            elif file_type in ['xlsx', 'xls']:
                return self._process_excel(file_path, bill_id)
            elif file_type in ['docx', 'doc']:
                return self._process_word(file_path, bill_id)
            else:
                logger.warning(f"Unsupported file type: {file_type} for {file_path}")
                return None
                
        except Exception as e:
            logger.error(f"Error processing invoice {file_path}: {str(e)}")
            return None

    def _get_file_type(self, file_path: str) -> str:
        return Path(file_path).suffix.lower().lstrip('.')

    def _process_pdf(self, file_path: str, bill_id: str) -> Optional[InvoiceData]:
        try:
            doc = fitz.open(file_path)
            
            # Extract text from all pages
            text_content = ""
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text_content += page.get_text()
            
            # Convert first page to image for visual analysis
            first_page = doc.load_page(0)
            pix = first_page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom
            img_data = pix.tobytes("png")
            
            doc.close()
            
            return self._analyze_with_openai(
                text_content=text_content,
                image_data=img_data,
                file_path=file_path,
                bill_id=bill_id
            )
            
        except Exception as e:
            logger.error(f"Error processing PDF {file_path}: {str(e)}")
            return None

    def _process_image(self, file_path: str, bill_id: str) -> Optional[InvoiceData]:
        try:
            with open(file_path, 'rb') as f:
                image_data = f.read()
            
            return self._analyze_with_openai(
                text_content="",
                image_data=image_data,
                file_path=file_path,
                bill_id=bill_id
            )
            
        except Exception as e:
            logger.error(f"Error processing image {file_path}: {str(e)}")
            return None

    def _process_excel(self, file_path: str, bill_id: str) -> Optional[InvoiceData]:
        try:
            import pandas as pd
            
            # Read all sheets
            excel_data = pd.read_excel(file_path, sheet_name=None)
            
            text_content = "Excel file contents:\n"
            for sheet_name, df in excel_data.items():
                text_content += f"\n--- Sheet: {sheet_name} ---\n"
                text_content += df.to_string(max_rows=50)
            
            return self._analyze_with_openai(
                text_content=text_content,
                image_data=None,
                file_path=file_path,
                bill_id=bill_id
            )
            
        except Exception as e:
            logger.error(f"Error processing Excel {file_path}: {str(e)}")
            return None

    def _process_word(self, file_path: str, bill_id: str) -> Optional[InvoiceData]:
        try:
            from docx import Document
            
            doc = Document(file_path)
            text_content = ""
            
            for paragraph in doc.paragraphs:
                text_content += paragraph.text + "\n"
            
            # Extract tables
            for table in doc.tables:
                for row in table.rows:
                    row_text = " | ".join([cell.text for cell in row.cells])
                    text_content += row_text + "\n"
            
            return self._analyze_with_openai(
                text_content=text_content,
                image_data=None,
                file_path=file_path,
                bill_id=bill_id
            )
            
        except Exception as e:
            logger.error(f"Error processing Word document {file_path}: {str(e)}")
            return None

    def _analyze_with_openai(self, text_content: str, image_data: bytes, 
                           file_path: str, bill_id: str) -> Optional[InvoiceData]:
        try:
            prompt = self._get_analysis_prompt()
            
            messages = [
                {
                    "role": "system",
                    "content": "You are an expert invoice data extraction system. Extract structured data from invoices and return valid JSON."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt}
                    ]
                }
            ]
            
            if text_content:
                messages[1]["content"].append({
                    "type": "text", 
                    "text": f"\nExtracted text content:\n{text_content[:8000]}"  # Limit text length
                })
            
            if image_data:
                base64_image = base64.b64encode(image_data).decode('utf-8')
                messages[1]["content"].append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64_image}",
                        "detail": "high"
                    }
                })
            
            response = openai.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=0.1
            )
            
            result = response.choices[0].message.content
            
            # Parse JSON response
            invoice_data_dict = json.loads(result)
            
            # Convert to InvoiceData object
            return self._dict_to_invoice_data(invoice_data_dict, bill_id, file_path)
            
        except Exception as e:
            logger.error(f"Error analyzing with OpenAI for {file_path}: {str(e)}")
            return None

    def _get_analysis_prompt(self) -> str:
        return """
        Extract the following information from the invoice and return it as valid JSON:

        {
            "vendor_name": "string - company/vendor that issued the invoice",
            "invoice_number": "string - invoice number",
            "invoice_date": "YYYY-MM-DD or null",
            "service_description": "string - description of services/products",
            "service_period_start": "YYYY-MM-DD or null - when service period starts",
            "service_period_end": "YYYY-MM-DD or null - when service period ends", 
            "line_items": [
                {
                    "description": "string - line item description",
                    "amount": "number - line item amount",
                    "period_start": "YYYY-MM-DD or null",
                    "period_end": "YYYY-MM-DD or null"
                }
            ],
            "total_amount": "number - total invoice amount",
            "currency": "string - currency code (USD, EUR, etc.)",
            "language": "string - detected language of invoice",
            "confidence_score": "number between 0 and 1 - confidence in extraction accuracy"
        }

        Important guidelines:
        1. If the invoice is in a foreign language, translate the service descriptions to English
        2. Look for service periods, subscription periods, or billing periods
        3. Extract all line items with their individual amounts
        4. Be very careful with date formats - use YYYY-MM-DD only
        5. For confidence_score, consider text clarity, completeness of data found
        6. Return only valid JSON, no additional text or explanations
        """

    def _dict_to_invoice_data(self, data_dict: Dict, bill_id: str, file_path: str) -> InvoiceData:
        return InvoiceData(
            bill_id=bill_id,
            vendor_name=data_dict.get('vendor_name', ''),
            invoice_number=data_dict.get('invoice_number', ''),
            invoice_date=self._parse_date(data_dict.get('invoice_date')),
            service_description=data_dict.get('service_description', ''),
            service_period_start=self._parse_date(data_dict.get('service_period_start')),
            service_period_end=self._parse_date(data_dict.get('service_period_end')),
            line_items=data_dict.get('line_items', []),
            total_amount=float(data_dict.get('total_amount', 0)),
            currency=data_dict.get('currency', 'USD'),
            language=data_dict.get('language', 'en'),
            confidence_score=float(data_dict.get('confidence_score', 0.5)),
            extracted_at=datetime.now(),
            file_path=file_path
        )

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, '%Y-%m-%d')
        except (ValueError, TypeError):
            return None

    def process_multiple_invoices(self, invoice_files: List[str], bill_id: str) -> List[InvoiceData]:
        results = []
        
        for file_path in invoice_files:
            result = self.process_invoice(file_path, bill_id)
            if result:
                results.append(result)
        
        logger.info(f"Processed {len(results)} invoices successfully for bill {bill_id}")
        return results

    def is_invoice_already_processed(self, bill_id: str, database) -> bool:
        """Check if invoice for this bill is already processed"""
        try:
            # This will be implemented when database is created
            # For now, return False to process all invoices
            return False
        except Exception as e:
            logger.error(f"Error checking if invoice processed for bill {bill_id}: {str(e)}")
            return False