import csv
from io import BytesIO, StringIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter


# --------------------------------------------------------------
# Standard Item Master fields
# --------------------------------------------------------------
#
# FIXED_COLUMNS always appear in the export, in this order —
# Invoice details, then Vendor, then Customer — regardless of
# supplier or how many invoices are combined into one export.
# They are never dropped even if a value is blank on some rows,
# because every exported row needs to be traceable back to
# which invoice/vendor/customer it came from.
#
# ITEM_MASTER_COLUMNS (the line-item columns) stay dynamic:
# (Excel/CSV header, row field). Which of these appear in a
# given export is decided from the data being exported — see
# _active_columns() below.

FIXED_COLUMNS = [
    ("Invoice Number", "invoice_invoice_number"),
    ("Invoice Date", "invoice_invoice_date"),
    ("Due Date", "invoice_due_date"),
    ("PO Number", "invoice_purchase_order_number"),
    ("Vendor Name", "invoice_vendor_name"),
    ("Vendor Address", "invoice_vendor_address"),
    ("Vendor Phone", "invoice_vendor_phone"),
    ("Vendor Email", "invoice_vendor_email"),
    ("Customer Name", "invoice_customer_name"),
    ("Customer Address", "invoice_customer_address"),
]

ITEM_MASTER_COLUMNS = [
    ("Manufacturer Part Number", "manufacturer_part_number"),
    ("Vendor Part Number", "vendor_part_number"),
    ("Description", "description"),
    ("UOM", "uom"),
    ("Qty Ship", "quantity_shipped"),
    ("Unit Price USD", "unit_price_usd"),
    ("Extended Price USD", "extended_price_usd"),
]


def _active_columns(
    line_items: list[dict[str, Any]],
) -> list[tuple[str, str]]:
    """
    Return the full column set for this export: the fixed
    Invoice / Vendor / Customer columns (always present) plus
    only the line-item columns that have real data somewhere in
    this batch of rows.

    A line-item column is dropped only when NOT ONE row in this
    export has a value for it — e.g. if nothing in this export
    has a manufacturer part number, that column doesn't appear
    at all, rather than exporting as an empty column.
    """

    active_item_columns = [
        (header, field)
        for header, field in ITEM_MASTER_COLUMNS
        if any(
            item.get(field) not in (None, "")
            for item in line_items
        )
    ]

    # Never let the line-item side be completely empty — if
    # somehow nothing matched (shouldn't happen once there's at
    # least one row), fall back to the full standard set.
    active_item_columns = active_item_columns or ITEM_MASTER_COLUMNS

    return FIXED_COLUMNS + active_item_columns


def build_item_master_workbook(
    export_rows: list[dict[str, Any]],
) -> bytes:
    """
    Build an Item Master Excel workbook from approved invoice
    export rows (see db.get_export_rows) collected across one or
    many invoices — potentially thousands, since each invoice
    just contributes a handful more rows to the same flat sheet.

    Invoice / Vendor / Customer columns are always present and
    fixed. Line-item columns are dynamic: only the ones that have
    real data anywhere in this batch are included.

    Returns:
        The .xlsx file contents as bytes, ready for a Streamlit
        download_button.
    """

    columns = _active_columns(export_rows)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Item Master"

    header_font = Font(bold=True)
    header_alignment = Alignment(horizontal="center")

    # --------------------------------------------------
    # Header row
    # --------------------------------------------------

    for col_index, (header, _field) in enumerate(columns, start=1):
        cell = sheet.cell(row=1, column=col_index, value=header)
        cell.font = header_font
        cell.alignment = header_alignment

    # --------------------------------------------------
    # Data rows
    # --------------------------------------------------

    for row_index, item in enumerate(export_rows, start=2):

        for col_index, (_header, field) in enumerate(
            columns, start=1
        ):
            sheet.cell(
                row=row_index,
                column=col_index,
                value=item.get(field),
            )

    # --------------------------------------------------
    # Column widths
    # --------------------------------------------------

    for col_index, (header, _field) in enumerate(columns, start=1):
        sheet.column_dimensions[
            get_column_letter(col_index)
        ].width = max(18, len(header) + 2)

    sheet.freeze_panes = "A2"

    # --------------------------------------------------
    # Serialize to bytes
    # --------------------------------------------------

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    return buffer.getvalue()


def build_item_master_csv(
    export_rows: list[dict[str, Any]],
) -> bytes:
    """
    Build an Item Master CSV from approved invoice export rows
    (see db.get_export_rows) collected across one or many
    invoices — this is the format meant for bulk runs (hundreds
    or thousands of PDFs): one CSV, one row per line item, with
    Invoice / Vendor / Customer repeated as fixed columns on
    every row so each line can be traced back to its source
    invoice without opening the PDF again.

    Uses the same column logic as the Excel export
    (_active_columns), so the two formats never drift apart.

    Returns:
        UTF-8 encoded CSV bytes, ready for a Streamlit
        download_button.
    """

    columns = _active_columns(export_rows)

    buffer = StringIO()

    writer = csv.writer(buffer)

    writer.writerow([header for header, _field in columns])

    for item in export_rows:

        writer.writerow(
            [
                item.get(field)
                if item.get(field) is not None
                else ""
                for _header, field in columns
            ]
        )

    return buffer.getvalue().encode("utf-8")