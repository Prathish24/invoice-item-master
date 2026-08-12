import os
from io import BytesIO
from pathlib import Path



import fitz
import pytesseract
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

tesseract_cmd = os.getenv("TESSERACT_CMD")

if tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd


def extract_text_with_ocr(pdf_path: str | Path) -> str:
    """
    Extract text from a PDF using Tesseract OCR.

    Each PDF page is converted to an image and processed
    independently by Tesseract.
    """

    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"File is not a PDF: {pdf_path}")

    extracted_pages = []

    with fitz.open(pdf_path) as document:

        for page_number, page in enumerate(document, start=1):

            # Render PDF page as an image
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(2, 2),
                alpha=False
            )

            # Convert image bytes to PIL Image
            image = Image.open(BytesIO(pixmap.tobytes("png")))

            # Run Tesseract OCR
            text = pytesseract.image_to_string(
                image,
                config="--psm 6"
            )

            if text.strip():
                extracted_pages.append(
                    f"\n--- Page {page_number} ---\n{text}"
                )

    return "\n".join(extracted_pages).strip()