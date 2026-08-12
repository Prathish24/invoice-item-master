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

For example:

Supplier A:
Part No | Description | Qty | UOM | Rate | Amount

Supplier B:
Item | Description | Qty | Price | Amount

Supplier C:
Part Number + Description | Qty | UOM | Price

Supplier D:
Description
Part Number
Qty
UOM
Price

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

The vendor is the company that ISSUED the invoice (the seller).

Extract, when present:

- vendor_name
- vendor_address (full mailing address as printed)
- vendor_phone
- vendor_email

These normally appear in the invoice letterhead/header.

If a value is not present, return null. Do not infer it from
a logo, watermark, or domain name in an email/URL.


============================================================
CUSTOMER INFORMATION (BILL TO)
============================================================

The customer is the company being BILLED (the buyer) — the
"Bill To" section of the invoice. This is a DIFFERENT company
from the vendor.

Extract, when present:

- customer_name
- customer_address (full mailing address as printed)

If the invoice has both a "Bill To" and a "Ship To" section,
use the "Bill To" section for customer_name / customer_address.

If a value is not present, return null.


============================================================
DYNAMIC LINE ITEMS
============================================================

The number of output line items must match the actual number
of line items present in the invoice.

If the invoice has 1 item:
return 1 line item.

If the invoice has 4 items:
return 4 line items.

If the invoice has 20 items:
return 20 line items.

Never combine separate invoice items.

Never create extra line items.


============================================================
CRITICAL: NEVER INVENT INFORMATION
============================================================

ONLY extract information that actually exists in the invoice.

NEVER:

- guess
- infer
- assume
- hallucinate
- fabricate
- create missing values

If a field is genuinely not present in the invoice,
return null.

A null value is CORRECT when the invoice does not contain
that information.


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

Only populate manufacturer_part_number when the invoice
provides evidence that the value belongs to the manufacturer.

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

If exactly ONE identifiable part number exists and the invoice
does not identify it as manufacturer-specific, use that value
as vendor_part_number.

Do NOT create a second part number.

If no identifiable part number exists:

vendor_part_number = null


============================================================
DESCRIPTION
============================================================

Extract the actual supplier description.

Preserve the supplier's wording.

Do not expand abbreviations.

Do not invent additional specifications.

Do not rewrite the description unnecessarily.


============================================================
UNIT OF MEASURE
============================================================

UOM MUST COME FROM THE INVOICE.

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

Example:

If the invoice says:

REWOUND BRAKE COIL
Qty: 1
Rate: 1300
Amount: 1300

and no UOM appears anywhere:

uom = null

Do NOT return EA merely because quantity is 1.


============================================================
UOM MULTIPLIER
============================================================

Only populate uom_multiplier when the UOM is actually present
and identifiable.

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

Extract the actual line-item quantity.

Look for:

- Qty
- Quantity
- Qty Ship
- Quantity Shipped
- Shipped
- Units
- Count

Do not confuse invoice totals with line-item quantities.

If quantity is not present:

quantity_shipped = null


============================================================
UNIT PRICE
============================================================

Extract the actual line-item unit price.

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


============================================================
EXTENDED PRICE
============================================================

Prefer the explicit line amount shown on the invoice.

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
ENTIRE INVOICE
============================================================

Examine the ENTIRE invoice before returning null.

A value may appear:

- inside the item table
- above the table
- below the table
- beside the description
- in a header
- in another invoice section
- in a supplier-specific item block

However, the value must actually exist.

Do not infer a value from common supplier practices.


============================================================
DYNAMIC INVOICE → STANDARD ITEM MASTER
============================================================

The invoice format is dynamic.

The Item Master format is fixed.

Map whatever information is actually present in the invoice
into these standard fields:

Manufacturer Part Number
Vendor Part Number
Description
UOM
Qty Ship
Unit Price USD
Extended Price USD


============================================================
FINAL RULE
============================================================

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
    "invoice_number": None,
    "invoice_date": None,
    "due_date": None,
    "purchase_order_number": None,
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
# CLEAN GROQ RESPONSE
# ============================================================

def clean_json_response(content: str) -> str:
    """
    Extract only the JSON object from the Groq response.

    Groq may occasionally return explanatory text before
    or after the JSON.
    """

    if not content:
        raise ValueError(
            "Groq returned an empty response"
        )

    content = content.strip()

    # Remove markdown fences if present
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

    # Find the first JSON object
    start = content.find("{")

    # Find the final JSON closing brace
    end = content.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError(
            "No JSON object found in Groq response:\n"
            f"{content}"
        )

    # Keep only JSON
    content = content[start:end + 1]

    return content.strip()


# ============================================================
# NORMALIZE DATA
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
        "vendor_name": data.get("vendor_name"),
        "vendor_address": data.get("vendor_address"),
        "vendor_phone": data.get("vendor_phone"),
        "vendor_email": data.get("vendor_email"),
        "customer_name": data.get("customer_name"),
        "customer_address": data.get("customer_address"),
        "invoice_number": data.get("invoice_number"),
        "invoice_date": data.get("invoice_date"),
        "due_date": data.get("due_date"),
        "purchase_order_number":
            data.get("purchase_order_number"),
        "line_items": [],
        "subtotal_usd": data.get("subtotal_usd"),
        "tax_usd": data.get("tax_usd"),
        "total_usd": data.get("total_usd"),
    }

    line_items = data.get(
        "line_items",
        []
    )

    if not isinstance(line_items, list):
        line_items = []

    for item in line_items:

        if not isinstance(item, dict):
            continue

        normalized_item = {
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

            "uom_multiplier":
                item.get(
                    "uom_multiplier"
                ),
        }

        normalized["line_items"].append(
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

IMPORTANT:

1. Examine the ENTIRE invoice.
2. Identify EVERY actual line item.
3. The supplier layout may be completely different.
4. Map the information into the standard Item Master fields.
5. Do not assume a fixed column layout.
6. Do not invent missing information.
7. If information is not actually present, return null.
8. Never assume EA when UOM is missing.
9. Never create a manufacturer part number.
10. Never create a vendor part number.
11. Preserve the supplier's description.
12. Keep the same number of line items as the invoice.

INVOICE:

---------------- BEGIN INVOICE ----------------

{invoice_text}

----------------- END INVOICE -----------------

Return ONLY valid JSON.

Use exactly this structure:

{json.dumps(EXTRACTION_SCHEMA, indent=2)}
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

    content = response.choices[0].message.content

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