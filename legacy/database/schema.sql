PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS Users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS Parts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    part_number TEXT NOT NULL UNIQUE,
    description TEXT,
    draw_rev TEXT,
    specifications TEXT,
    powder_coating_details TEXT
);

CREATE TABLE IF NOT EXISTS PartParameters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    part_number TEXT NOT NULL,
    sl_no INTEGER NOT NULL,
    parameter TEXT,
    specification TEXT,
    special_char TEXT,
    method TEXT,
    FOREIGN KEY (part_number) REFERENCES Parts(part_number)
);

CREATE TABLE IF NOT EXISTS Settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    company_name TEXT,
    logo_path TEXT,
    inspector_signature_path TEXT,
    quality_signature_path TEXT,
    format_no TEXT,
    issue_date TEXT,
    doc_rev_no TEXT,
    rev_date TEXT
);

CREATE TABLE IF NOT EXISTS Customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS Invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number TEXT NOT NULL,
    upload_date TEXT NOT NULL,
    uploaded_by INTEGER NOT NULL,
    FOREIGN KEY (uploaded_by) REFERENCES Users(id)
);

CREATE TABLE IF NOT EXISTS InvoiceParts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    part_number TEXT NOT NULL,
    quantity INTEGER,
    FOREIGN KEY (invoice_id) REFERENCES Invoices(id)
);

CREATE TABLE IF NOT EXISTS FIRReports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    part_number TEXT NOT NULL,
    observation TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (invoice_id) REFERENCES Invoices(id)
);

---------------------------------------------------------------------
-- Master Part Data (normalized structure for internal inspection)
---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS parts_master (
    part_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    part_no      TEXT NOT NULL UNIQUE,
    drawing_rev  TEXT,
    description  TEXT
);

CREATE TABLE IF NOT EXISTS part_spec_data (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    part_id              INTEGER NOT NULL,
    parameter            TEXT NOT NULL,
    specification        TEXT,
    special_char         TEXT,
    method_of_inspection TEXT,
    FOREIGN KEY (part_id) REFERENCES parts_master(part_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS customer_complaint_parameters (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    part_id              INTEGER NOT NULL,
    parameter            TEXT NOT NULL,
    specification        TEXT,
    special_char         TEXT,
    method_of_inspection TEXT,
    FOREIGN KEY (part_id) REFERENCES parts_master(part_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS material_grade (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    part_id        INTEGER NOT NULL,
    material_grade TEXT NOT NULL,
    FOREIGN KEY (part_id) REFERENCES parts_master(part_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS surface_coating_master (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    part_id              INTEGER NOT NULL,
    parameter            TEXT NOT NULL,
    specification        TEXT,
    special_char         TEXT,
    method_of_inspection TEXT,
    FOREIGN KEY (part_id) REFERENCES parts_master(part_id) ON DELETE CASCADE ON UPDATE CASCADE
);

