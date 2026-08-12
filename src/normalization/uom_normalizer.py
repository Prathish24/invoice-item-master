from typing import Optional


# Standard UOM mapping
UOM_MAP = {
    "E": "EA",
    "EA": "EA",
    "EACH": "EA",
    "PC": "EA",
    "PCS": "EA",
    "PIECE": "EA",
    "PIECES": "EA",

    "BOX": "BOX",
    "BOXES": "BOX",

    "SET": "SET",
    "SETS": "SET",

    "C": "C",
    "M": "M",
}


def normalize_uom(uom: Optional[str]) -> Optional[str]:
    """
    Normalize a vendor UOM into a standard UOM.

    Returns None when the UOM is missing or unknown.
    """

    if not uom:
        return None

    normalized = uom.strip().upper()

    return UOM_MAP.get(normalized, normalized)


def get_uom_multiplier(uom: Optional[str]) -> Optional[int]:
    """
    Return the quantity multiplier represented by the vendor UOM.

    E / EA = 1 each
    C       = 100 each
    M       = 1000 each
    """

    if not uom:
        return None

    normalized = uom.strip().upper()

    multipliers = {
        "E": 1,
        "EA": 1,
        "EACH": 1,
        "PC": 1,
        "PCS": 1,
        "PIECE": 1,
        "PIECES": 1,
        "BOX": 1,
        "BOXES": 1,
        "SET": 1,
        "SETS": 1,
        "C": 100,
        "M": 1000,
    }

    return multipliers.get(normalized)