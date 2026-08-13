from pathlib import Path

from .pdf_classifier import classify_pdf
from .pdf_text_extractor import (
    extract_text_from_pdf,
    extract_layout_aware_text,
)
from .ocr_extractor import extract_text_with_ocr


def extract_invoice_text(pdf_path: str | Path) -> dict:
    """
    Extract text from an invoice PDF.

    For normal/selectable-text PDFs:
        PyMuPDF extracts both normal text and
        layout-aware text using word coordinates.

    For scanned/image PDFs:
        Falls back to Tesseract OCR.

    The layout-aware text is preferred for normal PDFs
    because invoice tables depend on column positions.
    """

    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        return {
            "file_name": pdf_path.name,
            "file_path": str(pdf_path),
            "extraction_method": "ERROR",
            "text": "",
            "layout_text": "",
            "success": False,
            "error": f"PDF not found: {pdf_path}",
        }

    # --------------------------------------------------------
    # Classify PDF
    # --------------------------------------------------------

    extraction_type = classify_pdf(
        pdf_path
    )

    # --------------------------------------------------------
    # NORMAL TEXT PDF
    # --------------------------------------------------------

    if extraction_type == "TEXT":

        # Original plain text extraction
        text = extract_text_from_pdf(
            pdf_path
        )

        # New layout-aware extraction
        layout_text = extract_layout_aware_text(
            pdf_path
        )

        # ----------------------------------------------------
        # Combine both representations.
        #
        # Natural reading-order text ("text") is preferred for
        # header fields (vendor, customer, invoice number,
        # dates) because invoices commonly print two blocks
        # side-by-side (e.g. Vendor info next to Invoice#/Date,
        # or Bill To next to Ship To). The row-based layout
        # text reconstructs rows purely from y-position, which
        # interleaves the words of side-by-side blocks together
        # and makes it easy to misattribute a value to the
        # wrong block.
        #
        # The layout-aware view is still valuable for line-item
        # tables, where column alignment via x-position matters.
        # So it is appended as a clearly labeled supplementary
        # section rather than replacing the natural text.
        # ----------------------------------------------------

        if layout_text and layout_text.strip():

            extraction_text = (
                text
                + "\n\n"
                + "================================================\n"
                + "COLUMN / TABLE VIEW (word x-positions)\n"
                + "Use this section ONLY to line up table columns\n"
                + "for the line items. Header fields such as vendor,\n"
                + "customer, invoice number, and dates should be\n"
                + "read from the natural text above, not from this\n"
                + "coordinate view.\n"
                + "================================================\n"
                + layout_text
            )

        else:

            extraction_text = text

        return {
            "file_name": pdf_path.name,
            "file_path": str(pdf_path),
            "extraction_method": "TEXT_LAYOUT",
            "text": text,
            "layout_text": layout_text,
            "extraction_text": extraction_text,
            "success": bool(
                extraction_text.strip()
            ),
        }

    # --------------------------------------------------------
    # SCANNED / IMAGE PDF
    # --------------------------------------------------------

    else:

        text = extract_text_with_ocr(
            pdf_path
        )

        return {
            "file_name": pdf_path.name,
            "file_path": str(pdf_path),
            "extraction_method": "OCR",
            "text": text,
            "layout_text": "",
            "extraction_text": text,
            "success": bool(
                text.strip()
            ),
        }