from typing import Any

from src.parsers.base_parser import BaseInvoiceParser
from src.llm.invoice_extractor import extract_invoice_data


class GenericInvoiceParser(BaseInvoiceParser):
    """
    Generic parser for invoices that do not have
    a dedicated supplier-specific parser.

    Uses Groq to convert raw invoice text into
    the standard Item Master structure.
    """

    def parse(self, invoice_text: str) -> dict[str, Any]:
        if not invoice_text:
            raise ValueError("Invoice text is empty")

        return extract_invoice_data(invoice_text)