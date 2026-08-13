import json
import os
import re
from typing import Any

from groq import Groq


# ============================================================
# GROQ CLIENT
# ============================================================

client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)

MODEL_NAME = "llama-3.3-70b-versatile"

VISION_MODEL = "qwen/qwen3.6-27b"


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are an expert invoice data extraction system.

Your job is to extract invoice information from ANY supplier
invoice and convert it into a STANDARD Item Master structure.

The supplier invoice layout is dynamic.

Different suppliers may use completely different formats.

DO NOT assume a fixed invoice layout.

The OUTPUT Item Master structure is standardized.


============================================================
STANDARD ITEM MASTER FIELDS
============================================================

Every line item must contain:

1. manufacturer_part_number
2. vendor_part_number
3. description
4. uom
5. quantity_shipped
6. unit_price_usd
7. extended_price_usd
8. uom_multiplier


============================================================
VENDOR INFORMATION
============================================================

The vendor is the company that ISSUED the invoice.

Extract, when present:

- vendor_name
- vendor_address
- vendor_phone
- vendor_email

These normally appear in the invoice letterhead/header.

If a value is not present, return null.

Do not infer missing information.


============================================================
PHONE NUMBER — PRESERVE EXACTLY
============================================================

Extract the vendor phone number EXACTLY as it appears on
the CURRENT invoice.

DO NOT normalize, reformat, shorten, or modify phone numbers.

Preserve:

- country code
- + symbol
- parentheses
- spaces
- hyphens
- extensions
- punctuation

Example:

If the CURRENT invoice says:

+1 (718) 326-3404

The output MUST be:

+1 (718) 326-3404

DO NOT output:

(718) 326-3404

DO NOT remove +1.

DO NOT convert the phone number into another format.

If the phone number is not present on the CURRENT invoice:

vendor_phone = null


============================================================
EMAIL
============================================================

Extract the vendor email from the CURRENT invoice.

Return the actual email address only.

If the invoice contains:

arieselectricmotor@yahoo.com

return:

arieselectricmotor@yahoo.com

If the LLM response contains Markdown such as:

[arieselectricmotor@yahoo.com](mailto:arieselectricmotor@yahoo.com)

the application may clean the artificial Markdown wrapper.

Do not invent an email address.

If no email exists on the CURRENT invoice:

vendor_email = null


============================================================
CUSTOMER INFORMATION — BILL TO ONLY
============================================================

The customer is the BUYER shown in the invoice's
"Bill To" section.

THIS IS VERY IMPORTANT.

Many invoices contain TWO separate address blocks:

1. Bill To
2. Ship To

These are different sections and MUST NOT be combined.


CUSTOMER NAME:

customer_name MUST come ONLY from the "Bill To" section.

CUSTOMER ADDRESS:

customer_address MUST come ONLY from the "Bill To" section.


NEVER:

- copy Ship To information into customer_address
- combine Bill To and Ship To addresses
- combine Bill To and Ship To customer names
- use the Ship To company as customer_name
- use the Ship To address as customer_address


Example:

If the CURRENT invoice says:

Bill To:
CHAMPION ELEVATOR
1450 BROADWAY 5TH FLOOR
ATTN: ACCOUNTS PAYABLE
NEW YORK
NY 10018

Ship To:
TACONIC ELEV C/O CHAMPION ELEV
124 Raymond Ave
Poughkeepsie
NY

The correct output MUST be:

customer_name:
"CHAMPION ELEVATOR"

customer_address:
"1450 BROADWAY 5TH FLOOR, ATTN: ACCOUNTS PAYABLE, NEW YORK NY 10018"


The INCORRECT output would be:

customer_name:
"CHAMPION ELEVATOR TACONIC ELEV C/O CHAMPION ELEV"

customer_address:
"1450 BROADWAY 5TH FLOOR 124 Raymond Ave, NEW YORK NY 10018"


Do NOT produce the incorrect output.


If there is no Bill To section, look for another clearly
identified billing/customer section.

If customer information is genuinely unavailable:

customer_name = null
customer_address = null


Do not use:

- vendor address
- ship-to address
- shipping company
- shipping contact

as customer information.


============================================================
SHIP TO INFORMATION
============================================================

Many invoices contain a separate "Ship To" section.

If a Ship To section exists in the CURRENT invoice:

ship_to_name MUST come ONLY from the Ship To section.

ship_to_address MUST come ONLY from the Ship To section.

NEVER:

- copy Bill To information into ship_to_name
- copy Bill To information into ship_to_address
- combine Bill To and Ship To addresses
- combine Bill To and Ship To customer names

Preserve the Ship To information from the CURRENT invoice.
Do not invent or infer missing Ship To information.

If there is NO Ship To section in the CURRENT invoice:

ship_to_name = null
ship_to_address = null

Example:

Bill To:
CHAMPION ELEVATOR
1450 BROADWAY 5TH FLOOR
NEW YORK NY 10018

Ship To:
TACONIC ELEV C/O CHAMPION ELEV
124 Raymond Ave
Poughkeepsie NY

Correct output:

customer_name:
"CHAMPION ELEVATOR"

customer_address:
"1450 BROADWAY 5TH FLOOR, NEW YORK NY 10018"

ship_to_name:
"TACONIC ELEV C/O CHAMPION ELEV"

ship_to_address:
"124 Raymond Ave, Poughkeepsie NY"

The example is only an example. Extract values ONLY from the
CURRENT invoice.


============================================================
INVOICE HEADER — KEEP DATE, INVOICE NUMBER, AND PO SEPARATE
============================================================

Invoice Date, Invoice Number, Due Date, and Purchase Order
Number are separate fields.

Extract each value ONLY from the label/section it belongs to
on the CURRENT invoice.

Examples:

DATE: 8/13/2025
INVOICE NO.: T-01-9672
PO NO.: MNTLI-01-455102

must become:

invoice_date = "8/13/2025"
invoice_number = "T-01-9672"
purchase_order_number = "MNTLI-01-455102"

NEVER combine Invoice Date with Invoice Number.

NEVER use a date as the Purchase Order Number.

NEVER use a PO number as the Invoice Number.

NEVER copy a nearby number simply because it looks plausible.

If the relationship between a label and value is genuinely
unclear in the CURRENT invoice, return null for that field.

Do not guess.

============================================================

============================================================
CRITICAL: CURRENT INVOICE ONLY — NO CROSS-INVOICE DATA
============================================================

ONLY extract information that is actually present in the
CURRENT invoice provided in this request.

Every output field MUST be supported by information from the
CURRENT invoice.

The CURRENT invoice is the ONLY source of truth.


NEVER use information from:

- another invoice
- a previous invoice
- a previous extraction
- an earlier example
- another supplier
- another customer
- another database record
- memory
- assumptions about the customer or vendor


NEVER:

- guess
- infer
- assume
- hallucinate
- fabricate
- copy values from examples
- copy values from previous invoices
- copy values from previous responses


For example:

If a previous invoice contained:

ATTN: ACCOUNTS PAYABLE

but the CURRENT invoice does not contain:

ATTN: ACCOUNTS PAYABLE

then DO NOT output:

ATTN: ACCOUNTS PAYABLE


The value MUST NOT be added to the CURRENT invoice.


This rule applies to EVERY field, including:

- vendor name
- vendor address
- vendor phone
- vendor email
- customer name
- customer address
- invoice number
- invoice date
- due date
- PO number
- manufacturer part number
- vendor part number
- description
- UOM
- quantity
- unit price
- extended price


If a field is not present in the CURRENT invoice:

return null.


A null value is CORRECT when the information is not present
in the CURRENT invoice.


============================================================
OPTIONAL INVOICE-LEVEL INFORMATION
============================================================

In addition to the standard fields, invoices may contain other
useful invoice-level information.

When explicitly present and clearly labeled on the CURRENT
invoice, also extract:

- sales_order_number
- quote_number
- order_date
- ship_date
- delivery_date
- packing_slip_number
- customer_account_number
- vendor_account_number
- job_number
- project_number
- terms
- currency
- freight_usd
- discount_usd
- tracking_number
- salesperson
- tax_id

These fields are OPTIONAL.

IMPORTANT:
- Extract only information actually present on the CURRENT invoice.
- If a field is absent, return null.
- If a field is ambiguous, return null.
- Never use a nearby unrelated number.
- Never reinterpret an invoice number, PO number, date, phone,
  subtotal, tax, or total as an optional field unless the CURRENT
  invoice explicitly labels it that way.
- Never infer values from supplier conventions.
- Never copy values from examples or previous invoices.

============================================================
DYNAMIC LINE ITEMS
============================================================

The number of output line items must match the actual number
of line items present in the CURRENT invoice.

If the invoice has 1 item:
return 1 line item.

If the invoice has 4 items:
return 4 line items.

If the invoice has 20 items:
return 20 line items.

Never combine separate invoice items.

Never create extra line items.

Never drop actual invoice line items.


============================================================
MANUFACTURER PART NUMBER
============================================================

Manufacturer Part Number belongs to the actual manufacturer.

Look for explicit labels such as:

- Manufacturer Part Number
- Manufacturer P/N
- Mfr Part #
- MFR #
- MPN
- Manufacturer #
- Manufacturer Item
- Manufacturer Model

Only populate manufacturer_part_number when the CURRENT
invoice provides evidence that the value belongs to the
manufacturer.

If there is no manufacturer part number:

manufacturer_part_number = null


============================================================
VENDOR PART NUMBER
============================================================

Vendor Part Number belongs to the supplier/vendor.

Look for:

- Vendor Part Number
- Vendor P/N
- Vendor #
- Supplier Part #
- Supplier P/N
- Supplier Item
- Item #
- Item Number
- Part #
- Part Number
- Product Code
- Stock #
- Catalog #
- SKU

If exactly ONE identifiable part number exists and the CURRENT
invoice does not identify it as manufacturer-specific, use
that value as vendor_part_number.

Do NOT create a second part number.

If no identifiable part number exists:

vendor_part_number = null


============================================================
DESCRIPTION
============================================================

Extract the actual supplier description from the CURRENT
invoice.

Preserve the supplier's wording.

Do not expand abbreviations.

Do not invent additional specifications.

Do not rewrite the description unnecessarily.


============================================================
UNIT OF MEASURE
============================================================

UOM MUST COME FROM THE CURRENT INVOICE.

Possible UOM values include:

- E
- EA
- EACH
- BOX
- SET
- C
- M
- PCS
- PC
- PK
- LOT

IMPORTANT:

NEVER assume EA.

NEVER assume EACH.

NEVER convert a missing UOM into EA.

If the CURRENT invoice does not show a UOM:

uom = null

Do NOT return EA merely because quantity is 1.


============================================================
UOM MULTIPLIER
============================================================

Only populate uom_multiplier when the UOM is actually present
and identifiable on the CURRENT invoice.

Use:

E / EA / EACH = 1
BOX = 1
SET = 1
C = 100
M = 1000

If UOM is null:

uom_multiplier = null


============================================================
QUANTITY SHIPPED
============================================================

Extract the actual shipped quantity from the CURRENT invoice.

Look for:

- Qty
- Quantity
- Qty Ship
- Quantity Shipped
- Shipped
- Units
- Count

IMPORTANT:

Some invoices have multiple quantity columns, for example:

Qty Ordered
Qty
Back Ordered

When this happens, identify the column representing the
quantity actually shipped/fulfilled.

Do not automatically use Qty Ordered.

Do not confuse invoice totals with line-item quantities.

If the invoice clearly provides a shipped/fulfilled quantity,
use that quantity.

If quantity is not present:

quantity_shipped = null


============================================================
DYNAMIC ADDITIONAL LINE-ITEM INFORMATION
============================================================

Different suppliers may have additional columns or fields in
their item tables that are not part of the standard Item Master.

Examples include:

- Qty Ordered
- Back Ordered
- Allocated
- Available
- Sales Rep
- Warehouse
- Bin
- Serial Number
- Lot Number
- Manufacturer
- Country of Origin
- Lead Time
- Customer Item
- Requested Date
- Promised Date
- any other clearly labeled line-item information

DO NOT force these fields into the standard fields.

Instead, store them inside:

additional_info

Example:

"additional_info": {{
    "Qty Ordered": 40,
    "Back Ordered": 10
}}

Another invoice might contain:

"additional_info": {{
    "Serial Number": "ABC123",
    "Warehouse": "WH-02"
}}

IMPORTANT:

1. Only include additional information that is actually present
   on the CURRENT invoice.

2. Only include information that can clearly be associated with
   that specific line item.

3. Preserve the original label as the key whenever practical.

4. Preserve the source value without unnecessary rewriting.

5. Do NOT copy information from another invoice.

6. Do NOT invent additional fields.

7. Do NOT move standard fields into additional_info.

8. Do NOT put Qty Ordered into quantity_shipped.

9. Do NOT put Back Ordered into quantity_shipped.

10. quantity_shipped must continue to represent the actual
    shipped/fulfilled quantity.

11. If the invoice has no additional line-item information,
    additional_info must be an empty object:

    {}

12. Do not keep line-item additional_info entries whose value is
    null, empty, or blank.

13. If a field is invoice-level rather than line-item-level,
    keep it in the appropriate invoice-level field instead of
    repeating it inside every line item.


============================================================
DYNAMIC INVOICE-LEVEL ADDITIONAL INFORMATION
============================================================

Invoices may contain useful labeled information that does not
fit one of the standard invoice-level fields.

Examples include:

- PO#
- Order Number
- Customer ID
- Customer Number
- Account Number
- Sales Rep
- Salesperson
- Taker
- Shipping Method
- Requested Date

CRITICAL LABEL/VALUE ASSOCIATION RULE:

When the invoice header contains several labeled values near
each other, associate each value ONLY with the label it belongs to.

Example:

Invoice no: 4614230    Taker: PAUL SICKLER
Order Number: 4614230  Order Date: 08/11/2025
Customer ID: 124431    PO#: MODNY14-455006

Correct mapping:

invoice_number = "4614230"
salesperson = "PAUL SICKLER"
sales_order_number = "4614230"
order_date = "08/11/2025"
customer_account_number = "124431"
purchase_order_number = "MODNY14-455006"

NEVER put a nearby order number, invoice number, PO number,
customer ID, or date into Taker, Sales Rep, or Salesperson.
- Delivery Instructions
- Payment Instructions
- Approval Information
- any other clearly labeled invoice-level information

FIRST try to map the value into the correct standard field.

For example:

PO# MODNY14-455006

normally belongs in:

purchase_order_number = "MODNY14-455006"

If a clearly labeled value cannot be confidently mapped to a
standard field, DO NOT discard it.

Preserve it in the TOP-LEVEL additional_info object.

Example:

"additional_info": {{
    "PO#": "MODNY14-455006",
    "Sales Rep": "PAUL SICKLER",
    "Order Number": "4614230",
    "Customer ID": "124431"
}}

Rules:

1. Only include information actually present on the CURRENT invoice.
2. Preserve the original label as the key whenever practical.
3. Preserve the source value without unnecessary rewriting.
4. Do not use additional_info to replace a standard field when
   the standard field can be confidently populated.
5. Do not duplicate a standard field in additional_info when
   the same value is already confidently stored in that standard
   field. For example, if sales_order_number contains 4614230,
   do not also return "Order Number": "4614230" in additional_info.
   Only keep the value in additional_info when it represents
   separate information or cannot be confidently mapped.
6. Do not invent or infer additional fields.
7. Do not copy values from previous invoices or examples.
8. If no extra invoice-level information exists:
   additional_info = {{}}

============================================================
UNIT PRICE
============================================================

Extract the actual line-item unit price from the CURRENT
invoice.

Look for:

- Rate
- Unit Price
- Price
- Cost
- Unit Cost

Do NOT use:

- subtotal
- tax
- invoice total
- amount due

as unit price.


IMPORTANT:

Preserve the actual numeric precision from the CURRENT invoice.

For example:

8036.3178

must remain:

8036.3178

Do not round it to:

8036.32


If the invoice displays:

2499.0001

return:

2499.0001

Do not round it.


============================================================
EXTENDED PRICE
============================================================

Prefer the explicit line amount shown on the CURRENT invoice.

Look for:

- Amount
- Extension
- Extended
- Extended Price
- Line Total
- Net Amount

Do NOT use the invoice grand total as the line-item amount.

If an explicit line amount does not exist, calculate it only
when the required information is actually available.

Formula:

Extended Price =
Unit Price / UOM Multiplier × Quantity Shipped


============================================================
ENTIRE CURRENT INVOICE
============================================================

Examine the ENTIRE CURRENT invoice before returning null.

A value may appear:

- inside the item table
- above the table
- below the table
- beside the description
- in a header
- in another invoice section
- in a supplier-specific item block

However, the value must actually exist in the CURRENT invoice.

Do not infer a value from common supplier practices.

Do not use information from previous invoices.


============================================================
EXACT DATA PRESERVATION
============================================================

The goal is to preserve the information shown on the CURRENT
invoice.

Do not unnecessarily normalize or rewrite source values.

Preserve:

- part numbers
- phone numbers
- descriptions
- UOM
- invoice numbers
- PO numbers
- numeric precision

Only clean formatting that is clearly artificial,
such as Markdown wrappers around an email address.


============================================================
FINAL RULE
============================================================

The CURRENT invoice is the ONLY source of truth.

Missing information must remain null.

Do not fill blanks simply to make the table look complete.

Return ONLY valid JSON.
"""


# ============================================================
# OUTPUT SCHEMA
# ============================================================

EXTRACTION_SCHEMA = {
    "vendor_name": None,
    "vendor_address": None,
    "vendor_phone": None,
    "vendor_email": None,

    "customer_name": None,
    "customer_address": None,
    "ship_to_name": None,
    "ship_to_address": None,

    "invoice_number": None,
    "invoice_date": None,
    "due_date": None,
    "purchase_order_number": None,

    # Optional invoice-level fields. Extract only when explicitly
    # present and clearly labeled on the current invoice.
    "sales_order_number": None,
    "quote_number": None,
    "order_date": None,
    "ship_date": None,
    "delivery_date": None,
    "packing_slip_number": None,
    "customer_account_number": None,
    "vendor_account_number": None,
    "job_number": None,
    "project_number": None,
    "terms": None,
    "currency": None,
    "freight_usd": None,
    "discount_usd": None,
    "tracking_number": None,
    "salesperson": None,
    "tax_id": None,

    # Dynamic invoice-level information not represented by one
    # of the standard invoice fields.
    "additional_info": {},

    "line_items": [
        {
            "manufacturer_part_number": None,
            "vendor_part_number": None,
            "description": None,
            "quantity_shipped": None,
            "uom": None,
            "unit_price_usd": None,
            "extended_price_usd": None,
            "uom_multiplier": None,

            # Dynamic line-item information that does not belong
            # to the standard Item Master fields.
            "additional_info": {},
        }
    ],

    "subtotal_usd": None,
    "tax_usd": None,
    "total_usd": None,
}


# ============================================================
# STRUCTURED JSON SCHEMA
# ============================================================
#
# JSON mode only guarantees valid JSON syntax.
# This schema additionally constrains field names and data types.
#
# strict=False is intentional because the current
# llama-3.3-70b-versatile model is not listed by Groq among the
# models supporting strict constrained decoding. Groq documents
# best-effort JSON Schema support more broadly.
# ============================================================

INVOICE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "vendor_name": {"type": ["string", "null"]},
        "vendor_address": {"type": ["string", "null"]},
        "vendor_phone": {"type": ["string", "null"]},
        "vendor_email": {"type": ["string", "null"]},

        "customer_name": {"type": ["string", "null"]},
        "customer_address": {"type": ["string", "null"]},
        "ship_to_name": {"type": ["string", "null"]},
        "ship_to_address": {"type": ["string", "null"]},

        "invoice_number": {"type": ["string", "null"]},
        "invoice_date": {"type": ["string", "null"]},
        "due_date": {"type": ["string", "null"]},
        "purchase_order_number": {"type": ["string", "null"]},

        "sales_order_number": {"type": ["string", "null"]},
        "quote_number": {"type": ["string", "null"]},
        "order_date": {"type": ["string", "null"]},
        "ship_date": {"type": ["string", "null"]},
        "delivery_date": {"type": ["string", "null"]},
        "packing_slip_number": {"type": ["string", "null"]},
        "customer_account_number": {"type": ["string", "null"]},
        "vendor_account_number": {"type": ["string", "null"]},
        "job_number": {"type": ["string", "null"]},
        "project_number": {"type": ["string", "null"]},
        "terms": {"type": ["string", "null"]},
        "currency": {"type": ["string", "null"]},
        "freight_usd": {"type": ["number", "null"]},
        "discount_usd": {"type": ["number", "null"]},
        "tracking_number": {"type": ["string", "null"]},
        "salesperson": {"type": ["string", "null"]},
        "tax_id": {"type": ["string", "null"]},

        "additional_info": {
            "type": "object",
            "additionalProperties": {
                "type": [
                    "string",
                    "number",
                    "boolean",
                    "null"
                ]
            }
        },

        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    # Keep part numbers as strings so leading zeros
                    # are never lost.
                    "manufacturer_part_number": {
                        "type": ["string", "null"]
                    },
                    "vendor_part_number": {
                        "type": ["string", "null"]
                    },
                    "description": {
                        "type": ["string", "null"]
                    },
                    "quantity_shipped": {
                        "type": ["number", "null"]
                    },
                    "uom": {
                        "type": ["string", "null"]
                    },
                    "unit_price_usd": {
                        "type": ["number", "null"]
                    },
                    "extended_price_usd": {
                        "type": ["number", "null"]
                    },
                    "uom_multiplier": {
                        "type": ["number", "null"]
                    },

                    "additional_info": {
                        "type": "object",
                        "additionalProperties": {
                            "type": [
                                "string",
                                "number",
                                "boolean",
                                "null"
                            ]
                        }
                    },
                },
                "required": [
                    "manufacturer_part_number",
                    "vendor_part_number",
                    "description",
                    "quantity_shipped",
                    "uom",
                    "unit_price_usd",
                    "extended_price_usd",
                    "uom_multiplier",
                    "additional_info",
                ],
                "additionalProperties": False,
            },
        },

        "subtotal_usd": {"type": ["number", "null"]},
        "tax_usd": {"type": ["number", "null"]},
        "total_usd": {"type": ["number", "null"]},
    },

    "required": [
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
        "additional_info",
        "line_items",
        "subtotal_usd",
        "tax_usd",
        "total_usd",
    ],
    "additionalProperties": False,
}


# ============================================================
# CLEAN GROQ RESPONSE
# ============================================================

def clean_json_response(
    content: str,
) -> str:
    """
    Extract only the JSON object from the Groq response.
    """

    if not content:
        raise ValueError(
            "Groq returned an empty response"
        )

    content = content.strip()

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

    start = content.find("{")
    end = content.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError(
            "No JSON object found in Groq response:\n"
            f"{content}"
        )

    return content[start:end + 1].strip()


# ============================================================
# EMAIL NORMALIZATION
# ============================================================

def normalize_email(
    value: Any,
) -> str | None:
    """
    Clean an email address returned by the LLM.

    Only removes artificial Markdown/mailto wrappers.
    """

    if not value:
        return None

    email = str(value).strip()

    mailto_match = re.search(
        r"\[([^\]]+)\]\(mailto:([^)]+)\)",
        email,
        flags=re.IGNORECASE,
    )

    if mailto_match:
        email = (
            mailto_match
            .group(2)
            .strip()
        )

    if email.lower().startswith(
        "mailto:"
    ):
        email = email[7:].strip()

    email_match = re.search(
        r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",
        email,
    )

    if email_match:
        return email_match.group(0)

    return None


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(
    value: Any,
) -> str | None:
    """
    Clean extracted text without inventing information.

    Only removes surrounding whitespace.
    """

    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    return text


# ============================================================
# PHONE PRESERVATION
# ============================================================

def preserve_phone(
    value: Any,
) -> str | None:
    """
    Preserve the phone number exactly as returned by the LLM.

    No country-code removal.
    No punctuation removal.
    No formatting changes.

    Only surrounding whitespace is removed.
    """

    if value is None:
        return None

    phone = str(value).strip()

    if not phone:
        return None

    return phone


# ============================================================
# REMOVE DUPLICATES FROM DYNAMIC INVOICE INFORMATION
# ============================================================

def _normalize_dynamic_key(value: Any) -> str:
    """
    Normalize a dynamic field label only for duplicate detection.

    This does NOT change the value written to additional_info.
    """
    if value is None:
        return ""

    return re.sub(
        r"[^a-z0-9]+",
        " ",
        str(value).strip().lower(),
    ).strip()


def _is_same_value(
    left: Any,
    right: Any,
) -> bool:
    """
    Compare values conservatively for duplicate detection.

    Numeric values are compared numerically when possible.
    Text values are compared after trimming whitespace.
    """

    if left is None or right is None:
        return False

    try:
        return float(left) == float(right)
    except (TypeError, ValueError):
        return (
            str(left).strip().lower()
            == str(right).strip().lower()
        )


def _remove_standard_field_duplicates(
    additional_info: dict[str, Any],
    standard_fields: dict[str, Any],
) -> dict[str, Any]:
    """
    Remove dynamic additional-info entries when they simply
    duplicate a confidently populated standard field.

    Example:

        sales_order_number = "4614230"

        additional_info = {
            "Order Number": "4614230"
        }

    becomes:

        additional_info = {{}}
    """

    aliases = {
        "invoice number": "invoice_number",
        "invoice no": "invoice_number",
        "invoice #": "invoice_number",
        "invoice date": "invoice_date",

        "po": "purchase_order_number",
        "po number": "purchase_order_number",
        "po no": "purchase_order_number",
        "po #": "purchase_order_number",
        "po#": "purchase_order_number",
        "purchase order": "purchase_order_number",
        "purchase order number": "purchase_order_number",

        "order number": "sales_order_number",
        "order no": "sales_order_number",
        "order #": "sales_order_number",
        "order": "sales_order_number",
        "sales order": "sales_order_number",
        "sales order number": "sales_order_number",
        "sales order no": "sales_order_number",
        "sales order #": "sales_order_number",

        "sales rep": "salesperson",
        "salesperson": "salesperson",
        "sales person": "salesperson",
    }

    cleaned: dict[str, Any] = {}

    for key, value in additional_info.items():

        normalized_key = _normalize_dynamic_key(
            key
        )

        standard_field = aliases.get(
            normalized_key
        )

        if (
            standard_field
            and standard_fields.get(standard_field)
            not in (None, "")
            and _is_same_value(
                standard_fields.get(standard_field),
                value,
            )
        ):
            # Same information is already stored in the proper
            # standard field. Do not duplicate it.
            continue

        cleaned[key] = value

    return cleaned


# ============================================================
# NORMALIZE EXTRACTED DATA
# ============================================================

def normalize_extracted_data(
    data: dict[str, Any],
) -> dict[str, Any]:
    """
    Ensure the Groq response follows the standard structure.
    """

    if not isinstance(data, dict):
        raise ValueError(
            "Groq response is not a JSON object"
        )

    normalized = {
        "vendor_name": clean_text(
            data.get("vendor_name")
        ),

        "vendor_address": clean_text(
            data.get("vendor_address")
        ),

        "vendor_phone": preserve_phone(
            data.get("vendor_phone")
        ),

        "vendor_email": normalize_email(
            data.get("vendor_email")
        ),

        "customer_name": clean_text(
            data.get("customer_name")
        ),

        "customer_address": clean_text(
            data.get("customer_address")
        ),

        "ship_to_name": clean_text(
            data.get("ship_to_name")
        ),

        "ship_to_address": clean_text(
            data.get("ship_to_address")
        ),

        "invoice_number": clean_text(
            data.get("invoice_number")
        ),

        "invoice_date": clean_text(
            data.get("invoice_date")
        ),

        "due_date": clean_text(
            data.get("due_date")
        ),

        "purchase_order_number": clean_text(
            data.get("purchase_order_number")
        ),

        "sales_order_number": clean_text(
            data.get("sales_order_number")
        ),
        "quote_number": clean_text(
            data.get("quote_number")
        ),
        "order_date": clean_text(
            data.get("order_date")
        ),
        "ship_date": clean_text(
            data.get("ship_date")
        ),
        "delivery_date": clean_text(
            data.get("delivery_date")
        ),
        "packing_slip_number": clean_text(
            data.get("packing_slip_number")
        ),
        "customer_account_number": clean_text(
            data.get("customer_account_number")
        ),
        "vendor_account_number": clean_text(
            data.get("vendor_account_number")
        ),
        "job_number": clean_text(
            data.get("job_number")
        ),
        "project_number": clean_text(
            data.get("project_number")
        ),
        "terms": clean_text(
            data.get("terms")
        ),
        "currency": clean_text(
            data.get("currency")
        ),
        "freight_usd": data.get("freight_usd"),
        "discount_usd": data.get("discount_usd"),
        "tracking_number": clean_text(
            data.get("tracking_number")
        ),
        "salesperson": clean_text(
            data.get("salesperson")
        ),
        "tax_id": clean_text(
            data.get("tax_id")
        ),

        "additional_info": {},

        "line_items": [],

        "subtotal_usd": data.get(
            "subtotal_usd"
        ),

        "tax_usd": data.get(
            "tax_usd"
        ),

        "total_usd": data.get(
            "total_usd"
        ),
    }

    raw_invoice_additional_info = data.get(
        "additional_info",
        {},
    )

    if not isinstance(
        raw_invoice_additional_info,
        dict,
    ):
        raw_invoice_additional_info = {}

    cleaned_invoice_additional_info = {}

    for key, value in raw_invoice_additional_info.items():

        if key is None:
            continue

        key = str(key).strip()

        if not key:
            continue

        if isinstance(
            value,
            (str, int, float, bool)
        ) or value is None:

            cleaned_invoice_additional_info[key] = value

    cleaned_invoice_additional_info = (
        _remove_standard_field_duplicates(
            cleaned_invoice_additional_info,
            normalized,
        )
    )

    # --------------------------------------------------------
    # Safety check for a known header-association failure:
    #
    # If "Taker" was incorrectly assigned the sales order number
    # while a proper salesperson value already exists, remove
    # the incorrect dynamic copy. We do not invent or overwrite
    # the standard salesperson field here.
    # --------------------------------------------------------

    taker_value = None

    for key, value in (
        cleaned_invoice_additional_info.items()
    ):

        if _normalize_dynamic_key(key) == "taker":
            taker_value = value
            break

    if (
        taker_value is not None
        and normalized.get("salesperson") not in (None, "")
        and normalized.get("sales_order_number") not in (None, "")
        and _is_same_value(
            taker_value,
            normalized.get("sales_order_number"),
        )
    ):
        cleaned_invoice_additional_info = {
            key: value
            for key, value
            in cleaned_invoice_additional_info.items()
            if _normalize_dynamic_key(key) != "taker"
        }

    # --------------------------------------------------------
    # Remove empty/null dynamic invoice-level values.
    #
    # Example:
    #   {"Sales Rep": None, "Shipping Method": "Delivery"}
    #
    # becomes:
    #   {"Shipping Method": "Delivery"}
    # --------------------------------------------------------

    cleaned_invoice_additional_info = {
        key: value
        for key, value
        in cleaned_invoice_additional_info.items()
        if value not in (None, "")
    }

    normalized["additional_info"] = (
        cleaned_invoice_additional_info
    )

    line_items = data.get(
        "line_items",
        [],
    )

    if not isinstance(
        line_items,
        list,
    ):
        line_items = []

    for item in line_items:

        if not isinstance(
            item,
            dict,
        ):
            continue

        additional_info = item.get(
            "additional_info",
            {},
        )

        if not isinstance(
            additional_info,
            dict,
        ):
            additional_info = {{}}

        cleaned_additional_info = {}

        for key, value in additional_info.items():

            if key is None:
                continue

            key = str(key).strip()

            if not key:
                continue

            if (
                isinstance(
                    value,
                    (str, int, float, bool)
                )
                and value != ""
            ):
                cleaned_additional_info[key] = value

        normalized_item = {
            "manufacturer_part_number":
                clean_text(
                    item.get(
                        "manufacturer_part_number"
                    )
                ),

            "vendor_part_number":
                clean_text(
                    item.get(
                        "vendor_part_number"
                    )
                ),

            "description":
                clean_text(
                    item.get("description")
                ),

            "quantity_shipped":
                item.get(
                    "quantity_shipped"
                ),

            "uom":
                clean_text(
                    item.get("uom")
                ),

            "unit_price_usd":
                item.get(
                    "unit_price_usd"
                ),

            "extended_price_usd":
                item.get(
                    "extended_price_usd"
                ),

            "uom_multiplier":
                item.get(
                    "uom_multiplier"
                ),

            "additional_info":
                cleaned_additional_info,
        }

        normalized[
            "line_items"
        ].append(
            normalized_item
        )

    return normalized


# ============================================================
# MAIN EXTRACTION FUNCTION
# ============================================================

def extract_invoice_data(
    invoice_text: str,
) -> dict[str, Any]:
    """
    Extract structured invoice data.

    The supplier invoice layout can be completely different
    from one invoice to another.

    The standard Item Master fields remain stable while
    additional line-item information is preserved dynamically
    inside each item's additional_info object.

    Number of output rows = number of actual invoice line items.
    """

    if not invoice_text or not invoice_text.strip():
        raise ValueError(
            "Invoice text is empty"
        )

    # --------------------------------------------------------
    # USER PROMPT
    # --------------------------------------------------------

    user_prompt = f"""
Extract the invoice below into the standard Item Master format.

IMPORTANT EXTRACTION RULES:

1. Examine the ENTIRE CURRENT invoice before extracting.
2. Identify EVERY actual line item.
3. The supplier layout may be completely different.
4. Map the information into the standard Item Master fields.
5. Do not assume a fixed column layout.
6. Do not invent missing information.
7. If information is not actually present in the CURRENT
   invoice, return null.
8. Never assume EA when UOM is missing.
9. Never create a manufacturer part number.
10. Never create a vendor part number.
11. Preserve the supplier's description.
12. Keep the same number of line items as the CURRENT invoice.
13. Return the actual vendor email address only.
14. Do not return Markdown links for email addresses.
15. Detect additional line-item columns that are not part of the
    standard Item Master fields.
16. Put those clearly supported line-item values into
    additional_info.
17. Do not use additional_info to replace standard fields.
18. If no additional line-item information exists, return {{}}.
19. Preserve additional field labels and values from the CURRENT
    invoice.
20. Do not invent or infer additional fields.
21. Detect clearly labeled invoice-level information that does not
    fit the standard invoice fields and put it in TOP-LEVEL
    additional_info.
22. If a standard field cannot be confidently mapped but the
    CURRENT invoice clearly contains a labeled value, preserve
    that value in top-level additional_info instead of discarding it.
23. Do not use top-level additional_info to replace a standard
    field when the standard field can be confidently populated.
24. If there is no extra invoice-level information, use:
    additional_info = {{}}.
25. Preserve label-to-value associations from the CURRENT invoice.
26. Never assign a numeric order/invoice/PO/customer ID value to
    Taker, Sales Rep, or Salesperson when the invoice shows a
    different labeled person value.


============================================================
SOURCE-OF-TRUTH RULE
============================================================

Use ONLY the CURRENT invoice text between:

---------------- BEGIN INVOICE ----------------

and:

----------------- END INVOICE -----------------

Every extracted value MUST be supported by the CURRENT invoice.

Do NOT use information from:

- previous invoices
- previous examples
- previous responses
- previous extractions
- other suppliers
- other customers
- memory
- assumptions

If the CURRENT invoice does not contain a value:

return null.

For example:

If another invoice contained:

ATTN: ACCOUNTS PAYABLE

but the CURRENT invoice does not contain:

ATTN: ACCOUNTS PAYABLE

DO NOT output:

ATTN: ACCOUNTS PAYABLE


============================================================
PHONE NUMBER RULE
============================================================

Preserve the vendor phone number EXACTLY as printed on the
CURRENT invoice.

Preserve:

- +
- country code
- parentheses
- spaces
- hyphens
- extensions

Example:

Invoice:
+1 (718) 326-3404

Output:
+1 (718) 326-3404

NOT:

(718) 326-3404


============================================================
CUSTOMER / BILL TO RULE
============================================================

Find the "Bill To" section in the CURRENT invoice.

customer_name MUST come from Bill To.

customer_address MUST come from Bill To.

NEVER combine Bill To and Ship To.

NEVER put Ship To information into customer_name.

NEVER put Ship To information into customer_address.

For example:

Bill To:
CHAMPION ELEVATOR
1450 BROADWAY 5TH FLOOR
ATTN: ACCOUNTS PAYABLE
NEW YORK NY 10018

Ship To:
TACONIC ELEV C/O CHAMPION ELEV
124 Raymond Ave
Poughkeepsie NY

Correct:

customer_name =
"CHAMPION ELEVATOR"

customer_address =
"1450 BROADWAY 5TH FLOOR, ATTN: ACCOUNTS PAYABLE, NEW YORK NY 10018"

Do NOT use the Ship To information.

IMPORTANT:

The example above is ONLY an example of how to distinguish
Bill To from Ship To.

DO NOT copy "ATTN: ACCOUNTS PAYABLE" into the CURRENT invoice
unless those exact words actually appear in the CURRENT invoice.




============================================================
SHIP TO EXTRACTION
============================================================

If the CURRENT invoice contains a "Ship To" section:

Extract:

ship_to_name
ship_to_address

ship_to_name must come ONLY from Ship To.

ship_to_address must come ONLY from Ship To.

Keep Bill To and Ship To completely separate.

If there is no Ship To section in the CURRENT invoice:

ship_to_name = null
ship_to_address = null

Do not infer Ship To information from any other section.

============================================================
OPTIONAL INVOICE-LEVEL INFORMATION
============================================================

If the CURRENT invoice explicitly contains clearly labeled
additional invoice information, extract it into these fields:

- sales_order_number
- quote_number
- order_date
- ship_date
- delivery_date
- packing_slip_number
- customer_account_number
- vendor_account_number
- job_number
- project_number
- terms
- currency
- freight_usd
- discount_usd
- tracking_number
- salesperson
- tax_id

Only extract a field when the CURRENT invoice clearly supports
it. If it is missing or ambiguous, return null.

Do NOT guess or repurpose another field's value.

============================================================
QUANTITY RULE
============================================================

Some invoices contain multiple quantity columns.

For example:

Qty Ordered
Qty
Back Ordered

When multiple quantity columns exist, identify which one
represents the quantity actually shipped/fulfilled.

Use that value for:

quantity_shipped

Do not automatically use Qty Ordered.


============================================================
CURRENT INVOICE
============================================================

---------------- BEGIN INVOICE ----------------

{invoice_text}

----------------- END INVOICE -----------------

Return ONLY data supported by the CURRENT invoice.

The JSON Schema controls the output shape and field types.
It does NOT permit guessing.

If a value is not explicitly supported by the CURRENT invoice,
return null for that field.

Keep manufacturer and vendor part numbers as strings exactly as
printed, including leading zeros.

Do not derive Quantity or Unit Price from Extended Price.

For any extra table columns such as Qty Ordered or Back Ordered,
keep them in additional_info instead of replacing
quantity_shipped.

Example:

"additional_info": {{
    "Qty Ordered": 40,
    "Back Ordered": 10
}}

Use exactly this structure:

{json.dumps(INVOICE_JSON_SCHEMA, indent=2)}
"""

    # --------------------------------------------------------
    # GROQ CALL
    # --------------------------------------------------------

    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=0,
        response_format={
            "type": "json_object"
        },
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
    )

    # --------------------------------------------------------
    # RESPONSE CONTENT
    # --------------------------------------------------------

    content = (
        response
        .choices[0]
        .message
        .content
    )

    if not content:
        raise ValueError(
            "Groq returned an empty response"
        )

    # --------------------------------------------------------
    # CLEAN JSON
    # --------------------------------------------------------

    content = clean_json_response(
        content
    )

    # --------------------------------------------------------
    # PARSE JSON
    # --------------------------------------------------------

    try:

        data = json.loads(
            content
        )

    except json.JSONDecodeError as exc:

        raise ValueError(
            "Groq returned invalid JSON:\n"
            f"{content}"
        ) from exc

    # --------------------------------------------------------
    # NORMALIZE
    # --------------------------------------------------------

    return normalize_extracted_data(
        data
    )


# ============================================================
# VISION RESPONSE CLEANING
# ============================================================

def _clean_dynamic_dict(
    value: Any,
) -> dict[str, Any]:
    """
    Keep only real, non-empty dynamic values.
    """

    if not isinstance(
        value,
        dict,
    ):
        return {}

    return {
        str(key).strip(): item_value
        for key, item_value in value.items()
        if key is not None
        and str(key).strip()
        and item_value not in (
            None,
            "",
        )
    }


def _clean_vision_fields(
    value: Any,
) -> dict[str, Any]:
    """
    Keep only non-empty standard visual fields.
    """

    if not isinstance(
        value,
        dict,
    ):
        return {}

    return {
        str(key).strip(): item_value
        for key, item_value in value.items()
        if key is not None
        and str(key).strip()
        and item_value not in (
            None,
            "",
        )
    }


# ============================================================
# HEADER VISION PASS
# ============================================================

def _extract_invoice_header_with_vision(
    image_data_urls: list[str],
) -> dict[str, Any]:
    """
    Vision pass focused on invoice/header information only.

    The full invoice image is provided, but the task is limited
    to header/customer/shipping/totals and other invoice-level
    information.

    It does NOT extract line items.
    """

    images = [
        image
        for image in image_data_urls
        if isinstance(image, str)
        and image.startswith("data:image/")
    ][:5]

    if not images:
        raise ValueError(
            "No valid invoice images were provided."
        )

    prompt = """
Read the CURRENT invoice image(s).

Focus ONLY on invoice-level/header information.

Do NOT extract line items in this pass.

Return ONLY valid JSON.

Standard fields:
- invoice_number
- invoice_date
- due_date
- purchase_order_number
- sales_order_number
- customer_account_number
- vendor_account_number
- salesperson
- order_date
- ship_date
- delivery_date
- packing_slip_number
- tracking_number

Also capture clearly labeled invoice-level information that
does not fit those standard fields in additional_info.

Rules:
1. Use only values visible in the current invoice image.
2. Preserve exact values as printed.
3. Keep each label attached to the correct value.
4. Do not infer missing values.
5. Do not copy information from another invoice.
6. If a value is unclear, return null.
7. Do not place line-item values into additional_info.
8. Do not calculate values.

Return exactly:

{
  "fields": {
    "invoice_number": null,
    "invoice_date": null,
    "due_date": null,
    "purchase_order_number": null,
    "sales_order_number": null,
    "customer_account_number": null,
    "vendor_account_number": null,
    "salesperson": null,
    "order_date": null,
    "ship_date": null,
    "delivery_date": null,
    "packing_slip_number": null,
    "tracking_number": null
  },
  "additional_info": {}
}
"""

    content_parts = [
        {
            "type": "text",
            "text": prompt,
        }
    ]

    for image in images:
        content_parts.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": image,
                },
            }
        )

    response = client.chat.completions.create(
        model=VISION_MODEL,
        temperature=0,
        max_completion_tokens=3000,
        reasoning_effort="none",
        reasoning_format="hidden",
        response_format={
            "type": "json_object"
        },
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict invoice header "
                    "vision extractor. Return only JSON."
                ),
            },
            {
                "role": "user",
                "content": content_parts,
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
            "Header vision returned an empty response."
        )

    content = clean_json_response(
        content
    )

    result = json.loads(
        content
    )

    if not isinstance(
        result,
        dict,
    ):
        raise ValueError(
            "Header vision returned invalid JSON."
        )

    return {
        "fields": _clean_vision_fields(
            result.get("fields")
        ),
        "additional_info": _clean_dynamic_dict(
            result.get("additional_info")
        ),
    }


# ============================================================
# TABLE VISION PASS
# ============================================================

def _extract_line_items_with_vision(
    image_data_urls: list[str],
) -> dict[str, Any]:
    """
    Vision pass focused ONLY on the invoice item table.

    The model must visually identify the table headers first,
    then map each row using those column positions.

    This is intended to reduce Qty/Price/Amount column swaps.
    """

    images = [
        image
        for image in image_data_urls
        if isinstance(image, str)
        and image.startswith("data:image/")
    ][:5]

    if not images:
        raise ValueError(
            "No valid invoice images were provided."
        )

    prompt = """
Read the CURRENT invoice image(s).

Focus ONLY on the ITEM TABLE / LINE-ITEM SECTION.

Do not extract invoice header fields in this pass.

First identify the actual table column headers and their
left-to-right meanings.

Then extract EVERY actual line item.

STANDARD LINE-ITEM FIELDS:
- manufacturer_part_number
- vendor_part_number
- description
- quantity_shipped
- uom
- unit_price_usd
- extended_price_usd

RULES:

1. Use the visual table column positions as the source of truth.
2. Read the column headers before reading row values.
3. Keep each value in the column where it is visually printed.
4. Do NOT take numbers from inside the description as quantity.
5. Do NOT calculate quantity from unit price or amount.
6. Do NOT calculate unit price from amount.
7. Do NOT calculate amount from quantity.
8. Preserve part numbers exactly as printed.
9. Preserve the full description.
10. If the invoice has multiple quantity columns, identify the
    column that represents quantity actually shipped and put
    ONLY that column in quantity_shipped.
11. Put other quantity columns such as Qty Ordered or Back Ordered
    into that line item's additional_info.
12. Any other clearly labeled line-item column that is not one of
    the standard fields must go into that line item's
    additional_info.
13. If a line-item value is not readable, return null.
14. Do not invent rows.
15. Do not merge separate rows.
16. Do not split one invoice row into multiple rows.
17. Return one object per actual invoice line item.

Return exactly:

{
  "line_items": [
    {
      "manufacturer_part_number": null,
      "vendor_part_number": null,
      "description": null,
      "quantity_shipped": null,
      "uom": null,
      "unit_price_usd": null,
      "extended_price_usd": null,
      "additional_info": {}
    }
  ]
}
"""

    content_parts = [
        {
            "type": "text",
            "text": prompt,
        }
    ]

    for image in images:
        content_parts.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": image,
                },
            }
        )

    response = client.chat.completions.create(
        model=VISION_MODEL,
        temperature=0,
        max_completion_tokens=5000,
        reasoning_effort="none",
        reasoning_format="hidden",
        response_format={
            "type": "json_object"
        },
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict invoice table "
                    "vision extractor. Return only JSON."
                ),
            },
            {
                "role": "user",
                "content": content_parts,
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
            "Table vision returned an empty response."
        )

    content = clean_json_response(
        content
    )

    result = json.loads(
        content
    )

    if not isinstance(
        result,
        dict,
    ):
        raise ValueError(
            "Table vision returned invalid JSON."
        )

    raw_items = result.get(
        "line_items",
        [],
    )

    if not isinstance(
        raw_items,
        list,
    ):
        raw_items = []

    cleaned_items = []

    for item in raw_items:

        if not isinstance(
            item,
            dict,
        ):
            continue

        cleaned_items.append(
            {
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

                "additional_info":
                    _clean_dynamic_dict(
                        item.get(
                            "additional_info"
                        )
                    ),
            }
        )

    return {
        "line_items": cleaned_items,
    }


# ============================================================
# TWO-PASS VISION FALLBACK
# ============================================================

def extract_invoice_data_with_vision(
    image_data_urls: list[str],
    target_fields: list[str] | None = None,
) -> dict[str, Any]:
    """
    Run two focused vision passes:

        Pass 1:
            Header / invoice-level information

        Pass 2:
            Line-item table

    Both passes receive the actual invoice image(s).
    """

    header_result = (
        _extract_invoice_header_with_vision(
            image_data_urls
        )
    )

    table_result = (
        _extract_line_items_with_vision(
            image_data_urls
        )
    )

    return {
        "fields": header_result.get(
            "fields",
            {},
        ),
        "additional_info": header_result.get(
            "additional_info",
            {},
        ),
        "line_items": table_result.get(
            "line_items",
            [],
        ),
        "uncertain_fields": [],
    }



# ============================================================
# FOCUSED TABLE-ROW VISION VERIFICATION
# ============================================================

def verify_table_row_with_vision(
    image_data_urls: list[str],
    detected_columns: dict[str, Any],
    detected_row: dict[str, Any],
) -> dict[str, Any]:
    """
    Verify ONE dynamically detected table row against the
    actual invoice image.

    This is intentionally a small vision request.

    The local table detector has already identified:
        - the table headers
        - the column positions
        - the candidate row

    Qwen is only asked to confirm/correct that single row.

    This minimizes token usage compared with re-extracting the
    entire invoice through vision.
    """

    if not image_data_urls:
        raise ValueError(
            "No invoice images were provided."
        )

    images = [
        image
        for image in image_data_urls
        if isinstance(image, str)
        and image.startswith("data:image/")
    ][:3]

    if not images:
        raise ValueError(
            "No valid invoice image data URLs were provided."
        )

    prompt = f"""
Verify ONE invoice table row against the CURRENT invoice image.

The local table detector found these headers/columns:

{json.dumps(detected_columns, ensure_ascii=False)}

The local detector found this row:

{json.dumps(detected_row, ensure_ascii=False)}

Do NOT re-extract the whole invoice.

Only verify THIS ROW.

Check:
- vendor/item/part number
- description
- quantity shipped
- UOM
- unit price
- extended price
- any extra table columns

IMPORTANT:

1. Use the actual invoice image as the source of truth.
2. Read the table header and this row visually.
3. Do not move a number from the description into quantity unless
   the image clearly proves that it belongs to the quantity column.
4. Do not move a quantity into the description unless the image
   clearly proves that it belongs there.
5. Do not calculate missing values.
6. Do not guess.
7. Preserve exact printed text where readable.
8. Keep extra columns in additional_info.
9. Return one corrected row only.

Return ONLY valid JSON:

{{
  "status": "PASS",
  "corrected_row": {{
    "manufacturer_part_number": null,
    "vendor_part_number": null,
    "description": null,
    "quantity_shipped": null,
    "uom": null,
    "unit_price_usd": null,
    "extended_price_usd": null,
    "additional_info": {{}}
  }},
  "changes": [],
  "reason": ""
}}

status must be:
- PASS if the detected row is correct
- CORRECTED if one or more values are changed
- REVIEW if the image is too ambiguous to determine the correct value
"""

    content_parts: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": prompt,
        }
    ]

    for image in images:
        content_parts.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": image,
                },
            }
        )

    response = client.chat.completions.create(
        model=VISION_MODEL,
        temperature=0,
        max_completion_tokens=2500,
        reasoning_effort="none",
        reasoning_format="hidden",
        response_format={
            "type": "json_object"
        },
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict invoice table-row "
                    "verification system. Return only JSON."
                ),
            },
            {
                "role": "user",
                "content": content_parts,
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
            "Table-row vision returned an empty response."
        )

    content = clean_json_response(
        content
    )

    result = json.loads(
        content
    )

    if not isinstance(
        result,
        dict,
    ):
        raise ValueError(
            "Table-row vision returned invalid JSON."
        )

    corrected_row = result.get(
        "corrected_row",
        {},
    )

    if not isinstance(
        corrected_row,
        dict,
    ):
        corrected_row = {}

    corrected_row.setdefault(
        "additional_info",
        {}
    )

    if not isinstance(
        corrected_row.get(
            "additional_info"
        ),
        dict,
    ):
        corrected_row[
            "additional_info"
        ] = {}

    changes = result.get(
        "changes",
        [],
    )

    if not isinstance(
        changes,
        list,
    ):
        changes = []

    return {
        "status": result.get(
            "status",
            "REVIEW",
        ),
        "corrected_row": corrected_row,
        "changes": changes,
        "reason": str(
            result.get(
                "reason",
                "",
            )
            or ""
        ),
    }
