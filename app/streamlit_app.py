import sys
from pathlib import Path

import streamlit as st


# --------------------------------------------------
# Project path
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from src.pipeline import process_invoice
from src.validation.invoice_validator import validate_invoice
from src.export.item_master_export import (
    build_item_master_csv,
    build_item_master_workbook,
)
from src.database.db import (
    initialize_database,
    save_invoice_result,
    approve_invoice,
    get_export_rows,
)


# --------------------------------------------------
# Standard Item Master fields
# --------------------------------------------------
#
# (field key, display label, input kind). This is the full set
# of possible fields — which of them actually get shown for a
# given invoice is decided dynamically per invoice, based on
# what that invoice's extracted data actually contains.

ITEM_MASTER_FIELDS = [
    ("manufacturer_part_number", "Manufacturer Part Number", "text"),
    ("vendor_part_number", "Vendor Part Number", "text"),
    ("description", "Description", "text"),
    ("uom", "UOM", "text"),
    ("quantity_shipped", "Qty Ship", "quantity"),
    ("unit_price_usd", "Unit Price USD", "money"),
    ("extended_price_usd", "Extended Price USD", "money"),
]


def _any_line_item_has_value(
    line_items: list[dict],
    field: str,
) -> bool:
    """True if at least one line item has a real value for field."""

    for item in line_items:

        value = item.get(field)

        if value not in (None, ""):
            return True

    return False


# --------------------------------------------------
# Page configuration
# --------------------------------------------------

st.set_page_config(
    page_title="Invoice Item Master",
    page_icon="📄",
    layout="wide",
)


# --------------------------------------------------
# Initialize database
# --------------------------------------------------

initialize_database()


# --------------------------------------------------
# Session state
# --------------------------------------------------

if "processed_invoice" not in st.session_state:
    st.session_state.processed_invoice = None

if "pdf_path" not in st.session_state:
    st.session_state.pdf_path = None

if "invoice_id" not in st.session_state:
    st.session_state.invoice_id = None

if "invoice_approved" not in st.session_state:
    st.session_state.invoice_approved = False


# --------------------------------------------------
# Header
# --------------------------------------------------

st.title("📄 Invoice Item Master")

st.write(
    "Upload vendor invoices, extract item information, "
    "and verify the extracted Item Master data."
)


# --------------------------------------------------
# Upload invoices
# --------------------------------------------------

uploaded_files = st.file_uploader(
    "Upload Invoice PDFs",
    type=["pdf"],
    accept_multiple_files=True,
)


# --------------------------------------------------
# Process invoices
# --------------------------------------------------

if uploaded_files:

    st.write(f"Selected invoices: **{len(uploaded_files)}**")

    if st.button("🚀 Process Invoices"):

        input_dir = PROJECT_ROOT / "data" / "input" / "invoices"
        input_dir.mkdir(parents=True, exist_ok=True)

        progress = st.progress(0)

        for index, uploaded_file in enumerate(uploaded_files):

            st.write(f"Processing: **{uploaded_file.name}**")

            pdf_path = input_dir / uploaded_file.name

            with open(pdf_path, "wb") as file:
                file.write(uploaded_file.getbuffer())

            try:

                result = process_invoice(pdf_path)

                invoice_id = save_invoice_result(result)

                if result["success"]:

                    st.session_state.processed_invoice = result
                    st.session_state.pdf_path = pdf_path
                    st.session_state.invoice_id = invoice_id
                    st.session_state.invoice_approved = False

                    status = result["validation"]["status"]

                    if status == "PASS":
                        st.success(
                            f"✅ {uploaded_file.name} → PASS "
                            f"(ID: {invoice_id})"
                        )

                    elif status == "REVIEW":
                        st.warning(
                            f"⚠️ {uploaded_file.name} → REVIEW "
                            f"(ID: {invoice_id})"
                        )

                    else:
                        st.error(
                            f"❌ {uploaded_file.name} → FAIL "
                            f"(ID: {invoice_id})"
                        )

                else:

                    st.error(
                        f"❌ Extraction failed: {uploaded_file.name}"
                    )

            except Exception as e:

                st.error(
                    f"Error processing {uploaded_file.name}: {e}"
                )

            progress.progress(
                (index + 1) / len(uploaded_files)
            )

        st.success("Processing completed.")


# --------------------------------------------------
# Verification screen
# --------------------------------------------------

result = st.session_state.processed_invoice
pdf_path = st.session_state.pdf_path


if result and result.get("success"):

    st.divider()

    st.header("🔍 Invoice Verification")

    invoice = result["invoice"]
    validation = result["validation"]

    # --------------------------------------------------
    # Supplier + Layout information
    # --------------------------------------------------

    info1, info2, info3, info4 = st.columns(4)

    with info1:
        st.metric(
            "Supplier",
            result.get("supplier") or "Unknown",
        )

    with info2:
        st.metric(
            "Layout",
            result.get("layout") or "Generic",
        )

    with info3:
        st.metric(
            "Extraction",
            result.get("extraction_method") or "Unknown",
        )

    with info4:
        st.metric(
            "Status",
            "APPROVED"
            if st.session_state.invoice_approved
            else validation.get("status", "FAIL"),
        )

    # --------------------------------------------------
    # PDF + Invoice details
    # --------------------------------------------------

    left, right = st.columns([1, 1])

    # --------------------------------------------------
    # PDF
    # --------------------------------------------------

    with left:

        st.subheader("📄 Invoice")

        if pdf_path and pdf_path.exists():

            pdf_bytes = pdf_path.read_bytes()

            st.download_button(
                "Download Invoice PDF",
                data=pdf_bytes,
                file_name=pdf_path.name,
                mime="application/pdf",
            )

            st.pdf(pdf_bytes)

    # --------------------------------------------------
    # Invoice header
    # --------------------------------------------------

    with right:

        st.subheader("Invoice Details")

        invoice_number = st.text_input(
            "Invoice Number",
            value=invoice.get("invoice_number") or "",
        )

        invoice_date = st.text_input(
            "Invoice Date",
            value=invoice.get("invoice_date") or "",
        )

        due_date = st.text_input(
            "Due Date",
            value=invoice.get("due_date") or "",
        )

        purchase_order = st.text_input(
            "Purchase Order Number",
            value=invoice.get("purchase_order_number") or "",
        )

        st.subheader("Vendor Information")

        vendor_name = st.text_input(
            "Vendor Name",
            value=invoice.get("vendor_name") or "",
        )

        vendor_address = st.text_input(
            "Vendor Address",
            value=invoice.get("vendor_address") or "",
        )

        vendor_phone = st.text_input(
            "Vendor Phone",
            value=invoice.get("vendor_phone") or "",
        )

        vendor_email = st.text_input(
            "Vendor Email",
            value=invoice.get("vendor_email") or "",
        )

        st.subheader("Customer Information")

        customer_name = st.text_input(
            "Customer Name",
            value=invoice.get("customer_name") or "",
        )

        customer_address = st.text_input(
            "Customer Address",
            value=invoice.get("customer_address") or "",
        )

    # --------------------------------------------------
    # Item Master Verification
    # --------------------------------------------------

    st.divider()

    st.header("📦 Item Master Verification")

    st.caption(
        "Verify or correct the extracted values before approval."
    )

    line_items = invoice.get("line_items", [])

    # Collected below so it is still available further down the
    # page (Approval section) even when there are no line items.
    edited_items = []

    if not line_items:

        st.warning("No line items were extracted.")

    else:

        # --------------------------------------------------
        # Which fields actually appear on THIS invoice
        # --------------------------------------------------
        #
        # A field is shown only if at least one line item on
        # this invoice actually has a value for it. Nothing
        # fixed — a supplier that never gives a UOM simply
        # never shows a UOM box; one that gives manufacturer
        # part numbers shows that column for every item on
        # that invoice (blank on the rows that lack it).

        active_fields = [
            (field, label, kind)
            for field, label, kind in ITEM_MASTER_FIELDS
            if _any_line_item_has_value(line_items, field)
        ]

        for index, item in enumerate(line_items):

            st.markdown(f"#### Line Item {index + 1}")

            edited_values = {}

            # Render the active fields in rows of up to 4 columns.
            for chunk_start in range(0, len(active_fields), 4):

                chunk = active_fields[chunk_start:chunk_start + 4]

                columns = st.columns(len(chunk))

                for column, (field, label, kind) in zip(
                    columns, chunk
                ):

                    with column:

                        if kind == "text":

                            edited_values[field] = st.text_input(
                                label,
                                value=item.get(field) or "",
                                key=f"{field}_{index}",
                            ) or None

                        elif kind == "quantity":

                            edited_values[field] = st.number_input(
                                label,
                                min_value=0.0,
                                value=float(item.get(field) or 0),
                                key=f"{field}_{index}",
                            )

                        else:  # money

                            edited_values[field] = st.number_input(
                                label,
                                min_value=0.0,
                                value=float(item.get(field) or 0),
                                format="%.2f",
                                key=f"{field}_{index}",
                            )

            # --------------------------------------------------
            # UOM information
            # --------------------------------------------------

            uom_value = edited_values.get("uom")

            if uom_value:

                uom_upper = uom_value.strip().upper()

                if uom_upper in ["E", "EA", "EACH"]:

                    st.info("E / EA = 1 each")

                elif uom_upper == "C":

                    st.info("C = per hundred")

                elif uom_upper == "M":

                    st.info("M = per thousand")

            # --------------------------------------------------
            # Store edited row
            # --------------------------------------------------
            #
            # Fields not shown for this invoice stay None —
            # nothing is invented to fill out a fixed shape.

            edited_items.append(
                {
                    field: edited_values.get(field)
                    for field, _label, _kind in ITEM_MASTER_FIELDS
                }
            )

        # --------------------------------------------------
        # Show table preview
        # --------------------------------------------------

        st.divider()

        st.subheader("Item Master Preview")

        preview_rows = []

        for item in edited_items:

            preview_rows.append(
                {
                    label: (item.get(field) or "")
                    for field, label, _kind in active_fields
                }
            )

        st.dataframe(
            preview_rows,
            use_container_width=True,
            hide_index=True,
        )

    # --------------------------------------------------
    # Validation
    # --------------------------------------------------

    st.divider()

    st.subheader("🔎 Validation")

    if validation["status"] == "PASS":

        st.success("✅ PASS — Ready for approval")

    elif validation["status"] == "REVIEW":

        st.warning(
            "⚠️ REVIEW — Human verification required"
        )

    else:

        st.error(
            "❌ FAIL — Extraction or validation issue"
        )

    # --------------------------------------------------
    # Warnings
    # --------------------------------------------------

    if validation.get("warnings"):

        st.write("**Warnings:**")

        for warning in validation["warnings"]:

            st.warning(warning)

    # --------------------------------------------------
    # Errors
    # --------------------------------------------------

    if validation.get("errors"):

        st.write("**Errors:**")

        for error in validation["errors"]:

            st.error(error)

    # --------------------------------------------------
    # Approval
    # --------------------------------------------------

    st.divider()

    st.subheader("✅ Approval")

    if st.session_state.invoice_approved:

        st.info(
            "This invoice has already been approved. The "
            "verified values shown above have been saved."
        )

    if st.button(
        "✅ Approve Invoice",
        type="primary",
    ):

        # Build the invoice as the reviewer has edited it, so
        # header corrections and line-item corrections are both
        # captured before saving.

        edited_invoice = {
            "vendor_name": vendor_name or None,
            "vendor_address": vendor_address or None,
            "vendor_phone": vendor_phone or None,
            "vendor_email": vendor_email or None,
            "customer_name": customer_name or None,
            "customer_address": customer_address or None,
            "invoice_number": invoice_number or None,
            "invoice_date": invoice_date or None,
            "due_date": due_date or None,
            "purchase_order_number": purchase_order or None,
            "line_items": edited_items,
            "subtotal_usd": invoice.get("subtotal_usd"),
            "tax_usd": invoice.get("tax_usd"),
            "total_usd": invoice.get("total_usd"),
        }

        approval_validation = validate_invoice(edited_invoice)

        if approval_validation["status"] == "FAIL":

            st.error(
                "❌ Cannot approve — please resolve the "
                "following before approving:"
            )

            for error in approval_validation["errors"]:
                st.error(error)

        else:

            approve_invoice(
                st.session_state.invoice_id,
                edited_invoice,
            )

            st.session_state.invoice_approved = True

            st.success(
                "Invoice verified successfully and saved."
            )

            if approval_validation["warnings"]:

                st.write("**Saved with outstanding warnings:**")

                for warning in approval_validation["warnings"]:
                    st.warning(warning)


# --------------------------------------------------
# Export
# --------------------------------------------------

st.divider()

st.header("📤 Export Approved Item Master")

st.caption(
    "Combine every approved invoice — across all suppliers, "
    "even thousands of them — into one standardized Item "
    "Master file. Each row carries its Invoice, Vendor, and "
    "Customer details alongside that line item."
)

export_rows = get_export_rows()

st.write(
    f"Approved line items available for export: "
    f"**{len(export_rows)}**"
)

if export_rows:

    csv_bytes = build_item_master_csv(export_rows)
    workbook_bytes = build_item_master_workbook(export_rows)

    export_col1, export_col2 = st.columns(2)

    with export_col1:

        st.download_button(
            "⬇️ Download Item Master.csv",
            data=csv_bytes,
            file_name="item_master_export.csv",
            mime="text/csv",
        )

    with export_col2:

        st.download_button(
            "⬇️ Download Item Master.xlsx",
            data=workbook_bytes,
            file_name="item_master_export.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            ),
        )

else:

    st.info(
        "No approved invoices yet. Approve at least one "
        "invoice above to enable export."
    )


# --------------------------------------------------
# Pipeline
# --------------------------------------------------

st.divider()

st.subheader("Pipeline")

st.write(
    """
    PDF → Text/OCR → Supplier Detection → Layout Detection
    → Generic Parser → Groq → Normalization
    → Validation → Human Verification → Item Master CSV
    """
)