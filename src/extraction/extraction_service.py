from pathlib import Path

from .pdf_classifier import classify_pdf
from .pdf_text_extractor import extract_text_from_pdf
from .ocr_extractor import extract_text_with_ocr


def extract_invoice_text(pdf_path: str | Path) -> dict:
    """
    Extract text from an invoice PDF.

    Uses normal PDF text extraction when selectable text is available.
    Falls back to Tesseract OCR when the PDF has little/no text.
    """

    pdf_path = Path(pdf_path)

    extraction_type = classify_pdf(pdf_path)

    if extraction_type == "TEXT":
        text = extract_text_from_pdf(pdf_path)
        method = "TEXT"

    else:
        text = extract_text_with_ocr(pdf_path)
        method = "OCR"

    return {
        "file_name": pdf_path.name,
        "file_path": str(pdf_path),
        "extraction_method": method,
        "text": text,
        "success": bool(text.strip()),
    }