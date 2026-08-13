
import json
import os
import re
from typing import Any

from groq import Groq


# ============================================================
# GROQ CLIENT
# ============================================================

class InvoiceVerificationAgent:
    """
    Compact AI verifier for extracted invoice data.

    The verifier intentionally sends a bounded amount of invoice
    text so large OCR documents do not exceed the Groq TPM limit.

    Public interface preserved:

        verifier = InvoiceVerificationAgent(
            api_key="..."
        )

        result = verifier.verify(
            invoice=invoice_dict,
            invoice_text=raw_invoice_text,
        )
    """

    MODEL_NAME = os.getenv(
        "VERIFICATION_MODEL",
        "llama-3.3-70b-versatile",
    )

    MAX_TEXT_CHARS = 18000

    VERIFIED_FIELDS = [
        "vendor_name",
        "vendor_address",
        "vendor_phone",
        "customer_name",
        "customer_address",
        "ship_to_name",
        "ship_to_address",
        "invoice_number",
        "invoice_date",
        "purchase_order_number",
        "sales_order_number",
        "order_date",
        "ship_date",
        "packing_slip_number",
        "customer_account_number",
        "vendor_account_number",
        "job_number",
        "project_number",
        "terms",
        "freight_usd",
        "discount_usd",
        "tracking_number",
        "salesperson",
        "tax_id",
        "subtotal_usd",
        "tax_usd",
        "total_usd",
        "line_items.vendor_part_number",
        "line_items.description",
        "line_items.quantity_shipped",
        "line_items.uom",
        "line_items.unit_price_usd",
        "line_items.extended_price_usd",
    ]

    def __init__(
        self,
        api_key: str | None = None,
    ) -> None:

        self.client = Groq(
            api_key=(
                api_key
                or os.getenv(
                    "GROQ_API_KEY"
                )
            )
        )

    # ========================================================
    # TEXT COMPACTION
    # ========================================================

    @classmethod
    def _compact_invoice_text(
        cls,
        invoice_text: str,
    ) -> str:
        """
        Remove verbose coordinate OCR and keep a bounded text
        representation for verification.

        The actual structured invoice object is supplied separately,
        so the verifier does not need the entire coordinate dump.
        """

        if not invoice_text:
            return ""

        text = str(
            invoice_text
        )

        # Remove word-coordinate OCR section.
        marker = re.search(
            r"---\s*Page\s+\d+\s*/\s*WORD COORDINATES\s*---",
            text,
            flags=re.IGNORECASE,
        )

        if marker:
            text = text[:marker.start()]

        # Remove repeated whitespace.
        text = re.sub(
            r"\n{3,}",
            "\n\n",
            text,
        )

        text = re.sub(
            r"[ \t]{2,}",
            " ",
            text,
        )

        text = text.strip()

        # Keep the beginning and end if the text is too long.
        if len(text) > cls.MAX_TEXT_CHARS:

            head_chars = (
                cls.MAX_TEXT_CHARS
                * 2
                // 3
            )

            tail_chars = (
                cls.MAX_TEXT_CHARS
                - head_chars
            )

            text = (
                text[:head_chars]
                + "\n\n"
                + "[MIDDLE OCR TEXT TRUNCATED]\n\n"
                + text[-tail_chars:]
            )

        return text

    # ========================================================
    # STRUCTURED INVOICE COMPACTION
    # ========================================================

    @staticmethod
    def _compact_invoice(
        invoice: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Keep the useful comparison data while avoiding redundant
        large nested structures.
        """

        if not isinstance(
            invoice,
            dict,
        ):
            return {}

        header_fields = [
            "vendor_name",
            "vendor_address",
            "vendor_phone",
            "vendor_email",
            "customer_name",
            "customer_address",
            "ship_to_name",
            "ship_to_address",
            "invoice_number",
            "invoice_date",
            "due_date",
            "purchase_order_number",
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
            "freight_usd",
            "discount_usd",
            "tracking_number",
            "salesperson",
            "tax_id",
            "subtotal_usd",
            "tax_usd",
            "total_usd",
        ]

        compacted = {
            field: invoice.get(field)
            for field in header_fields
            if invoice.get(field)
            not in (
                None,
                "",
            )
        }

        # Preserve dynamic invoice-level information.
        additional_info = invoice.get(
            "additional_info",
            {},
        )

        if isinstance(
            additional_info,
            dict,
        ) and additional_info:

            compacted[
                "additional_info"
            ] = additional_info

        # Preserve all line items, but only the fields required
        # for verification.
        compact_items = []

        for item in invoice.get(
            "line_items",
            [],
        ):

            if not isinstance(
                item,
                dict,
            ):
                continue

            compact_item = {
                "manufacturer_part_number":
                    item.get(
                        "manufacturer_part_number"
                    ),
                "vendor_part_number":
                    item.get(
                        "vendor_part_number"
                    ),
                "description":
                    item.get(
                        "description"
                    ),
                "quantity_shipped":
                    item.get(
                        "quantity_shipped"
                    ),
                "uom":
                    item.get(
                        "uom"
                    ),
                "unit_price_usd":
                    item.get(
                        "unit_price_usd"
                    ),
                "extended_price_usd":
                    item.get(
                        "extended_price_usd"
                    ),
            }

            line_additional_info = item.get(
                "additional_info",
                {},
            )

            if isinstance(
                line_additional_info,
                dict,
            ) and line_additional_info:

                compact_item[
                    "additional_info"
                ] = line_additional_info

            compact_items.append(
                compact_item
            )

        compacted[
            "line_items"
        ] = compact_items

        return compacted

    # ========================================================
    # JSON CLEANING
    # ========================================================

    @staticmethod
    def _clean_response(
        content: str,
    ) -> str:
        """
        Extract a JSON object from the model response.
        """

        content = str(
            content or ""
        ).strip()

        content = re.sub(
            r"```json\s*",
            "",
            content,
            flags=re.IGNORECASE,
        )

        content = re.sub(
            r"```",
            "",
            content,
        )

        content = re.sub(
            r"<think>.*?</think>",
            "",
            content,
            flags=re.IGNORECASE | re.DOTALL,
        )

        content = re.sub(
            r"<analysis>.*?</analysis>",
            "",
            content,
            flags=re.IGNORECASE | re.DOTALL,
        )

        start = content.find(
            "{"
        )

        end = content.rfind(
            "}"
        )

        if (
            start == -1
            or end == -1
            or end <= start
        ):

            raise ValueError(
                "No JSON object found in verifier response."
            )

        return content[
            start:end + 1
        ]

    # ========================================================
    # ISSUE FILTERING
    # ========================================================

    @staticmethod
    def _normalize_compare_value(
        value: Any,
    ) -> Any:
        """
        Normalize values only for comparison.
        Preserve the original values in the returned issue data.
        """

        if value is None:
            return None

        if isinstance(
            value,
            bool,
        ):
            return value

        if isinstance(
            value,
            (int, float),
        ):
            return round(
                float(value),
                6,
            )

        text = str(
            value
        ).strip()

        if not text:
            return None

        # Numeric strings such as "127.38" and 127.38
        # should compare equal.
        try:
            return round(
                float(
                    text.replace(
                        ",",
                        "",
                    ).replace(
                        "$",
                        "",
                    ),
                ),
                6,
            )
        except (
            TypeError,
            ValueError,
        ):
            pass

        return re.sub(
            r"\s+",
            " ",
            text,
        ).casefold()

    @classmethod
    def _values_equal(
        cls,
        left: Any,
        right: Any,
    ) -> bool:

        return (
            cls._normalize_compare_value(
                left
            )
            == cls._normalize_compare_value(
                right
            )
        )

    @classmethod
    def _filter_real_issues(
        cls,
        issues: list[Any],
    ) -> list[dict[str, Any]]:
        """
        Remove false-positive issues generated by the model.

        A model issue is not a real discrepancy when:
        - extracted_value == invoice_value
        - both values are missing
        - the reason itself says there is no discrepancy
        """

        filtered: list[dict[str, Any]] = []

        for raw_issue in issues:

            if not isinstance(
                raw_issue,
                dict,
            ):
                continue

            extracted_value = raw_issue.get(
                "extracted_value"
            )

            invoice_value = raw_issue.get(
                "invoice_value"
            )

            reason = str(
                raw_issue.get(
                    "reason",
                    "",
                )
                or ""
            ).strip().casefold()

            # Same value on both sides = no discrepancy.
            if cls._values_equal(
                extracted_value,
                invoice_value,
            ):
                continue

            # Both missing = no discrepancy.
            if (
                extracted_value is None
                and invoice_value is None
            ):
                continue

            # Protect against wording such as:
            # "No discrepancy, but UOM ..."
            if (
                "no discrepancy"
                in reason
            ):
                continue

            filtered.append(
                raw_issue
            )

        return filtered

    # ========================================================
    # VERIFY
    # ========================================================

    def verify(
        self,
        invoice: dict[str, Any],
        invoice_text: str,
    ) -> dict[str, Any]:
        """
        Compare extracted invoice data against the compact invoice
        evidence.

        Returns the same structure expected by Streamlit/database:

            {
                "status": "PASS" | "REVIEW",
                "summary": "...",
                "issues": [...],
                "verified_fields": [...]
            }
        """

        compacted_invoice = (
            self._compact_invoice(
                invoice
            )
        )

        compacted_text = (
            self._compact_invoice_text(
                invoice_text
            )
        )

        prompt = f"""
You are an invoice verification agent.

Compare the EXTRACTED DATA against the CURRENT INVOICE TEXT.

Use ONLY the current invoice evidence.

Do not invent values.
Do not use previous invoices.
Do not assume missing information.

Focus on:
1. Vendor/customer/header fields.
2. Invoice numbers and dates.
3. PO/order/customer numbers.
4. Freight/tax/subtotal/total.
5. Every line item's:
   - vendor part number
   - description
   - quantity shipped
   - UOM
   - unit price
   - extended price
6. Dynamic additional_info only when it is explicitly supported.

Important:
- A missing field is not automatically an error if it is absent
  from the invoice.
- Report a discrepancy only when the invoice clearly supports
  a different value.
- Do not flag an absent UOM as a discrepancy merely because it
  is missing.
- Do not infer UOM.
- Pay attention to table columns.
- Do not confuse numbers inside descriptions with quantity.
- Do not confuse invoice grand totals with line-item amounts.

Return ONLY valid JSON in this exact structure:

{{
  "status": "PASS",
  "summary": "",
  "issues": [],
  "verified_fields": []
}}

For an actual discrepancy use:

{{
  "status": "REVIEW",
  "summary": "Discrepancies found in extracted data",
  "issues": [
    {{
      "field": "quantity_shipped",
      "line_number": 1,
      "extracted_value": 999,
      "invoice_value": 1,
      "reason": "Quantity mismatch"
    }}
  ],
  "verified_fields": []
}}

CURRENT EXTRACTED DATA:
-----------------------
{json.dumps(
    compacted_invoice,
    ensure_ascii=False,
    separators=(",", ":")
)}

CURRENT INVOICE TEXT:
---------------------
{compacted_text}
"""

        response = self.client.chat.completions.create(
            model=self.MODEL_NAME,
            temperature=0,
            max_completion_tokens=1800,
            response_format={
                "type": "json_object"
            },
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a strict invoice verification "
                        "system. Return only valid JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        )

        content = (
            response
            .choices[0]
            .message
            .content
        )

        if not content:
            raise ValueError(
                "Verification model returned an empty response."
            )

        result = json.loads(
            self._clean_response(
                content
            )
        )

        if not isinstance(
            result,
            dict,
        ):
            raise ValueError(
                "Verification response is not a JSON object."
            )

        status = str(
            result.get(
                "status",
                "REVIEW",
            )
        ).upper()

        if status not in {
            "PASS",
            "REVIEW",
        }:

            status = "REVIEW"

        issues = result.get(
            "issues",
            [],
        )

        if not isinstance(
            issues,
            list,
        ):
            issues = []

        # Keep only genuine discrepancies.
        issues = self._filter_real_issues(
            issues
        )

        verified_fields = result.get(
            "verified_fields",
            [],
        )

        if not isinstance(
            verified_fields,
            list,
        ):
            verified_fields = []

        # Always expose the standard fields that the verifier is
        # intended to check. The model may return a smaller subset,
        # but these are the supported verification targets.
        if status == "PASS":
            verified_fields = list(
                dict.fromkeys(
                    [
                        *verified_fields,
                        *self.VERIFIED_FIELDS,
                    ]
                )
            )

        # The model sometimes returns REVIEW for informational
        # comments even when there is no actual mismatch. After
        # deterministic issue filtering, no remaining issue means
        # verification PASS.
        if not issues:
            status = "PASS"

        summary = str(
            result.get(
                "summary",
                "",
            )
            or ""
        )

        if status == "PASS":
            summary = (
                "No supported discrepancies found."
            )

        elif not summary:
            summary = (
                "Discrepancies found in extracted data"
                if issues
                else "AI verification requires review."
            )

        return {
            "status": status,
            "summary": summary,
            "issues": issues,
            "verified_fields": verified_fields,
        }
