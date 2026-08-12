import re
from typing import Optional


def normalize_description(description: Optional[str]) -> Optional[str]:
    """
    Perform safe normalization of an invoice item description.

    This function does NOT change the meaning of the description.
    It only cleans formatting differences such as whitespace,
    repeated spaces, and unnecessary separators.
    """

    if not description:
        return None

    text = description.strip()

    # Replace multiple whitespace characters with one space
    text = re.sub(r"\s+", " ", text)

    # Normalize spaces around hyphens
    text = re.sub(r"\s*-\s*", " - ", text)

    # Remove repeated hyphens
    text = re.sub(r"-{2,}", "-", text)

    # Remove spaces before/after commas
    text = re.sub(r"\s*,\s*", ", ", text)

    return text.strip()