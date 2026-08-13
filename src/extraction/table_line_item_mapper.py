from __future__ import annotations

from typing import Any


# ============================================================
# STANDARD FIELD MAPPING
# ============================================================

STANDARD_FIELDS = {
    "manufacturer_part_number",
    "vendor_part_number",
    "description",
    "quantity_shipped",
    "uom",
    "unit_price_usd",
    "extended_price_usd",
}


def _normalize_label(
    value: str,
) -> str:
    return (
        str(value)
        .strip()
        .lower()
        .replace("_", " ")
    )


def _clean_value(
    value: Any,
) -> Any:

    if isinstance(
        value,
        list,
    ):
        value = " ".join(
            str(v).strip()
            for v in value
            if v not in (
                None,
                "",
            )
        ).strip()

    elif value is not None:

        value = str(
            value
        ).strip()

    if value == "":
        return None

    return value


# ============================================================
# COLUMN SEMANTIC MAPPING
# ============================================================

def _semantic_field(
    label: str,
) -> str | None:

    normalized = _normalize_label(
        label
    )

    aliases = {
        "part": "vendor_part_number",
        "part #": "vendor_part_number",
        "part no": "vendor_part_number",
        "part number": "vendor_part_number",
        "item": "vendor_part_number",
        "item #": "vendor_part_number",
        "item no": "vendor_part_number",
        "item number": "vendor_part_number",

        "description": "description",
        "item description": "description",
        "product description": "description",

        "qty": "quantity_shipped",
        "quantity": "quantity_shipped",
        "qty ship": "quantity_shipped",
        "qty shipped": "quantity_shipped",
        "quantity shipped": "quantity_shipped",
        "shipped": "quantity_shipped",

        "uom": "uom",
        "unit": "uom",
        "units": "uom",

        "rate": "unit_price_usd",
        "price": "unit_price_usd",
        "unit price": "unit_price_usd",
        "unit cost": "unit_price_usd",
        "cost": "unit_price_usd",

        "amount": "extended_price_usd",
        "extended": "extended_price_usd",
        "extended price": "extended_price_usd",
        "extended amount": "extended_price_usd",
        "line total": "extended_price_usd",
        "ext": "extended_price_usd",
    }

    return aliases.get(
        normalized
    )


# ============================================================
# MAP ONE DETECTED ROW
# ============================================================

def map_table_row(
    row: dict[str, Any],
) -> dict[str, Any]:

    mapped = {
        "manufacturer_part_number": None,
        "vendor_part_number": None,
        "description": None,
        "quantity_shipped": None,
        "uom": None,
        "unit_price_usd": None,
        "extended_price_usd": None,
        "additional_info": {},
    }

    columns = row.get(
        "columns",
        {}
    )

    if not isinstance(
        columns,
        dict,
    ):
        return mapped

    for label, raw_values in columns.items():

        field = _semantic_field(
            label
        )

        value = _clean_value(
            raw_values
        )

        if value is None:
            continue

        # ----------------------------------------------------
        # Standard field
        # ----------------------------------------------------

        if field in STANDARD_FIELDS:

            # If the same standard field somehow appears twice,
            # preserve the first value instead of silently
            # replacing it.
            if mapped.get(field) in (
                None,
                "",
            ):

                if field in {
                    "quantity_shipped",
                    "unit_price_usd",
                    "extended_price_usd",
                }:

                    try:

                        numeric_text = (
                            str(value)
                            .replace(
                                ",",
                                "",
                            )
                            .replace(
                                "$",
                                "",
                            )
                            .strip()
                        )

                        mapped[field] = float(
                            numeric_text
                        )

                    except (
                        TypeError,
                        ValueError,
                    ):

                        mapped[field] = value

                else:

                    mapped[field] = value

            continue

        # ----------------------------------------------------
        # Extra dynamic column
        # ----------------------------------------------------

        mapped[
            "additional_info"
        ][
            str(label).strip()
        ] = value

    return mapped


# ============================================================
# MAP ALL DETECTED ITEM ROWS
# ============================================================

def map_table_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    mapped_items = []

    for row in rows:

        if not row.get(
            "is_item_row",
            True,
        ):
            continue

        item = map_table_row(
            row
        )

        # ----------------------------------------------------
        # Require some meaningful item evidence.
        # ----------------------------------------------------

        has_content = any(
            item.get(field)
            not in (
                None,
                "",
            )
            for field
            in STANDARD_FIELDS
        )

        if not has_content:
            continue

        mapped_items.append(
            item
        )

    return mapped_items


__all__ = [
    "map_table_row",
    "map_table_rows",
]