app_name = "nrs_compliance"
app_title = "NRS Compliance"
app_publisher = "Osama Siddiqui"
app_description = "Nigeria Revenue Service (FIRS) e-invoicing compliance for ERPNext"
app_email = "osama.siddiqui2017@gmail.com"
app_license = "mit"
app_icon = "octicon octicon-briefcase"
app_color = "green"
required_apps = ["erpnext"]


add_to_apps_screen = [
    {
        "name": app_name,
        "logo": "/assets/nrs_compliance/images/logo.svg",
        "title": app_title,
        "route": "/app/nrs-compliance",
        "has_permission": "nrs_compliance.api.permissions.check_app_permission",
    }
]

# Document Events
# ---------------
# Scope: Sales Invoice only. A Credit Note is an ERPNext Sales Invoice with
# is_return = 1, so it flows through the same hooks (invoice_type_code 381).
# POS Invoice is intentionally NOT handled.
doc_events = {
    "Company": {
        "validate": "nrs_compliance.utils.sync_company_nrs_config",
    },
    "Sales Invoice": {
        "validate": "nrs_compliance.api.nrs_validation.validate_nrs_fields",
        "before_submit": "nrs_compliance.api.nrs_validation.validate_before_submit",
        "on_submit": "nrs_compliance.api.nrs_submission.submit_invoice_on_submit",
        "before_cancel": "nrs_compliance.api.nrs_validation.block_cancel_for_transmitted_invoice",
        "on_cancel": "nrs_compliance.api.nrs_validation.cleanup_nrs_queue_on_cancel",
    },
}

doctype_js = {
    "Sales Invoice": "public/js/sales_invoice.js",
    "Company": "public/js/company.js",
}

doctype_list_js = {
    "Sales Invoice": "public/js/sales_invoice_list.js",
}

# Scheduled Tasks
# ---------------
scheduler_events = {
    # Process the NRS queue every 15 minutes
    "cron": {
        "*/15 * * * *": ["nrs_compliance.api.nrs_queue.process_nrs_queue_scheduled"]
    },
}

# Custom fields that should be searchable
search_fields = {
    "Sales Invoice": ["custom_nrs_irn", "custom_nrs_status"],
}

# On app install / migrate
# ------------------------
after_install = "nrs_compliance.install.after_install"
after_migrate = "nrs_compliance.install.after_migrate"

# Backup hook - include NRS data in backups
include_in_backup = ["NRS Logs", "NRS Queue"]
