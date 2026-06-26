import frappe

DEFAULT_BASE_URL = "https://api.cryptwaresystemsltd.com"


def get_default_company():
    company = frappe.defaults.get_global_default("company")
    if not company:
        company = frappe.db.get_single_value("Global Defaults", "default_company")
    return company


def _resolve_company(company=None):
    return company or get_default_company()


def get_nrs_base_url(company=None):
    company = _resolve_company(company)
    url = None
    if company:
        url = frappe.db.get_value("Company", company, "custom_nrs_api_base_url")
    return (url or DEFAULT_BASE_URL).rstrip("/")


def get_nrs_api_key(company=None):
    company = _resolve_company(company)
    if not company:
        return ""
    try:
        key = frappe.get_doc("Company", company).get_password(
            "custom_nrs_api_key", raise_exception=False
        )
        return key or ""
    except Exception:
        return ""


def is_nrs_enabled(company=None):
    company = _resolve_company(company)
    if not company:
        return False
    return bool(frappe.db.get_value("Company", company, "custom_nrs_enabled"))


def get_nrs_client(company=None):
    """Return a configured NRSClient for the given (or default) company."""
    from nrs_compliance.api.client import NRSClient

    company = _resolve_company(company)
    return NRSClient(
        base_url=get_nrs_base_url(company),
        api_key=get_nrs_api_key(company),
    )
