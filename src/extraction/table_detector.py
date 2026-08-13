from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


# ============================================================
# HEADER LABEL ALIASES
# ============================================================

# These are only semantic hints.
# They are NOT fixed column positions and do NOT define the
# complete set of possible invoice columns.
KNOWN_HEADER_HINTS = {
    "part": {
        "part",
        "part #",
        "part no",
        "part number",
        "item",
        "item #",
        "item no",
        "item number",
        "product",
        "product #",
        "catalog",
    },
    "description": {
        "description",
        "item description",
        "product description",
        "material description",
        "details",
    },
    "quantity_shipped": {
        "qty",
        "qty ship",
        "qty shipped",
        "quantity",
        "quantity shipped",
        "shipped",
        "ship qty",
    },
    "quantity_ordered": {
        "qty ordered",
        "quantity ordered",
        "ordered",
        "order qty",
    },
    "back_ordered": {
        "back ordered",
        "backorder",
        "back ordered qty",
        "bo",
    },
    "uom": {
        "uom",
        "unit",
        "units",
        "unit of measure",
    },
    "unit_price_usd": {
        "rate",
        "unit price",
        "price",
        "unit cost",
        "cost",
        "unit rate",
    },
    "extended_price_usd": {
        "amount",
        "extended",
        "extended price",
        "extended amount",
        "line total",
        "total",
        "ext",
    },
}


# ============================================================
# DATA MODELS
# ============================================================

@dataclass
class OCRWord:
    text: str
    x: float
    y: float
    width: float
    height: float
    confidence: float


@dataclass
class HeaderCell:
    label: str
    x: float
    width: float
    semantic_field: str | None


@dataclass
class TableStructure:
    page_number: int
    header_y: float
    headers: list[HeaderCell]
    row_y_values: list[float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "page_number": self.page_number,
            "header_y": self.header_y,
            "headers": [
                {
                    "label": header.label,
                    "x": header.x,
                    "width": header.width,
                    "semantic_field": header.semantic_field,
                }
                for header in self.headers
            ],
            "row_y_values": self.row_y_values,
        }


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def _normalize_label(value: str) -> str:
    """
    Normalize a header label for matching only.

    The original OCR label is preserved elsewhere.
    """

    value = value.lower().strip()

    value = value.replace(
        "\n",
        " ",
    )

    value = re.sub(
        r"[^a-z0-9#]+",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def _semantic_field(
    label: str,
) -> str | None:
    """
    Map a detected header label to a standard field when the
    meaning is reasonably clear.

    Unknown labels remain None and are handled dynamically.
    """

    normalized = _normalize_label(
        label
    )

    for field, aliases in KNOWN_HEADER_HINTS.items():

        for alias in aliases:

            alias_normalized = _normalize_label(
                alias
            )

            if normalized == alias_normalized:
                return field

    # Small amount of conservative fuzzy matching.
    # We intentionally avoid aggressive guessing.
    if "back" in normalized and (
        "order" in normalized
        or "bo" in normalized
    ):
        return "back_ordered"

    if (
        "qty" in normalized
        or "quantity" in normalized
    ):
        if "order" in normalized:
            return "quantity_ordered"

        if "ship" in normalized:
            return "quantity_shipped"

    if (
        "unit" in normalized
        and "price" in normalized
    ):
        return "unit_price_usd"

    if normalized in {
        "rate",
        "price",
        "cost",
    }:
        return "unit_price_usd"

    if (
        "extended" in normalized
        or "amount" in normalized
        or normalized == "ext"
    ):
        return "extended_price_usd"

    return None


# ============================================================
# PARSE COORDINATE OCR
# ============================================================

_COORDINATE_PATTERN = re.compile(
    r"""
    ^(?P<text>.*?)\s*\|\s*
    x=(?P<x>-?\d+(?:\.\d+)?)\s+
    y=(?P<y>-?\d+(?:\.\d+)?)\s+
    w=(?P<w>-?\d+(?:\.\d+)?)\s+
    h=(?P<h>-?\d+(?:\.\d+)?)\s+
    conf=(?P<conf>-?\d+(?:\.\d+)?)\s*$
    """,
    re.VERBOSE,
)


def parse_coordinate_ocr(
    text: str,
) -> list[OCRWord]:
    """
    Parse the WORD COORDINATES section generated by
    ocr_extractor.py.

    Lines that do not match the coordinate format are ignored.
    """

    words: list[OCRWord] = []

    for line in text.splitlines():

        match = _COORDINATE_PATTERN.match(
            line.strip()
        )

        if not match:
            continue

        word_text = (
            match.group("text")
            .strip()
        )

        if not word_text:
            continue

        words.append(
            OCRWord(
                text=word_text,
                x=float(
                    match.group("x")
                ),
                y=float(
                    match.group("y")
                ),
                width=float(
                    match.group("w")
                ),
                height=float(
                    match.group("h")
                ),
                confidence=float(
                    match.group("conf")
                ),
            )
        )

    return words


# ============================================================
# GROUP WORDS INTO VISUAL ROWS
# ============================================================

def group_words_by_y(
    words: list[OCRWord],
    y_tolerance: float | None = None,
) -> list[list[OCRWord]]:
    """
    Group OCR words into visual rows using their actual y
    coordinates.

    No fixed page size is assumed.

    y_tolerance is derived automatically from the median word
    height when not supplied.
    """

    if not words:
        return []

    sorted_words = sorted(
        words,
        key=lambda word: (
            word.y,
            word.x,
        ),
    )

    if y_tolerance is None:

        heights = sorted(
            max(1.0, word.height)
            for word in sorted_words
        )

        middle = len(heights) // 2

        if len(heights) % 2:
            median_height = heights[middle]
        else:
            median_height = (
                heights[middle - 1]
                + heights[middle]
            ) / 2.0

        # Dynamic tolerance based on actual font size.
        y_tolerance = max(
            6.0,
            median_height * 0.7,
        )

    rows: list[list[OCRWord]] = []

    for word in sorted_words:

        placed = False

        for row in rows:

            row_y = sum(
                item.y
                for item in row
            ) / len(row)

            if abs(
                word.y - row_y
            ) <= y_tolerance:

                row.append(word)
                placed = True
                break

        if not placed:
            rows.append(
                [word]
            )

    for row in rows:
        row.sort(
            key=lambda item: item.x
        )

    rows.sort(
        key=lambda row: min(
            item.y
            for item in row
        )
    )

    return rows


# ============================================================
# JOIN NEARBY HEADER WORDS
# ============================================================

def _combine_header_words(
    row: list[OCRWord],
) -> list[HeaderCell]:
    """
    Build candidate header cells from one visual row.

    Words are combined only when their horizontal gap is small
    relative to the observed word heights.

    Example:

        Qty | Ship

    can become:

        Qty Ship
    """

    if not row:
        return []

    median_height = sorted(
        max(1.0, word.height)
        for word in row
    )[len(row) // 2]

    max_gap = max(
        12.0,
        median_height * 1.5,
    )

    cells: list[HeaderCell] = []

    current_words: list[OCRWord] = []

    for word in row:

        if not current_words:

            current_words.append(
                word
            )
            continue

        previous = current_words[-1]

        gap = (
            word.x
            - (
                previous.x
                + previous.width
            )
        )

        if gap <= max_gap:

            current_words.append(
                word
            )

        else:

            cells.append(
                _header_cell_from_words(
                    current_words
                )
            )

            current_words = [
                word
            ]

    if current_words:

        cells.append(
            _header_cell_from_words(
                current_words
            )
        )

    return cells


def _header_cell_from_words(
    words: list[OCRWord],
) -> HeaderCell:

    label = " ".join(
        word.text
        for word in words
    ).strip()

    return HeaderCell(
        label=label,
        x=min(
            word.x
            for word in words
        ),
        width=(
            max(
                word.x
                + word.width
                for word in words
            )
            - min(
                word.x
                for word in words
            )
        ),
        semantic_field=_semantic_field(
            label
        ),
    )


# ============================================================
# SCORE HEADER CANDIDATES
# ============================================================

def _score_header_row(
    cells: list[HeaderCell],
) -> float:
    """
    Score a visual row as a potential item-table header.

    The score uses semantic clues, but does not require all
    standard headers to be present.

    Unknown/custom columns are allowed.
    """

    if len(cells) < 2:
        return 0.0

    recognized = sum(
        1
        for cell in cells
        if cell.semantic_field is not None
    )

    labels = " ".join(
        _normalize_label(
            cell.label
        )
        for cell in cells
    )

    score = recognized * 3.0

    # Strong table signals.
    if "description" in labels:
        score += 2.5

    if (
        "quantity" in labels
        or "qty" in labels
    ):
        score += 2.5

    if (
        "price" in labels
        or "rate" in labels
        or "cost" in labels
    ):
        score += 2.0

    if (
        "amount" in labels
        or "extended" in labels
        or "total" in labels
    ):
        score += 2.0

    if (
        "part" in labels
        or "item" in labels
        or "product" in labels
    ):
        score += 1.5

    return score


# ============================================================
# DETECT TABLE STRUCTURE
# ============================================================

def detect_table_structure(
    coordinate_text: str,
) -> TableStructure | None:
    """
    Dynamically detect an invoice item-table header row.

    No fixed page size or fixed header position is used.

    The function returns the most likely table header and the
    y positions below it where line items may appear.

    A later LLM/table-mapping step can use the discovered
    headers and x positions to map rows.
    """

    words = parse_coordinate_ocr(
        coordinate_text
    )

    if not words:
        return None

    rows = group_words_by_y(
        words
    )

    candidates: list[
        tuple[float, int, list[HeaderCell]]
    ] = []

    for index, row in enumerate(
        rows
    ):

        cells = _combine_header_words(
            row
        )

        score = _score_header_row(
            cells
        )

        if score <= 0:
            continue

        header_y = min(
            word.y
            for word in row
        )

        candidates.append(
            (
                score,
                index,
                cells,
            )
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    best_score, best_index, headers = (
        candidates[0]
    )

    if best_score < 4.0:
        return None

    header_y = min(
        word.y
        for word in rows[
            best_index
        ]
    )

    row_y_values = [
        min(
            word.y
            for word in row
        )
        for row in rows[
            best_index + 1:
        ]
        if min(
            word.y
            for word in row
        ) > header_y
    ]

    return TableStructure(
        page_number=1,
        header_y=header_y,
        headers=headers,
        row_y_values=row_y_values,
    )


# ============================================================
# BUILD DYNAMIC TABLE MAP
# ============================================================

def build_table_column_map(
    structure: TableStructure,
) -> dict[str, Any]:
    """
    Convert the detected table structure into a compact,
    model-friendly representation.

    Unknown columns are preserved as dynamic labels instead of
    being discarded.
    """

    columns = []

    for index, header in enumerate(
        structure.headers,
        start=1,
    ):

        columns.append(
            {
                "column_index": index,
                "label": header.label,
                "x_start": header.x,
                "x_end": (
                    header.x
                    + header.width
                ),
                "semantic_field": (
                    header.semantic_field
                ),
            }
        )

    return {
        "header_y": structure.header_y,
        "columns": columns,
        "row_y_values": structure.row_y_values,
    }


__all__ = [
    "OCRWord",
    "HeaderCell",
    "TableStructure",
    "parse_coordinate_ocr",
    "group_words_by_y",
    "detect_table_structure",
    "build_table_column_map",
]



# ============================================================
# DYNAMIC TABLE ROW EXTRACTION
# ============================================================

def _column_center(
    column: dict[str, Any],
) -> float:
    return (
        float(column["x_start"])
        + float(column["x_end"])
    ) / 2.0


def _assign_word_to_column(
    word: OCRWord,
    columns: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """
    Assign an OCR word to the nearest detected table column.

    The decision is based on the actual header-derived x
    positions for this invoice.
    """

    if not columns:
        return None

    word_center = (
        word.x
        + (word.width / 2.0)
    )

    # Prefer a column whose horizontal span actually contains
    # the word center.
    containing = [
        column
        for column in columns
        if (
            float(column["x_start"])
            <= word_center
            <= float(column["x_end"])
        )
    ]

    if len(containing) == 1:
        return containing[0]

    # Otherwise choose the nearest column center.
    return min(
        columns,
        key=lambda column: abs(
            word_center
            - _column_center(column)
        ),
    )


def _group_table_rows(
    rows: list[list[OCRWord]],
    header_y: float,
    row_tolerance: float | None = None,
) -> list[list[OCRWord]]:
    """
    Keep only visual rows below the table header and regroup them
    using a tolerance derived from the observed word heights.

    This does not assume a fixed row height or page size.
    """

    candidate_rows = [
        row
        for row in rows
        if row
        and min(
            word.y
            for word in row
        ) > header_y
    ]

    if not candidate_rows:
        return []

    all_words = [
        word
        for row in candidate_rows
        for word in row
    ]

    heights = sorted(
        max(1.0, word.height)
        for word in all_words
    )

    middle = len(heights) // 2

    if heights:

        if len(heights) % 2:
            median_height = heights[middle]
        else:
            median_height = (
                heights[middle - 1]
                + heights[middle]
            ) / 2.0

    else:

        median_height = 20.0

    if row_tolerance is None:

        row_tolerance = max(
            8.0,
            median_height * 0.8,
        )

    grouped_rows: list[list[OCRWord]] = []

    for row in candidate_rows:

        row_y = min(
            word.y
            for word in row
        )

        # Start a new logical row.
        if not grouped_rows:

            grouped_rows.append(
                list(row)
            )
            continue

        previous_row = grouped_rows[-1]

        previous_y = min(
            word.y
            for word in previous_row
        )

        if abs(
            row_y - previous_y
        ) <= row_tolerance:

            previous_row.extend(
                row
            )
            previous_row.sort(
                key=lambda word: word.x
            )

        else:

            grouped_rows.append(
                list(row)
            )

    return grouped_rows


def extract_dynamic_table_rows(
    coordinate_text: str,
    structure: TableStructure,
) -> list[dict[str, Any]]:
    """
    Extract dynamically grouped table rows using the table
    structure detected from the same invoice.

    Returned shape:

        [
            {
                "row_y": 1084.0,
                "columns": {
                    "QUANTITY": ["5"],
                    "PART": ["AAD20390P998"],
                    "DESCRIPTION": [
                        "STRAWBERRY",
                        "HILL,ASY-HPU,2.5"
                    ],
                    "PRICE": ["9236.22"],
                    "AMOUNT": ["9236.22"]
                }
            }
        ]

    No invoice-specific x positions are hardcoded.
    """

    words = parse_coordinate_ocr(
        coordinate_text
    )

    if not words:
        return []

    rows = group_words_by_y(
        words
    )

    table_map = build_table_column_map(
        structure
    )

    columns = table_map[
        "columns"
    ]

    grouped_table_rows = _group_table_rows(
        rows,
        structure.header_y,
    )

    extracted_rows = []

    # --------------------------------------------------------
    # Stop candidate rows at the first long blank/table-summary
    # region only when there is strong evidence of a non-item
    # section. Otherwise keep collecting; later LLM verification
    # can reject non-item rows.
    # --------------------------------------------------------

    for row in grouped_table_rows:

        row_y = min(
            word.y
            for word in row
        )

        column_values: dict[
            str,
            list[str]
        ] = {}

        for column in columns:

            label = str(
                column["label"]
            ).strip()

            column_values[
                label
            ] = []

        for word in row:

            column = _assign_word_to_column(
                word,
                columns,
            )

            if column is None:
                continue

            label = str(
                column["label"]
            ).strip()

            column_values[
                label
            ].append(
                word.text
            )

        # Discard completely empty rows.
        if not any(
            values
            for values
            in column_values.values()
        ):
            continue

        extracted_rows.append(
            {
                "row_y": row_y,
                "columns": column_values,
            }
        )

    return extracted_rows



# ============================================================
# DYNAMIC ITEM-ROW CLASSIFICATION
# ============================================================

# These are semantic signals only. They are not supplier-specific
# row coordinates.
SUMMARY_TERMS = {
    "subtotal",
    "sub total",
    "tax",
    "sales tax",
    "freight",
    "shipping",
    "invoice amount",
    "amount due",
    "total",
    "total due",
    "total paid",
    "discount",
    "terms",
    "shipment",
    "shipment #",
    "shipped by",
    "remit",
    "please remit",
    "customer",
    "bill to",
    "ship to",
    "payment",
}


def _row_text(
    row: dict[str, Any],
) -> str:
    """
    Return the full visible text represented by a detected table row.
    """

    parts = []

    for values in row.get(
        "columns",
        {},
    ).values():

        parts.extend(
            str(value)
            for value in values
            if value not in (
                None,
                "",
            )
        )

    return " ".join(
        parts
    ).strip()


def _looks_like_summary_row(
    row: dict[str, Any],
) -> bool:
    """
    Detect obvious non-item invoice sections such as subtotal,
    tax, freight, shipment and totals.

    This is label/semantic based, not position based.
    """

    text = _normalize_label(
        _row_text(row)
    )

    if not text:
        return True

    for term in SUMMARY_TERMS:

        normalized_term = _normalize_label(
            term
        )

        if normalized_term in text:
            return True

    return False


def _numeric_tokens(
    values: list[str],
) -> list[float]:
    """
    Convert numeric-looking cell text into numbers.
    """

    numbers = []

    for value in values:

        cleaned = (
            str(value)
            .replace(",", "")
            .replace("$", "")
            .strip()
        )

        # Do not treat IDs/part numbers with letters as money/qty.
        if re.search(
            r"[A-Za-z]",
            cleaned,
        ):
            continue

        match = re.fullmatch(
            r"-?\d+(?:\.\d+)?",
            cleaned,
        )

        if not match:
            continue

        try:
            numbers.append(
                float(cleaned)
            )
        except ValueError:
            continue

    return numbers


def score_item_row(
    row: dict[str, Any],
    structure: TableStructure,
) -> float:
    """
    Score whether a detected visual row is probably a real
    invoice line item.

    The score is based on the actual detected table columns,
    not fixed coordinates.

    Signals:
        - part/item-like value
        - description text
        - quantity value
        - unit price
        - extended amount
        - multiple populated table columns

    Negative signals:
        - totals/shipping/summary language
        - almost no populated table columns
    """

    if _looks_like_summary_row(row):
        return -100.0

    columns = row.get(
        "columns",
        {},
    )

    # --------------------------------------------------------
    # Hard guard:
    #
    # A true item row must contain at least one numeric token
    # in a recognized numeric column (quantity/price/amount).
    #
    # This rejects legal text, addresses, terms, and other prose
    # that happens to overlap the detected table columns.
    # --------------------------------------------------------

    semantic_by_label = {
        _normalize_label(
            header["label"]
        ): header.get(
            "semantic_field"
        )
        for header in build_table_column_map(
            structure
        )["columns"]
    }

    numeric_semantic_fields = {
        "quantity_shipped",
        "quantity_ordered",
        "back_ordered",
        "unit_price_usd",
        "extended_price_usd",
    }

    numeric_column_count = 0

    for label, values in columns.items():

        semantic_field = semantic_by_label.get(
            _normalize_label(label)
        )

        if (
            semantic_field
            in numeric_semantic_fields
            and _numeric_tokens(values)
        ):

            numeric_column_count += 1

    if numeric_column_count == 0:
        return -100.0

    score = 0.0

    populated = 0

    for key, values in columns.items():

        if values:
            populated += 1

    score += min(
        populated * 1.5,
        7.5,
    )

    # --------------------------------------------------------
    # Semantic standard fields
    # --------------------------------------------------------

    for label, values in columns.items():

        semantic_field = semantic_by_label.get(
            _normalize_label(label)
        )

        if not values:
            continue

        if semantic_field == "part":

            # Part/item values usually contain letters/numbers
            # and are stronger item-row evidence than prose.
            value = " ".join(values).strip()

            if (
                re.search(
                    r"[A-Za-z0-9]",
                    value,
                )
                and len(value) <= 100
            ):
                score += 3.0

        elif semantic_field == "description":

            text_value = " ".join(
                values
            ).strip()

            if len(text_value) >= 3:
                score += 2.5

        elif semantic_field in {
            "quantity_shipped",
            "quantity_ordered",
            "back_ordered",
            "unit_price_usd",
            "extended_price_usd",
        }:

            numeric_values = _numeric_tokens(
                values
            )

            if numeric_values:
                score += 2.0

    # --------------------------------------------------------
    # Strong item-row requirement:
    #
    # Real line items should have:
    #
    #   1. an item identity (part or description), AND
    #   2. a numeric value in a real numeric table column, AND
    #   3. enough populated table columns to resemble a row.
    #
    # This rejects prose/address/terms rows that merely contain
    # words which happen to land inside the detected columns.
    # --------------------------------------------------------

    has_identity = False
    numeric_column_count = 0

    for label, values in columns.items():

        semantic_field = semantic_by_label.get(
            _normalize_label(label)
        )

        if semantic_field in {
            "part",
            "description",
        } and values:

            has_identity = True

        if semantic_field in {
            "quantity_shipped",
            "quantity_ordered",
            "back_ordered",
            "unit_price_usd",
            "extended_price_usd",
        }:

            if _numeric_tokens(values):

                numeric_column_count += 1

    populated_standard_columns = 0

    for label, values in columns.items():

        semantic_field = semantic_by_label.get(
            _normalize_label(label)
        )

        if (
            semantic_field is not None
            and values
        ):

            populated_standard_columns += 1

    if (
        has_identity
        and numeric_column_count >= 1
        and populated_standard_columns >= 3
    ):
        score += 6.0

    else:
        score -= 8.0

    # Stronger preference for actual item rows that contain both
    # identification and money/quantity evidence.
    if (
        has_identity
        and numeric_column_count >= 2
    ):
        score += 3.0

    if (
        "extended_price_usd" in {
            semantic_by_label.get(
                _normalize_label(label)
            )
            for label in columns
        }
        and _numeric_tokens(
            next(
                (
                    values
                    for label, values
                    in columns.items()
                    if semantic_by_label.get(
                        _normalize_label(label)
                    )
                    == "extended_price_usd"
                ),
                [],
            )
        )
    ):
        score += 2.0

    return score


def classify_table_rows(
    rows: list[dict[str, Any]],
    structure: TableStructure,
    minimum_score: float = 4.0,
) -> list[dict[str, Any]]:
    """
    Return only rows that look like real invoice line items.

    Each returned row also contains:

        "row_score"

    so downstream logic can decide whether to accept, review,
    or send the row to a vision/LLM fallback.
    """

    classified = []

    for row in rows:

        score = score_item_row(
            row,
            structure,
        )

        row_copy = dict(
            row
        )

        row_copy[
            "row_score"
        ] = score

        row_copy[
            "is_item_row"
        ] = score >= minimum_score

        if score >= minimum_score:

            classified.append(
                row_copy
            )

    return classified


__all__.extend(
    [
        "extract_dynamic_table_rows",
        "score_item_row",
        "classify_table_rows",
    ]
)
