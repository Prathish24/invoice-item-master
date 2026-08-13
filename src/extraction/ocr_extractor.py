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


# ============================================================
# RENDER RESOLUTION
# ============================================================
#
# Many "digital" invoices are actually a single scanned/flattened
# image embedded in the PDF at a fixed resolution (300 DPI is the
# most common scan resolution in the wild). A fixed zoom factor
# like Matrix(2, 2) renders at only ~144 DPI regardless of what
# the source image's real resolution is - that downsamples a
# 300 DPI scan and visibly blurs small text, which is exactly
# what caused character-level OCR errors here (e.g. an invoice
# number misread as "JNY5S16AYT" instead of "JNY516AYT", and a
# whole address line disappearing into unrecognizable garbage).
#
# Rendering at the target DPI below instead of a fixed zoom
# matches common source-scan resolution and measurably improves
# accuracy. Going much higher than the source resolution doesn't
# help further (it's just interpolation, not more real detail),
# so this is intentionally not maxed out.
OCR_TARGET_DPI = 300

PDF_BASE_DPI = 72


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

    zoom = OCR_TARGET_DPI / PDF_BASE_DPI

    with fitz.open(pdf_path) as document:

        for page_number, page in enumerate(document, start=1):

            # Render PDF page as an image at OCR_TARGET_DPI,
            # honoring the page's own rotation automatically.
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(zoom, zoom),
                alpha=False
            )

            # Convert image bytes to PIL Image
            image = Image.open(BytesIO(pixmap.tobytes("png")))

            # PSM 3 (fully automatic page segmentation) lets
            # Tesseract detect distinct blocks/columns on the
            # page. PSM 6 (the previous setting) forces the
            # whole page to be treated as a single uniform text
            # block, which has no concept of columns - so a
            # multi-column header (e.g. vendor info printed next
            # to invoice#/date, or Bill To next to Ship To) gets
            # read line-by-line across both columns at once,
            # interleaving unrelated header fields together.
            text = pytesseract.image_to_string(
                image,
                config="--psm 3"
            )

            if text.strip():
                extracted_pages.append(
                    f"\n--- Page {page_number} ---\n{text}"
                )

    return "\n".join(extracted_pages).strip()