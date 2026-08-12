import re
from typing import Optional


def normalize_part_number(part_number: Optional[str]) -> Optional[str]:
    """
    Safely normalize a vendor/manufacturer part number.

    This does not attempt to guess or change the actual part number.
    It only removes formatting inconsistencies.
    """

    if not part_number:
        return None

    part_number = part_number.strip().upper()

    # Normalize whitespace
    part_number = re.sub(r"\s+", " ", part_number)

    # Remove spaces around common separators
    part_number = re.sub(r"\s*-\s*", "-", part_number)
    part_number = re.sub(r"\s*/\s*", "/", part_number)

    return part_number.strip()