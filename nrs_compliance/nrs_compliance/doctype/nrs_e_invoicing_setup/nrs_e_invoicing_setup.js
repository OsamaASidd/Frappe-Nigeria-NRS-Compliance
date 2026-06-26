frappe.ui.form.on("NRS E-Invoicing Setup", {
    sync_reference_data(frm) {
        frappe.dom.freeze(__("Syncing reference data from FIRS..."));
        frappe.call({
            method: "nrs_compliance.nrs_compliance.doctype.nrs_e_invoicing_setup.nrs_e_invoicing_setup.sync_reference_data",
            callback(r) {
                frappe.dom.unfreeze();
                const d = r.message || {};
                if (d.success) {
                    frappe.msgprint({
                        title: __("Reference Data Synced"),
                        indicator: "green",
                        message: __("Tax categories synced: {0}", [d.tax_categories || 0]),
                    });
                    frm.reload_doc();
                } else {
                    frappe.msgprint({
                        title: __("Sync Failed"),
                        indicator: "red",
                        message: d.error || __("Unknown error"),
                    });
                }
            },
            error() {
                frappe.dom.unfreeze();
            },
        });
    },

    test_connection(frm) {
        frappe.call({
            method: "nrs_compliance.nrs_compliance.doctype.nrs_e_invoicing_setup.nrs_e_invoicing_setup.test_connection",
            freeze: true,
            freeze_message: __("Testing connection..."),
            callback(r) {
                const d = r.message || {};
                frappe.msgprint({
                    title: d.success ? __("Connection OK") : __("Connection Failed"),
                    indicator: d.success ? "green" : "red",
                    message: d.message || d.error || "",
                });
                frm.reload_doc();
            },
        });
    },
});
