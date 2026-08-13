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

    The final Item Master structure remains standardized.

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
            "type": "json_schema",
            "json_schema": {
                "name": "invoice_extraction",
                "strict": False,
                "schema": INVOICE_JSON_SCHEMA,
            },
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