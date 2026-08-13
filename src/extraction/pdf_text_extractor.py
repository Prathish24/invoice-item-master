import fitz
from pathlib import Path
from typing import Any


# ============================================================
# BASIC TEXT EXTRACTION
# ============================================================

def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract normal text from a PDF using PyMuPDF.
    """

    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(
            f"PDF not found: {pdf_path}"
        )

    pages = []

    with fitz.open(pdf_path) as document:

        for page_number, page in enumerate(document):

            text = page.get_text("text")

            if text:
                pages.append(
                    f"\n--- PAGE {page_number + 1} ---\n{text}"
                )

    return "\n".join(pages).strip()


# ============================================================
# WORD EXTRACTION WITH COORDINATES
# ============================================================

def extract_words_with_coordinates(
    pdf_path: str,
) -> list[dict[str, Any]]:
    """
    Extract every word from the PDF together with its
    bounding-box coordinates.

    This preserves information about where text appears
    on the page.
    """

    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(
            f"PDF not found: {pdf_path}"
        )

    words = []

    with fitz.open(pdf_path) as document:

        for page_number, page in enumerate(document):

            page_words = page.get_text(
                "words"
            )

            for word in page_words:

                x0, y0, x1, y1, text, block_no, line_no, word_no = word

                if not text or not text.strip():
                    continue

                words.append(
                    {
                        "page": page_number + 1,
                        "x0": float(x0),
                        "y0": float(y0),
                        "x1": float(x1),
                        "y1": float(y1),
                        "text": text.strip(),
                        "block": block_no,
                        "line": line_no,
                        "word": word_no,
                    }
                )

    return words


# ============================================================
# GROUP WORDS INTO VISUAL ROWS
# ============================================================

def group_words_into_rows(
    words: list[dict[str, Any]],
    y_tolerance: float = 3.0,
) -> list[list[dict[str, Any]]]:
    """
    Group words that appear on approximately the same
    horizontal line.

    This helps preserve invoice table rows.

    IMPORTANT:
    Each row is anchored to the y-position of the FIRST word
    placed into it, and every subsequent word is compared
    against that fixed anchor (not against whichever word was
    most recently added).

    A previous implementation compared each new word only to
    the last word already placed in a row. That allowed small
    per-word offsets to "chain" together (e.g. 100 -> 102 -> 104,
    each step within tolerance) until two visually distinct
    invoice rows drifted into being merged into one, or a
    single row got incorrectly split. This silently scrambled
    which quantity/price/description belonged to which line
    item on invoices with tight line spacing, multi-line
    descriptions, or slightly skewed scans - while invoices
    with perfectly even spacing were unaffected. Anchoring to
    a fixed reference point (and choosing the closest matching
    row instead of the first match found) prevents that drift.
    """

    if not words:
        return []

    sorted_words = sorted(
        words,
        key=lambda item: (
            item["page"],
            item["y0"],
            item["x0"],
        ),
    )

    # Each row tracks: page, a fixed y-anchor, and its words.
    rows: list[dict[str, Any]] = []

    for word in sorted_words:

        best_row = None
        best_diff = None

        for row in rows:

            # Different page → cannot be same row
            if word["page"] != row["page"]:
                continue

            diff = abs(word["y0"] - row["y_anchor"])

            if diff <= y_tolerance:

                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    best_row = row

        if best_row is not None:
            best_row["words"].append(word)
        else:
            rows.append(
                {
                    "page": word["page"],
                    "y_anchor": word["y0"],
                    "words": [word],
                }
            )

    # --------------------------------------------------------
    # Finalize: order words left-to-right within each row, and
    # order rows top-to-bottom (per page) for stable output.
    # --------------------------------------------------------

    ordered_rows = sorted(
        rows,
        key=lambda row: (row["page"], row["y_anchor"]),
    )

    result: list[list[dict[str, Any]]] = []

    for row in ordered_rows:

        row_words = sorted(
            row["words"],
            key=lambda item: item["x0"],
        )

        result.append(row_words)

    return result


# ============================================================
# BUILD LAYOUT-AWARE TEXT
# ============================================================

def build_layout_aware_text(
    words: list[dict[str, Any]],
    y_tolerance: float = 3.0,
) -> str:
    """
    Convert coordinate-aware words into a structured
    text representation.

    The output keeps visual row/column information instead
    of simply concatenating the PDF text.
    """

    rows = group_words_into_rows(
        words,
        y_tolerance=y_tolerance,
    )

    output = []

    current_page = None

    for row_number, row in enumerate(rows, start=1):

        if not row:
            continue

        page = row[0]["page"]

        if page != current_page:

            output.append(
                f"\n========== PAGE {page} =========="
            )

            current_page = page

        # ----------------------------------------------------
        # Build row
        # ----------------------------------------------------

        row_parts = []

        for word in row:

            text = word["text"]

            x = round(word["x0"], 1)

            row_parts.append(
                f"[x={x}] {text}"
            )

        output.append(
            f"ROW {row_number}: "
            + " | ".join(row_parts)
        )

    return "\n".join(output)


# ============================================================
# MAIN STRUCTURED EXTRACTION
# ============================================================

def extract_layout_aware_text(
    pdf_path: str,
) -> str:
    """
    Main function used by the invoice pipeline.

    Extracts words + coordinates and reconstructs
    layout-aware rows.
    """

    words = extract_words_with_coordinates(
        pdf_path
    )

    if not words:
        return ""

    return build_layout_aware_text(
        words
    )


# ============================================================
# COMBINED EXTRACTION
# ============================================================

def extract_pdf_content(
    pdf_path: str,
) -> dict[str, Any]:
    """
    Extract both normal text and layout-aware text.

    This gives the downstream pipeline both representations.
    """

    normal_text = extract_text_from_pdf(
        pdf_path
    )

    layout_text = extract_layout_aware_text(
        pdf_path
    )

    return {
        "text": normal_text,
        "layout_text": layout_text,
        "has_text": bool(normal_text.strip()),
        "has_layout_text": bool(
            layout_text.strip()
        ),
    }