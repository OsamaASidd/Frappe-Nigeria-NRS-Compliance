# NRS Compliance — Company Configuration Guide

This guide lists **everything a client must configure in their ERPNext instance**
to transmit Sales Invoices and Credit Notes to the Nigeria Revenue Service (FIRS)
through the Cryptware FIRS E-Invoicing API, **after** the NRS Compliance app is
installed and **NRS E-Invoicing is enabled on the Company**.

> Scope: **Sales Invoice** and **Credit Note** only. A Credit Note is an ERPNext
> Sales Invoice with `is_return = 1`. POS Invoices are not handled.

---

## 0. Prerequisites (once per instance)

| # | Item | Notes |
|---|------|-------|
| 1 | NRS Compliance app installed | `bench --site <site> install-app nrs_compliance` |
| 2 | ERPNext **Scheduler enabled** | Required for the background NRS Queue to process. Check under **System Settings → Enable Scheduler**, or `bench --site <site> enable-scheduler`. |
| 3 | Outbound internet from the ERPNext server | The server must reach `preprod-api.cryptwaresystemsltd.com` (sandbox) and `api.cryptwaresystemsltd.com` (production) on port 443. |
| 4 | A Cryptware **API key** per environment | Generated from the Cryptware portal (or `POST /auth/api-keys`). Sandbox and production keys are different. |

---

## 1. Company — NRS E-Invoicing tab

Open **Company → (your company) → NRS E-Invoicing** tab and set:

| Field | Required | What to enter |
|-------|:--------:|---------------|
| **Enable NRS E-Invoicing** (`custom_nrs_enabled`) | ✅ | Tick to activate NRS for this company. |
| **Environment** (`custom_nrs_environment`) | ✅ | `Sandbox` for testing, `Production` when live. |
| **API Base URL** (`custom_nrs_api_base_url`) | auto | **Read-only** — set automatically from Environment:<br>• Sandbox → `https://preprod-api.cryptwaresystemsltd.com`<br>• Production → `https://api.cryptwaresystemsltd.com` |
| **NRS API Key (X-API-KEY)** (`custom_nrs_api_key`) | ✅ | Paste the Cryptware API key for the selected environment. |
| **Supplier TIN** (`custom_nrs_supplier_tin`) | optional | Your company's Taxpayer Identification Number. Falls back to the Company's **Tax ID** if left blank. |

> ⚠️ **Changing the Environment clears the API Key.** Because sandbox and
> production use different keys, switching Environment empties the API Key field
> (and re-points the Base URL). Re-paste the correct key for the new environment.

**Also confirm on the Company:**
- **Default Currency** = `NGN` (or the transaction currency you invoice in).
- **Tax ID** filled (used as the Supplier TIN fallback).

---

## 2. Reference data — FIRS Tax Categories

FIRS expects each invoice line's tax to reference a **tax category code**. The app
stores these in the **FIRS Tax Category** doctype and sends the code as
`tax_category_id` in the payload.

**Accepted `tax_category_id` values:**
`STANDARD_VAT`, `REDUCED_VAT`, `ZERO_VAT`, `STANDARD_GST`, `REDUCED_GST`, `ZERO_GST`.

**Set them up one of two ways:**

**A. Sync from FIRS** — open **NRS E-Invoicing Setup**, click **Test Connection**
(verifies the API key), then **Sync Reference Data** to pull categories from the API.

**B. Create manually** — **FIRS Tax Category → New** for at least:

| Tax Category ID | Category Name | Tax Rate (%) |
|-----------------|---------------|:------------:|
| `STANDARD_VAT`  | Standard VAT  | 7.5 |
| `ZERO_VAT`      | Zero-rated VAT | 0 |
| `EXEMPTED`      | VAT Exempt    | 0 |

> The app normalizes automatically: if a line's category isn't one of the accepted
> codes, it defaults to `STANDARD_VAT` when the rate > 0, else `ZERO_VAT`.

---

## 3. Tax accounts & template (for ERPNext accounting)

The NRS payload calculates line tax from the **FIRS Tax Category rate**. To keep
ERPNext's own accounting (GL, customer balances) consistent with what is reported
to FIRS, configure matching ERPNext tax:

1. **Chart of Accounts** — ensure a VAT liability account exists (e.g. `VAT 7.5% - <ABBR>`, type *Tax*).
2. **Sales Taxes and Charges Template** — e.g. **"Nigeria VAT 7.5%"** with one row:
   *On Net Total, 7.5%, account = the VAT account above*.
3. Apply this template on invoices (or set it as the company default) so the
   ERPNext grand total includes the same VAT the app reports to FIRS.

---

## 4. Item configuration

Open each sellable **Item → NRS Compliance** section:

| Field | Required | What to enter |
|-------|:--------:|---------------|
| **HSN Code** (`custom_nrs_hsn_code`) | ✅ | HS code in **`0000.00`** format (e.g. `9983.00` for services, `2701.90`). The app coerces other formats and falls back to `9983.00` if unusable. |
| **FIRS Tax Category** (`custom_nrs_tax_category`) | ✅ | Link to the FIRS Tax Category (e.g. `STANDARD_VAT`). |
| **FIRS Service Code** (`custom_nrs_service_code`) | optional | If the goods/service requires a specific FIRS service code. |

These values auto-fetch onto **Sales Invoice Item** rows (HSN Code and FIRS Tax
Category) but can be overridden per line.

---

## 5. Customer configuration

FIRS requires buyer party details. Open **Customer → NRS Compliance** section and
the standard contact/address fields:

| Field | Required | Notes |
|-------|:--------:|-------|
| **Tax ID** (`tax_id`) | ✅ for B2B | The buyer's TIN. **Its presence decides the transaction category:** TIN set → **B2B**, blank → **B2C**. |
| **Email** (`email_id`) | recommended | Must be a valid address; used in the party block. |
| **Mobile No** (`mobile_no`) | recommended | Normalized to E.164 (e.g. `+234…`). |
| **Primary Address** | recommended | Street, City, Postal Code, Country (ISO used from Country). |
| **Business Description** (`custom_nrs_business_description`) | optional | Short description of the buyer's business. |
| **NRS Customer ID** (`custom_nrs_customer_id`) | optional | Cryptware customer UUID; when set, the invoice references the customer by ID instead of embedding party details. |

> The app fills **placeholders** for any required party field left blank
> (TIN, email, phone, business description, address) so invoices still transmit —
> but real values are strongly recommended for correct FIRS records.

---

## 6. Posting a Sales Invoice to NRS

1. Create a **Sales Invoice** for the NRS-enabled company. Ensure each line has an
   **HSN Code** and **FIRS Tax Category** (auto-filled from the Item).
2. On the **NRS E-Invoicing** tab, tick **Submit to NRS** (`custom_submit_to_nrs`).
3. **Submit** the invoice.
   - With **Submit to NRS** ticked, it is automatically queued and transmitted in
     the background.
   - Or click **Post to NRS** (NRS button on the toolbar), or select invoices in
     the Sales Invoice list → **Actions → Submit to NRS**.
4. Once transmitted, these read-only fields populate on the invoice:

| Field | Meaning |
|-------|---------|
| **NRS Status** (`custom_nrs_status`) | `Valid` / `Invalid` / `Error` / `Pending` |
| **NRS IRN** (`custom_nrs_irn`) | FIRS Invoice Reference Number |
| **NRS Submission Time** (`custom_nrs_datetime`) | Timestamp |
| **NRS QR Code** (`custom_qr_code`) | Signed QR string |
| **NRS QR Code URL** (`custom_qr_code_url`) | QR image link |
| **NRS Response** (`custom_nrs_response`) | Full API response (JSON) |

**Monitoring:** track progress under **NRS Queue** (in-flight/retrying) and
**NRS Logs** (full request/response audit). Failed items retry automatically
(up to 5 attempts) via the scheduler.

> Once an invoice has an IRN it **cannot be cancelled** — issue a Credit Note instead.

---

## 7. Credit Notes

A Credit Note is a **Return** against a posted invoice:

1. Open the **original invoice** (it must already have an **IRN**).
2. **Create → Return / Credit Note** (`is_return = 1`, `return_against` = original).
3. Tick **Submit to NRS**, submit, and post it.

The app sends invoice type code `380` (Credit Note) with `cancel_references`
pointing at the original invoice's IRN.

> ⚠️ **Order matters:** always post the original invoice **first** (so it has an
> IRN), then post the Credit Note. Posting a Credit Note whose original has no IRN
> is rejected by FIRS.

---

## 8. Print format

A ready-made **NRS Sales Invoice** print format is included. On any invoice →
**Print → NRS Sales Invoice**. It shows the invoice, the **IRN**, status, and the
**QR code** image. (Optionally set it as the default print format for Sales Invoice.)

---

## 9. Go-live checklist

- [ ] Company: **Enable NRS**, **Environment = Production**, production **API Key**, **Tax ID / Supplier TIN**.
- [ ] Scheduler enabled; server can reach `api.cryptwaresystemsltd.com`.
- [ ] FIRS Tax Categories present (`STANDARD_VAT`, `ZERO_VAT`, …).
- [ ] ERPNext VAT template configured at the matching rate.
- [ ] All sellable Items have **HSN Code** + **FIRS Tax Category**.
- [ ] Customers have **TIN** (B2B), email, phone, address.
- [ ] Test one invoice end-to-end in **Sandbox** first, confirm **Valid** + IRN + QR.

---

## 10. Troubleshooting

| Symptom / API message | Cause & fix |
|-----------------------|-------------|
| `Network is unreachable` / connection error | Server has no outbound internet to the API host. Fix networking/firewall/proxy on the ERPNext server. |
| `Invalid email address` | Customer email missing/invalid. Set a valid **Email** on the Customer. |
| `HSN code must be in format 0000.00` | Item **HSN Code** wrong format. Use `0000.00` (e.g. `9983.00`). |
| `Invalid option … STANDARD_VAT / ZERO_VAT …` | Line's FIRS Tax Category isn't an accepted code. Use one of the accepted `tax_category_id` values. |
| `Cancel references are required for Credit Note` | A Credit Note was posted before its original had an IRN. Post the original first. |
| Invoice stuck in **NRS Queue** as Failed | Open **NRS Logs** for the error; fix the data; re-post (retries run automatically each scheduler cycle). |
| `API Key is not configured` | Set the **NRS API Key** on the Company (it is cleared when Environment changes). |

---

## Appendix — Custom fields added by the app

**Company:** `custom_nrs_enabled`, `custom_nrs_environment`, `custom_nrs_api_base_url` (read-only), `custom_nrs_api_key`, `custom_nrs_supplier_tin`
**Customer:** `custom_nrs_business_description`, `custom_nrs_customer_id`
**Item:** `custom_nrs_hsn_code`, `custom_nrs_tax_category`, `custom_nrs_service_code`
**Sales Invoice:** `custom_submit_to_nrs`, `custom_nrs_status`, `custom_nrs_irn`, `custom_nrs_datetime`, `custom_qr_code`, `custom_qr_code_url`, `custom_nrs_response`
**Sales Invoice Item:** `custom_nrs_hsn_code`, `custom_nrs_tax_category`

**Doctypes added:** NRS E-Invoicing Setup (Single), NRS Queue, NRS Logs, FIRS Tax Category.
