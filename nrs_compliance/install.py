import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def after_install():
    install_custom_fields()
    frappe.db.commit()


def after_migrate():
    install_custom_fields()


def install_custom_fields():
    """Create/refresh all custom fields this app adds to standard doctypes.

    Idempotent: create_custom_fields updates existing fields in place.
    """
    create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)


# Scope note: only Sales Invoice (and its return = Credit Note) is targeted.
# No POS Invoice fields are added.
CUSTOM_FIELDS = {
    "Company": [
        {
            "fieldname": "custom_nrs_tab",
            "fieldtype": "Tab Break",
            "label": "NRS E-Invoicing",
            "insert_after": "default_operating_cost_account",
        },
        {
            "fieldname": "custom_nrs_enabled",
            "fieldtype": "Check",
            "label": "Enable NRS E-Invoicing",
            "insert_after": "custom_nrs_tab",
            "default": "0",
        },
        {
            "fieldname": "custom_nrs_environment",
            "fieldtype": "Select",
            "label": "Environment",
            "options": "Sandbox\nProduction",
            "default": "Sandbox",
            "insert_after": "custom_nrs_enabled",
        },
        {
            "fieldname": "custom_nrs_api_base_url",
            "fieldtype": "Data",
            "label": "API Base URL",
            "default": "https://api.cryptwaresystemsltd.com",
            "insert_after": "custom_nrs_environment",
        },
        {
            "fieldname": "custom_nrs_column_break",
            "fieldtype": "Column Break",
            "insert_after": "custom_nrs_api_base_url",
        },
        {
            "fieldname": "custom_nrs_api_key",
            "fieldtype": "Password",
            "label": "NRS API Key (X-API-KEY)",
            "insert_after": "custom_nrs_column_break",
        },
        {
            "fieldname": "custom_nrs_supplier_tin",
            "fieldtype": "Data",
            "label": "Supplier TIN",
            "description": "Falls back to the Company's Tax ID when blank.",
            "insert_after": "custom_nrs_api_key",
        },
    ],
    "Customer": [
        {
            "fieldname": "custom_nrs_section",
            "fieldtype": "Section Break",
            "label": "NRS Compliance",
            "collapsible": 1,
            "insert_after": "tax_id",
        },
        {
            "fieldname": "custom_nrs_business_description",
            "fieldtype": "Data",
            "label": "Business Description",
            "insert_after": "custom_nrs_section",
        },
        {
            "fieldname": "custom_nrs_customer_column",
            "fieldtype": "Column Break",
            "insert_after": "custom_nrs_business_description",
        },
        {
            "fieldname": "custom_nrs_customer_id",
            "fieldtype": "Data",
            "label": "NRS Customer ID",
            "description": "Cryptware customer UUID. When set, the invoice references this customer by id instead of embedding party details.",
            "insert_after": "custom_nrs_customer_column",
        },
    ],
    "Sales Invoice": [
        {
            "fieldname": "custom_nrs_tab",
            "fieldtype": "Tab Break",
            "label": "NRS E-Invoicing",
            "insert_after": "remarks",
        },
        {
            "fieldname": "custom_submit_to_nrs",
            "fieldtype": "Check",
            "label": "Submit to NRS",
            "default": "0",
            "insert_after": "custom_nrs_tab",
        },
        {
            "fieldname": "custom_nrs_status",
            "fieldtype": "Select",
            "label": "NRS Status",
            "options": "\nPending\nValid\nInvalid\nError",
            "read_only": 1,
            "allow_on_submit": 1,
            "insert_after": "custom_submit_to_nrs",
        },
        {
            "fieldname": "custom_nrs_irn",
            "fieldtype": "Data",
            "label": "NRS IRN",
            "read_only": 1,
            "allow_on_submit": 1,
            "insert_after": "custom_nrs_status",
        },
        {
            "fieldname": "custom_nrs_column_break",
            "fieldtype": "Column Break",
            "insert_after": "custom_nrs_irn",
        },
        {
            "fieldname": "custom_nrs_datetime",
            "fieldtype": "Datetime",
            "label": "NRS Submission Time",
            "read_only": 1,
            "allow_on_submit": 1,
            "insert_after": "custom_nrs_column_break",
        },
        {
            "fieldname": "custom_nrs_qr",
            "fieldtype": "Small Text",
            "label": "NRS QR / Signed Data",
            "read_only": 1,
            "allow_on_submit": 1,
            "insert_after": "custom_nrs_datetime",
        },
        {
            "fieldname": "custom_nrs_response",
            "fieldtype": "Long Text",
            "label": "NRS Response",
            "read_only": 1,
            "allow_on_submit": 1,
            "insert_after": "custom_nrs_qr",
        },
    ],
    "Sales Invoice Item": [
        {
            "fieldname": "custom_nrs_hsn_code",
            "fieldtype": "Data",
            "label": "HSN Code",
            "fetch_from": "item_code.custom_nrs_hsn_code",
            "fetch_if_empty": 1,
            "insert_after": "item_tax_template",
        },
        {
            "fieldname": "custom_nrs_tax_category",
            "fieldtype": "Link",
            "label": "FIRS Tax Category",
            "options": "FIRS Tax Category",
            "fetch_from": "item_code.custom_nrs_tax_category",
            "fetch_if_empty": 1,
            "insert_after": "custom_nrs_hsn_code",
        },
    ],
    "Item": [
        {
            "fieldname": "custom_nrs_section",
            "fieldtype": "Section Break",
            "label": "NRS Compliance",
            "collapsible": 1,
            "insert_after": "item_group",
        },
        {
            "fieldname": "custom_nrs_hsn_code",
            "fieldtype": "Data",
            "label": "HSN Code",
            "insert_after": "custom_nrs_section",
        },
        {
            "fieldname": "custom_nrs_item_column",
            "fieldtype": "Column Break",
            "insert_after": "custom_nrs_hsn_code",
        },
        {
            "fieldname": "custom_nrs_tax_category",
            "fieldtype": "Link",
            "label": "FIRS Tax Category",
            "options": "FIRS Tax Category",
            "insert_after": "custom_nrs_item_column",
        },
        {
            "fieldname": "custom_nrs_service_code",
            "fieldtype": "Data",
            "label": "FIRS Service Code",
            "insert_after": "custom_nrs_tax_category",
        },
    ],
}
