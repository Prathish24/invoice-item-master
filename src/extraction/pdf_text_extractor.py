import fitz  # PyMuPDF
from pathlib import Path


def extract_text_from_pdf(pdf_path: str | Path) -> str:
    """
    Extract selectable text from a PDF using PyMuPDF.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Extracted text from all pages.
    """

    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"File is not a PDF: {pdf_path}")

    extracted_text = []

    with fitz.open(pdf_path) as document:
        for page_number, page in enumerate(document, start=1):
            text = page.get_text("text")

            if text.strip():
                extracted_text.append(
                    f"\n--- Page {page_number} ---\n{text}"
                )

    return "\n".join(extracted_text).strip()