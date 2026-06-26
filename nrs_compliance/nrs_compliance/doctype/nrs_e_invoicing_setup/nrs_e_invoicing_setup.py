import frappe
from frappe.model.document import Document


class NRSEInvoicingSetup(Document):
    pass


@frappe.whitelist()
def sync_reference_data():
    """Pull reference data (tax categories, etc.) from the Cryptware FIRS API."""
    from nrs_compliance.api.reference_data import sync_all_reference_data

    return sync_all_reference_data()


@frappe.whitelist()
def test_connection():
    """Verify the default Company's NRS API credentials."""
    from nrs_compliance.api.reference_data import test_connection as _test

    return _test()
