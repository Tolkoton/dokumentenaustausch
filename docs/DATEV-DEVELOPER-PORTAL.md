# DATEV Developer Portal — Reference for Claude Code

> **Source:** <https://developer.datev.de/en/products>
> **Compiled:** 2026-05-12
> **Status:** Starter pack. The portal is a JS-rendered SPA, so this document is an *index + concept reference* assembled from public sources. To fetch the full rendered content of each page, run the included `scrape-datev-docs.py` script.

---

## 1. What is DATEV?

DATEV eG is a German cooperative providing software and IT services used across Germany for **accounting, tax computation, payroll, and HR**. It is the de facto standard for tax consultants (Steuerberater) and a huge share of German SMEs.

DATEV's integration model is **fundamentally different from typical REST APIs**:

- Core accounting operations are **asynchronous, batch-based file processing** (you submit a file as a job, poll for status). They are **not** synchronous JSON request/response calls.
- Some niche products **do** offer REST endpoints (Cash Register Import / MeinFiskal, Document Management, etc.).
- Two parallel ecosystems exist:
  - **DATEV Unternehmen Online (DUO)** — cloud platform for companies to share receipts/invoices with their tax advisor. OAuth2.
  - **DATEV Rechnungswesen** — on-premise accounting software used by the tax advisor or in-house team. Account/password auth.
- Production access requires a **multi-step approval process** (DATEV Marketplace listing requires >25 active connections, customer interviews, strategic fit review).

---

## 2. Portal structure & URL patterns

The portal lives at `https://developer.datev.de/`. Available in `/en/` and `/de/`.

| Path                                                        | What's there                                       |
| ----------------------------------------------------------- | -------------------------------------------------- |
| `/en/products`                                              | Full catalog of API products                       |
| `/en/guides/interface-requirements`                         | Approval / certification requirements              |
| `/datev/platform/en/documentations`                         | Top-level docs (Data Services, file IFs, DATEVconnect) |
| `/datev/platform/en/online-apis`                            | Online APIs overview                               |
| `/datev/platform/en/desktop-apis`                           | DATEVconnect (LAN-only desktop APIs)               |
| `/en/product-detail/{product-slug}/{version}/overview`      | Per-product overview                               |
| `/en/product-detail/{product-slug}/{version}/documentation` | Per-product narrative docs                         |
| `/en/product-detail/{product-slug}/{version}/reference`     | Per-product OpenAPI reference (endpoints, schemas) |

Replace `en` with `de` for German.

---

## 3. Known API products (catalog)

This list was assembled from search-engine snippets. It is the right set to feed into the scraper script; the script will discover any newer additions.

### 3.1 Accounting (Bookkeeping)

| Product slug                     | Version | Purpose                                                                                                  |
| -------------------------------- | ------- | -------------------------------------------------------------------------------------------------------- |
| `accounting`                     | 1.7.4   | High-level accounting API (clients, fiscal years, accounts receivable/payable, etc.)                     |
| `accounting-clients`             | 2.0     | Client master records under the tax advisor (Mandantenstamm)                                             |
| `accounting-extf-files`          | 2.0     | Submit DATEV-Format EXTF files (the canonical Buchungsdaten format) for import. Base URL: `https://accounting-extf-files.api.datev.de/platform/v3/` |
| `accounting-documents`           | 2.0     | Upload/download receipts (Belege) tied to bookings. Base URL: `https://accounting-documents.api.datev.de/platform/v2/` |

### 3.2 HR / Payroll

| Product slug         | Version | Purpose                                                                              |
| -------------------- | ------- | ------------------------------------------------------------------------------------ |
| `hr-imports` (a.k.a. `hr:files`) | 2.0.0   | Upload payroll import files to DATEV LODAS / Lohn und Gehalt                         |
| `hr-payrollreports`  | 2.0.0   | Download payroll reports (PDF or ZIP). Sandbox `client-id = 455148-1`                |
| `eau-api` (`hr:eau`) | 1.0.0   | Elektronische Arbeitsunfähigkeits-Bescheinigung (electronic sick-leave certificates) |

### 3.3 Tax

| Product slug                  | Version | Purpose                                              |
| ----------------------------- | ------- | ---------------------------------------------------- |
| `my-tax-income-tax-documents-1` | 1     | Document exchange around income-tax declarations (MyTax) |

### 3.4 Master data & infrastructure

| Product slug                       | Version | Purpose                                       |
| ---------------------------------- | ------- | --------------------------------------------- |
| `client-master-data`               | 1.7.0   | Customer master data of DATEV members (paid API, special terms) |
| `document-management`              | 2.3.0   | DATEV Document Management (DMS / Dokumentenablage) — query, modify, save documents |
| `b4value-net-smarttransfer-inbound` | 1.2     | b4value.net Smart Transfer (inbound)         |

### 3.5 DATEVconnect (desktop / LAN APIs)

Documented under `/datev/platform/en/desktop-apis`. These run **inside the customer's LAN** against the DATEV desktop stack — no internet endpoint. Examples:

- Document Management (DMS) REST endpoints
- Functional self-test endpoints
- File-based interfaces (CSV / XML) for data export/import

---

## 4. Authentication

Three different auth schemes, depending on product family:

### 4.1 OAuth 2.0 + OpenID Connect (Online APIs / DUO)

Used by all `/platform/` cloud APIs.

- **Authorization Code Flow with PKCE** is the standard.
- Tokens are bearer tokens passed as `Authorization: Bearer <token>` headers.
- Scope per API product, granted by the user during consent.
- Refresh tokens enable autarkic (unattended) data exchange after first consent.

### 4.2 Account credentials (Rechnungswesen on-prem)

Username + password against the on-premise installation. For DUO additionally need Consultant Number (`Beraternummer`) and Client Number (`Mandantennummer`).

### 4.3 No auth / network ACL (DATEVconnect)

Desktop APIs are reachable only from inside the customer's LAN. Trust is established by network topology, not by tokens.

---

## 5. The standard batch workflow (cloud APIs)

This is the pattern you'll use for **any file-import API** (`accounting-extf-files`, `hr-imports`, `accounting-documents`, ...):

```text
1. PUT/POST  /clients/{client-id}/<resource>          → 202 Accepted + Location header
                                                        + Retry-After (seconds)

2. (wait Retry-After seconds — do NOT poll immediately)

3. GET       <Location URL>                           → 200 OK + job status
                                                        status ∈ { pending, success, error }

4. If status == "error" → read the structured error payload, do NOT mark as success.
```

**Hard rule from DATEV's certification:**
> Only if the response returns `result = success` may the transmission be displayed as successful in the 3rd-party app. Otherwise, error messages must be visualized to the user.

### Sandbox vs Production base URLs

| Environment | Base URL pattern                                   |
| ----------- | -------------------------------------------------- |
| Sandbox     | `https://<api-name>.api.datev.de/platform-sandbox/` |
| Production  | `https://<api-name>.api.datev.de/platform/`         |

Sandbox does only rough validation; no real processing, no persistence of results.

### Test data quirks

- Sandbox client-id for HR payrollreports: `455148-1`.
- For Buchungsdatenservice, **consultant 455148 / client 2** is wired to *always return an error* — use it to exercise your error-handling path.
- Retransmission of already-transferred data is also a required test case.

---

## 6. Key request / response shapes

### 6.1 `POST /clients/{client-id}/extf-files/import` (accounting-extf-files v3)

```bash
curl --request POST \
  --url https://accounting-extf-files.api.datev.de/platform/v3/clients/29098-100/extf-files/import \
  --header 'Authorization: Bearer REPLACE_BEARER_TOKEN' \
  --header 'Content-Type: text/plain;charset=ISO-8859-1' \
  --data-binary @EXTF_Buchungsstapel.csv
```

- `client-id` (path, required): `{Beraternummer}-{Mandantennummer}`, e.g. `29098-100`.
- File must be DATEV-Format **EXTF** (CSV-like, ISO-8859-1, very strict header).
- Response **202** with `Retry-After` and `Location` (redirect URL to poll for job status).
- If the file is infected or malicious → silently deleted.

### 6.2 `PUT /clients/{client-id}/documents/{guid}` (accounting-documents v2)

Preferred upload endpoint. The 3rd-party app generates its own GUID per document — guarantees idempotency (DUO will refuse a second upload with the same GUID).

```text
PUT https://accounting-documents.api.datev.de/platform-sandbox/v2/clients/{client-id}/documents/{guid}
```

Alternative `POST .../documents` (no GUID) — server assigns the GUID and returns it. Use only when client cannot generate a UUID.

### 6.3 hr-payrollreports — accept headers

The same path serves multiple content types — pick via `Accept`:

| `Accept`            | Returns                              |
| ------------------- | ------------------------------------ |
| `application/pdf`   | A single PDF report                  |
| `application/zip`   | All reports for the period bundled   |

Query params: `period` (required), `employee_number` (optional). Path param: `document_types`.

---

## 7. Certification / approval requirements ("MUST" rules)

These are mandatory for production access — captured from the public Interface-Requirements page:

- **MUST**: Use one of the two documented endpoints for querying permissions for a dataset. Show the client the company name and the consultant + client number.
- **MUST**: Transmitted (PUT/POST) and read (GET) requests must be in a *healthy ratio*. Spamming 30 GETs per successful POST is grounds for rejection.
- **MUST**: A file containing transaction data must be passed (Buchungsdatenservice).
- **MUST**: Visualize error responses to the user; never display a failed submission as successful.
- **SHOULD**: Do not poll job status immediately after the POST — wait at least `Retry-After` seconds.
- **MUST**: Before production approval, demonstrate processing of real data into a real test client with proper authorizations.
- **MARKETPLACE**: A DATEV Marketplace listing requires **>25 active connections**, customer interviews, and a strategic-fit review with DATEV.

---

## 8. Glossary (German terms you will encounter)

| German                       | English / meaning                                   |
| ---------------------------- | --------------------------------------------------- |
| Beraternummer                | Consultant number (tax advisor ID)                  |
| Mandant / Mandantennummer    | Client (of the tax advisor) / client number         |
| Buchung                      | Booking / journal entry                             |
| Buchungsstapel               | Batch of bookings                                   |
| Buchungsdatenservice         | Booking-data service (the EXTF import workflow)     |
| Beleg / Belege               | Receipt / receipts                                  |
| EXTF                         | External-format CSV (the canonical DATEV file type) |
| Kanzlei                      | Tax-advisor firm                                    |
| DUO — DATEV Unternehmen Online | Cloud platform (companies ↔ tax advisor)          |
| Rechnungswesen               | Accounting (the on-prem product family)             |
| LODAS / Lohn und Gehalt      | Payroll products                                    |
| Dokumentenablage / DMS       | Document Management                                 |
| eAU                          | Elektronische Arbeitsunfähigkeitsbescheinigung (electronic sick note) |

---

## 9. What to read first (recommended order)

1. **`/datev/platform/en/documentations`** — top-level architecture (Data Services vs file IFs vs DATEVconnect).
2. **`/en/guides/interface-requirements`** — the certification bar. Read this *before* coding so you don't have to retrofit later.
3. **`/datev/platform/en/online-apis`** — overview of the OAuth2 ecosystem.
4. **`/en/product-detail/accounting-extf-files/2.0/overview`** + `…/documentation` + `…/reference` — the canonical "batch import" workflow. Once you've internalized this, every other DATEV upload API looks the same.
5. **`/en/product-detail/accounting-documents/2.0/overview`** — pairs with extf-files (bookings reference documents by GUID).
6. The product you actually need (HR, Tax, MyTax, etc.).

---

## 10. Sources used to assemble this document

- <https://developer.datev.de/en/products> (catalog page)
- <https://developer.datev.de/datev/platform/en/documentations>
- <https://developer.datev.de/datev/platform/en/online-apis>
- <https://developer.datev.de/datev/platform/en/desktop-apis>
- <https://developer.datev.de/en/product-detail/accounting-extf-files/2.0/reference/...>
- <https://developer.datev.de/en/product-detail/accounting-extf-files/2.0/documentation/interface-requirements-for-buchungsdatenservice>
- <https://developer.datev.de/en/product-detail/hr-payrollreports/2.0.0/overview>
- Apideck DATEV API integration guide
- Chift DATEV API integration article
- Maesn DATEV integration documentation

**Caveat:** the live portal content may have moved on since this was compiled. Run `scrape-datev-docs.py` (next to this file) to refresh against the live site.
