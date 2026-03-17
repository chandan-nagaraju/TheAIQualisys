# FIR Automation System

A web application to automate **Final Inspection Report (FIR)** generation for manufacturing. Users upload Excel invoices, select parts, and generate printable/downloadable inspection reports with dimension parameters, customer complaint parameters, material grade, and surface coating sections—all driven by master data stored in the database.

---

## Table of Contents

1. [Overview](#overview)
2. [Tech Stack](#tech-stack)
3. [Project Structure](#project-structure)
4. [Database Schema](#database-schema)
5. [Application Flow](#application-flow)
6. [Building From Scratch (Blueprint)](#building-from-scratch-blueprint)
7. [Setup & Run](#setup--run)
8. [Configuration & Customization](#configuration--customization)
9. [Deployment Notes (e.g. ngrok)](#deployment-notes-eg-ngrok)

---

## Overview

- **Purpose:** Generate standardized Final Inspection Reports from invoice data and part master data.
- **Users:** ~10 internal users; session-based auth.
- **Inputs:** Excel (.xlsx / .xls) invoices; part master data (parts, dimensions, complaints, material, coating).
- **Outputs:** A4-formatted FIR (HTML) with optional PDF download; one report per part.

**Key features:**

- User signup/login with hashed passwords
- Customer/vendor master: select customer before upload; if only one, auto-selected
- Invoice upload: Excel parsed with flexible column mapping (Part Number, Description, Quantity, Invoice Number, Date)
- Extracted data table → select rows → inspection results
- Parts master: part number, description, drawing revision; per-part detail: dimension parameters (A), customer complaint parameters (B), material grade (C), surface coating (D)
- FIR preview page: header (logo, vendor, customer, report no, date, etc.), sections A–D tables, signatures, sampling plan; editable table; auto-fill measured values; PDF download
- Global settings: company name, logo, inspector/quality signatures, format no, issue date, doc rev no, rev date
- Quali_1 font for “Actual Measured Values” and “Remarks”: embedded as base64 so it works on all computers (no local install)

---

## Tech Stack

| Layer      | Technology |
|-----------|------------|
| Frontend  | HTML, CSS, Vanilla JavaScript |
| Backend   | Python 3, Flask |
| Database  | SQLite (v1); schema supports migration to PostgreSQL later |
| Excel     | pandas, openpyxl |
| PDF       | Client-side: html2pdf.js + html2canvas (in `fir_preview.html`) |

**Python dependencies:** See `requirements.txt` (Flask, Werkzeug, pandas, openpyxl, etc.).

---

## Project Structure

```
fir-automation/
├── app.py                 # Flask app: routes, auth, DB, Excel parsing, FIR preview + font embedding
├── requirements.txt       # Python dependencies
├── README.md              # This file
├── database/
│   ├── schema.sql         # Full DB schema (run on init)
│   └── fir.db             # SQLite DB (created at first run)
├── static/
│   ├── css/
│   │   └── main.css       # Global styles (nav, flash, tables, buttons)
│   └── fonts/
│       ├── README.txt    # Instructions for Quali_1 font files
│       └── Quali_1.ttf   # (optional) Placed by user; else embedded from app
├── templates/
│   ├── base.html         # Layout: header nav, flash messages, footer
│   ├── landing.html      # Home (redirect to dashboard if logged in)
│   ├── login.html        # Login form
│   ├── signup.html       # Signup form
│   ├── dashboard.html    # Links: Upload, Parts, Customers, Settings
│   ├── upload.html       # Excel file upload (and select customer if >1)
│   ├── extracted_table.html  # Show extracted rows; "Continue to inspection"
│   ├── inspection.html   # Select rows for FIR; submit to results
│   ├── inspection_results.html  # Table with "Preview FIR" per part (links to fir-preview with query params)
│   ├── fir_preview.html  # Single-page FIR: header + A/B/C/D tables + signatures; JS builds DOM, auto-fill, PDF
│   ├── parts.html        # List parts_master; add/edit; link to part_detail
│   ├── part_detail.html  # Edit part: spec (A), CCP (B), material (C), coating (D); bulk paste / row add/delete
│   ├── customers.html    # List/add customers (vendor_code, name)
│   ├── select_customer.html  # Choose customer before upload (if multiple)
│   └── settings.html     # Company name, logo, inspector/quality signatures, format no, dates
└── uploads/              # Uploaded Excel + logo/signature images (created at run)
```

---

## Database Schema

- **Users** – id, name, email, password_hash  
- **Settings** – single row (id=1): company_name, logo_path, inspector_signature_path, quality_signature_path, format_no, issue_date, doc_rev_no, rev_date  
- **Customers** – id, vendor_code, name  
- **Invoices** – id, invoice_number, upload_date, uploaded_by (FK Users)  
- **InvoiceParts** – id, invoice_id, part_number, quantity  
- **FIRReports** – id, invoice_id, part_number, observation, created_at  
- **Parts** – legacy/supplementary: id, part_number, description, draw_rev, etc.  
- **PartParameters** – legacy: part_number, sl_no, parameter, specification, etc.  

**Master part data (normalized):**

- **parts_master** – part_id (PK), part_no (unique), drawing_rev, description  
- **part_spec_data** – dimension parameters (A): part_id (FK, CASCADE), parameter, specification, special_char, method_of_inspection  
- **customer_complaint_parameters** – (B): same structure, part_id FK  
- **material_grade** – (C): part_id FK, material_grade  
- **surface_coating_master** – (D): same as spec/CCP, part_id FK  

All child tables use `ON DELETE CASCADE ON UPDATE CASCADE` on `part_id`.

---

## Application Flow

1. **Landing** → Login or Sign up.
2. **Dashboard** → Upload Invoice | Parts | Customers | Settings.
3. **Customers:** Add vendor_code + name. If multiple customers, **Select customer** is required before upload; if one, auto-selected.
4. **Upload Invoice:** Choose Excel (.xlsx/.xls) → parse with column mapping → **Extracted table** (Part Number, Description, Quantity, Invoice Number, Date).
5. **Continue to inspection** → **Inspection** page: select which rows (parts) to include → Submit.
6. **Inspection results:** For each part, show Part Number, Description, Draw Rev, Quantity, Invoice No, Date; **Preview FIR** opens `/fir-preview?partName=...&description=...&drawRev=...&invoiceNo=...&vendorCode=...&customer=...&reportNo=...&reportDate=...&quantity=...&sampleSize=...&noOfParams=...`.
7. **FIR Preview:** Single HTML page; JS reads query params and `spec_data`, `ccp_data`, `material_data`, `coating_data` (injected from backend). Builds header table (logo, vendor, customer, report no, date, part no, lot qty, invoice no, description, sample size, draw rev), then sections A, B, C, D, then signatures and sampling plan. User can edit cells, click “Auto-fill measured values”, then “Download PDF”. Quali_1 font is embedded as base64 so it works on all computers.
8. **Parts:** List/add/edit parts (part_no, description, drawing_rev). Click part → **Part detail:** edit A (dimension), B (complaints), C (material), D (coating); bulk paste and row add/delete supported.
9. **Settings:** Company name, logo image, inspector/quality signatures, format no, issue date, doc rev no, rev date. Stored in `Settings` and used in FIR header and signature blocks.

**Sample size rule (in app.py, inspection_results):**  
- Quantity ≤ 0 → blank; 1–5 → 2; 6–10 → 3; >10 → 5.

---

## Building From Scratch (Blueprint)

Use this section to rebuild the project if the codebase is lost.

### 1. Environment

- Python 3.8+
- Virtual environment recommended: `python -m venv venv` then activate and `pip install -r requirements.txt`.

### 2. Folder layout

Create:

- `fir-automation/`
  - `app.py`
  - `requirements.txt`
  - `database/` (empty; `schema.sql` and `fir.db` go here)
  - `static/css/main.css`
  - `static/fonts/` (optional: `Quali_1.ttf` or `.woff2`/`.woff`)
  - `templates/` (all HTML files listed above)
  - `uploads/` (created by app if missing)

### 3. Database

- Create `database/schema.sql` with the full schema (Users, Settings, Customers, Invoices, InvoiceParts, FIRReports, Parts, PartParameters, parts_master, part_spec_data, customer_complaint_parameters, material_grade, surface_coating_master) and `PRAGMA foreign_keys = ON`.
- In `app.py`, `init_db()` must: create `database/` dir, connect to `database/fir.db`, run `schema.sql`, then run any lightweight migrations (e.g. `ALTER TABLE ... ADD COLUMN ...` for existing installs).

### 4. Flask app (app.py)

- `create_app()`: create Flask app; set `SECRET_KEY`, `UPLOAD_FOLDER`; ensure `database/` and `uploads/` exist; call `init_db()`.
- Helpers: `get_db_connection()`, `get_settings()`, `current_user()`, `login_required` decorator.
- Context processor: inject `current_year`, `settings`.
- Routes:
  - `/` → landing (redirect to dashboard if logged in).
  - `/signup`, `/login`, `/logout` (session, password hash via Werkzeug).
  - `/dashboard` (login_required).
  - `/upload` (or `/upload-invoice`): if no customers, redirect to customers; if multiple customers and no `current_customer_id` in session, redirect to select-customer; on POST: save Excel, read with pandas, normalize columns via a mapping (part number, description, quantity, invoice number, date), store rows in `session['extracted_rows']`, render extracted table.
  - `/inspection`: GET show extracted rows; POST save `session['selected_rows']`, redirect to inspection results.
  - `/inspection/results`: load selected rows; for each part resolve `parts_master` for draw_rev and param count; compute sample_size by quantity; load current customer from session; render table with “Preview FIR” links.
  - `/customers`: list/add customers (vendor_code, name).
  - `/select-customer`: list customers; POST set `session['current_customer_id']`, redirect to upload.
  - `/parts`: list parts_master; POST add/update by part_no (and part_id for edit).
  - `/parts/<part_id>`: part detail; POST handle section saves (spec, ccp, material, coating) and bulk saves; load spec_rows, ccp_rows, material_rows, coating_rows; render part_detail.
  - `/settings`: GET/POST single row Settings (id=1); handle file uploads for logo, inspector_signature, quality_signature; save paths in DB.
  - `/uploads/<filename>`: send_from_directory for uploaded files (login_required).
  - `/fir-preview`: GET; `partName` from query; load spec_data, ccp_data, material_data, coating_data from parts_master children; **embed Quali_1 font**: read first available of `Quali_1.woff2`, `.woff`, `.ttf` from `static/fonts/`, base64 encode, pass `quali_font_data_uri` and `quali_font_format` to template; render `fir_preview.html` with spec_data, ccp_data, material_data, coating_data, quali_font_data_uri, quali_font_format.

### 5. Excel column mapping

In upload route, build a dict mapping lowercase header names to canonical names, e.g. `"part number"` → `"Part Number"`, `"description"` → `"Description"`, `"qty"` / `"quantity"` → `"Quantity"`, `"invoice no"` → `"Invoice Number"`, `"date"` → `"Date"`. Rename columns, reindex to display columns, fillna(""), store in session.

### 6. FIR preview page (fir_preview.html)

- Backend injects: `spec_data`, `ccp_data`, `material_data`, `coating_data` (lists of dicts), and `quali_font_data_uri`, `quali_font_format`.
- Page is mostly one big script: read query params (partName, description, drawRev, invoiceNo, vendorCode, customer, reportNo, reportDate, quantity, sampleSize, noOfParams); output script tags that set JS arrays from Jinja (e.g. `FIR_SPEC_DATA = {{ spec_data | tojson }}`).
- Build HTML string: report container; header table (logo cell with id, title, doc info cell); section A (Dimension Parameters) table with Sl No, Parameter, Specification, Special Char., Method, Actual Measured Values (5 cols), Remarks; section B (Customer Complaints) same structure; section C (Material Grade) table; section D (Surface Coating) same as A/B; signatures section (inspector, quality head, status Accepted/Rejected, sampling plan).
- After build, set `#companyCode` innerHTML from globalSettings (logo img, company name); set doc info from settings; set signature img src from settings.
- Implement “Auto-fill measured values”: for each data row, read specification and method; if “VISUAL”, fill “OK”; else parse numeric tolerance (e.g. ±, min–max), generate random value in range, fill actual columns and set Remarks to “OK”/“Not OK”. Use Quali_1 for actual/remarks. Update “Accepted”/“Rejected” visibility from remarks.
- PDF download: use html2pdf.js (with html2canvas); add class to body during generate; use CSS page-break and avoid extra blank pages; optional scale 2 for clarity.
- CSS: @font-face for Quali_1: if `quali_font_data_uri` present, use it as first `src` with correct format; then local and url() fallbacks. Style header table, data tables, section titles, signature cells, status buttons, inputs (method-input, special-char-input, actual-value, remarks-value).

### 7. Part detail (part_detail.html)

- Four sections with tables; each has “Add one row” and optional bulk paste; save all / delete row (X) per section. Field names match DB: spec_param, spec_spec, spec_char, spec_method; ccp_*, material_grade, coat_*.

### 8. Base template (base.html)

- Nav: if logged in, Dashboard, Upload Invoice, Logout; else Home, Login, Sign up. Flash messages above `{% block content %}`.

### 9. Static assets

- `main.css`: layout (top bar, page main, footer), flash styles, table wrapper, buttons.
- Quali_1: place `.ttf` (or `.woff2`/`.woff`) in `static/fonts/` for fallback; app embeds it so other computers don’t need the font installed.

### 10. Run

- `python app.py` or `flask run` (with `FLASK_APP=app:app` if needed). App runs `create_app()` and `init_db()`; open `/` and sign up, then follow flow.

---

## Setup & Run

```bash
cd fir-automation
python -m venv venv
# Activate venv: Windows `venv\Scripts\activate`, Unix `source venv/bin/activate`
pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:5000/`. Create an account, add at least one customer, add parts and their detail (A/B/C/D), then upload an Excel invoice and go through inspection → results → Preview FIR.

---

## Configuration & Customization

- **Excel columns:** Edit the `column_mapping` dict in `app.py` (upload route) to add more Excel header variants.
- **Sample size rule:** In `inspection_results`, adjust the quantity thresholds (e.g. 1–5 → 2, 6–10 → 3, >10 → 5).
- **FIR layout:** Edit `fir_preview.html` (header cols, section titles, column widths, CSS).
- **Quali font:** Put `Quali_1.ttf` (or woff2/woff) in `static/fonts/`; the app embeds it so it works on all computers.

---

## Deployment Notes (e.g. ngrok)

- For access from other computers (e.g. via ngrok), run Flask as usual and expose with ngrok. The FIR page uses **embedded base64 font** for Quali_1, so no extra font request is needed and the font displays on all clients.
- Set `SECRET_KEY` via environment in production. Ensure `uploads/` and `database/` are writable and backed up.
- For production, use a WSGI server (e.g. Gunicorn) and optionally HTTPS; static files and uploads are served by Flask (or configure nginx to serve `static/` and `uploads/`).

---

## License & Support

Internal use. Adjust schema, routes, and templates as needed for your organization. This README is the blueprint to rebuild the FIR Automation System from scratch if the project files are ever lost or deleted.
