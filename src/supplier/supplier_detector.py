from typing import Optional


SUPPLIER_PATTERNS = {
    "ARIES": [
        "ARIES ELECTRIC MOTOR",
        "ARIES ELECTRIC",
    ],
    "EQUIPTEX": [
        "EQUIPTEX INDUSTRIAL PRODUCTS",
        "EQUIPTEX",
    ],
    "BENFIELD": [
        "BENFIELD ELECTRIC SUPPLY",
        "BENFIELD ELECTRIC",
    ],
}


def detect_supplier(invoice_text: str) -> Optional[str]:
    """
    Detect the supplier from invoice text.

    Returns:
        Supplier identifier such as ARIES, EQUIPTEX, BENFIELD,
        or None if the supplier cannot be identified.
    """

    if not invoice_text:
        return None

    text = invoice_text.upper()

    for supplier, patterns in SUPPLIER_PATTERNS.items():

        for pattern in patterns:

            if pattern in text:
                return supplier

    return None