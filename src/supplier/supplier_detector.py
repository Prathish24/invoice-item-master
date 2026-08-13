from typing import Optional


# ============================================================
# SUPPLIER PATTERNS
# ============================================================

SUPPLIER_PATTERNS = {
    "ARIES": [
        "ARIES ELECTRIC MOTOR",
        "ARIES ELECTRIC",
        "ARIES",
    ],

    "EQUIPTEX": [
        "EQUIPTEX INDUSTRIAL PRODUCTS",
        "EQUIPTEX",
    ],

    "BENFIELD": [
        "BENFIELD ELECTRIC SUPPLY CO. INC.",
        "BENFIELD ELECTRIC SUPPLY CO",
        "BENFIELD ELECTRIC SUPPLY",
        "BENFIELD ELECTRIC",
        "BENFIELD",
    ],
}


# ============================================================
# SUPPLIER DETECTION
# ============================================================

def detect_supplier(
    invoice_text: str,
) -> Optional[str]:
    """
    Detect supplier from invoice text.

    Returns:
        Supplier identifier such as:
        ARIES
        EQUIPTEX
        BENFIELD

        Returns None when the supplier cannot
        be identified confidently.
    """

    if not invoice_text:
        return None

    # --------------------------------------------------------
    # Normalize text
    # --------------------------------------------------------

    text = invoice_text.upper()

    # Replace common separators so that:
    #
    # BENFIELD ELECTRIC
    # SUPPLY CO. INC.
    #
    # can still be detected reliably.
    normalized_text = (
        text
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("\t", " ")
    )

    # Collapse multiple spaces
    normalized_text = " ".join(
        normalized_text.split()
    )

    # --------------------------------------------------------
    # Match supplier patterns
    # --------------------------------------------------------

    for supplier, patterns in SUPPLIER_PATTERNS.items():

        for pattern in patterns:

            normalized_pattern = (
                pattern
                .upper()
                .replace("\n", " ")
                .replace("\r", " ")
            )

            normalized_pattern = " ".join(
                normalized_pattern.split()
            )

            if normalized_pattern in normalized_text:

                return supplier

    # --------------------------------------------------------
    # Supplier not confidently identified
    # --------------------------------------------------------

    return None