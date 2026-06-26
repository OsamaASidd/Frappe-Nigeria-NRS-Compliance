"""Validation hooks for Sales Invoice / Credit Note NRS submission."""

import frappe
from frappe import _


def validate_nrs_fields(doc, method=None):
    """Light validation on save (no hard stops here)."""
    # Credit Notes (is_return) should reference the original invoice so we can
    # build cancel_references at submission time.
    if getattr(doc, "custom_submit_to_nrs", 0) and getattr(doc, "is_return", 0):
        if not doc.get("return_against"):
            frappe.msgprint(
                _("This Credit Note has no 'Return Against' invoice; NRS requires the original invoice IRN."),
                indicator="orange",
                alert=True,
            )


def validate_before_submit(doc, method=None):
    """Hard validation right before submit when NRS submission is requested."""
    if not getattr(doc, "custom_submit_to_nrs", 0):
        return

    from nrs_compliance.utils import is_nrs_enabled, get_nrs_api_key

    if not is_nrs_enabled(doc.company):
        frappe.throw(
            _("Enable NRS E-Invoicing on Company {0} (NRS E-Invoicing tab) before submitting to NRS.").format(doc.company)
        )
    if not get_nrs_api_key(doc.company):
        frappe.throw(
            _("Set the NRS API Key on Company {0} (NRS E-Invoicing tab) before submitting to NRS.").format(doc.company)
        )
    if not doc.items:
        frappe.throw(_("Cannot submit an invoice without items to NRS."))

    if getattr(doc, "is_return", 0):
        original = doc.get("return_against")
        if not original:
            frappe.throw(_("A Credit Note must reference the original invoice ('Return Against') for NRS."))
        original_irn = frappe.db.get_value("Sales Invoice", original, "custom_nrs_irn")
        if not original_irn:
            frappe.throw(
                _("The original invoice {0} has no NRS IRN yet, so this Credit Note cannot be submitted.").format(original)
            )


def block_cancel_for_transmitted_invoice(doc, method=None):
    """Once an invoice has an IRN it cannot be cancelled; issue a Credit Note instead."""
    if frappe.flags.get("nrs_ignore_cancel_block"):
        return
    irn = (getattr(doc, "custom_nrs_irn", "") or "").strip()
    status = (getattr(doc, "custom_nrs_status", "") or "").strip().lower()
    if irn or status == "valid":
        frappe.throw(
            _(
                "{0} has been transmitted to NRS (IRN {1}) and cannot be cancelled. "
                "Create a Credit Note (Return) against it instead."
            ).format(doc.name, irn or "issued")
        )


def cleanup_nrs_queue_on_cancel(doc, method=None):
    """Remove any pending/failed queue rows for a cancelled invoice."""
    try:
        rows = frappe.get_all(
            "NRS Queue",
            filters={"document_type": doc.doctype, "document_name": doc.name},
            pluck="name",
        )
        for name in rows:
            frappe.delete_doc("NRS Queue", name, ignore_permissions=True, force=True)
    except Exception as e:
        frappe.log_error(f"Error cleaning NRS Queue for {doc.name}: {e}", "NRS Queue Cleanup")
