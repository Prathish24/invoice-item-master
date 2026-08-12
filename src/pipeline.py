from pathlib import Path
from typing import Any

from src.extraction.extraction_service import extract_invoice_text
from src.supplier.supplier_detector import detect_supplier
from src.supplier.layout_detector import detect_layout
from src.parsers.generic_parser import GenericInvoiceParser

from src.normalization.uom_normalizer import (
    normalize_uom,
    get_uom_multiplier,
)
from src.normalization.description_normalizer import normalize_description
from src.normalization.part_number_normalizer import normalize_part_number
from src.validation.invoice_validator import validate_invoice


def normalize_invoice(invoice: dict[str, Any]) -> dict[str, Any]:
    """Normalize extracted invoice data."""

    normalized = invoice.copy()
    normalized_line_items = []

    for item in invoice.get("line_items", []):

        normalized_item = item.copy()

        normalized_item["description"] = normalize_description(
            item.get("description")
        )

        normalized_item["manufacturer_part_number"] = (
            normalize_part_number(
                item.get("manufacturer_part_number")
            )
        )

        normalized_item["vendor_part_number"] = (
            normalize_part_number(
                item.get("vendor_part_number")
            )
        )

        normalized_item["uom"] = normalize_uom(
            item.get("uom")
        )

        normalized_item["uom_multiplier"] = get_uom_multiplier(
            item.get("uom")
        )

        normalized_line_items.append(normalized_item)

    normalized["line_items"] = normalized_line_items

    return normalized


def process_invoice(pdf_path: str | Path) -> dict[str, Any]:
    """
    Complete invoice processing pipeline.

    PDF
      ↓
    Text / OCR
      ↓
    Supplier Detection
      ↓
    Layout Detection
      ↓
    Generic Parser
      ↓
    Normalization
      ↓
    Validation
    """

    pdf_path = Path(pdf_path)

    # --------------------------------------------------
    # 1. PDF extraction
    # --------------------------------------------------

    extraction_result = extract_invoice_text(pdf_path)

    if not extraction_result["success"]:
        return {
            "file_name": pdf_path.name,
            "success": False,
            "extraction": extraction_result,
            "supplier": None,
            "layout": None,
            "invoice": None,
            "validation": {
                "status": "FAIL",
                "errors": ["Could not extract text from PDF"],
                "warnings": [],
                "is_valid": False,
            },
        }

    invoice_text = extraction_result["text"]

    # --------------------------------------------------
    # 2. Supplier detection
    # --------------------------------------------------

    supplier = detect_supplier(invoice_text)

    # --------------------------------------------------
    # 3. Layout detection
    # --------------------------------------------------

    layout = detect_layout(
        invoice_text,
        supplier,
    )

    # --------------------------------------------------
    # 4. Parser selection
    # --------------------------------------------------

    # For now we use GenericParser for ALL suppliers.
    # Later, specialized parsers can be added only when
    # a recurring supplier/layout requires one.

    parser = GenericInvoiceParser()

    invoice_data = parser.parse(invoice_text)

    # --------------------------------------------------
    # 5. Normalization
    # --------------------------------------------------

    normalized_invoice = normalize_invoice(
        invoice_data
    )

    # --------------------------------------------------
    # 6. Validation
    # --------------------------------------------------

    validation_result = validate_invoice(
        normalized_invoice
    )

    # --------------------------------------------------
    # 7. Final result
    # --------------------------------------------------

    return {
        "file_name": pdf_path.name,
        "success": True,

        "extraction_method": (
            extraction_result["extraction_method"]
        ),

        "supplier": supplier,

        "layout": layout,

        "invoice": normalized_invoice,

        "validation": validation_result,
    }