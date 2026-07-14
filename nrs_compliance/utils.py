import frappe

# Cryptware FIRS API endpoints, selected by the Company's NRS environment.
SANDBOX_BASE_URL = "https://preprod-api.cryptwaresystemsltd.com"
PRODUCTION_BASE_URL = "https://api.cryptwaresystemsltd.com"


def get_default_company():
    company = frappe.defaults.get_global_default("company")
    if not company:
        company = frappe.db.get_single_value("Global Defaults", "default_company")
    return company


def _resolve_company(company=None):
    return company or get_default_company()


def get_nrs_base_url(company=None):
    """Resolve the API base URL from the Company's NRS environment.

    Sandbox    -> https://preprod-api.cryptwaresystemsltd.com
    Production -> https://api.cryptwaresystemsltd.com
    """
    company = _resolve_company(company)
    environment = None
    if company:
        environment = frappe.db.get_value("Company", company, "custom_nrs_environment")
    if (environment or "").strip().lower() == "production":
        return PRODUCTION_BASE_URL
    return SANDBOX_BASE_URL


def sync_company_nrs_config(doc, method=None):
    """Keep NRS config coherent with the selected Environment.

    - API Base URL (read-only) mirrors the environment.
    - The API key is cleared whenever the environment changes, since sandbox
      and production use different keys.
    """
    if not doc.meta.has_field("custom_nrs_api_base_url"):
        return
    env = (doc.get("custom_nrs_environment") or "").strip().lower()
    doc.custom_nrs_api_base_url = PRODUCTION_BASE_URL if env == "production" else SANDBOX_BASE_URL

    before = doc.get_doc_before_save() if not doc.is_new() else None
    if before and before.get("custom_nrs_environment") != doc.get("custom_nrs_environment"):
        doc.custom_nrs_api_key = ""


# Backwards-compatible alias (previous hook target).
set_company_base_url = sync_company_nrs_config


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
