frappe.ui.form.on("Company", {
    custom_nrs_environment(frm) {
        nrs_set_base_url(frm);
    },
    refresh(frm) {
        if (!frm.doc.custom_nrs_api_base_url && frm.doc.custom_nrs_environment) {
            nrs_set_base_url(frm);
        }
    },
});

function nrs_set_base_url(frm) {
    const url =
        frm.doc.custom_nrs_environment === "Production"
            ? "https://api.cryptwaresystemsltd.com"
            : "https://preprod-api.cryptwaresystemsltd.com";
    frm.set_value("custom_nrs_api_base_url", url);
}
