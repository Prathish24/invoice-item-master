import json
import sys
from pathlib import Path

import streamlit as st


# ============================================================
# PROJECT PATH
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================
# IMPORTS
# ============================================================

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
    get_all_invoices,
)


# ============================================================
# STANDARD ITEM MASTER FIELDS
# ============================================================

ITEM_MASTER_FIELDS = [
    (
        "manufacturer_part_number",
        "Manufacturer Part Number",
        "text",
    ),
    (
        "vendor_part_number",
        "Vendor Part Number",
        "text",
    ),
    (
        "description",
        "Description",
        "text",
    ),
    (
        "uom",
        "UOM",
        "text",
    ),
    (
        "quantity_shipped",
        "Qty Ship",
        "quantity",
    ),
    (
        "unit_price_usd",
        "Unit Price USD",
        "money",
    ),
    (
        "extended_price_usd",
        "Extended Price USD",
        "money",
    ),
]


# ============================================================
# HELPER
# ============================================================

def any_line_item_has_value(
    line_items: list[dict],
    field: str,
) -> bool:
    """
    Return True if at least one line item has a real value.
    """

    for item in line_items:

        value = item.get(field)

        if value not in (None, ""):
            return True

    return False


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Invoice Item Master",
    page_icon="📄",
    layout="wide",
)


# ============================================================
# INITIALIZE DATABASE
# ============================================================

initialize_database()


# ============================================================
# SESSION STATE
# ============================================================

if "selected_invoice_id" not in st.session_state:
    st.session_state.selected_invoice_id = None

if "processed_batch_ids" not in st.session_state:
    st.session_state.processed_batch_ids = []

if "invoice_approved" not in st.session_state:
    st.session_state.invoice_approved = False


# ============================================================
# HEADER
# ============================================================

st.title("📄 Invoice Item Master")

st.write(
    "Upload vendor invoices, extract item information, "
    "and verify the extracted Item Master data."
)


# ============================================================
# UPLOAD INVOICES
# ============================================================

uploaded_files = st.file_uploader(
    "Upload Invoice PDFs",
    type=["pdf"],
    accept_multiple_files=True,
)


# ============================================================
# PROCESS MULTIPLE INVOICES
# ============================================================

if uploaded_files:

    st.write(
        f"Selected invoices: **{len(uploaded_files)}**"
    )

    if st.button(
        "🚀 Process Invoices",
        type="primary",
    ):

        input_dir = (
            PROJECT_ROOT
            / "data"
            / "input"
            / "invoices"
        )

        input_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        progress = st.progress(0)

        current_batch_ids = []

        for index, uploaded_file in enumerate(
            uploaded_files
        ):

            st.write(
                f"Processing: **{uploaded_file.name}**"
            )

            pdf_path = (
                input_dir
                / uploaded_file.name
            )

            try:

                # ------------------------------------------------
                # Save PDF
                # ------------------------------------------------

                with open(
                    pdf_path,
                    "wb",
                ) as file:

                    file.write(
                        uploaded_file.getbuffer()
                    )

                # ------------------------------------------------
                # Process invoice
                # ------------------------------------------------

                result = process_invoice(
                    pdf_path
                )

                # ------------------------------------------------
                # Save invoice to DB
                #
                # Keep the existing database schema unchanged.
                # Store the AI verification result inside the
                # existing validation_data JSON.
                # ------------------------------------------------

                result.setdefault(
                    "validation",
                    {}
                )

                result["validation"]["verification"] = result.get(
                    "verification",
                    {
                        "status": "REVIEW",
                        "summary": (
                            "AI verification result was not returned."
                        ),
                        "issues": [],
                        "verified_fields": [],
                    },
                )

                invoice_id = save_invoice_result(
                    result
                )

                current_batch_ids.append(
                    invoice_id
                )

                # ------------------------------------------------
                # Show result
                # ------------------------------------------------

                if result.get("success"):

                    status = (
                        result
                        .get("validation", {})
                        .get("status", "FAIL")
                    )

                    if status == "PASS":

                        st.success(
                            f"✅ {uploaded_file.name} "
                            f"→ PASS "
                            f"(ID: {invoice_id})"
                        )

                    elif status == "REVIEW":

                        st.warning(
                            f"⚠️ {uploaded_file.name} "
                            f"→ REVIEW "
                            f"(ID: {invoice_id})"
                        )

                    else:

                        st.error(
                            f"❌ {uploaded_file.name} "
                            f"→ FAIL "
                            f"(ID: {invoice_id})"
                        )

                else:

                    st.error(
                        f"❌ Extraction failed: "
                        f"{uploaded_file.name}"
                    )

            except Exception as error:

                st.error(
                    f"❌ Error processing "
                    f"{uploaded_file.name}: {error}"
                )

            progress.progress(
                (index + 1)
                / len(uploaded_files)
            )

        # --------------------------------------------------------
        # Store ALL processed invoice IDs
        # --------------------------------------------------------

        st.session_state.processed_batch_ids = (
            current_batch_ids
        )

        # Automatically select first invoice
        if current_batch_ids:

            st.session_state.selected_invoice_id = (
                current_batch_ids[0]
            )

            st.session_state.invoice_approved = False

        st.success(
            f"Processing completed. "
            f"{len(current_batch_ids)} invoice(s) processed."
        )


# ============================================================
# LOAD ALL INVOICES FROM DATABASE
# ============================================================

all_invoices = get_all_invoices()


# ============================================================
# INVOICE SELECTOR
# ============================================================

if all_invoices:

    st.divider()

    st.header("📋 Processed Invoices")

    # --------------------------------------------------------
    # Create invoice lookup
    # --------------------------------------------------------

    invoice_lookup = {
        row["id"]: row
        for row in all_invoices
    }

    # --------------------------------------------------------
    # Prefer current batch if available
    # --------------------------------------------------------

    if st.session_state.processed_batch_ids:

        available_ids = [
            invoice_id
            for invoice_id
            in st.session_state.processed_batch_ids
            if invoice_id in invoice_lookup
        ]

    else:

        available_ids = [
            row["id"]
            for row in all_invoices
        ]

    # --------------------------------------------------------
    # Fallback
    # --------------------------------------------------------

    if not available_ids:

        available_ids = [
            row["id"]
            for row in all_invoices
        ]

    # --------------------------------------------------------
    # Ensure selected invoice is valid
    # --------------------------------------------------------

    if (
        st.session_state.selected_invoice_id
        not in available_ids
    ):

        st.session_state.selected_invoice_id = (
            available_ids[0]
        )

    # --------------------------------------------------------
    # Dropdown labels
    # --------------------------------------------------------

    def invoice_label(
        invoice_id: int,
    ) -> str:

        row = invoice_lookup[invoice_id]

        supplier = (
            row.get("supplier")
            or "Unknown Supplier"
        )

        return (
            f"{row.get('file_name', 'Unknown PDF')}"
            f" - {supplier}"
            f" (ID: {invoice_id})"
        )

    # --------------------------------------------------------
    # Dropdown
    # --------------------------------------------------------

    selected_id = st.selectbox(
        "Select invoice to verify",
        options=available_ids,
        index=available_ids.index(
            st.session_state.selected_invoice_id
        ),
        format_func=invoice_label,
        key="invoice_selector",
    )

    # --------------------------------------------------------
    # Detect invoice change
    # --------------------------------------------------------

    if (
        selected_id
        != st.session_state.selected_invoice_id
    ):

        st.session_state.selected_invoice_id = (
            selected_id
        )

        st.session_state.invoice_approved = (
            invoice_lookup[selected_id].get(
                "approval_status"
            )
            == "APPROVED"
        )

        # Force rerun so all widgets show the new invoice
        st.rerun()


# ============================================================
# GET CURRENT INVOICE
# ============================================================

current_invoice_row = None

if (
    st.session_state.selected_invoice_id
    is not None
):

    for row in all_invoices:

        if (
            row["id"]
            == st.session_state.selected_invoice_id
        ):

            current_invoice_row = row
            break


# ============================================================
# VERIFICATION SCREEN
# ============================================================

if current_invoice_row:

    row = current_invoice_row

    # --------------------------------------------------------
    # Load approved data if available.
    # Otherwise load original extracted data.
    # --------------------------------------------------------

    approved_data = row.get(
        "approved_invoice_data"
    )

    original_data = row.get(
        "invoice_data"
    )

    if approved_data:

        invoice = json.loads(
            approved_data
        )

    elif original_data:

        invoice = json.loads(
            original_data
        )

    else:

        invoice = {}

    # --------------------------------------------------------
    # Validation data
    # --------------------------------------------------------

    validation_data = row.get(
        "validation_data"
    )

    if validation_data:

        validation = json.loads(
            validation_data
        )

    else:

        validation = validate_invoice(
            invoice
        )

    # --------------------------------------------------------
    # PDF path
    # --------------------------------------------------------

    pdf_path = (
        PROJECT_ROOT
        / "data"
        / "input"
        / "invoices"
        / row["file_name"]
    )

    # --------------------------------------------------------
    # Approval state
    # --------------------------------------------------------

    is_approved = (
        row.get("approval_status")
        == "APPROVED"
    )

    st.session_state.invoice_approved = (
        is_approved
    )

    # ========================================================
    # VERIFICATION HEADER
    # ========================================================

    st.divider()

    st.header(
        "🔍 Invoice Verification"
    )

    st.caption(
        f"Currently viewing: "
        f"**{row.get('file_name')}**"
    )

    # --------------------------------------------------------
    # Supplier + Layout
    # --------------------------------------------------------

    info1, info2, info3, info4 = (
        st.columns(4)
    )

    with info1:

        st.metric(
            "Supplier",
            row.get("supplier")
            or "Unknown",
        )

    with info2:

        st.metric(
            "Layout",
            row.get("layout")
            or "Generic",
        )

    with info3:

        st.metric(
            "Extraction",
            row.get("extraction_method")
            or "Unknown",
        )

    with info4:

        st.metric(
            "Status",
            "APPROVED"
            if is_approved
            else validation.get(
                "status",
                "FAIL",
            ),
        )

    # ========================================================
    # PDF + HEADER INFORMATION
    # ========================================================

    left, right = st.columns(
        [1, 1]
    )

    # --------------------------------------------------------
    # PDF
    # --------------------------------------------------------

    with left:

        st.subheader(
            "📄 Invoice"
        )

        if pdf_path.exists():

            pdf_bytes = (
                pdf_path.read_bytes()
            )

            st.download_button(
                "Download Invoice PDF",
                data=pdf_bytes,
                file_name=pdf_path.name,
                mime="application/pdf",
                key=(
                    f"download_pdf_"
                    f"{row['id']}"
                ),
            )

            st.pdf(
                pdf_bytes
            )

        else:

            st.warning(
                "Invoice PDF could not be found."
            )

    # --------------------------------------------------------
    # Invoice Header
    # --------------------------------------------------------

    with right:

        st.subheader(
            "Invoice Details"
        )

        invoice_number = st.text_input(
            "Invoice Number",
            value=(
                invoice.get(
                    "invoice_number"
                )
                or ""
            ),
            key=(
                f"invoice_number_"
                f"{row['id']}"
            ),
        )

        invoice_date = st.text_input(
            "Invoice Date",
            value=(
                invoice.get(
                    "invoice_date"
                )
                or ""
            ),
            key=(
                f"invoice_date_"
                f"{row['id']}"
            ),
        )

        due_date = st.text_input(
            "Due Date",
            value=(
                invoice.get(
                    "due_date"
                )
                or ""
            ),
            key=(
                f"due_date_"
                f"{row['id']}"
            ),
        )

        purchase_order = st.text_input(
            "Purchase Order Number",
            value=(
                invoice.get(
                    "purchase_order_number"
                )
                or ""
            ),
            key=(
                f"purchase_order_"
                f"{row['id']}"
            ),
        )

        st.subheader(
            "Vendor Information"
        )

        vendor_name = st.text_input(
            "Vendor Name",
            value=(
                invoice.get(
                    "vendor_name"
                )
                or ""
            ),
            key=(
                f"vendor_name_"
                f"{row['id']}"
            ),
        )

        vendor_address = st.text_input(
            "Vendor Address",
            value=(
                invoice.get(
                    "vendor_address"
                )
                or ""
            ),
            key=(
                f"vendor_address_"
                f"{row['id']}"
            ),
        )

        vendor_phone = st.text_input(
            "Vendor Phone",
            value=(
                invoice.get(
                    "vendor_phone"
                )
                or ""
            ),
            key=(
                f"vendor_phone_"
                f"{row['id']}"
            ),
        )

        vendor_email = st.text_input(
            "Vendor Email",
            value=(
                invoice.get(
                    "vendor_email"
                )
                or ""
            ),
            key=(
                f"vendor_email_"
                f"{row['id']}"
            ),
        )

        st.subheader(
            "Customer Information"
        )

        customer_name = st.text_input(
            "Customer Name",
            value=(
                invoice.get(
                    "customer_name"
                )
                or ""
            ),
            key=(
                f"customer_name_"
                f"{row['id']}"
            ),
        )

        customer_address = st.text_input(
            "Customer Address",
            value=(
                invoice.get(
                    "customer_address"
                )
                or ""
            ),
            key=(
                f"customer_address_"
                f"{row['id']}"
            ),
        )

        ship_to_name = st.text_input(
            "Ship To Name",
            value=(
                invoice.get(
                    "ship_to_name"
                )
                or ""
            ),
            key=(
                f"ship_to_name_"
                f"{row['id']}"
            ),
        )

        ship_to_address = st.text_input(
            "Ship To Address",
            value=(
                invoice.get(
                    "ship_to_address"
                )
                or ""
            ),
            key=(
                f"ship_to_address_"
                f"{row['id']}"
            ),
        )

    # ========================================================
    # ITEM MASTER VERIFICATION
    # ========================================================

    st.divider()

    st.header(
        "📦 Item Master Verification"
    )

    st.caption(
        "Verify or correct the extracted values "
        "before approval."
    )

    line_items = invoice.get(
        "line_items",
        [],
    )

    edited_items = []

    if not line_items:

        st.warning(
            "No line items were extracted."
        )

    else:

        # ----------------------------------------------------
        # Dynamic fields for this invoice
        # ----------------------------------------------------

        active_fields = [
            (
                field,
                label,
                kind,
            )
            for field, label, kind
            in ITEM_MASTER_FIELDS
            if any_line_item_has_value(
                line_items,
                field,
            )
        ]

        # ----------------------------------------------------
        # Line items
        # ----------------------------------------------------

        for index, item in enumerate(
            line_items
        ):

            st.markdown(
                f"#### Line Item {index + 1}"
            )

            edited_values = {}

            # ------------------------------------------------
            # Render fields
            # ------------------------------------------------

            for chunk_start in range(
                0,
                len(active_fields),
                4,
            ):

                chunk = active_fields[
                    chunk_start:
                    chunk_start + 4
                ]

                columns = st.columns(
                    len(chunk)
                )

                for column, (
                    field,
                    label,
                    kind,
                ) in zip(
                    columns,
                    chunk,
                ):

                    with column:

                        widget_key = (
                            f"{field}_"
                            f"{row['id']}_"
                            f"{index}"
                        )

                        if kind == "text":

                            edited_values[
                                field
                            ] = st.text_input(
                                label,
                                value=(
                                    item.get(
                                        field
                                    )
                                    or ""
                                ),
                                key=widget_key,
                            ) or None

                        elif kind == "quantity":

                            edited_values[
                                field
                            ] = st.number_input(
                                label,
                                min_value=0.0,
                                value=float(
                                    item.get(
                                        field
                                    )
                                    or 0
                                ),
                                format="%.4f",
                                key=widget_key,
                            )

                        else:

                            # ------------------------------------------------
                            # IMPORTANT:
                            # Do NOT force prices to 2 decimal places.
                            #
                            # Your invoices can contain:
                            #
                            # 8036.3178
                            # 2499.0001
                            # 1534.4765
                            #
                            # We preserve the extracted precision.
                            # ------------------------------------------------

                            edited_values[
                                field
                            ] = st.number_input(
                                label,
                                min_value=0.0,
                                value=float(
                                    item.get(
                                        field
                                    )
                                    or 0
                                ),
                                format="%.4f",
                                key=widget_key,
                            )

            # ------------------------------------------------
            # Dynamic additional information
            # ------------------------------------------------

            additional_info = item.get(
                "additional_info",
                {}
            )

            if isinstance(
                additional_info,
                dict,
            ) and additional_info:

                with st.expander(
                    "Additional Information",
                    expanded=False,
                ):

                    st.json(
                        additional_info
                    )

            # ------------------------------------------------
            # UOM information
            # ------------------------------------------------

            uom_value = (
                edited_values.get(
                    "uom"
                )
            )

            if uom_value:

                uom_upper = (
                    uom_value
                    .strip()
                    .upper()
                )

                if uom_upper in [
                    "E",
                    "EA",
                    "EACH",
                ]:

                    st.info(
                        "E / EA = 1 each"
                    )

                elif uom_upper == "C":

                    st.info(
                        "C = per hundred"
                    )

                elif uom_upper == "M":

                    st.info(
                        "M = per thousand"
                    )

            # ------------------------------------------------
            # Store edited row
            #
            # IMPORTANT:
            # Preserve dynamic additional_info from the original
            # extracted line item so it is not lost during approval.
            # ------------------------------------------------

            edited_item = {
                field: edited_values.get(
                    field
                )
                for field, _label, _kind
                in ITEM_MASTER_FIELDS
            }

            original_additional_info = item.get(
                "additional_info",
                {}
            )

            if isinstance(
                original_additional_info,
                dict,
            ):
                edited_item[
                    "additional_info"
                ] = dict(
                    original_additional_info
                )
            else:
                edited_item[
                    "additional_info"
                ] = {}

            edited_items.append(
                edited_item
            )

        # ====================================================
        # PREVIEW
        # ====================================================

        st.divider()

        st.subheader(
            "Item Master Preview"
        )

        preview_rows = []

        for item in edited_items:

            preview_rows.append(
                {
                    label: (
                        item.get(field)
                        if item.get(field)
                        is not None
                        else ""
                    )
                    for field, label, _kind
                    in active_fields
                }
            )

        st.dataframe(
            preview_rows,
            use_container_width=True,
            hide_index=True,
        )

    # ========================================================
    # AI VERIFICATION
    # ========================================================

    st.divider()

    st.subheader(
        "🤖 AI Verification"
    )

    # Verification is stored inside validation_data when the
    # invoice is saved, so it survives Streamlit reruns.

    verification = validation.get(
        "verification"
    )

    if not isinstance(verification, dict):
        verification = {
            "status": "REVIEW",
            "summary": (
                "AI verification was not run "
                "for this stored invoice."
            ),
            "issues": [],
            "verified_fields": [],
        }

    verification_status = verification.get(
        "status",
        "REVIEW",
    )

    verification_summary = verification.get(
        "summary",
        "",
    )

    verification_issues = verification.get(
        "issues",
        [],
    )

    verification_fields = verification.get(
        "verified_fields",
        [],
    )

    if verification_status == "PASS":
        st.success(
            "✅ AI Verification PASS — "
            "No discrepancies found."
        )
    else:
        st.warning(
            "⚠️ AI Verification REVIEW — "
            "Human verification is required."
        )

    if verification_summary:
        st.write(
            f"**Summary:** {verification_summary}"
        )

    if verification_issues:
        st.write("**Detected Issues:**")

        for issue_index, issue in enumerate(
            verification_issues,
            start=1,
        ):
            if not isinstance(issue, dict):
                continue

            field = issue.get(
                "field",
                "Unknown field",
            )

            line_number = issue.get(
                "line_number"
            )

            extracted_value = issue.get(
                "extracted_value"
            )

            invoice_value = issue.get(
                "invoice_value"
            )

            reason = issue.get(
                "reason",
                "",
            )

            if line_number is not None:
                st.error(
                    f"**Issue {issue_index} — "
                    f"Line {line_number} — {field}**\n\n"
                    f"Extracted: `{extracted_value}`  \n"
                    f"Invoice: `{invoice_value}`  \n"
                    f"Reason: {reason}"
                )
            else:
                st.error(
                    f"**Issue {issue_index} — "
                    f"{field}**\n\n"
                    f"Extracted: `{extracted_value}`  \n"
                    f"Invoice: `{invoice_value}`  \n"
                    f"Reason: {reason}"
                )

    elif verification_status == "PASS":
        st.caption(
            "The verification agent found no clearly "
            "supported discrepancies."
        )

    if verification_fields:
        with st.expander(
            "Fields checked by AI verifier"
        ):
            st.write(
                verification_fields
            )

    # ========================================================
    # VALIDATION
    # ========================================================

    st.divider()

    st.subheader(
        "🔎 Validation"
    )

    if validation.get(
        "status"
    ) == "PASS":

        st.success(
            "✅ PASS — Ready for approval"
        )

    elif validation.get(
        "status"
    ) == "REVIEW":

        st.warning(
            "⚠️ REVIEW — Human verification required"
        )

    else:

        st.error(
            "❌ FAIL — Extraction or validation issue"
        )

    # --------------------------------------------------------
    # Warnings
    # --------------------------------------------------------

    if validation.get(
        "warnings"
    ):

        st.write(
            "**Warnings:**"
        )

        for warning in validation[
            "warnings"
        ]:

            st.warning(
                warning
            )

    # --------------------------------------------------------
    # Errors
    # --------------------------------------------------------

    if validation.get(
        "errors"
    ):

        st.write(
            "**Errors:**"
        )

        for error in validation[
            "errors"
        ]:

            st.error(
                error
            )

    # ========================================================
    # APPROVAL
    # ========================================================

    st.divider()

    st.subheader(
        "✅ Approval"
    )

    if is_approved:

        st.info(
            "This invoice has already been approved. "
            "The verified values shown above are saved "
            "in the database."
        )

    # --------------------------------------------------------
    # Approve button
    # --------------------------------------------------------

    if st.button(
        "✅ Approve Invoice",
        type="primary",
        key=(
            f"approve_invoice_"
            f"{row['id']}"
        ),
    ):

        # ----------------------------------------------------
        # Build verified invoice
        # ----------------------------------------------------

        edited_invoice = {

            "vendor_name":
                vendor_name or None,

            "vendor_address":
                vendor_address or None,

            "vendor_phone":
                vendor_phone or None,

            "vendor_email":
                vendor_email or None,

            "customer_name":
                customer_name or None,

            "customer_address":
                customer_address or None,

            "ship_to_name":
                ship_to_name or None,

            "ship_to_address":
                ship_to_address or None,

            "invoice_number":
                invoice_number or None,

            "invoice_date":
                invoice_date or None,

            "due_date":
                due_date or None,

            "purchase_order_number":
                purchase_order or None,

            # ------------------------------------------------
            # Preserve optional invoice-level fields.
            # These were previously dropped during approval.
            # ------------------------------------------------

            "sales_order_number":
                invoice.get(
                    "sales_order_number"
                ),

            "quote_number":
                invoice.get(
                    "quote_number"
                ),

            "order_date":
                invoice.get(
                    "order_date"
                ),

            "ship_date":
                invoice.get(
                    "ship_date"
                ),

            "delivery_date":
                invoice.get(
                    "delivery_date"
                ),

            "packing_slip_number":
                invoice.get(
                    "packing_slip_number"
                ),

            "customer_account_number":
                invoice.get(
                    "customer_account_number"
                ),

            "vendor_account_number":
                invoice.get(
                    "vendor_account_number"
                ),

            "job_number":
                invoice.get(
                    "job_number"
                ),

            "project_number":
                invoice.get(
                    "project_number"
                ),

            "terms":
                invoice.get(
                    "terms"
                ),

            "currency":
                invoice.get(
                    "currency"
                ),

            "freight_usd":
                invoice.get(
                    "freight_usd"
                ),

            "discount_usd":
                invoice.get(
                    "discount_usd"
                ),

            "tracking_number":
                invoice.get(
                    "tracking_number"
                ),

            "salesperson":
                invoice.get(
                    "salesperson"
                ),

            "tax_id":
                invoice.get(
                    "tax_id"
                ),

            "line_items":
                edited_items,

            "subtotal_usd":
                invoice.get(
                    "subtotal_usd"
                ),

            "tax_usd":
                invoice.get(
                    "tax_usd"
                ),

            "total_usd":
                invoice.get(
                    "total_usd"
                ),
        }

        # ----------------------------------------------------
        # Validate edited invoice
        # ----------------------------------------------------

        approval_validation = (
            validate_invoice(
                edited_invoice
            )
        )

        if (
            approval_validation["status"]
            == "FAIL"
        ):

            st.error(
                "❌ Cannot approve — "
                "please resolve the following "
                "before approving:"
            )

            for error in (
                approval_validation[
                    "errors"
                ]
            ):

                st.error(
                    error
                )

        else:

            # ------------------------------------------------
            # Save approved invoice
            # ------------------------------------------------

            approve_invoice(
                row["id"],
                edited_invoice,
            )

            st.session_state.invoice_approved = (
                True
            )

            st.success(
                "✅ Invoice verified successfully "
                "and saved."
            )

            if approval_validation.get(
                "warnings"
            ):

                st.write(
                    "**Saved with outstanding warnings:**"
                )

                for warning in (
                    approval_validation[
                        "warnings"
                    ]
                ):

                    st.warning(
                        warning
                    )

            # ------------------------------------------------
            # Refresh data
            # ------------------------------------------------

            st.rerun()


# ============================================================
# EXPORT APPROVED ITEM MASTER
# ============================================================

st.divider()

st.header(
    "📤 Export Approved Item Master"
)

st.caption(
    "Combine every approved invoice — across all suppliers, "
    "even thousands of them — into one standardized Item "
    "Master file. Each row carries its Invoice, Vendor, and "
    "Customer details alongside that line item."
)


# ============================================================
# GET ALL APPROVED EXPORT ROWS
# ============================================================

export_rows = get_export_rows()


st.write(
    "Approved line items available for export: "
    f"**{len(export_rows)}**"
)


if export_rows:

    csv_bytes = build_item_master_csv(
        export_rows
    )

    workbook_bytes = (
        build_item_master_workbook(
            export_rows
        )
    )

    export_col1, export_col2 = (
        st.columns(2)
    )

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
        "No approved invoices yet. "
        "Approve at least one invoice above "
        "to enable export."
    )


# ============================================================
# PIPELINE
# ============================================================

st.divider()

st.subheader(
    "Pipeline"
)

st.write(
    """
PDF → Text/OCR → Supplier Detection → Layout Detection
→ Generic Parser → Groq → Normalization
→ AI Verification Agent → Validation
→ Human Verification → Item Master CSV
"""
)
