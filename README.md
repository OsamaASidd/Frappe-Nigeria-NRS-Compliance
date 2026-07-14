# NRS Compliance

Nigeria Revenue Service (FIRS) e-invoicing compliance for ERPNext / Frappe v15.

This app integrates ERPNext with the **Cryptware FIRS E-Invoicing API**
(`https://api.cryptwaresystemsltd.com`) so that **Sales Invoices** and
**Credit Notes** are transmitted to the FIRS Exchange for IRN issuance and
validation.

> Scope: **Sales Invoice** and **Credit Note** only. A Credit Note is an
> ERPNext Sales Invoice with `is_return = 1` (invoice type code `381`).
> POS Invoices are **not** handled by this app.

## Features

- Per-Company credentials (API base URL + `X-API-KEY`), so each company posts
  under its own FIRS organisation.
- Asynchronous, retrying submission pipeline (**NRS Queue**) with full audit
  trail (**NRS Logs**).
- Maps ERPNext Sales Invoices to the FIRS `/invoice/generate` payload
  (`invoice_lines`, `tax_total`, `legal_monetary_total`, customer party).
- Credit Notes carry `cancel_references` pointing at the original invoice IRN.
- Reference-data sync (tax categories, etc.) into **FIRS Tax Category**.

## Installation

```bash
bench get-app https://github.com/OsamaASidd/Frappe-Nigeria-NRS-Compliance.git
bench --site <your-site> install-app nrs_compliance
```

## Configuration

1. Open the **Company** form → **NRS E-Invoicing** tab.
2. Tick **Enable NRS E-Invoicing**, choose the **Environment** (Sandbox or
   Production), and set the **API Key**. The API base URL is derived from the
   environment automatically:
   - Sandbox → `https://preprod-api.cryptwaresystemsltd.com`
   - Production → `https://api.cryptwaresystemsltd.com`
3. From **NRS E-Invoicing Setup**, click **Sync Reference Data** to pull tax
   categories and other lookups.
4. On a Sales Invoice, tick **Submit to NRS** and submit the document — it is
   queued and transmitted in the background. The issued **IRN** and status are
   written back onto the invoice.

## Authentication

Authentication uses the `X-API-KEY` header. Generate the key from the Cryptware
portal (or `POST /auth/api-keys`) and paste it into the Company's NRS tab.

## License

MIT
