import fitz
from pathlib import Path

from .pdf_text_extractor import extract_text_from_pdf


# ============================================================
# DOMINANT IMAGE DETECTION
# ============================================================

def _page_has_dominant_image(
    pdf_path: str | Path,
    coverage_threshold: float = 0.5,
) -> bool:
    """
    Return True if any page in the PDF contains one or more
    images whose combined area covers a large fraction of that
    page.

    Some invoices are scanned/flattened into a single full-page
    image, then later have a small amount of REAL selectable
    text added on top - for example an "APPROVED" stamp from an
    approval/e-signature tool, a watermark, or a page number.

    That small amount of overlay text can be enough on its own
    to clear a simple character-count threshold, which causes
    the PDF to be misclassified as a normal text PDF and OCR to
    be skipped entirely - even though the actual invoice content
    (vendor, customer, amounts, line items) only exists inside
    the image and was never extracted as text at all.

    Detecting a page that is dominated by one large image lets
    us force OCR in that situation regardless of how much
    incidental overlay text happens to be present.
    """

    pdf_path = Path(pdf_path)

    with fitz.open(pdf_path) as document:

        for page in document:

            page_area = (
                page.rect.width
                * page.rect.height
            )

            if page_area <= 0:
                continue

            image_area = 0.0

            for image_info in page.get_image_info():

                bbox = image_info.get("bbox")

                if not bbox:
                    continue

                x0, y0, x1, y1 = bbox

                image_area += (
                    max(0.0, x1 - x0)
                    * max(0.0, y1 - y0)
                )

            if (
                image_area / page_area
            ) >= coverage_threshold:

                return True

    return False


# ============================================================
# PDF CLASSIFICATION
# ============================================================

def classify_pdf(
    pdf_path: str | Path,
    min_text_length: int = 50,
) -> str:
    """
    Classify a PDF based on the amount of selectable text.

    Returns:
        TEXT  -> PDF contains enough selectable text
        OCR   -> PDF has little/no selectable text and needs OCR

    A page that is mostly one large embedded image is treated
    as needing OCR even if it also contains a small amount of
    overlay text (stamps, watermarks, page numbers) that would
    otherwise clear the character-count threshold below.
    """

    pdf_path = Path(pdf_path)

    try:

        if _page_has_dominant_image(pdf_path):
            return "OCR"

    except Exception:

        # If image inspection fails for any reason, fall back
        # to the text-length heuristic below instead of raising -
        # classification should never hard-fail the pipeline.
        pass

    text = extract_text_from_pdf(pdf_path)

    if len(text.strip()) >= min_text_length:
        return "TEXT"

    return "OCR"