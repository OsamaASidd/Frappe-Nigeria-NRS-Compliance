"""Thin HTTP client for the Cryptware FIRS E-Invoicing API.

Authentication uses the ``X-API-KEY`` header (per-Company key). Every method
returns a normalized result dict so callers never deal with raw responses:

    {
        "success": bool,
        "status_code": int | None,
        "data": dict,
        "error": str,
        "retryable": bool,
        "failure_type": str,
        "api_version": str,
    }
"""

import json

import requests
from requests.exceptions import RequestException

RETRYABLE_HTTP_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
NON_RETRYABLE_HTTP_STATUS_CODES = {400, 401, 403, 404, 409, 422}


def _classify(status_code):
    if status_code in NON_RETRYABLE_HTTP_STATUS_CODES:
        return "http_validation_error"
    return "http_error"


def _is_retryable(status_code):
    if status_code is None:
        return True
    if status_code in NON_RETRYABLE_HTTP_STATUS_CODES:
        return False
    return status_code in RETRYABLE_HTTP_STATUS_CODES or status_code >= 500


def _err(message, retryable=True, failure_type="config_error", status_code=None):
    return {
        "success": False,
        "status_code": status_code,
        "data": {},
        "error": message,
        "retryable": retryable,
        "failure_type": failure_type,
        "api_version": "",
    }


def _parse_response(resp):
    text = resp.text or ""
    try:
        data = resp.json() if text else {}
    except ValueError:
        data = {"raw": text}

    api_version = ""
    if isinstance(data, dict):
        api_version = str(data.get("apiVersion") or data.get("version") or "")

    status_code = resp.status_code
    if status_code >= 400:
        err = None
        if isinstance(data, dict):
            err = data.get("message") or data.get("error")
            if not err and data.get("errors") is not None:
                err = json.dumps(data.get("errors"))
        return {
            "success": False,
            "status_code": status_code,
            "data": data if isinstance(data, dict) else {"raw": text},
            "error": f"HTTP {status_code}: {err or text[:500]}",
            "retryable": _is_retryable(status_code),
            "failure_type": _classify(status_code),
            "api_version": api_version,
        }

    if not isinstance(data, dict):
        data = {"raw": text}
    return {
        "success": True,
        "status_code": status_code,
        "data": data,
        "error": "",
        "retryable": False,
        "failure_type": "",
        "api_version": api_version,
    }


class NRSClient:
    def __init__(self, base_url, api_key, verify_ssl=None, timeout=(10, 40)):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        if verify_ssl is None:
            import frappe

            verify_ssl = bool(frappe.conf.get("nrs_verify_ssl", True))
        self.verify_ssl = verify_ssl
        self.timeout = timeout

    def _headers(self, extra=None):
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Client": "ERPNext NRS Compliance",
        }
        if extra:
            headers.update({k: v for k, v in extra.items() if v is not None})
        return headers

    def _request(self, method, path, payload=None, extra_headers=None):
        if not self.base_url:
            return _err("NRS API Base URL is not configured on the Company.")
        if not self.api_key:
            return _err("NRS API Key (X-API-KEY) is not configured on the Company.")

        url = f"{self.base_url}{path}"
        try:
            resp = requests.request(
                method,
                url,
                json=payload,
                headers=self._headers(extra_headers),
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
        except RequestException as e:
            return _err(
                f"NRS HTTP connection error: {e}",
                retryable=True,
                failure_type="network_error",
            )
        except Exception as e:
            return _err(
                f"NRS request internal error: {e}",
                retryable=False,
                failure_type="unknown_error",
            )
        return _parse_response(resp)

    # --- Invoices -------------------------------------------------------
    def generate_invoice(self, payload, doc_ref=None):
        return self._request(
            "POST", "/invoice/generate", payload, {"X-Document-Name": str(doc_ref or "")}
        )

    def transmit(self, irn):
        return self._request("POST", f"/invoice/transmit/{irn}")

    def get_status(self, irn):
        return self._request("GET", f"/invoice/status/{irn}")

    def cancel_invoice(self, irn, reason=""):
        return self._request("PATCH", f"/invoice/{irn}/cancel", {"reason": reason})

    # --- Reference data -------------------------------------------------
    def get_reference(self, kind):
        return self._request("GET", f"/reference-data/{kind}")
