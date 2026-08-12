from typing import Any


def validate_invoice(invoice: dict[str, Any]) -> dict[str, Any]:
    """
    Validate extracted and normalized invoice data.

    Returns validation status, errors, and warnings.
    """

    errors = []
    warnings = []

    # -------------------------
    # Header validation
    # -------------------------

    required_headers = {
        "vendor_name": "Vendor name",
        "invoice_number": "Invoice number",
        "invoice_date": "Invoice date",
    }

    for field, label in required_headers.items():
        if not invoice.get(field):
            errors.append(f"Missing {label}")

    # Customer (bill-to) name is required for the Item Master
    # export, which always shows an Invoice / Vendor / Customer
    # block — but it's downgraded to a warning rather than an
    # error, since some invoices genuinely omit a bill-to name
    # and that shouldn't block an otherwise-valid extraction.

    if not invoice.get("customer_name"):
        warnings.append("Customer name not found")

    if not invoice.get("vendor_address"):
        warnings.append("Vendor address not found")

    if not invoice.get("customer_address"):
        warnings.append("Customer address not found")

    # -------------------------
    # Line item validation
    # -------------------------

    line_items = invoice.get("line_items", [])

    if not line_items:
        errors.append("No line items found")

    for index, item in enumerate(line_items, start=1):

        description = item.get("description")
        quantity = item.get("quantity_shipped")
        unit_price = item.get("unit_price_usd")
        extended_price = item.get("extended_price_usd")

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

        # -------------------------
        # Price calculation check
        # -------------------------

        if (
            quantity is not None
            and unit_price is not None
            and extended_price is not None
        ):
            try:
                expected_amount = float(quantity) * float(unit_price)
                actual_amount = float(extended_price)

                if abs(expected_amount - actual_amount) > 0.01:
                    errors.append(
                        f"Line {index}: Extended price mismatch "
                        f"(expected {expected_amount:.2f}, "
                        f"found {actual_amount:.2f})"
                    )

            except (TypeError, ValueError):
                errors.append(
                    f"Line {index}: Invalid numeric value"
                )

        # -------------------------
        # Part number warning
        # -------------------------

        if not item.get("manufacturer_part_number"):
            warnings.append(
                f"Line {index}: Manufacturer part number not found"
            )

        if not item.get("vendor_part_number"):
            warnings.append(
                f"Line {index}: Vendor part number not found"
            )

        # -------------------------
        # UOM warning
        # -------------------------

        if not item.get("uom"):
            warnings.append(
                f"Line {index}: UOM not found"
            )

    # -------------------------
    # Overall status
    # -------------------------

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