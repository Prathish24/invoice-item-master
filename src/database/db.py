import json
import sqlite3
from pathlib import Path
from typing import Any


DB_PATH = Path("data/invoice_master.db")


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection() -> sqlite3.Connection:
    """Create and return a SQLite database connection."""

    DB_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(DB_PATH)

    connection.row_factory = sqlite3.Row

    return connection


# ============================================================
# SCHEMA MIGRATION HELPER
# ============================================================

def _ensure_column(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    """
    Add a column to an existing table if it does not already exist.

    This allows the database schema to evolve without requiring
    the existing database file to be deleted.
    """

    existing_columns = {
        row["name"]
        for row in connection.execute(
            f"PRAGMA table_info({table})"
        )
    }

    if column not in existing_columns:

        connection.execute(
            f"""
            ALTER TABLE {table}
            ADD COLUMN {column} {definition}
            """
        )


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def initialize_database() -> None:
    """Create the invoices table and required columns."""

    connection = get_connection()

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            file_name TEXT NOT NULL,

            extraction_method TEXT,

            supplier TEXT,

            layout TEXT,

            vendor_name TEXT,

            customer_name TEXT,

            ship_to_name TEXT,

            invoice_number TEXT,

            invoice_date TEXT,

            due_date TEXT,

            purchase_order_number TEXT,

            invoice_data TEXT NOT NULL,

            validation_data TEXT NOT NULL,

            status TEXT NOT NULL,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # ========================================================
    # DATABASE MIGRATIONS
    # ========================================================

    _ensure_column(
        connection,
        "invoices",
        "customer_name",
        "TEXT",
    )

    _ensure_column(
        connection,
        "invoices",
        "ship_to_name",
        "TEXT",
    )

    _ensure_column(
        connection,
        "invoices",
        "ship_to_address",
        "TEXT",
    )

    _ensure_column(
        connection,
        "invoices",
        "approval_status",
        "TEXT DEFAULT 'PENDING'",
    )

    _ensure_column(
        connection,
        "invoices",
        "approved_invoice_data",
        "TEXT",
    )

    _ensure_column(
        connection,
        "invoices",
        "approved_at",
        "TIMESTAMP",
    )

    connection.commit()

    connection.close()


# ============================================================
# SAVE INVOICE RESULT
# ============================================================

def save_invoice_result(
    result: dict[str, Any],
) -> int:
    """
    Save a processed invoice result into the database.

    Returns:
        Database ID of the inserted invoice.
    """

    invoice = (
        result.get("invoice")
        or {}
    )

    validation = (
        result.get("validation")
        or {}
    )

    connection = get_connection()

    cursor = connection.execute(
        """
        INSERT INTO invoices (
            file_name,
            extraction_method,
            supplier,
            layout,
            vendor_name,
            customer_name,
            ship_to_name,
            ship_to_address,
            invoice_number,
            invoice_date,
            due_date,
            purchase_order_number,
            invoice_data,
            validation_data,
            status,
            approval_status
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            result.get(
                "file_name"
            ),

            result.get(
                "extraction_method"
            ),

            result.get(
                "supplier"
            ),

            result.get(
                "layout"
            ),

            invoice.get(
                "vendor_name"
            ),

            invoice.get(
                "customer_name"
            ),

            invoice.get(
                "ship_to_name"
            ),

            invoice.get(
                "ship_to_address"
            ),

            invoice.get(
                "invoice_number"
            ),

            invoice.get(
                "invoice_date"
            ),

            invoice.get(
                "due_date"
            ),

            invoice.get(
                "purchase_order_number"
            ),

            json.dumps(
                invoice
            ),

            json.dumps(
                validation
            ),

            validation.get(
                "status",
                "FAIL",
            ),

            "PENDING",
        ),
    )

    invoice_id = cursor.lastrowid

    connection.commit()

    connection.close()

    return invoice_id


# ============================================================
# APPROVE INVOICE
# ============================================================

def approve_invoice(
    invoice_id: int,
    approved_invoice: dict[str, Any],
) -> None:
    """
    Save human-reviewed/corrected invoice data and mark the
    invoice as APPROVED.

    The original extracted invoice_data remains untouched as
    the audit trail.
    """

    connection = get_connection()

    connection.execute(
        """
        UPDATE invoices

        SET approved_invoice_data = ?,

            approval_status = 'APPROVED',

            approved_at = CURRENT_TIMESTAMP

        WHERE id = ?
        """,
        (
            json.dumps(
                approved_invoice
            ),

            invoice_id,
        ),
    )

    connection.commit()

    connection.close()


# ============================================================
# GET ALL INVOICES
# ============================================================

def get_all_invoices() -> list[dict[str, Any]]:
    """Return all stored invoices."""

    connection = get_connection()

    rows = connection.execute(
        """
        SELECT *
        FROM invoices
        ORDER BY id DESC
        """
    ).fetchall()

    connection.close()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# GET APPROVED LINE ITEMS
# ============================================================

def get_approved_line_items() -> list[dict[str, Any]]:
    """
    Return standardized Item Master line items for every
    APPROVED invoice.

    Uses approved_invoice_data when available and falls back
    to the original invoice_data defensively.
    """

    connection = get_connection()

    rows = connection.execute(
        """
        SELECT
            approved_invoice_data,
            invoice_data

        FROM invoices

        WHERE approval_status = 'APPROVED'

        ORDER BY id ASC
        """
    ).fetchall()

    connection.close()

    line_items: list[dict[str, Any]] = []

    for row in rows:

        raw_data = (
            row["approved_invoice_data"]
            or row["invoice_data"]
        )

        if not raw_data:
            continue

        invoice = json.loads(
            raw_data
        )

        for item in invoice.get(
            "line_items",
            [],
        ):

            line_items.append(
                item
            )

    return line_items


# ============================================================
# EXPORT HEADER FIELDS
# ============================================================

INVOICE_HEADER_FIELDS = [
    "invoice_number",
    "invoice_date",
    "due_date",
    "purchase_order_number",
]


VENDOR_HEADER_FIELDS = [
    "vendor_name",
    "vendor_address",
    "vendor_phone",
    "vendor_email",
]


CUSTOMER_HEADER_FIELDS = [
    "customer_name",
    "customer_address",
]


# NEW:
# Ship To is kept separate from Bill To / Customer.

SHIP_TO_HEADER_FIELDS = [
    "ship_to_name",
    "ship_to_address",
]


# ============================================================
# ADDITIONAL INVOICE HEADER FIELDS
# ============================================================
#
# These fields are stored inside invoice_data / approved_invoice_data.
# They are passed through to the Item Master export when present.
#
# They are NOT guessed by this database layer. If the extractor
# did not find a value, the exported field remains blank.
# ============================================================

ADDITIONAL_INVOICE_HEADER_FIELDS = [
    "sales_order_number",
    "quote_number",
    "order_date",
    "ship_date",
    "delivery_date",
    "packing_slip_number",
    "customer_account_number",
    "vendor_account_number",
    "job_number",
    "project_number",
    "terms",
    "currency",
    "freight",
    "discount",
    "tracking_number",
    "salesperson",
    "tax_id",
]


# ============================================================
# GET EXPORT ROWS
# ============================================================

def get_export_rows(
    invoice_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    """
    Return one flattened export row per line item for every
    APPROVED invoice.

    Each row contains:

        Invoice information
        Vendor information
        Bill To / Customer information
        Ship To information
        Additional invoice information, when available
        Line-item information

    This supports combining many invoices into one Item Master
    export.
    """

    connection = get_connection()

    query = """
        SELECT
            id,
            file_name,
            approved_invoice_data,
            invoice_data

        FROM invoices

        WHERE approval_status = 'APPROVED'
    """

    params: tuple = ()

    if invoice_ids:

        placeholders = ",".join(
            "?"
            for _ in invoice_ids
        )

        query += (
            f" AND id IN ({placeholders})"
        )

        params = tuple(
            invoice_ids
        )

    query += """
        ORDER BY id ASC
    """

    rows = connection.execute(
        query,
        params,
    ).fetchall()

    connection.close()

    export_rows: list[
        dict[str, Any]
    ] = []

    for row in rows:

        raw_data = (
            row["approved_invoice_data"]
            or row["invoice_data"]
        )

        if not raw_data:
            continue

        invoice = json.loads(
            raw_data
        )

        # ----------------------------------------------------
        # Header information
        # ----------------------------------------------------

        header: dict[str, Any] = {
            "invoice_source_file":
                row["file_name"]
        }

        all_header_fields = (
            INVOICE_HEADER_FIELDS
            + VENDOR_HEADER_FIELDS
            + CUSTOMER_HEADER_FIELDS
            + SHIP_TO_HEADER_FIELDS
            + ADDITIONAL_INVOICE_HEADER_FIELDS
        )

        # Some export field names don't match the extractor's
        # actual output key. The extractor returns freight_usd /
        # discount_usd, but the exported column is invoice_freight /
        # invoice_discount (see item_master_export.py). Map those
        # explicitly so the value is actually read from the
        # invoice instead of silently coming back None.
        field_source_overrides = {
            "freight": "freight_usd",
            "discount": "discount_usd",
        }

        for field in all_header_fields:

            source_field = field_source_overrides.get(
                field,
                field,
            )

            header[
                f"invoice_{field}"
            ] = invoice.get(
                source_field
            )

        # ----------------------------------------------------
        # Line items
        # ----------------------------------------------------

        line_items = invoice.get(
            "line_items",
            [],
        )

        if not line_items:

            export_rows.append(
                dict(header)
            )

            continue

        for item in line_items:

            export_row = dict(
                header
            )

            export_row.update(
                item
            )

            export_rows.append(
                export_row
            )

    return export_rows