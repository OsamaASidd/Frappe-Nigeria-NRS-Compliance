frappe.ui.form.on("Sales Invoice", {
    refresh(frm) {
        if (frm.doc.docstatus !== 1) return;
        if (!frm.doc.custom_submit_to_nrs) return;

        const irn = (frm.doc.custom_nrs_irn || "").trim();
        if (irn) {
            frm.dashboard.set_headline_alert(
                __("NRS IRN: {0} ({1})", [irn, frm.doc.custom_nrs_status || "Valid"]),
                "green"
            );
            return;
        }

        frm.add_custom_button(__("Post to NRS"), () => {
            frappe.call({
                method: "nrs_compliance.api.nrs_queue.post_invoice_to_nrs",
                args: { doctype: frm.doc.doctype, docname: frm.doc.name },
                freeze: true,
                freeze_message: __("Queuing for NRS..."),
                callback() {
                    frappe.show_alert({ message: __("Queued for NRS submission."), indicator: "blue" });
                },
            });
        }, __("NRS"));
    },
});
