"""Submit Sales Invoices / Credit Notes to the Cryptware FIRS API.

The on_submit hook only *queues* the document; the actual HTTP call happens in
the background worker (see ``nrs_queue``) so document submission stays fast and
resilient to FIRS downtime.
"""

import json
from time import perf_counter

import frappe
from frappe import _
from frappe.utils import cint, now

SUPPORTED_DOCTYPES = {"Sales Invoice"}


def _normalize_text(value):
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.casefold() in {"none", "null"} else text


def _extract_irn(data):
    """Pull the IRN out of a variety of plausible response shapes."""
    if not isinstance(data, dict):
        return ""
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    for key in ("irn", "IRN", "invoice_reference", "invoiceReference"):
        if payload.get(key):
            return str(payload[key])
    invoice = payload.get("invoice") if isinstance(payload.get("invoice"), dict) else {}
    for key in ("irn", "IRN"):
        if invoice.get(key):
            return str(invoice[key])
    return ""


def _extract_qr(data):
    if not isinstance(data, dict):
        return ""
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    for key in ("qr_code", "qrCode", "qr", "signed_qr", "signedQrCode"):
        if payload.get(key):
            return str(payload[key])
    return ""


# --- on_submit hook ----------------------------------------------------
def submit_invoice_on_submit(doc, method=None):
    """Queue the invoice for FIRS submission when 'Submit to NRS' is ticked."""
    if not getattr(doc, "custom_submit_to_nrs", 0):
        return

    from nrs_compliance.utils import is_nrs_enabled

    if not is_nrs_enabled(doc.company):
        frappe.msgprint(
            _("NRS E-Invoicing is not enabled on Company {0}; invoice was not queued.").format(doc.company),
            indicator="orange",
            alert=True,
        )
        return

    from nrs_compliance.api.nrs_queue import post_invoice_to_nrs

    try:
        result = post_invoice_to_nrs(doctype=doc.doctype, docname=doc.name)
        if result and result.get("success"):
            frappe.msgprint(
                _("Invoice has been queued for NRS submission."),
                title=_("Queued for NRS"),
                indicator="blue",
                alert=True,
            )
    except Exception as e:
        frappe.log_error(
            f"Failed to auto-queue {doc.name} for NRS: {e}", "NRS Auto Queue"
        )


# --- core submission ---------------------------------------------------
@frappe.whitelist()
def submit_single_invoice(doctype, docname, is_retry=False, retry_attempt=0):
    """Build the payload and POST it to FIRS. Returns a structured result.

    Called by the queue worker; does not persist fields itself (the worker does).
    """
    start = perf_counter()
    retry_attempt = max(0, cint(retry_attempt))

    if doctype not in SUPPORTED_DOCTYPES:
        return {
            "success": False,
            "status": "error",
            "error": f"Unsupported doctype for NRS: {doctype}",
            "retryable": False,
            "failure_type": "payload_error",
            "response": {},
        }

    try:
        doc = frappe.get_doc(doctype, docname)
    except Exception as e:
        return {
            "success": False,
            "status": "error",
            "error": f"{doctype} {docname} not found: {e}",
            "retryable": False,
            "failure_type": "document_error",
            "response": {},
        }

    if _normalize_text(getattr(doc, "custom_nrs_irn", "")):
        return {
            "success": True,
            "status": "already_submitted",
            "message": "Already submitted to NRS.",
            "response": _stored_response(doc),
            "retryable": False,
            "failure_type": "",
        }

    # 1. Build payload
    try:
        from nrs_compliance.api.build_nrs_payload import build_payload

        payload = build_payload(doc)
    except Exception as e:
        error = f"Unable to build NRS payload: {e}"
        response = {"status": "error", "error": error}
        log_submission(doctype, docname, {}, response, "Invalid", retry_attempt=retry_attempt,
                       processing_time=round((perf_counter() - start) * 1000, 2))
        return {
            "success": False,
            "status": "invalid",
            "error": error,
            "retryable": False,
            "failure_type": "payload_error",
            "response": response,
        }

    # 2. Submit
    from nrs_compliance.utils import get_nrs_client

    client = get_nrs_client(doc.company)
    api_result = client.generate_invoice(payload, doc_ref=doc.name)
    response = api_result.get("data") or {}
    status_code = api_result.get("status_code")
    processing_time = round((perf_counter() - start) * 1000, 2)

    if api_result.get("success"):
        irn = _extract_irn(response)
        log_submission(doctype, docname, payload, response, "Success",
                       response_status_code=status_code, retry_attempt=retry_attempt,
                       processing_time=processing_time, irn=irn,
                       api_version=api_result.get("api_version"))
        return {
            "success": True,
            "status": "valid",
            "message": "Submitted to NRS",
            "response": response,
            "irn": irn,
            "retryable": False,
            "failure_type": "",
        }

    # 3. Failure
    error = api_result.get("error") or "NRS submission failed"
    retryable = bool(api_result.get("retryable"))
    failure_type = api_result.get("failure_type") or "http_error"
    log_status = "Invalid" if failure_type == "http_validation_error" else "Error"
    log_submission(doctype, docname, payload, response or {"error": error}, log_status,
                   response_status_code=status_code, retry_attempt=retry_attempt,
                   processing_time=processing_time, api_version=api_result.get("api_version"),
                   validation_errors=error)
    return {
        "success": False,
        "status": "invalid" if log_status == "Invalid" else "error",
        "error": error,
        "response": response,
        "retryable": retryable,
        "failure_type": failure_type,
    }


def persist_response_fields(doctype, docname, result):
    """Write IRN/status/response back onto the invoice (used by the worker)."""
    try:
        response = result.get("response") if isinstance(result, dict) else {}
        irn = result.get("irn") or _extract_irn(response)
        if result.get("success"):
            status = "Valid"
        elif result.get("status") == "invalid":
            status = "Invalid"
        else:
            status = "Error"

        values = {
            "custom_nrs_status": status,
            "custom_nrs_response": json.dumps(response, indent=2) if response else "",
        }
        if irn:
            values["custom_nrs_irn"] = irn
            values["custom_nrs_datetime"] = now()
        qr = _extract_qr(response)
        if qr:
            values["custom_nrs_qr"] = qr

        frappe.db.set_value(doctype, docname, values, update_modified=False)
    except Exception as e:
        frappe.log_error(
            f"Error persisting NRS response for {doctype} {docname}: {e}",
            "NRS Response Persistence",
        )


def _stored_response(doc):
    raw = getattr(doc, "custom_nrs_response", "")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return {}


def log_submission(document_type, document_name, payload, response, status,
                   response_status_code=None, retry_attempt=0, processing_time=None,
                   irn="", api_version="", validation_errors=""):
    try:
        log = frappe.new_doc("NRS Logs")
        log.update(
            {
                "document_type": document_type,
                "document_name": document_name,
                "request_payload": json.dumps(payload, indent=2) if payload else "",
                "response_data": json.dumps(response, indent=2) if response else "",
                "status": status,
                "submitted_at": now(),
                "irn": irn or _extract_irn(response),
                "response_status_code": str(response_status_code or ""),
                "retry_attempt": retry_attempt or 0,
                "processing_time": processing_time if processing_time is not None else 0,
                "api_version": api_version or "",
                "validation_errors": validation_errors or "",
            }
        )
        log.insert(ignore_permissions=True)
    except Exception as e:
        frappe.log_error(f"Error writing NRS Logs: {e}", "NRS Logging")


@frappe.whitelist()
def bulk_submit_invoices(docnames):
    """Queue several Sales Invoices for NRS submission."""
    if isinstance(docnames, str):
        try:
            docnames = json.loads(docnames)
        except Exception:
            docnames = [docnames]
    if not isinstance(docnames, list):
        frappe.throw(_("docnames must be a list or JSON array"))

    from nrs_compliance.api.nrs_queue import add_to_queue, process_queue

    queued, skipped = [], []
    for name in {str(n).strip() for n in docnames if n}:
        row = frappe.db.get_value(
            "Sales Invoice", name, ["docstatus", "custom_nrs_irn"], as_dict=True
        )
        if not row or row.docstatus != 1 or _normalize_text(row.custom_nrs_irn):
            skipped.append(name)
            continue
        result = add_to_queue("Sales Invoice", name, status="Pending")
        (queued if result.get("success") else skipped).append(name)

    if queued:
        process_queue(limit=len(queued))

    return {
        "queued_count": len(queued),
        "queued": queued,
        "skipped": skipped,
        "queue_route": "/app/nrs-queue",
        "message": _("Queued {0} invoice(s) for NRS; skipped {1}.").format(len(queued), len(skipped)),
    }
