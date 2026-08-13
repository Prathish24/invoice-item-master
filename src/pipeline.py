
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.extraction.extraction_service import (
    extract_invoice_text,
)
from src.extraction.ocr_extractor import (
    render_pdf_pages_as_data_urls,
)
from src.extraction.table_detector import (
    detect_table_structure,
    extract_dynamic_table_rows,
    classify_table_rows,
    build_table_column_map,
)
from src.extraction.table_line_item_mapper import (
    map_table_rows,
)

from src.supplier.supplier_detector import (
    detect_supplier,
)
from src.supplier.layout_detector import (
    detect_layout,
)
from src.parsers.generic_parser import (
    GenericInvoiceParser,
)

from src.normalization.uom_normalizer import (
    normalize_uom,
    get_uom_multiplier,
)
from src.normalization.description_normalizer import (
    normalize_description,
)
from src.normalization.part_number_normalizer import (
    normalize_part_number,
)
from src.validation.invoice_validator import (
    validate_invoice,
)

from src.verification.invoice_verifier import (
    InvoiceVerificationAgent,
)

from src.llm.invoice_extractor import (
    extract_invoice_data_with_vision,
    verify_table_row_with_vision,
)


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# COMPACT OCR
# ============================================================

def compact_ocr_text(
    text: str,
) -> str:
    """
    Remove the verbose WORD COORDINATES section before sending
    OCR text to the text LLM.
    """

    if not text:
        return ""

    lines = text.splitlines()

    compact_lines = []

    for line in lines:

        if (
            "/ WORD COORDINATES"
            in line.upper()
        ):
            break

        compact_lines.append(
            line
        )

    compacted = "\n".join(
        compact_lines
    ).strip()

    max_characters = 45000

    if len(compacted) > max_characters:
        compacted = compacted[
            :max_characters
        ]

    return compacted


# ============================================================
# MERGE VISION HEADER RESULT
# ============================================================

def merge_vision_result(
    invoice: dict[str, Any],
    vision_result: dict[str, Any],
) -> dict[str, Any]:

    merged = invoice.copy()

    vision_fields = vision_result.get(
        "fields",
        {},
    )

    if not isinstance(
        vision_fields,
        dict,
    ):
        vision_fields = {}

    standard_fields = {
        "invoice_number",
        "invoice_date",
        "due_date",
        "purchase_order_number",
        "sales_order_number",
        "customer_account_number",
        "vendor_account_number",
        "salesperson",
        "order_date",
        "ship_date",
        "delivery_date",
        "packing_slip_number",
        "tracking_number",
    }

    for field in standard_fields:

        vision_value = vision_fields.get(
            field
        )

        existing_value = merged.get(
            field
        )

        if (
            vision_value not in (
                None,
                "",
            )
            and existing_value in (
                None,
                "",
            )
        ):

            merged[field] = vision_value

    existing_additional_info = merged.get(
        "additional_info",
        {},
    )

    if not isinstance(
        existing_additional_info,
        dict,
    ):
        existing_additional_info = {}

    vision_additional_info = vision_result.get(
        "additional_info",
        {},
    )

    if not isinstance(
        vision_additional_info,
        dict,
    ):
        vision_additional_info = {}

    combined_additional_info = dict(
        existing_additional_info
    )

    for key, value in vision_additional_info.items():

        if key is None:
            continue

        key = str(
            key
        ).strip()

        if not key:
            continue

        if value in (
            None,
            "",
        ):
            continue

        if key not in combined_additional_info:
            combined_additional_info[key] = value

    merged[
        "additional_info"
    ] = combined_additional_info

    return merged


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_invoice(
    invoice: dict[str, Any],
) -> dict[str, Any]:

    normalized = invoice.copy()

    invoice_additional_info = normalized.get(
        "additional_info",
        {},
    )

    if not isinstance(
        invoice_additional_info,
        dict,
    ):
        invoice_additional_info = {}

    normalized[
        "additional_info"
    ] = {
        str(key).strip(): value
        for key, value
        in invoice_additional_info.items()
        if key is not None
        and str(key).strip()
        and value not in (
            None,
            "",
        )
    }

    normalized_line_items = []

    for item in invoice.get(
        "line_items",
        [],
    ):

        normalized_item = item.copy()

        # ----------------------------------------------------
        # Description
        # ----------------------------------------------------

        normalized_item["description"] = (
            normalize_description(
                item.get("description")
            )
        )

        # ----------------------------------------------------
        # Manufacturer Part Number
        # ----------------------------------------------------

        normalized_item[
            "manufacturer_part_number"
        ] = normalize_part_number(
            item.get(
                "manufacturer_part_number"
            )
        )

        # ----------------------------------------------------
        # Vendor Part Number
        # ----------------------------------------------------

        normalized_item[
            "vendor_part_number"
        ] = normalize_part_number(
            item.get(
                "vendor_part_number"
            )
        )

        # ----------------------------------------------------
        # UOM
        # ----------------------------------------------------

        normalized_item["uom"] = (
            normalize_uom(
                item.get("uom")
            )
        )

        # ----------------------------------------------------
        # UOM multiplier
        # ----------------------------------------------------

        normalized_item[
            "uom_multiplier"
        ] = get_uom_multiplier(
            item.get("uom")
        )

        # ----------------------------------------------------
        # Numeric line-item fields
        # ----------------------------------------------------

        for numeric_field in (
            "quantity_shipped",
            "unit_price_usd",
            "extended_price_usd",
        ):

            value = item.get(
                numeric_field
            )

            if value in (
                None,
                "",
            ):

                normalized_item[
                    numeric_field
                ] = None

            else:

                try:

                    normalized_item[
                        numeric_field
                    ] = float(
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

                except (
                    TypeError,
                    ValueError,
                ):

                    normalized_item[
                        numeric_field
                    ] = value

        # ----------------------------------------------------
        # Dynamic line-item additional info
        # ----------------------------------------------------

        line_additional_info = item.get(
            "additional_info",
            {},
        )

        if not isinstance(
            line_additional_info,
            dict,
        ):
            line_additional_info = {}

        normalized_item[
            "additional_info"
        ] = {
            str(key).strip(): value
            for key, value
            in line_additional_info.items()
            if key is not None
            and str(key).strip()
            and value not in (
                None,
                "",
            )
        }

        normalized_line_items.append(
            normalized_item
        )

    normalized[
        "line_items"
    ] = normalized_line_items

    return normalized


# ============================================================
# APPLY LOCAL TABLE DETECTION
# ============================================================

def apply_dynamic_table_extraction(
    pdf_path: Path,
    invoice: dict[str, Any],
) -> dict[str, Any]:

    try:

        extraction_result = extract_invoice_text(
            pdf_path
        )

        if (
            extraction_result.get(
                "extraction_method"
            )
            != "OCR"
        ):
            return invoice

        coordinate_text = (
            extraction_result.get(
                "extraction_text",
                "",
            )
        )

        structure = detect_table_structure(
            coordinate_text
        )

        if not structure:
            return invoice

        rows = extract_dynamic_table_rows(
            coordinate_text,
            structure,
        )

        classified_rows = classify_table_rows(
            rows,
            structure,
        )

        if not classified_rows:
            return invoice

        mapped_items = map_table_rows(
            classified_rows
        )

        if not mapped_items:
            return invoice

        current_items = invoice.get(
            "line_items",
            [],
        )

        if (
            not current_items
            or len(current_items)
            == len(mapped_items)
        ):

            updated = invoice.copy()

            updated[
                "line_items"
            ] = mapped_items

            return updated

        return invoice

    except Exception:

        return invoice


# ============================================================
# VERIFY DYNAMIC TABLE ROWS
# ============================================================

def verify_dynamic_rows(
    pdf_path: Path,
    invoice: dict[str, Any],
) -> tuple[
    dict[str, Any],
    dict[str, Any],
]:

    result = invoice.copy()

    line_items = result.get(
        "line_items",
        [],
    )

    if not line_items:
        return (
            result,
            {
                "used": False,
                "verified_rows": [],
            },
        )

    try:

        extraction_result = extract_invoice_text(
            pdf_path
        )

        if (
            extraction_result.get(
                "extraction_method"
            )
            != "OCR"
        ):

            return (
                result,
                {
                    "used": False,
                    "verified_rows": [],
                },
            )

        coordinate_text = (
            extraction_result.get(
                "extraction_text",
                "",
            )
        )

        structure = detect_table_structure(
            coordinate_text
        )

        if not structure:
            return (
                result,
                {
                    "used": False,
                    "verified_rows": [],
                },
            )

        rows = extract_dynamic_table_rows(
            coordinate_text,
            structure,
        )

        classified_rows = classify_table_rows(
            rows,
            structure,
        )

        if not classified_rows:
            return (
                result,
                {
                    "used": False,
                    "verified_rows": [],
                },
            )

        image_data_urls = (
            render_pdf_pages_as_data_urls(
                pdf_path
            )
        )

        column_map = build_table_column_map(
            structure
        )

        verified_rows = []

        final_items = []

        for index, local_row in enumerate(
            classified_rows
        ):

            if index >= len(
                line_items
            ):
                break

            current_item = line_items[
                index
            ]

            try:

                verification = (
                    verify_table_row_with_vision(
                        image_data_urls=image_data_urls,
                        detected_columns=column_map,
                        detected_row=local_row,
                    )
                )

                verified_rows.append(
                    {
                        "line_number": index + 1,
                        "status": verification.get(
                            "status",
                            "REVIEW",
                        ),
                        "changes": verification.get(
                            "changes",
                            [],
                        ),
                        "reason": verification.get(
                            "reason",
                            "",
                        ),
                    }
                )

                corrected_row = verification.get(
                    "corrected_row",
                    {},
                )

                if (
                    verification.get(
                        "status"
                    )
                    in {
                        "PASS",
                        "CORRECTED",
                    }
                    and isinstance(
                        corrected_row,
                        dict,
                    )
                ):

                    merged_item = dict(
                        current_item
                    )

                    for field, value in (
                        corrected_row.items()
                    ):

                        if value not in (
                            None,
                            "",
                        ):

                            if field == (
                                "additional_info"
                            ):

                                existing_extra = (
                                    merged_item.get(
                                        "additional_info",
                                        {},
                                    )
                                )

                                if not isinstance(
                                    existing_extra,
                                    dict,
                                ):
                                    existing_extra = {}

                                new_extra = value

                                if isinstance(
                                    new_extra,
                                    dict,
                                ):

                                    merged_item[
                                        "additional_info"
                                    ] = {
                                        **existing_extra,
                                        **new_extra,
                                    }

                            else:

                                merged_item[
                                    field
                                ] = value

                    final_items.append(
                        merged_item
                    )

                else:

                    final_items.append(
                        current_item
                    )

            except Exception as error:

                verified_rows.append(
                    {
                        "line_number": index + 1,
                        "status": "REVIEW",
                        "changes": [],
                        "reason": (
                            "Row verification error: "
                            f"{error}"
                        ),
                    }
                )

                final_items.append(
                    current_item
                )

        result[
            "line_items"
        ] = final_items

        return (
            result,
            {
                "used": bool(
                    verified_rows
                ),
                "verified_rows": verified_rows,
            },
        )

    except Exception as error:

        return (
            result,
            {
                "used": False,
                "verified_rows": [],
                "error": str(error),
            },
        )


# ============================================================
# PROCESS INVOICE
# ============================================================

def process_invoice(
    pdf_path: str | Path,
) -> dict[str, Any]:

    pdf_path = Path(
        pdf_path
    )

    # ========================================================
    # 1. EXTRACTION
    # ========================================================

    extraction_result = extract_invoice_text(
        pdf_path
    )

    if not extraction_result.get(
        "success"
    ):

        return {
            "file_name": pdf_path.name,
            "success": False,
            "supplier": None,
            "layout": None,
            "invoice": None,
            "verification": {
                "status": "REVIEW",
                "summary": (
                    "Verification was not possible "
                    "because PDF extraction failed."
                ),
                "issues": [],
                "verified_fields": [],
            },
            "validation": {
                "status": "FAIL",
                "errors": [
                    "Could not extract text from PDF"
                ],
                "warnings": [],
                "is_valid": False,
            },
        }

    # ========================================================
    # 2. TEXT
    # ========================================================

    raw_invoice_text = (
        extraction_result.get(
            "extraction_text"
        )
        or extraction_result.get(
            "text",
            "",
        )
    )

    if not raw_invoice_text.strip():

        return {
            "file_name": pdf_path.name,
            "success": False,
            "supplier": None,
            "layout": None,
            "invoice": None,
            "verification": {
                "status": "REVIEW",
                "summary": (
                    "Verification was not possible "
                    "because invoice text is empty."
                ),
                "issues": [],
                "verified_fields": [],
            },
            "validation": {
                "status": "FAIL",
                "errors": [
                    "Extracted invoice text is empty"
                ],
                "warnings": [],
                "is_valid": False,
            },
        }

    invoice_text_for_llm = (
        compact_ocr_text(
            raw_invoice_text
        )
        if extraction_result.get(
            "extraction_method"
        ) == "OCR"
        else raw_invoice_text
    )

    # ========================================================
    # 3. SUPPLIER
    # ========================================================

    supplier = detect_supplier(
        invoice_text_for_llm
    )

    # ========================================================
    # 4. LAYOUT
    # ========================================================

    layout = detect_layout(
        invoice_text_for_llm,
        supplier,
    )

    # ========================================================
    # 5. STANDARD TEXT EXTRACTION
    # ========================================================

    parser = GenericInvoiceParser()

    invoice_data = parser.parse(
        invoice_text_for_llm
    )

    # ========================================================
    # 6. VISION HEADER PASS
    # ========================================================

    vision_result = {
        "used": False,
        "fields": {},
        "additional_info": {},
        "uncertain_fields": [],
    }

    if (
        extraction_result.get(
            "extraction_method"
        )
        == "OCR"
    ):

        try:

            image_data_urls = (
                render_pdf_pages_as_data_urls(
                    pdf_path
                )
            )

            if image_data_urls:

                header_vision = (
                    extract_invoice_data_with_vision(
                        image_data_urls=image_data_urls
                    )
                )

                invoice_data = (
                    merge_vision_result(
                        invoice_data,
                        header_vision,
                    )
                )

                vision_result[
                    "used"
                ] = True

                vision_result[
                    "fields"
                ] = header_vision.get(
                    "fields",
                    {},
                )

                vision_result[
                    "additional_info"
                ] = header_vision.get(
                    "additional_info",
                    {},
                )

                vision_result[
                    "uncertain_fields"
                ] = header_vision.get(
                    "uncertain_fields",
                    [],
                )

        except Exception as error:

            vision_result[
                "error"
            ] = str(
                error
            )

    # ========================================================
    # 7. DYNAMIC TABLE EXTRACTION
    # ========================================================

    invoice_data = (
        apply_dynamic_table_extraction(
            pdf_path,
            invoice_data,
        )
    )

    # ========================================================
    # 8. TARGETED ROW VERIFICATION
    # ========================================================

    invoice_data, row_verification = (
        verify_dynamic_rows(
            pdf_path,
            invoice_data,
        )
    )

    # ========================================================
    # 9. NORMALIZATION
    # ========================================================

    normalized_invoice = normalize_invoice(
        invoice_data
    )

    # ========================================================
    # 10. AI VERIFICATION AGENT
    # ========================================================

    verification_result = {
        "status": "REVIEW",
        "summary": "",
        "issues": [],
        "verified_fields": [],
    }

    try:

        verifier = InvoiceVerificationAgent(
            api_key=os.getenv(
                "GROQ_API_KEY"
            )
        )

        verification_result = (
            verifier.verify(
                invoice=normalized_invoice,
                invoice_text=raw_invoice_text,
            )
        )

    except Exception as error:

        verification_result = {
            "status": "REVIEW",
            "summary": (
                "AI verification could not be completed."
            ),
            "issues": [
                {
                    "field": None,
                    "line_number": None,
                    "extracted_value": None,
                    "invoice_value": None,
                    "reason": (
                        "Verification agent error: "
                        f"{error}"
                    ),
                }
            ],
            "verified_fields": [],
        }

    # ========================================================
    # 11. DETERMINISTIC VALIDATION
    # ========================================================

    validation_result = validate_invoice(
        normalized_invoice
    )

    # ========================================================
    # 12. FINAL STATUS
    # ========================================================

    if (
        validation_result.get(
            "status"
        )
        == "FAIL"
    ):

        final_status = "FAIL"

    elif (
        verification_result.get(
            "status"
        )
        == "REVIEW"
    ):

        final_status = "REVIEW"

    elif (
        validation_result.get(
            "status"
        )
        == "REVIEW"
    ):

        final_status = "REVIEW"

    else:

        final_status = "PASS"

    return {
        "file_name": pdf_path.name,
        "success": True,
        "extraction_method": (
            extraction_result.get(
                "extraction_method"
            )
        ),
        "supplier": supplier,
        "layout": layout,
        "invoice": normalized_invoice,
        "vision": {
            **vision_result,
            "row_verification": row_verification,
        },
        "verification": verification_result,
        "validation": {
            **validation_result,
            "status": final_status,
        },
    }
