const NRS_RESULT_FIELDS = [
    "custom_nrs_status",
    "custom_nrs_irn",
    "custom_nrs_datetime",
    "custom_qr_code",
    "custom_qr_code_url",
    "custom_nrs_response",
];

frappe.ui.form.on("Sales Invoice", {
    onload(frm) {
        // A new Credit Note (Create > Return/Credit Note from a posted invoice):
        // auto-enable NRS submission and clear any NRS result fields carried over
        // from the original invoice.
        if (frm.is_new() && frm.doc.is_return && frm.doc.return_against) {
            if (!frm.doc.custom_submit_to_nrs) {
                frm.set_value("custom_submit_to_nrs", 1);
            }
            NRS_RESULT_FIELDS.forEach((f) => {
                if (frm.doc[f]) frm.set_value(f, null);
            });
        }
    },

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
