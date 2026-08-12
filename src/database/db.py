import json
import sqlite3
from pathlib import Path
from typing import Any


DB_PATH = Path("data/invoice_master.db")


def get_connection() -> sqlite3.Connection:
    """Create and return a SQLite database connection."""

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    return connection


def _ensure_column(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    """
    Add a column to an existing table if it does not already exist.

    Lets the schema evolve (e.g. adding the approval workflow
    columns) without breaking a database that was created by an
    earlier version of this app.
    """

    existing_columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table})")
    }

    if column not in existing_columns:
        connection.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )


def initialize_database() -> None:
    """Create the invoices table if it does not already exist."""

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

    # --------------------------------------------------
    # Approval workflow columns
    # --------------------------------------------------
    #
    # `status` already tracks the extraction/validation outcome
    # (PASS / REVIEW / FAIL), so the human-review approval state
    # is tracked separately and never overwrites it.

    # Older databases (created before customer/vendor contact
    # info was tracked) get this column added on startup too.

    _ensure_column(
        connection,
        "invoices",
        "customer_name",
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


def save_invoice_result(result: dict[str, Any]) -> int:
    """
    Save a processed invoice result into the database.

    Returns:
        Database ID of the inserted invoice.
    """

    invoice = result.get("invoice") or {}
    validation = result.get("validation") or {}

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
            invoice_number,
            invoice_date,
            due_date,
            purchase_order_number,
            invoice_data,
            validation_data,
            status,
            approval_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result.get("file_name"),
            result.get("extraction_method"),
            result.get("supplier"),
            result.get("layout"),
            invoice.get("vendor_name"),
            invoice.get("customer_name"),
            invoice.get("invoice_number"),
            invoice.get("invoice_date"),
            invoice.get("due_date"),
            invoice.get("purchase_order_number"),
            json.dumps(invoice),
            json.dumps(validation),
            validation.get("status", "FAIL"),
            "PENDING",
        ),
    )

    invoice_id = cursor.lastrowid

    connection.commit()
    connection.close()

    return invoice_id


def approve_invoice(
    invoice_id: int,
    approved_invoice: dict[str, Any],
) -> None:
    """
    Save the human-reviewed/corrected invoice data and mark the
    invoice as APPROVED.

    This is what makes edits made on the verification screen
    (corrected part numbers, UOM, prices, etc.) durable — the
    original extracted `invoice_data` is left untouched as an
    audit trail, and the verified values are stored separately
    in `approved_invoice_data`.
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
            json.dumps(approved_invoice),
            invoice_id,
        ),
    )

    connection.commit()
    connection.close()


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

    return [dict(row) for row in rows]


def get_approved_line_items() -> list[dict[str, Any]]:
    """
    Return the standardized Item Master line items for every
    APPROVED invoice, across all suppliers.

    Uses the human-verified `approved_invoice_data` when present
    (falls back to the original `invoice_data` defensively, so a
    row can never be silently dropped from export).

    Kept for backward compatibility. For the actual Item Master
    export (which needs Invoice / Vendor / Customer as fixed
    columns), use get_export_rows() instead.
    """

    connection = get_connection()

    rows = connection.execute(
        """
        SELECT approved_invoice_data, invoice_data
        FROM invoices
        WHERE approval_status = 'APPROVED'
        ORDER BY id ASC
        """
    ).fetchall()

    connection.close()

    line_items: list[dict[str, Any]] = []

    for row in rows:

        raw_data = row["approved_invoice_data"] or row["invoice_data"]

        if not raw_data:
            continue

        invoice = json.loads(raw_data)

        for item in invoice.get("line_items", []):
            line_items.append(item)

    return line_items


# --------------------------------------------------------------
# Header fields that get repeated on every exported line-item
# row. These three groups (Invoice / Vendor / Customer) are the
# "fixed columns" the export always shows, no matter how many
# invoices or suppliers are combined in one export run.
# --------------------------------------------------------------

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


def get_export_rows(invoice_ids: list[int] | None = None) -> list[dict[str, Any]]:
    """
    Return one flattened export row PER LINE ITEM, for every
    APPROVED invoice (or a specific subset, via invoice_ids).

    Each row carries the fixed Invoice / Vendor / Customer header
    fields (prefixed so they never collide with line-item field
    names) plus that line item's own fields — e.g.:

        {
            "invoice_invoice_number": "18956",
            "invoice_vendor_name": "Aries Electric Motor",
            "invoice_customer_name": "CHAMPION ELEVATOR",
            "description": "REWOUND BRAKE COIL",
            "quantity_shipped": 1,
            ...
        }

    This is what the Item Master export is built from, and it
    scales the same way whether one invoice or a thousand were
    processed: it's just more rows in the same flat table.
    """

    connection = get_connection()

    query = """
        SELECT id, file_name, approved_invoice_data, invoice_data
        FROM invoices
        WHERE approval_status = 'APPROVED'
    """

    params: tuple = ()

    if invoice_ids:
        placeholders = ",".join("?" for _ in invoice_ids)
        query += f" AND id IN ({placeholders})"
        params = tuple(invoice_ids)

    query += " ORDER BY id ASC"

    rows = connection.execute(query, params).fetchall()

    connection.close()

    export_rows: list[dict[str, Any]] = []

    for row in rows:

        raw_data = row["approved_invoice_data"] or row["invoice_data"]

        if not raw_data:
            continue

        invoice = json.loads(raw_data)

        header: dict[str, Any] = {"invoice_source_file": row["file_name"]}

        for field in INVOICE_HEADER_FIELDS + VENDOR_HEADER_FIELDS + CUSTOMER_HEADER_FIELDS:
            header[f"invoice_{field}"] = invoice.get(field)

        line_items = invoice.get("line_items", [])

        if not line_items:
            # An approved invoice with no line items still gets
            # one row, so its header data isn't silently dropped
            # from the export.
            export_rows.append(dict(header))
            continue

        for item in line_items:
            export_row = dict(header)
            export_row.update(item)
            export_rows.append(export_row)

    return export_rows