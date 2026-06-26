"""Sync FIRS reference data (tax categories, ...) into local doctypes."""

import frappe
from frappe.utils import flt, now_datetime


def _as_list(data):
    """Reference endpoints may return a list, or {data: [...]}, or {items: [...]}."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "items", "results", "tax_categories", "taxCategories"):
            value = data.get(key)
            if isinstance(value, list):
                return value
        # single object
        if data:
            return [data]
    return []


def _pick(row, *keys):
    for key in keys:
        if isinstance(row, dict) and row.get(key) not in (None, ""):
            return row[key]
    return None


def sync_tax_categories(company=None):
    from nrs_compliance.utils import get_nrs_client

    client = get_nrs_client(company)
    result = client.get_reference("tax-categories")
    if not result.get("success"):
        return {"success": False, "error": result.get("error"), "count": 0}

    rows = _as_list(result.get("data"))
    count = 0
    for row in rows:
        cat_id = _pick(row, "id", "tax_category_id", "code", "categoryId")
        if cat_id is None:
            continue
        cat_id = str(cat_id)
        values = {
            "category_name": _pick(row, "name", "category_name", "label", "title") or cat_id,
            "tax_rate": flt(_pick(row, "rate", "tax_rate", "percent", "tax_percent") or 0),
            "description": _pick(row, "description", "desc") or "",
            "is_active": 1,
        }
        if frappe.db.exists("FIRS Tax Category", cat_id):
            frappe.db.set_value("FIRS Tax Category", cat_id, values, update_modified=False)
        else:
            doc = frappe.new_doc("FIRS Tax Category")
            doc.tax_category_id = cat_id
            doc.update(values)
            doc.insert(ignore_permissions=True)
        count += 1

    frappe.db.commit()
    return {"success": True, "count": count}


@frappe.whitelist()
def sync_all_reference_data(company=None):
    tax = sync_tax_categories(company)
    try:
        setup = frappe.get_single("NRS E-Invoicing Setup")
        setup.tax_categories_retrieved = 1 if tax.get("success") else 0
        setup.reference_data_synced_at = now_datetime()
        setup.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        pass

    return {
        "success": bool(tax.get("success")),
        "tax_categories": tax.get("count", 0),
        "error": tax.get("error"),
    }


@frappe.whitelist()
def test_connection(company=None):
    from nrs_compliance.utils import get_nrs_client

    client = get_nrs_client(company)
    result = client.get_reference("tax-categories")
    ok = bool(result.get("success"))
    try:
        setup = frappe.get_single("NRS E-Invoicing Setup")
        setup.is_api_key_valid = 1 if ok else 0
        setup.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        pass

    return {
        "success": ok,
        "message": "Connection to the Cryptware FIRS API succeeded." if ok else None,
        "error": None if ok else (result.get("error") or "Connection failed"),
    }
