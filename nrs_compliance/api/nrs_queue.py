"""Asynchronous, retrying submission queue for NRS (Sales Invoice / Credit Note).

A single item is processed at a time for deterministic ordering. Successful and
exhausted items are removed; retryable failures back off to the next scheduler
run.
"""

import frappe
from frappe.utils import cint, now, now_datetime, add_to_date

DEFAULT_MAX_RETRIES = 5
STUCK_PROCESSING_TIMEOUT_MINUTES = 30
SUPPORTED_DOCUMENT_TYPES = {"Sales Invoice"}
NON_RETRYABLE_FAILURE_TYPES = {"payload_error", "http_validation_error", "business_invalid"}


def _is_already_submitted(doctype, docname):
    irn = frappe.db.get_value(doctype, docname, "custom_nrs_irn")
    return bool((irn or "").strip())


def _has_processing():
    return bool(frappe.db.exists("NRS Queue", {"status": "Processing"}))


def _sync_retry_fields(doc):
    doc.remaining_retries = max(0, DEFAULT_MAX_RETRIES - cint(doc.retry_count))


def _enqueue(queue_item_name):
    frappe.enqueue(
        "nrs_compliance.api.nrs_queue._process_single_queue_item",
        queue="short",
        queue_item_name=queue_item_name,
        enqueue_after_commit=True,
        job_id=f"nrs_queue_item::{queue_item_name}",
        deduplicate=True,
    )


def _claim_and_start(queue_item_name):
    claimed = frappe.db.get_value(
        "NRS Queue",
        {"name": queue_item_name, "status": "Pending"},
        "name",
        for_update=True,
        skip_locked=True,
    )
    if not claimed:
        return False
    frappe.db.set_value("NRS Queue", claimed, {"status": "Processing", "next_retry_at": None})
    _enqueue(claimed)
    return True


def _kick():
    try:
        process_queue(limit=1)
    except Exception as e:
        frappe.log_error(f"NRS queue kick error: {e}", "NRS Queue Kick")


@frappe.whitelist()
def add_to_queue(doctype, docname, status="Pending", force_immediate=False):
    docstatus = frappe.db.get_value(doctype, docname, "docstatus")
    if docstatus is None:
        frappe.throw(f"Cannot queue {doctype} '{docname}': it does not exist.")
    if docstatus != 1:
        frappe.throw(f"Cannot queue {doctype} '{docname}': only submitted documents can be sent to NRS.")
    if _is_already_submitted(doctype, docname):
        frappe.throw(f"{doctype} '{docname}' already has an NRS IRN.")

    existing = frappe.db.exists("NRS Queue", {"document_type": doctype, "document_name": docname})
    if existing:
        doc = frappe.get_doc("NRS Queue", existing)
        if doc.status == "Failed":
            doc.status = "Pending"
            doc.next_retry_at = now_datetime()
            doc.error_message = ""
        elif doc.status == "Pending" and force_immediate:
            doc.next_retry_at = now_datetime()
        _sync_retry_fields(doc)
        doc.save(ignore_permissions=True)
        return {"success": True, "queue_id": doc.name, "state": "requeued"}

    doc = frappe.new_doc("NRS Queue")
    doc.document_type = doctype
    doc.document_name = docname
    doc.status = "Pending"
    doc.retry_count = 0
    doc.created_at = now()
    doc.next_retry_at = now_datetime()
    _sync_retry_fields(doc)
    doc.insert(ignore_permissions=True)
    return {"success": True, "queue_id": doc.name, "state": "queued"}


@frappe.whitelist()
def post_invoice_to_nrs(doctype, docname):
    """Queue + immediately try to start processing one invoice."""
    if doctype not in SUPPORTED_DOCUMENT_TYPES:
        frappe.throw(f"Unsupported doctype for NRS posting: {doctype}")
    if _is_already_submitted(doctype, docname):
        return {"success": True, "state": "already_submitted"}

    result = add_to_queue(doctype, docname, status="Pending", force_immediate=True)
    if not result.get("success"):
        return {"success": False, "state": "error", "error": result.get("error")}

    if not _has_processing():
        _claim_and_start(result["queue_id"])
    _kick()
    return {"success": True, "state": "queued", "queue_id": result["queue_id"]}


@frappe.whitelist()
def process_queue(limit=50):
    limit = max(1, cint(limit) or 1)
    enqueued = 0
    try:
        while enqueued < limit:
            if _has_processing():
                break
            items = frappe.get_all(
                "NRS Queue",
                filters={"status": "Pending", "next_retry_at": ["<=", now_datetime()]},
                order_by="created_at ASC, name ASC",
                limit=1,
            )
            if not items:
                break
            if _claim_and_start(items[0].name):
                enqueued += 1
            else:
                continue
    except Exception as e:
        frappe.log_error(f"Error processing NRS queue: {e}", "NRS Queue")
    return {"enqueued_count": enqueued}


def _mark_retry_or_fail(doc, error_message, response=None, retryable=True):
    import json

    doc.retry_count = cint(doc.retry_count) + 1
    doc.last_retry_at = now()
    doc.error_message = error_message
    if response:
        doc.nrs_response = json.dumps(response, indent=2)
    doc.status = "Failed"
    _sync_retry_fields(doc)
    if retryable and cint(doc.retry_count) < DEFAULT_MAX_RETRIES:
        doc.next_retry_at = now_datetime()
    else:
        doc.next_retry_at = None
    doc.save(ignore_permissions=True)


def _process_single_queue_item(queue_item_name):
    if not frappe.db.exists("NRS Queue", queue_item_name):
        return
    entry = frappe.get_doc("NRS Queue", queue_item_name)
    if entry.status != "Processing":
        return

    from nrs_compliance.api.nrs_submission import submit_single_invoice, persist_response_fields

    try:
        docstatus = frappe.db.get_value(entry.document_type, entry.document_name, "docstatus")
        if docstatus != 1:
            frappe.delete_doc("NRS Queue", queue_item_name, ignore_permissions=True, force=True)
            return

        retry_attempt = cint(entry.retry_count) + 1
        result = submit_single_invoice(
            entry.document_type, entry.document_name, is_retry=True, retry_attempt=retry_attempt
        )
        persist_response_fields(entry.document_type, entry.document_name, result)

        if result.get("success") or result.get("status") == "already_submitted":
            frappe.delete_doc("NRS Queue", queue_item_name, ignore_permissions=True, force=True)
            return

        failure_type = str(result.get("failure_type") or "").strip().lower()
        if not result.get("retryable", True) and failure_type in NON_RETRYABLE_FAILURE_TYPES:
            # Terminal business/validation failure: keep the Logs, drop the queue row.
            frappe.delete_doc("NRS Queue", queue_item_name, ignore_permissions=True, force=True)
            return

        _mark_retry_or_fail(
            entry,
            result.get("error") or "NRS submission failed",
            response=result.get("response"),
            retryable=bool(result.get("retryable", True)),
        )
    except Exception as e:
        frappe.log_error(f"Error executing NRS queue item {queue_item_name}: {e}", "NRS Queue Processing")
        try:
            _mark_retry_or_fail(entry, f"Exception: {e}", retryable=True)
        except Exception:
            pass
    finally:
        _kick()


def recover_stuck_and_retryable_items():
    now_dt = now_datetime()
    cutoff = add_to_date(now_dt, minutes=-STUCK_PROCESSING_TIMEOUT_MINUTES)

    for item in frappe.get_all("NRS Queue", filters={"status": "Processing", "modified": ["<=", cutoff]}):
        try:
            _mark_retry_or_fail(
                frappe.get_doc("NRS Queue", item.name),
                f"Recovered stuck item after {STUCK_PROCESSING_TIMEOUT_MINUTES} min",
                retryable=True,
            )
        except Exception as e:
            frappe.log_error(f"Error recovering stuck NRS item {item.name}: {e}")

    for item in frappe.get_all(
        "NRS Queue", filters={"status": "Failed", "next_retry_at": ["<=", now_dt]}
    ):
        try:
            doc = frappe.get_doc("NRS Queue", item.name)
            if cint(doc.retry_count) < DEFAULT_MAX_RETRIES:
                doc.status = "Pending"
                doc.next_retry_at = now_dt
                _sync_retry_fields(doc)
                doc.save(ignore_permissions=True)
        except Exception as e:
            frappe.log_error(f"Error recovering failed NRS item {item.name}: {e}")


def process_nrs_queue_scheduled():
    try:
        recover_stuck_and_retryable_items()
        process_queue(limit=1)
    except Exception as e:
        frappe.log_error(f"Error in scheduled NRS queue processing: {e}", "NRS Queue Scheduled")


@frappe.whitelist()
def retry_failed_items():
    now_dt = now_datetime()
    count = 0
    for item in frappe.get_all("NRS Queue", filters={"status": "Failed"}):
        doc = frappe.get_doc("NRS Queue", item.name)
        if cint(doc.retry_count) < DEFAULT_MAX_RETRIES:
            doc.status = "Pending"
            doc.next_retry_at = now_dt
            _sync_retry_fields(doc)
            doc.save(ignore_permissions=True)
            count += 1
    _kick()
    return {"retry_count": count}
