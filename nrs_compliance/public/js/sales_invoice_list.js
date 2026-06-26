frappe.listview_settings["Sales Invoice"] = frappe.listview_settings["Sales Invoice"] || {};

(function () {
    const existing = frappe.listview_settings["Sales Invoice"].onload;
    frappe.listview_settings["Sales Invoice"].onload = function (listview) {
        if (existing) existing(listview);

        listview.page.add_action_item(__("Submit to NRS"), () => {
            const names = listview.get_checked_items(true);
            if (!names.length) {
                frappe.msgprint(__("Select at least one Sales Invoice."));
                return;
            }
            frappe.call({
                method: "nrs_compliance.api.nrs_submission.bulk_submit_invoices",
                args: { docnames: names },
                freeze: true,
                freeze_message: __("Queuing invoices for NRS..."),
                callback(r) {
                    const d = r.message || {};
                    frappe.msgprint({
                        title: __("NRS Submission"),
                        indicator: "blue",
                        message: d.message || __("Done."),
                    });
                    listview.refresh();
                },
            });
        });
    };
})();
