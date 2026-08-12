from pathlib import Path

from .pdf_text_extractor import extract_text_from_pdf


def classify_pdf(pdf_path: str | Path, min_text_length: int = 50) -> str:
    """
    Classify a PDF based on the amount of selectable text.

    Returns:
        TEXT  -> PDF contains enough selectable text
        OCR   -> PDF has little/no selectable text and needs OCR
    """

    text = extract_text_from_pdf(pdf_path)

    if len(text.strip()) >= min_text_length:
        return "TEXT"

    return "OCR"