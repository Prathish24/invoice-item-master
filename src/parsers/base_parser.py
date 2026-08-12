from abc import ABC, abstractmethod
from typing import Any


class BaseInvoiceParser(ABC):
    """
    Base interface for all invoice parsers.

    Every supplier-specific or generic parser should
    implement the parse() method.
    """

    @abstractmethod
    def parse(self, invoice_text: str) -> dict[str, Any]:
        """
        Parse raw invoice text into structured invoice data.

        Args:
            invoice_text: Raw text extracted from the invoice.

        Returns:
            Structured invoice dictionary.
        """
        pass