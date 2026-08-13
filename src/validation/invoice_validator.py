import re
from typing import Any


def validate_invoice(
    invoice: dict[str, Any],
) -> dict[str, Any]:
    """
    Validate extracted and normalized invoice data.

    Important rule:
    A field that is genuinely absent from the invoice should
    not automatically be treated as an extraction error.

    Price validation respects the invoice UOM multiplier:

        EA / E / EACH:
            Unit Price × Quantity

        C:
            Unit Price / 100 × Quantity

        M:
            Unit Price / 1000 × Quantity

        BOX / SET:
            Unit Price × Quantity

    Suspicious OCR values are flagged for REVIEW rather than
    automatically corrected.
    """

    errors = []
    warnings = []

    # ========================================================
    # HEADER VALIDATION
    # ========================================================

    required_headers = {
        "vendor_name": "Vendor name",
        "invoice_number": "Invoice number",
        "invoice_date": "Invoice date",
    }

    for field, label in required_headers.items():

        if not invoice.get(field):

            errors.append(
                f"Missing {label}"
            )

    # These fields may legitimately be absent.

    if not invoice.get("customer_name"):

        warnings.append(
            "Customer name not found in invoice"
        )

    if not invoice.get("vendor_address"):

        warnings.append(
            "Vendor address not found in invoice"
        )

    if not invoice.get("customer_address"):

        warnings.append(
            "Customer address not found in invoice"
        )

    # ========================================================
    # LINE ITEMS
    # ========================================================

    line_items = invoice.get(
        "line_items",
        [],
    )

    if not line_items:

        errors.append(
            "No line items found"
        )

    for index, item in enumerate(
        line_items,
        start=1,
    ):

        description = item.get(
            "description"
        )

        quantity = item.get(
            "quantity_shipped"
        )

        unit_price = item.get(
            "unit_price_usd"
        )

        extended_price = item.get(
            "extended_price_usd"
        )

        uom = item.get(
            "uom"
        )

        uom_multiplier = item.get(
            "uom_multiplier"
        )

        # ====================================================
        # REQUIRED LINE INFORMATION
        # ====================================================

        if not description:

            errors.append(
                f"Line {index}: Missing description"
            )

        if quantity is None:

            errors.append(
                f"Line {index}: Missing quantity"
            )

        if unit_price is None:

            errors.append(
                f"Line {index}: Missing unit price"
            )

        if extended_price is None:

            errors.append(
                f"Line {index}: Missing extended price"
            )

        # ====================================================
        # UOM
        # ====================================================

        if not uom:

            warnings.append(
                f"Line {index}: UOM not found in invoice"
            )

        # ====================================================
        # SUSPICIOUS QUANTITY / DESCRIPTION CHECK
        # ====================================================
        #
        # OCR can sometimes take a number from the description
        # and incorrectly use it as the quantity.
        #
        # Example:
        #
        # Description:
        #     5 STRAWBERRY HILL, ASY-HPU, 2.5
        #
        # Extracted:
        #     quantity = 5
        #
        # The quantity may be correct OR it may have been
        # incorrectly extracted from the description.
        #
        # Therefore:
        #
        #     DO NOT automatically change quantity.
        #
        # We only flag it for human review.
        # ====================================================

        if (
            description
            and quantity is not None
        ):

            try:

                description_text = str(
                    description
                ).strip()

                quantity_text = str(
                    quantity
                ).strip()

                # ------------------------------------------------
                # Normalize numeric representation.
                #
                # This allows:
                #
                # 5
                # 5.0
                # 5.00
                #
                # to be compared consistently.
                # ------------------------------------------------

                quantity_value = float(
                    quantity
                )

                # Only perform this check for finite values.
                if (
                    quantity_value
                    == quantity_value
                    and quantity_value
                    not in (
                        float("inf"),
                        float("-inf"),
                    )
                ):

                    if quantity_value.is_integer():

                        normalized_quantity = str(
                            int(quantity_value)
                        )

                    else:

                        normalized_quantity = (
                            quantity_text
                        )

                    # ------------------------------------------------
                    # Search for the quantity as a complete number
                    # inside the description.
                    #
                    # Example:
                    #
                    # quantity = 5
                    #
                    # description =
                    # "5 STRAWBERRY HILL, ASY-HPU, 2.5"
                    #
                    # -> suspicious
                    #
                    # But:
                    #
                    # quantity = 5
                    # description = "25 AMP FUSE"
                    #
                    # -> NOT suspicious because 5 is not a
                    #    complete numeric token.
                    # ------------------------------------------------

                    quantity_pattern = (
                        r"(?<![\d.])"
                        + re.escape(
                            normalized_quantity
                        )
                        + r"(?![\d.])"
                    )

                    if re.search(
                        quantity_pattern,
                        description_text,
                    ):

                        warnings.append(
                            f"Line {index}: "
                            f"Quantity {quantity} also appears "
                            f"inside the description; "
                            f"verify quantity"
                        )

            except (
                TypeError,
                ValueError,
            ):

                # Numeric validation below will handle
                # genuinely invalid quantity values.
                pass

        # ====================================================
        # PRICE VALIDATION
        # ====================================================

        if (
            quantity is not None
            and unit_price is not None
            and extended_price is not None
        ):

            try:

                quantity_value = float(
                    quantity
                )

                unit_price_value = float(
                    unit_price
                )

                actual_amount = float(
                    extended_price
                )

                # ------------------------------------------------
                # Determine multiplier
                # ------------------------------------------------

                if uom_multiplier is not None:

                    multiplier = float(
                        uom_multiplier
                    )

                else:

                    normalized_uom = (
                        str(uom)
                        .strip()
                        .upper()
                        if uom
                        else ""
                    )

                    if normalized_uom in {
                        "M",
                        "MIL",
                        "THOUSAND",
                    }:

                        multiplier = 1000.0

                    elif normalized_uom in {
                        "C",
                        "HUNDRED",
                    }:

                        multiplier = 100.0

                    else:

                        multiplier = 1.0

                if multiplier <= 0:

                    errors.append(
                        f"Line {index}: "
                        f"Invalid UOM multiplier"
                    )

                    continue

                # ------------------------------------------------
                # Calculate expected extended price
                # ------------------------------------------------

                expected_amount = (
                    unit_price_value
                    / multiplier
                    * quantity_value
                )

                # ------------------------------------------------
                # Compare with invoice amount
                # ------------------------------------------------

                if abs(
                    expected_amount
                    - actual_amount
                ) > 0.02:

                    errors.append(
                        f"Line {index}: "
                        f"Extended price mismatch "
                        f"(expected "
                        f"{expected_amount:.2f}, "
                        f"found "
                        f"{actual_amount:.2f})"
                    )

            except (
                TypeError,
                ValueError,
                ZeroDivisionError,
            ):

                errors.append(
                    f"Line {index}: "
                    f"Invalid numeric value"
                )

        # ====================================================
        # PART NUMBERS
        # ====================================================

        # IMPORTANT:
        #
        # We do NOT warn just because manufacturer_part_number
        # is empty.
        #
        # The invoice may genuinely contain only a vendor/item
        # number.
        #
        # Example:
        #
        # Manufacturer Part Number = blank
        # Vendor Part Number       = 99069802450
        #
        # This is valid if the invoice does not identify a
        # manufacturer part number.
        #
        # Same principle for vendor_part_number.
        #
        # We only flag missing part numbers if the extraction
        # logic later explicitly tells us that the invoice
        # contained such a field.

    # ========================================================
    # OVERALL STATUS
    # ========================================================

    if errors:

        status = "FAIL"

    elif warnings:

        status = "REVIEW"

    else:

        status = "PASS"

    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "is_valid": len(errors) == 0,
    }