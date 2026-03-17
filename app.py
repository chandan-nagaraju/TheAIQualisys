import base64
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    send_from_directory,
)
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "database" / "fir.db"
UPLOAD_FOLDER = BASE_DIR / "uploads"


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)

    # Ensure folders exist
    (BASE_DIR / "database").mkdir(parents=True, exist_ok=True)
    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

    init_db()

    # ---------- Database helpers ----------
    def get_db_connection():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def get_settings():
        conn = get_db_connection()
        row = conn.execute("SELECT * FROM Settings WHERE id = 1").fetchone()
        if not row:
            conn.execute("INSERT OR IGNORE INTO Settings (id, company_name) VALUES (1, '')")
            conn.commit()
            row = conn.execute("SELECT * FROM Settings WHERE id = 1").fetchone()
        conn.close()
        return dict(row)

    @app.context_processor
    def inject_now():
        return {
            "current_year": datetime.utcnow().year,
            "settings": get_settings(),
        }

    # ---------- Auth helpers ----------
    def current_user():
        user_id = session.get("user_id")
        if not user_id:
            return None
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM Users WHERE id = ?", (user_id,)).fetchone()
        conn.close()
        return user

    def login_required(view_func):
        from functools import wraps

        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not current_user():
                flash("Please log in to continue.", "warning")
                return redirect(url_for("login"))
            return view_func(*args, **kwargs)

        return wrapped

    # ---------- Routes ----------
    @app.route("/")
    def landing():
        if current_user():
            return redirect(url_for("dashboard"))
        return render_template("landing.html")

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")

            if not name or not email or not password:
                flash("All fields are required.", "danger")
                return render_template("signup.html", name=name, email=email)

            conn = get_db_connection()
            existing = conn.execute(
                "SELECT id FROM Users WHERE email = ?", (email,)
            ).fetchone()
            if existing:
                conn.close()
                flash("Email already registered. Please log in.", "warning")
                return redirect(url_for("login"))

            password_hash = generate_password_hash(password)
            conn.execute(
                "INSERT INTO Users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, password_hash),
            )
            conn.commit()
            conn.close()
            flash("Account created. Please log in.", "success")
            return redirect(url_for("login"))

        return render_template("signup.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")

            conn = get_db_connection()
            user = conn.execute(
                "SELECT * FROM Users WHERE email = ?", (email,)
            ).fetchone()
            conn.close()

            if not user or not check_password_hash(user["password_hash"], password):
                flash("Invalid email or password.", "danger")
                return render_template("login.html", email=email)

            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            flash("Logged in successfully.", "success")
            return redirect(url_for("dashboard"))

        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("You have been logged out.", "info")
        return redirect(url_for("landing"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        return render_template("dashboard.html", user=current_user())

    @app.route("/upload", methods=["GET", "POST"])
    @login_required
    def upload_invoice():
        # Ensure a customer/vendor is selected before upload
        conn = get_db_connection()
        customers = conn.execute("SELECT id, vendor_code, name FROM Customers").fetchall()
        conn.close()
        if not customers:
            flash("Please add at least one customer/vendor before uploading invoices.", "warning")
            return redirect(url_for("customers"))
        if len(customers) == 1 and "current_customer_id" not in session:
            session["current_customer_id"] = customers[0]["id"]
        if len(customers) > 1 and "current_customer_id" not in session and request.method == "GET":
            return redirect(url_for("select_customer"))

        if request.method == "POST":
            file = request.files.get("invoice_file")
            if not file or file.filename == "":
                flash("Please choose an Excel file to upload.", "warning")
                return redirect(request.url)

            # Basic extension check
            if not (
                file.filename.lower().endswith(".xlsx")
                or file.filename.lower().endswith(".xls")
            ):
                flash("Only .xlsx or .xls files are supported.", "danger")
                return redirect(request.url)

            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            safe_name = f"{timestamp}_{file.filename}"
            save_path = UPLOAD_FOLDER / safe_name
            file.save(save_path)

            try:
                df = pd.read_excel(save_path)
            except Exception as exc:  # pragma: no cover - simple error path
                flash(f"Failed to read Excel file: {exc}", "danger")
                return redirect(request.url)

            # Expect columns; we keep this flexible but map known names and your Excel headers
            column_mapping = {
                # Part number / material code
                "part number": "Part Number",
                "part_no": "Part Number",
                "part": "Part Number",
                "material code": "Part Number",

                # Description
                "description": "Description",
                "material desc.": "Description",
                "material desc": "Description",

                # Quantity
                "qty": "Quantity",
                "quantity": "Quantity",
                "advised qty": "Quantity",

                # Invoice / DC number
                "invoice no": "Invoice Number",
                "invoice": "Invoice Number",
                "invoice/dc no.": "Invoice Number",
                "invoice/dc no": "Invoice Number",

                # Date / DC date
                "date": "Date",
                "dc date": "Date",
            }

            normalized_cols = {}
            for col in df.columns:
                key = str(col).strip().lower()
                if key in column_mapping:
                    normalized_cols[col] = column_mapping[key]

            df_renamed = df.rename(columns=normalized_cols)

            display_cols = [
                "Part Number",
                "Description",
                "Quantity",
                "Invoice Number",
                "Date",
            ]
            extracted = df_renamed.reindex(columns=display_cols)

            # Fill NaNs with empty string for display
            extracted = extracted.fillna("")

            session["last_upload_file"] = safe_name
            table_data = extracted.to_dict(orient="records")
            # store in session so inspection flow can reuse
            session["extracted_rows"] = table_data
            session["extracted_columns"] = display_cols
            return render_template(
                "extracted_table.html",
                rows=table_data,
                columns=display_cols,
                filename=file.filename,
            )

        return render_template("upload.html")

    @app.route("/inspection", methods=["GET", "POST"])
    @login_required
    def inspection():
        rows = session.get("extracted_rows") or []
        columns = session.get("extracted_columns") or [
            "Part Number",
            "Description",
            "Quantity",
            "Invoice Number",
            "Date",
        ]
        if not rows:
            flash("No extracted data found. Please upload an invoice first.", "warning")
            return redirect(url_for("upload_invoice"))

        if request.method == "POST":
            # indices of selected rows
            selected_indices = request.form.getlist("rows")
            if selected_indices:
                selected_indices = [int(i) for i in selected_indices]
                selected_rows = [rows[i] for i in selected_indices if 0 <= i < len(rows)]
            else:
                selected_rows = rows

            session["selected_rows"] = selected_rows
            return redirect(url_for("inspection_results"))

        return render_template("inspection.html", rows=rows, columns=columns)

    @app.route("/inspection/results")
    @login_required
    def inspection_results():
        rows = session.get("selected_rows") or []
        conn = get_db_connection()
        # enrich with master data (draw_rev, parameter count) from parts_master / part_spec_data
        if rows:
            parts_rows = conn.execute(
                "SELECT part_id, part_no, drawing_rev FROM parts_master"
            ).fetchall()
            parts_by_no = {p["part_no"]: p for p in parts_rows}
            # pre-compute parameter counts per part_id from part_spec_data
            param_counts = {
                r["part_id"]: r["cnt"]
                for r in conn.execute(
                    "SELECT part_id, COUNT(*) as cnt FROM part_spec_data GROUP BY part_id"
                ).fetchall()
            }
            for r in rows:
                part_no = str(r.get("Part Number", "")).strip()
                part = parts_by_no.get(part_no)
                part_id = part["part_id"] if part else None
                r["draw_rev"] = part["drawing_rev"] if part else ""
                # derive sample size from quantity
                try:
                    qty_val = float(r.get("Quantity") or 0)
                except (TypeError, ValueError):
                    qty_val = 0
                if qty_val <= 0:
                    sample = ""
                elif qty_val <= 5:
                    sample = 2
                elif qty_val <= 10:
                    sample = 3
                else:
                    # for all quantities >10, including >100, use 5 samples
                    sample = 5
                r["sample_size"] = sample
                # number of parameters for this part (controls SL No rows)
                r["num_params"] = param_counts.get(part_id, 17) if part_id else 17
        # current customer/vendor for header data
        customer = None
        cid = session.get("current_customer_id")
        if cid is not None:
            customer = conn.execute(
                "SELECT id, vendor_code, name FROM Customers WHERE id = ?", (cid,)
            ).fetchone()
        conn.close()
        current_date = datetime.utcnow().date().isoformat()
        return render_template(
            "inspection_results.html",
            rows=rows,
            customer=customer,
            current_date=current_date,
        )

    @app.route("/customers", methods=["GET", "POST"])
    @login_required
    def customers():
        conn = get_db_connection()
        if request.method == "POST":
            vendor_code = request.form.get("vendor_code", "").strip()
            name = request.form.get("name", "").strip()
            if not vendor_code or not name:
                flash("Vendor code and customer name are required.", "danger")
            else:
                try:
                    conn.execute(
                        "INSERT INTO Customers (vendor_code, name) VALUES (?, ?)",
                        (vendor_code, name),
                    )
                    conn.commit()
                    flash("Customer added.", "success")
                except sqlite3.IntegrityError:
                    flash("Vendor code already exists.", "warning")
        rows = conn.execute(
            "SELECT id, vendor_code, name FROM Customers ORDER BY name"
        ).fetchall()
        conn.close()
        return render_template("customers.html", customers=rows)

    @app.route("/select-customer", methods=["GET", "POST"])
    @login_required
    def select_customer():
        conn = get_db_connection()
        rows = conn.execute(
            "SELECT id, vendor_code, name FROM Customers ORDER BY name"
        ).fetchall()
        conn.close()
        if not rows:
            flash("Please add a customer first.", "warning")
            return redirect(url_for("customers"))
        if request.method == "POST":
            selected_id = request.form.get("customer_id")
            if selected_id:
                session["current_customer_id"] = int(selected_id)
                flash("Customer selected for this session.", "info")
                return redirect(url_for("upload_invoice"))
        return render_template("select_customer.html", customers=rows)

    @app.route("/parts", methods=["GET", "POST"])
    @login_required
    def parts():
        """Simple CRUD for parts_master (high-level fields only)."""
        conn = get_db_connection()
        if request.method == "POST":
            part_id = request.form.get("part_id", "").strip()
            part_no = request.form.get("part_no", "").strip()
            description = request.form.get("description", "").strip()
            drawing_rev = request.form.get("drawing_rev", "").strip()
            if not part_no:
                flash("Part number is required.", "danger")
            elif part_id and part_id.isdigit():
                # Edit existing part by part_id
                conn.execute(
                    "UPDATE parts_master SET part_no = ?, description = ?, drawing_rev = ? WHERE part_id = ?",
                    (part_no, description, drawing_rev, int(part_id)),
                )
                conn.commit()
                flash("Part updated.", "success")
            else:
                # New part: upsert by part_no
                cur = conn.execute(
                    "UPDATE parts_master SET description = ?, drawing_rev = ? WHERE part_no = ?",
                    (description, drawing_rev, part_no),
                )
                if cur.rowcount == 0:
                    conn.execute(
                        "INSERT INTO parts_master (part_no, drawing_rev, description) VALUES (?, ?, ?)",
                        (part_no, drawing_rev, description),
                    )
                conn.commit()
                flash("Part saved.", "success")
        parts = conn.execute(
            "SELECT part_id, part_no, drawing_rev, description FROM parts_master ORDER BY part_no"
        ).fetchall()
        conn.close()
        return render_template("parts.html", parts=parts)

    @app.route("/parts/<int:part_id>", methods=["GET", "POST"])
    @login_required
    def part_detail(part_id: int):
        """Detail editor for a single part: spec, complaints, material, coating."""
        conn = get_db_connection()
        part = conn.execute(
            "SELECT part_id, part_no, drawing_rev, description FROM parts_master WHERE part_id = ?",
            (part_id,),
        ).fetchone()
        if not part:
            conn.close()
            flash("Part not found.", "danger")
            return redirect(url_for("parts"))

        if request.method == "POST":
            section = request.form.get("section")
            if section == "delete_spec":
                row_id = request.form.get("spec_row_id", type=int)
                if row_id is not None:
                    conn.execute("DELETE FROM part_spec_data WHERE id = ? AND part_id = ?", (row_id, part_id))
                    conn.commit()
                    flash("Parameter row deleted.", "info")
            elif section == "save_spec_bulk":
                conn.execute("DELETE FROM part_spec_data WHERE part_id = ?", (part_id,))
                params = request.form.getlist("spec_param")
                specs = request.form.getlist("spec_spec")
                chars = request.form.getlist("spec_char")
                methods = request.form.getlist("spec_method")
                for i in range(len(params)):
                    if params[i].strip():
                        conn.execute(
                            """
                            INSERT INTO part_spec_data (part_id, parameter, specification, special_char, method_of_inspection)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (part_id, params[i].strip(), specs[i].strip() if i < len(specs) else "", chars[i].strip() if i < len(chars) else "", methods[i].strip() if i < len(methods) else ""),
                        )
                conn.commit()
                flash("Dimension parameters saved.", "success")
            elif section == "spec":
                conn.execute(
                    """
                    INSERT INTO part_spec_data (part_id, parameter, specification, special_char, method_of_inspection)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        part_id,
                        request.form.get("parameter", "").strip(),
                        request.form.get("specification", "").strip(),
                        request.form.get("special_char", "").strip(),
                        request.form.get("method_of_inspection", "").strip(),
                    ),
                )
                conn.commit()
                flash("Dimension parameter added.", "success")
            elif section == "save_ccp_bulk":
                conn.execute("DELETE FROM customer_complaint_parameters WHERE part_id = ?", (part_id,))
                params = request.form.getlist("ccp_param")
                specs = request.form.getlist("ccp_spec")
                chars = request.form.getlist("ccp_char")
                methods = request.form.getlist("ccp_method")
                for i in range(len(params)):
                    if params[i].strip():
                        conn.execute(
                            """
                            INSERT INTO customer_complaint_parameters (part_id, parameter, specification, special_char, method_of_inspection)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (part_id, params[i].strip(), specs[i].strip() if i < len(specs) else "", chars[i].strip() if i < len(chars) else "", methods[i].strip() if i < len(methods) else ""),
                        )
                conn.commit()
                flash("Customer complaint parameters saved.", "success")
            elif section == "save_material_bulk":
                conn.execute("DELETE FROM material_grade WHERE part_id = ?", (part_id,))
                for grade in request.form.getlist("material_grade"):
                    if grade.strip():
                        conn.execute("INSERT INTO material_grade (part_id, material_grade) VALUES (?, ?)", (part_id, grade.strip()))
                conn.commit()
                flash("Material grades saved.", "success")
            elif section == "save_coating_bulk":
                conn.execute("DELETE FROM surface_coating_master WHERE part_id = ?", (part_id,))
                params = request.form.getlist("coat_param")
                specs = request.form.getlist("coat_spec")
                chars = request.form.getlist("coat_char")
                methods = request.form.getlist("coat_method")
                for i in range(len(params)):
                    if params[i].strip():
                        conn.execute(
                            """
                            INSERT INTO surface_coating_master (part_id, parameter, specification, special_char, method_of_inspection)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (part_id, params[i].strip(), specs[i].strip() if i < len(specs) else "", chars[i].strip() if i < len(chars) else "", methods[i].strip() if i < len(methods) else ""),
                        )
                conn.commit()
                flash("Surface coating parameters saved.", "success")
            elif section == "ccp":
                conn.execute(
                    """
                    INSERT INTO customer_complaint_parameters (part_id, parameter, specification, special_char, method_of_inspection)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        part_id,
                        request.form.get("parameter", "").strip(),
                        request.form.get("specification", "").strip(),
                        request.form.get("special_char", "").strip(),
                        request.form.get("method_of_inspection", "").strip(),
                    ),
                )
                conn.commit()
                flash("Complaint parameter added.", "success")
            elif section == "material":
                conn.execute(
                    "INSERT INTO material_grade (part_id, material_grade) VALUES (?, ?)",
                    (part_id, request.form.get("material_grade", "").strip()),
                )
                conn.commit()
                flash("Material grade added.", "success")
            elif section == "coating":
                conn.execute(
                    """
                    INSERT INTO surface_coating_master (part_id, parameter, specification, special_char, method_of_inspection)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        part_id,
                        request.form.get("parameter", "").strip(),
                        request.form.get("specification", "").strip(),
                        request.form.get("special_char", "").strip(),
                        request.form.get("method_of_inspection", "").strip(),
                    ),
                )
                conn.commit()
                flash("Surface coating parameter added.", "success")

        spec_rows = conn.execute(
            "SELECT id, parameter, specification, special_char, method_of_inspection FROM part_spec_data WHERE part_id = ? ORDER BY id",
            (part_id,),
        ).fetchall()
        ccp_rows = conn.execute(
            "SELECT parameter, specification, special_char, method_of_inspection FROM customer_complaint_parameters WHERE part_id = ? ORDER BY id",
            (part_id,),
        ).fetchall()
        material_rows = conn.execute(
            "SELECT material_grade FROM material_grade WHERE part_id = ? ORDER BY id",
            (part_id,),
        ).fetchall()
        coating_rows = conn.execute(
            "SELECT parameter, specification, special_char, method_of_inspection FROM surface_coating_master WHERE part_id = ? ORDER BY id",
            (part_id,),
        ).fetchall()
        conn.close()

        return render_template(
            "part_detail.html",
            part=part,
            spec_rows=spec_rows,
            ccp_rows=ccp_rows,
            material_rows=material_rows,
            coating_rows=coating_rows,
        )

    @app.route("/settings", methods=["GET", "POST"])
    @login_required
    def settings_view():
        conn = get_db_connection()
        settings = conn.execute("SELECT * FROM Settings WHERE id = 1").fetchone()
        if not settings:
            conn.execute("INSERT OR IGNORE INTO Settings (id, company_name) VALUES (1, '')")
            conn.commit()
            settings = conn.execute("SELECT * FROM Settings WHERE id = 1").fetchone()
        if request.method == "POST":
            company_name = request.form.get("company_name", "").strip()
            format_no = request.form.get("format_no", "").strip()
            issue_date = request.form.get("issue_date", "").strip()
            doc_rev_no = request.form.get("doc_rev_no", "").strip()
            rev_date = request.form.get("rev_date", "").strip()

            logo_path = settings["logo_path"] if settings else None
            inspector_sig_path = settings["inspector_signature_path"] if settings else None
            quality_sig_path = settings["quality_signature_path"] if settings else None
            logo_file = request.files.get("logo")
            if logo_file and logo_file.filename:
                filename = f"logo_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{logo_file.filename}"
                save_path = UPLOAD_FOLDER / filename
                logo_file.save(save_path)
                logo_path = url_for("uploaded_file", filename=filename)

            inspector_file = request.files.get("inspector_signature")
            if inspector_file and inspector_file.filename:
                filename = f"inspector_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{inspector_file.filename}"
                save_path = UPLOAD_FOLDER / filename
                inspector_file.save(save_path)
                inspector_sig_path = url_for("uploaded_file", filename=filename)

            quality_file = request.files.get("quality_signature")
            if quality_file and quality_file.filename:
                filename = f"quality_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{quality_file.filename}"
                save_path = UPLOAD_FOLDER / filename
                quality_file.save(save_path)
                quality_sig_path = url_for("uploaded_file", filename=filename)

            conn.execute(
                """
                INSERT INTO Settings (id, company_name, logo_path, inspector_signature_path, quality_signature_path, format_no, issue_date, doc_rev_no, rev_date)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  company_name=excluded.company_name,
                  logo_path=excluded.logo_path,
                  inspector_signature_path=excluded.inspector_signature_path,
                  quality_signature_path=excluded.quality_signature_path,
                  format_no=excluded.format_no,
                  issue_date=excluded.issue_date,
                  doc_rev_no=excluded.doc_rev_no,
                  rev_date=excluded.rev_date
                """,
                (company_name, logo_path, inspector_sig_path, quality_sig_path, format_no, issue_date, doc_rev_no, rev_date),
            )
            conn.commit()
            flash("Settings saved.", "success")
            settings = conn.execute("SELECT * FROM Settings WHERE id = 1").fetchone()
        conn.close()
        return render_template("settings.html", settings=settings)

    @app.route("/uploads/<path:filename>")
    @login_required
    def uploaded_file(filename: str):
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    @app.route("/fir-preview")
    @login_required
    def fir_preview():
        part_no = request.args.get("partName", "").strip()
        spec_data = []
        ccp_data = []
        material_data = []
        coating_data = []
        if part_no:
            conn = get_db_connection()
            part = conn.execute(
                "SELECT part_id FROM parts_master WHERE part_no = ?", (part_no,)
            ).fetchone()
            if part:
                pid = part["part_id"]
                spec_data = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT parameter, specification, special_char, method_of_inspection FROM part_spec_data WHERE part_id = ? ORDER BY id",
                        (pid,),
                    ).fetchall()
                ]
                ccp_data = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT parameter, specification, special_char, method_of_inspection FROM customer_complaint_parameters WHERE part_id = ? ORDER BY id",
                        (pid,),
                    ).fetchall()
                ]
                material_data = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT material_grade FROM material_grade WHERE part_id = ? ORDER BY id",
                        (pid,),
                    ).fetchall()
                ]
                coating_data = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT parameter, specification, special_char, method_of_inspection FROM surface_coating_master WHERE part_id = ? ORDER BY id",
                        (pid,),
                    ).fetchall()
                ]
            conn.close()
        # Embed Quali_1 font as base64 so it works on all computers (no local install needed)
        quali_font_data_uri = None
        quali_font_format = "truetype"
        for name, mime, fmt in [
            ("Quali_1.woff2", "font/woff2", "woff2"),
            ("Quali_1.woff", "font/woff", "woff"),
            ("Quali_1.ttf", "font/ttf", "truetype"),
        ]:
            path = BASE_DIR / "static" / "fonts" / name
            if path.is_file():
                try:
                    data = base64.b64encode(path.read_bytes()).decode("ascii")
                    quali_font_data_uri = f"data:{mime};base64,{data}"
                    quali_font_format = fmt
                except Exception:
                    pass
                break
        return render_template(
            "fir_preview.html",
            spec_data=spec_data,
            ccp_data=ccp_data,
            material_data=material_data,
            coating_data=coating_data,
            quali_font_data_uri=quali_font_data_uri,
            quali_font_format=quali_font_format,
        )

    return app


def init_db():
    """Initialize SQLite database if it does not exist."""
    (BASE_DIR / "database").mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    with (BASE_DIR / "database" / "schema.sql").open("r", encoding="utf-8") as f:
        conn.executescript(f.read())
    # lightweight migrations
    try:
        conn.execute("ALTER TABLE Parts ADD COLUMN draw_rev TEXT")
    except sqlite3.OperationalError:
        # column already exists
        pass
    try:
        conn.execute("ALTER TABLE Settings ADD COLUMN inspector_signature_path TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE Settings ADD COLUMN quality_signature_path TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)

