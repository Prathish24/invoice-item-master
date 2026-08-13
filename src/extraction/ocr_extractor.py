import base64
import os
from io import BytesIO
from pathlib import Path

import fitz
import pytesseract
from dotenv import load_dotenv
from PIL import Image, ImageOps


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

tesseract_cmd = os.getenv("TESSERACT_CMD")

if tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = (
        tesseract_cmd
    )


# ============================================================
# RENDER SETTINGS
# ============================================================

OCR_TARGET_DPI = 300
PDF_BASE_DPI = 72


# ============================================================
# IMAGE PREPROCESSING
# ============================================================

def _prepare_image(
    image: Image.Image,
) -> Image.Image:
    """
    Prepare a rendered PDF page for OCR.

    Keeps the rendered resolution and improves grayscale contrast
    without making assumptions about invoice size or layout.
    """

    image = image.convert("L")

    image = ImageOps.autocontrast(
        image
    )

    return image


# ============================================================
# OCR TEXT
# ============================================================

def _run_ocr(
    image: Image.Image,
    psm: int,
) -> str:
    """
    Run Tesseract OCR with the requested page segmentation mode.
    """

    text = pytesseract.image_to_string(
        image,
        config=f"--psm {psm}",
    )

    return text.strip()


# ============================================================
# WORD-LEVEL OCR
# ============================================================

def _run_word_level_ocr(
    image: Image.Image,
) -> str:
    """
    Run Tesseract word-level OCR and preserve coordinates.

    Output is intentionally plain text so the downstream invoice
    extractor can use it as additional evidence.

    Each detected word is represented approximately as:

        WORD | x=100 y=200 w=55 h=18 conf=95

    The coordinates are relative to the rendered image.
    """

    data = pytesseract.image_to_data(
        image,
        config="--psm 11",
        output_type=pytesseract.Output.DICT,
    )

    lines = []

    count = len(
        data.get("text", [])
    )

    for index in range(count):

        text = (
            data["text"][index]
            or ""
        ).strip()

        if not text:
            continue

        confidence = data["conf"][index]

        try:
            confidence_value = float(
                confidence
            )
        except (
            TypeError,
            ValueError,
        ):
            confidence_value = -1.0

        # Ignore extremely low-confidence garbage while still
        # retaining most useful invoice text.
        if (
            confidence_value >= 0
            and confidence_value < 20
        ):
            continue

        left = int(
            data["left"][index]
        )

        top = int(
            data["top"][index]
        )

        width = int(
            data["width"][index]
        )

        height = int(
            data["height"][index]
        )

        lines.append(
            (
                f"{text} | "
                f"x={left} "
                f"y={top} "
                f"w={width} "
                f"h={height} "
                f"conf={confidence_value:.1f}"
            )
        )

    return "\n".join(lines)


# ============================================================
# RENDER PDF PAGES FOR VISION MODELS
# ============================================================

def render_pdf_pages_as_data_urls(
    pdf_path: str | Path,
    max_pages: int | None = None,
) -> list[str]:
    """
    Render PDF pages into base64 data URLs suitable for Groq
    multimodal model requests.

    The function does not assume a fixed page size or invoice
    layout.

    Each returned item has the form:

        data:image/png;base64,...

    max_pages:
        Optional limit for the number of rendered pages.
        None means render every page.
    """

    pdf_path = Path(
        pdf_path
    )

    if not pdf_path.exists():
        raise FileNotFoundError(
            f"PDF not found: {pdf_path}"
        )

    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(
            f"File is not a PDF: {pdf_path}"
        )

    zoom = (
        OCR_TARGET_DPI
        / PDF_BASE_DPI
    )

    data_urls = []

    with fitz.open(
        pdf_path
    ) as document:

        page_count = len(
            document
        )

        if max_pages is None:
            pages_to_render = page_count
        else:
            pages_to_render = min(
                max_pages,
                page_count,
            )

        for page_index in range(
            pages_to_render
        ):

            page = document[
                page_index
            ]

            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(
                    zoom,
                    zoom,
                ),
                alpha=False,
            )

            png_bytes = pixmap.tobytes(
                "png"
            )

            encoded = base64.b64encode(
                png_bytes
            ).decode(
                "utf-8"
            )

            data_urls.append(
                f"data:image/png;base64,{encoded}"
            )

    return data_urls


# ============================================================
# MAIN OCR EXTRACTION
# ============================================================

def extract_text_with_ocr(
    pdf_path: str | Path,
) -> str:
    """
    Extract text from scanned/image PDFs using multiple
    layout-independent OCR representations.

    For every page we produce:

        1. Primary OCR
           PSM 3 - normal page/block detection.

        2. Sparse OCR
           PSM 11 - useful for separated invoice fields.

        3. Word-coordinate OCR
           Tesseract image_to_data() output containing each
           detected word and its position.

    No fixed invoice dimensions, header percentages, or
    supplier-specific coordinates are assumed.
    """

    pdf_path = Path(
        pdf_path
    )

    if not pdf_path.exists():
        raise FileNotFoundError(
            f"PDF not found: {pdf_path}"
        )

    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(
            f"File is not a PDF: {pdf_path}"
        )

    extracted_pages = []

    zoom = (
        OCR_TARGET_DPI
        / PDF_BASE_DPI
    )

    with fitz.open(
        pdf_path
    ) as document:

        for page_number, page in enumerate(
            document,
            start=1,
        ):

            # ------------------------------------------------
            # Render page
            # ------------------------------------------------

            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(
                    zoom,
                    zoom,
                ),
                alpha=False,
            )

            image = Image.open(
                BytesIO(
                    pixmap.tobytes(
                        "png"
                    )
                )
            )

            image = _prepare_image(
                image
            )

            # ------------------------------------------------
            # PRIMARY OCR
            # ------------------------------------------------

            primary_text = _run_ocr(
                image,
                psm=3,
            )

            # ------------------------------------------------
            # SPARSE OCR
            # ------------------------------------------------

            sparse_text = _run_ocr(
                image,
                psm=11,
            )

            # ------------------------------------------------
            # WORD-LEVEL OCR WITH COORDINATES
            # ------------------------------------------------

            coordinate_text = _run_word_level_ocr(
                image
            )

            page_sections = []

            if primary_text:

                page_sections.append(
                    (
                        f"\n--- Page {page_number} "
                        f"/ PRIMARY OCR ---\n"
                        f"{primary_text}"
                    )
                )

            if sparse_text:

                page_sections.append(
                    (
                        f"\n--- Page {page_number} "
                        f"/ SPARSE OCR ---\n"
                        f"{sparse_text}"
                    )
                )

            if coordinate_text:

                page_sections.append(
                    (
                        f"\n--- Page {page_number} "
                        f"/ WORD COORDINATES ---\n"
                        f"{coordinate_text}"
                    )
                )

            if page_sections:

                extracted_pages.append(
                    "\n".join(
                        page_sections
                    )
                )

    return "\n".join(
        extracted_pages
    ).strip()
