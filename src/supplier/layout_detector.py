from typing import Optional


LAYOUT_PATTERNS = {
    "EQUIPTEX": {
        "keywords": [
            "PRODUCT",
            "DESCRIPTION",
            "QTY",
            "UOM",
            "UNIT PRICE",
            "AMOUNT",
        ],
        "layout_type": "COLUMNAR_LINE_ITEMS",
    },

    "BENFIELD": {
        "keywords": [
            "QTY",
            "UOM",
            "UNIT PRICE",
            "EXTENDED",
        ],
        "uom_patterns": ["C", "M", "E"],
        "layout_type": "COLUMNAR_WITH_VENDOR_UOM",
    },

    "GENERIC": {
        "keywords": [],
        "layout_type": "GENERIC",
    },
}


def detect_layout(
    invoice_text: str,
    supplier: Optional[str] = None,
) -> str:
    """
    Detect the likely invoice layout.

    Returns a layout identifier that can later be used
    to select the appropriate parser.
    """

    if not invoice_text:
        return "GENERIC"

    text = invoice_text.upper()

    # --------------------------------------------------
    # Supplier-specific layout detection
    # --------------------------------------------------

    if supplier == "EQUIPTEX":

        keywords = LAYOUT_PATTERNS["EQUIPTEX"]["keywords"]

        matches = sum(
            1 for keyword in keywords
            if keyword in text
        )

        if matches >= 3:
            return "EQUIPTEX_COLUMNAR"

    if supplier == "BENFIELD":

        keywords = LAYOUT_PATTERNS["BENFIELD"]["keywords"]

        matches = sum(
            1 for keyword in keywords
            if keyword in text
        )

        if matches >= 2:
            return "BENFIELD_UOM"

    # --------------------------------------------------
    # Generic layout detection
    # --------------------------------------------------

    generic_keywords = [
        "QTY",
        "QUANTITY",
        "DESCRIPTION",
        "UNIT PRICE",
        "AMOUNT",
        "TOTAL",
    ]

    matches = sum(
        1 for keyword in generic_keywords
        if keyword in text
    )

    if matches >= 3:
        return "COLUMNAR_GENERIC"

    return "GENERIC"