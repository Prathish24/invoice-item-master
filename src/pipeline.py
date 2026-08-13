from pathlib import Path
from typing import Any

from src.extraction.extraction_service import (
    extract_invoice_text,
)
from src.supplier.supplier_detector import (
    detect_supplier,
)
from src.supplier.layout_detector import (
    detect_layout,
)
from src.parsers.generic_parser import (
    GenericInvoiceParser,
)

from src.normalization.uom_normalizer import (
    normalize_uom,
    get_uom_multiplier,
)
from src.normalization.description_normalizer import (
    normalize_description,
)
from src.normalization.part_number_normalizer import (
    normalize_part_number,
)
from src.validation.invoice_validator import (
    validate_invoice,
)


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_invoice(
    invoice: dict[str, Any],
) -> dict[str, Any]:
    """
    Normalize extracted invoice data.
    """

    normalized = invoice.copy()

    normalized_line_items = []

    for item in invoice.get(
        "line_items",
        [],
    ):

        normalized_item = item.copy()

        # ----------------------------------------------------
        # Description
        # ----------------------------------------------------

        normalized_item["description"] = (
            normalize_description(
                item.get("description")
            )
        )

        # ----------------------------------------------------
        # Manufacturer Part Number
        # ----------------------------------------------------

        normalized_item[
            "manufacturer_part_number"
        ] = normalize_part_number(
            item.get(
                "manufacturer_part_number"
            )
        )

        # ----------------------------------------------------
        # Vendor Part Number
        # ----------------------------------------------------

        normalized_item[
            "vendor_part_number"
        ] = normalize_part_number(
            item.get(
                "vendor_part_number"
            )
        )

        # ----------------------------------------------------
        # UOM
        # ----------------------------------------------------

        normalized_item["uom"] = (
            normalize_uom(
                item.get("uom")
            )
        )

        # ----------------------------------------------------
        # UOM multiplier
        # ----------------------------------------------------

        normalized_item[
            "uom_multiplier"
        ] = get_uom_multiplier(
            item.get("uom")
        )

        normalized_line_items.append(
            normalized_item
        )

    normalized["line_items"] = (
        normalized_line_items
    )

    return normalized


# ============================================================
# PROCESS INVOICE
# ============================================================

def process_invoice(
    pdf_path: str | Path,
) -> dict[str, Any]:
    """
    Complete invoice processing pipeline.

    PDF
      ↓
    Text / OCR
      ↓
    Layout-aware extraction
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

    # ========================================================
    # 1. PDF EXTRACTION
    # ========================================================

    extraction_result = extract_invoice_text(
        pdf_path
    )

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
                "errors": [
                    "Could not extract text from PDF"
                ],
                "warnings": [],
                "is_valid": False,
            },
        }

    # ========================================================
    # 2. CHOOSE BEST TEXT REPRESENTATION
    # ========================================================

    # For normal PDFs, extraction_service now provides
    # layout-aware text.
    #
    # For OCR PDFs, extraction_text will contain OCR text.

    invoice_text = extraction_result.get(
        "extraction_text"
    )

    # Safety fallback for older extraction results
    if not invoice_text:
        invoice_text = extraction_result.get(
            "text",
            ""
        )

    if not invoice_text.strip():

        return {
            "file_name": pdf_path.name,

            "success": False,

            "extraction": extraction_result,

            "supplier": None,

            "layout": None,

            "invoice": None,

            "validation": {
                "status": "FAIL",
                "errors": [
                    "Extracted invoice text is empty"
                ],
                "warnings": [],
                "is_valid": False,
            },
        }

    # ========================================================
    # 3. SUPPLIER DETECTION
    # ========================================================

    supplier = detect_supplier(
        invoice_text
    )

    # ========================================================
    # 4. LAYOUT DETECTION
    # ========================================================

    layout = detect_layout(
        invoice_text,
        supplier,
    )

    # ========================================================
    # 5. PARSER SELECTION
    # ========================================================

    # Generic parser is currently used for all suppliers.
    #
    # Later, supplier-specific parsers can be introduced
    # only when a recurring supplier/layout requires one.

    parser = GenericInvoiceParser()

    invoice_data = parser.parse(
        invoice_text
    )

    # ========================================================
    # 6. NORMALIZATION
    # ========================================================

    normalized_invoice = normalize_invoice(
        invoice_data
    )

    # ========================================================
    # 7. VALIDATION
    # ========================================================

    validation_result = validate_invoice(
        normalized_invoice
    )

    # ========================================================
    # 8. FINAL RESULT
    # ========================================================

    return {
        "file_name": pdf_path.name,

        "success": True,

        "extraction_method": (
            extraction_result[
                "extraction_method"
            ]
        ),

        "supplier": supplier,

        "layout": layout,

        "invoice": normalized_invoice,

        "validation": validation_result,
    }