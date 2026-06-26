"""Map an ERPNext Sales Invoice (or its return = Credit Note) to the Cryptware
FIRS ``POST /invoice/generate`` request body.

Design notes
------------
* All monetary figures are computed from the line items so the per-line, the
  ``tax_total`` and the ``legal_monetary_total`` blocks are internally
  consistent (FIRS rejects payloads whose sums disagree).
* A Credit Note is an ERPNext Sales Invoice with ``is_return = 1``. ERPNext
  stores its quantities/amounts as negatives; FIRS expects positive magnitudes
  on the ``381`` document plus a ``cancel_references`` entry pointing at the
  original invoice IRN.
"""

import re

import frappe
from frappe.utils import flt, getdate


def _date(value):
    """FIRS expects plain calendar dates as YYYY-MM-DD."""
    if not value:
        return None
    try:
        return getdate(value).strftime("%Y-%m-%d")
    except Exception:
        return str(value)[:10]


def _time(value):
    """FIRS issue_time as HH:MM:SS."""
    if not value:
        return "00:00:00"
    text = str(value)
    return text[:8] if len(text) >= 8 else text


def _normalize_phone(value):
    """Best-effort E.164 (+234...) normalization for a Nigerian phone number."""
    if not value:
        return ""
    raw = str(value).strip()
    if raw.startswith("+"):
        digits = "+" + re.sub(r"\D", "", raw[1:])
        return digits if len(digits) > 3 else ""
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    if digits.startswith("234"):
        return "+" + digits
    if digits.startswith("0"):
        return "+234" + digits[1:]
    return "+" + digits


def _country_code(country_name):
    if not country_name:
        return "NG"
    code = frappe.db.get_value("Country", country_name, "code")
    return (code or "ng").upper()[:2]


def _primary_address(link_doctype, link_name):
    if not (link_doctype and link_name):
        return {}
    names = frappe.get_all(
        "Dynamic Link",
        filters={
            "parenttype": "Address",
            "link_doctype": link_doctype,
            "link_name": link_name,
        },
        pluck="parent",
        limit=50,
    )
    if not names:
        return {}
    rows = frappe.get_all(
        "Address",
        filters={"name": ["in", names], "disabled": 0},
        fields=["address_line1", "address_line2", "city", "state", "pincode", "country"],
        order_by="is_primary_address desc, creation desc",
        limit=1,
    )
    if not rows:
        return {}
    a = rows[0]
    street = ", ".join([p for p in [a.get("address_line1"), a.get("address_line2")] if p])
    return {
        "street_name": street,
        "city_name": a.get("city") or a.get("state") or "",
        "postal_zone": a.get("pincode") or "",
        "country": _country_code(a.get("country")),
    }


def _normalize_tax_category(cat, percent):
    """Map a FIRS Tax Category to one of the API's accepted tax_category_id enums.

    Honours an explicit valid value; otherwise falls back by rate so the payload
    always carries a recognised category.
    """
    if cat in VALID_TAX_CATEGORIES:
        return cat
    return "STANDARD_VAT" if flt(percent) > 0 else "ZERO_VAT"


def _format_hsn(value):
    """Coerce an HSN/HS code to the FIRS 0000.00 format; placeholder if unusable."""
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) >= 6:
        return f"{digits[:4]}.{digits[4:6]}"
    if len(digits) >= 4:
        return f"{digits[:4]}.{digits[4:].ljust(2, '0')[:2]}"
    return PLACEHOLDER_HSN


def _line_tax(row):
    """Return (tax_category_id, tax_percent) for an invoice line.

    Prefers the FIRS Tax Category linked on the row; the doctype is autonamed by
    ``tax_category_id`` so the link value *is* the id sent to FIRS.
    """
    cat = row.get("custom_nrs_tax_category")
    if cat:
        rate = frappe.db.get_value("FIRS Tax Category", cat, "tax_rate")
        return cat, flt(rate)
    return "", _item_tax_template_rate(row.get("item_tax_template"))


def _item_tax_template_rate(template):
    if not template:
        return 0.0
    try:
        itt = frappe.get_doc("Item Tax Template", template)
        if getattr(itt, "taxes", None):
            return flt(itt.taxes[0].tax_rate)
    except Exception:
        pass
    return 0.0


# Placeholder values used when the Customer record is missing data that FIRS
# requires as a (valid, non-empty) string. Keeps sample/test invoices flowing
# without having to fully populate every customer field.
# FIRS-accepted tax category identifiers (sent as tax_category_id).
VALID_TAX_CATEGORIES = {
    "STANDARD_VAT", "REDUCED_VAT", "ZERO_VAT",
    "STANDARD_GST", "REDUCED_GST", "ZERO_GST",
}

PLACEHOLDER_HSN = "9983.00"  # FIRS requires HSN as 0000.00; 9983 = business services
PLACEHOLDER_TIN = "00000000-0001"
PLACEHOLDER_EMAIL = "customer@example.com"
PLACEHOLDER_PHONE = "+2348000000000"
PLACEHOLDER_BUSINESS = "General goods and services"
PLACEHOLDER_ADDRESS = {
    "street_name": "1 Marina Road",
    "city_name": "Lagos",
    "postal_zone": "100001",
    "country": "NG",
}


def _customer_block(doc):
    cust = (
        frappe.db.get_value(
            "Customer",
            doc.customer,
            ["customer_name", "tax_id", "email_id", "mobile_no", "custom_nrs_business_description"],
            as_dict=True,
        )
        or {}
    )

    address = _primary_address("Customer", doc.customer) or {}
    postal_address = {
        "street_name": address.get("street_name") or PLACEHOLDER_ADDRESS["street_name"],
        "city_name": address.get("city_name") or PLACEHOLDER_ADDRESS["city_name"],
        "postal_zone": address.get("postal_zone") or PLACEHOLDER_ADDRESS["postal_zone"],
        "country": address.get("country") or PLACEHOLDER_ADDRESS["country"],
    }

    return {
        "party_name": cust.get("customer_name") or doc.customer_name or doc.customer,
        "tin": cust.get("tax_id") or PLACEHOLDER_TIN,
        "email": cust.get("email_id") or doc.get("contact_email") or PLACEHOLDER_EMAIL,
        "telephone": _normalize_phone(cust.get("mobile_no") or doc.get("contact_mobile")) or PLACEHOLDER_PHONE,
        "business_description": cust.get("custom_nrs_business_description") or PLACEHOLDER_BUSINESS,
        "postal_address": postal_address,
    }


def _credit_note_reference(doc):
    original = doc.get("return_against")
    if not original:
        return None
    info = frappe.db.get_value(
        "Sales Invoice",
        original,
        ["custom_nrs_irn", "posting_date", "posting_time"],
        as_dict=True,
    )
    if not info or not info.get("custom_nrs_irn"):
        return None
    return {
        "original_irn": info["custom_nrs_irn"],
        "original_issue_date": _date(info.get("posting_date")),
    }


@frappe.whitelist()
def build_invoice_payload(sales_invoice_name):
    doc = frappe.get_doc("Sales Invoice", sales_invoice_name)
    return build_payload(doc)


def build_payload(doc):
    is_credit_note = bool(getattr(doc, "is_return", 0))
    # FIRS invoice type codes (from /reference-data/invoice-types):
    #   380 = Credit Note, 381 = Commercial Invoice (standard), 384 = Debit Note.
    invoice_type_code = "380" if is_credit_note else "381"
    currency = doc.currency or "NGN"

    customer = _customer_block(doc)
    real_tin = frappe.db.get_value("Customer", doc.customer, "tax_id")
    transaction_category = "B2B" if real_tin else "B2C"

    lines = []
    total_line_ext = 0.0
    total_tax = 0.0
    subtotals = {}

    for row in doc.items or []:
        line_ext = abs(flt(row.get("net_amount") or row.get("amount")))
        rate_each = abs(flt(row.get("net_rate") or row.get("rate")))
        qty = abs(flt(row.qty)) or 1
        cat_id, percent = _line_tax(row)
        cat_id = _normalize_tax_category(cat_id, percent)
        tax_amt = round(line_ext * percent / 100.0, 2)

        lines.append(
            {
                "description": row.get("description") or row.get("item_name") or row.get("item_code"),
                "hsn_code": _format_hsn(row.get("custom_nrs_hsn_code")),
                "product_category": row.get("item_group") or "",
                "invoiced_quantity": qty,
                "price_amount": rate_each,
                "base_quantity": 1,
                "price_unit": f"{currency} per {row.get('uom') or row.get('stock_uom') or 'unit'}",
                "discount_amount": abs(flt(row.get("discount_amount") or 0.0)),
                "line_extension_amount": round(line_ext, 2),
                "tax_amount": tax_amt,
                "total_amount": round(line_ext + tax_amt, 2),
            }
        )

        total_line_ext += line_ext
        total_tax += tax_amt
        if cat_id:
            bucket = subtotals.setdefault(cat_id, {"taxable": 0.0, "tax": 0.0, "percent": percent})
            bucket["taxable"] += line_ext
            bucket["tax"] += tax_amt

    total_line_ext = round(total_line_ext, 2)
    total_tax = round(total_tax, 2)

    tax_subtotals = [
        {
            "taxable_amount": round(v["taxable"], 2),
            "tax_amount": round(v["tax"], 2),
            "tax_category_id": cat_id,
            "tax_percent": v["percent"],
        }
        for cat_id, v in subtotals.items()
    ]
    tax_total_entry = {"tax_amount": total_tax}
    if tax_subtotals:
        tax_total_entry["tax_subtotals"] = tax_subtotals

    payload = {
        "invoice_type": "STANDARD",
        "transaction_category": transaction_category,
        "document_identifier": doc.name,
        "issue_date": _date(doc.posting_date),
        "issue_time": _time(doc.get("posting_time")),
        "invoice_type_code": invoice_type_code,
        "document_currency_code": currency,
        "tax_currency_code": currency,
        "invoice_lines": lines,
        "legal_monetary_total": {
            "line_extension_amount": total_line_ext,
            "tax_exclusive_amount": total_line_ext,
            "tax_inclusive_amount": round(total_line_ext + total_tax, 2),
            "payable_amount": round(total_line_ext + total_tax, 2),
        },
        "tax_total": [tax_total_entry],
    }

    if doc.get("due_date"):
        payload["due_date"] = _date(doc.due_date)
    note = (doc.get("remarks") or "").strip()
    if note and note.lower() != "no remarks":
        payload["note"] = note

    customer_id = frappe.db.get_value("Customer", doc.customer, "custom_nrs_customer_id")
    if customer_id:
        payload["customer_id"] = customer_id
    else:
        payload["accounting_customer_party"] = customer

    if is_credit_note:
        ref = _credit_note_reference(doc)
        if ref:
            payload["cancel_references"] = [ref]

    return payload
