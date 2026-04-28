import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "perfreview_secret_2024")

# ── Google Sheets config ─────────────────────────────────────────────────────
# Set these as environment variables in Railway (or locally in .env)
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_gc = None

def get_client():
    """Return a cached gspread client, initialising once per process."""
    global _gc
    if _gc is not None:
        return _gc
    raw = os.environ.get("GOOGLE_CREDENTIALS", "")
    if raw:
        # Production: credentials stored as env-var JSON string
        info = json.loads(raw)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        _gc = gspread.authorize(creds)
    elif os.path.exists("credentials.json"):
        # Local dev: credentials file on disk
        _gc = gspread.service_account(filename="credentials.json")
    else:
        raise RuntimeError(
            "No Google credentials found. "
            "Set GOOGLE_CREDENTIALS env var or place credentials.json in the project root."
        )
    return _gc


def get_spreadsheet():
    return get_client().open_by_key(SPREADSHEET_ID)


# ── Users & constants ────────────────────────────────────────────────────────
USERS = {
    "chandra":   {"password": "pass123", "role": "lead"},
    "uma":       {"password": "pass123", "role": "lead"},
    "vinoth":    {"password": "pass123", "role": "lead"},
    "tejas":     {"password": "pass123", "role": "lead"},
    "suresh":    {"password": "pass123", "role": "lead"},
    "aishwarya": {"password": "pass123", "role": "lead"},
    "dheeraj":   {"password": "pass123", "role": "lead"},
    "naveen":    {"password": "pass123", "role": "director"},
}
LEADS = [u for u, d in USERS.items() if d["role"] == "lead"]

RATING_CATEGORIES = [
    "Technical Skills", "Communication",
    "Teamwork", "Productivity", "Leadership",
]
TALKING_POINTS = [
    "Achieves goals consistently",   "Proactive in problem-solving",
    "Demonstrates growth mindset",   "Collaborates effectively",
    "Meets deadlines reliably",      "Communicates blockers early",
    "Shows initiative",              "Supports team members",
]

REV_HEADERS = (
    ["employee", "status"]
    + RATING_CATEGORIES
    + ["notes", "comments", "shared_with"]
)

ORG_PLACEHOLDERS = [
    ("chandra_r1",   "chandra",   "Developer"),
    ("chandra_r2",   "chandra",   "Analyst"),
    ("chandra_r3",   "chandra",   "QA Engineer"),
    ("uma_r1",       "uma",       "Frontend Developer"),
    ("uma_r2",       "uma",       "UX Designer"),
    ("uma_r3",       "uma",       "Tester"),
    ("vinoth_r1",    "vinoth",    "Backend Developer"),
    ("vinoth_r2",    "vinoth",    "DevOps Engineer"),
    ("vinoth_r3",    "vinoth",    "Systems Analyst"),
    ("tejas_r1",     "tejas",     "Mobile Developer"),
    ("tejas_r2",     "tejas",     "Cloud Architect"),
    ("tejas_r3",     "tejas",     "Full Stack Developer"),
    ("suresh_r1",    "suresh",    "ML Engineer"),
    ("suresh_r2",    "suresh",    "Data Scientist"),
    ("suresh_r3",    "suresh",    "BI Analyst"),
    ("aishwarya_r1", "aishwarya", "Security Engineer"),
    ("aishwarya_r2", "aishwarya", "Product Manager"),
    ("aishwarya_r3", "aishwarya", "Scrum Master"),
    ("dheeraj_r1",   "dheeraj",  "Infrastructure Engineer"),
    ("dheeraj_r2",   "dheeraj",  "Technical Writer"),
    ("dheeraj_r3",   "dheeraj",  "Support Engineer"),
]


# ── Sheet initialisation (runs once on first request) ────────────────────────
_sheet_ready = False

def _init_sheets():
    """Create sheet tabs and seed placeholder data if they don't exist yet."""
    global _sheet_ready
    if _sheet_ready:
        return
    sh = get_spreadsheet()
    existing = {ws.title for ws in sh.worksheets()}

    # org tab
    if "org" not in existing:
        ws = sh.add_worksheet("org", rows=200, cols=5)
        ws.append_row(["employee", "lead", "role"])
        for row in ORG_PLACEHOLDERS:
            ws.append_row(list(row))

    # per-lead tabs
    for lead in LEADS:
        if lead not in existing:
            ws = sh.add_worksheet(lead, rows=200, cols=len(REV_HEADERS))
            ws.append_row(REV_HEADERS)
            # seed placeholder employee rows for this lead
            for emp, emp_lead, _ in ORG_PLACEHOLDERS:
                if emp_lead == lead:
                    ws.append_row(
                        [emp, "Pending"] + [0] * len(RATING_CATEGORIES) + ["", "[]", "[]"]
                    )

    _sheet_ready = True


@app.before_request
def ensure_sheets():
    try:
        _init_sheets()
    except Exception as e:
        # Don't crash on auth errors for static assets
        pass


# ── Sheet helpers ─────────────────────────────────────────────────────────────
def _parse_ws(ws):
    """Read all values → (headers list, rows list-of-lists)."""
    data = ws.get_all_values()
    if not data:
        return [], []
    return data[0], data[1:]


def _row_to_rec(headers, row):
    padded = row + [""] * max(0, len(headers) - len(row))
    rec = dict(zip(headers, padded))
    for field in ["comments", "shared_with"]:
        try:
            rec[field] = json.loads(rec.get(field) or "[]")
        except Exception:
            rec[field] = []
    for cat in RATING_CATEGORIES:
        try:
            rec[cat] = int(rec.get(cat) or 0)
        except (ValueError, TypeError):
            rec[cat] = 0
    return rec


def load_org():
    sh = get_spreadsheet()
    try:
        ws = sh.worksheet("org")
    except gspread.WorksheetNotFound:
        return {}, {}
    headers, rows = _parse_ws(ws)
    emp_info, lead_emps = {}, {}
    for row in rows:
        padded = row + [""] * max(0, len(headers) - len(row))
        rec = dict(zip(headers, padded))
        emp  = rec.get("employee", "").strip()
        lead = rec.get("lead", "").strip()
        role = rec.get("role", "Employee").strip() or "Employee"
        if emp and lead:
            emp_info[emp] = {"lead": lead, "role": role}
            lead_emps.setdefault(lead, []).append(emp)
    return emp_info, lead_emps


def load_review(lead, emp_name):
    sh = get_spreadsheet()
    try:
        ws = sh.worksheet(lead)
    except gspread.WorksheetNotFound:
        return None
    headers, rows = _parse_ws(ws)
    for row in rows:
        if row and row[0] == emp_name:
            return _row_to_rec(headers, row)
    return None


def load_all_lead_reviews(lead):
    """Read all reviews for a lead in a single API call."""
    sh = get_spreadsheet()
    try:
        ws = sh.worksheet(lead)
    except gspread.WorksheetNotFound:
        return []
    headers, rows = _parse_ws(ws)
    return [_row_to_rec(headers, row) for row in rows if row and row[0]]


def save_review(lead, emp_name, data):
    sh = get_spreadsheet()
    try:
        ws = sh.worksheet(lead)
    except gspread.WorksheetNotFound:
        return
    all_data = ws.get_all_values()
    if not all_data:
        return
    headers = all_data[0]

    # Build row values in header order
    def serialise(val):
        if isinstance(val, (list, dict)):
            return json.dumps(val)
        return val if val is not None else ""

    values = [serialise(data.get(h, "")) for h in headers]
    end_col = chr(ord("A") + len(headers) - 1)

    # Find existing row
    for i, row in enumerate(all_data[1:], start=2):
        if row and row[0] == emp_name:
            ws.update(f"A{i}:{end_col}{i}", [values])
            return

    # Not found — append
    ws.append_row(values)


def compute_avg(review):
    ratings = [review.get(c, 0) or 0 for c in RATING_CATEGORIES]
    return round(sum(ratings) / len(ratings), 1) if any(ratings) else 0


def get_shared_employees(lead):
    sh = get_spreadsheet()
    all_ws = {ws.title: ws for ws in sh.worksheets()}
    shared = []
    for owner_lead in LEADS:
        if owner_lead == lead or owner_lead not in all_ws:
            continue
        headers, rows = _parse_ws(all_ws[owner_lead])
        try:
            sw_idx = headers.index("shared_with")
        except ValueError:
            continue
        for row in rows:
            padded = row + [""] * max(0, len(headers) - len(row))
            try:
                sw = json.loads(padded[sw_idx] or "[]")
            except Exception:
                sw = []
            if lead in sw and padded[0]:
                shared.append({
                    "emp": padded[0],
                    "owner_lead": owner_lead,
                    "review": _row_to_rec(headers, row),
                })
    return shared


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def login():
    if "lead" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "").strip()
        user = USERS.get(username)
        if user and user["password"] == password:
            session["lead"] = username
            session["role"] = user["role"]
            return redirect(url_for("dashboard"))
        flash("Invalid credentials. Please try again.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    if "lead" not in session:
        return redirect(url_for("login"))

    if session.get("role") == "director":
        emp_info, lead_emps = load_org()
        lead_tiles = []
        for lead in LEADS:
            reviews = load_all_lead_reviews(lead)
            rev_map = {r["employee"]: r for r in reviews}
            emps = lead_emps.get(lead, [])
            rated, total_avg = 0, 0
            status_counts = {"Pending": 0, "In Progress": 0, "Completed": 0}
            for emp in emps:
                rev = rev_map.get(emp)
                if rev:
                    avg = compute_avg(rev)
                    if avg:
                        total_avg += avg
                        rated += 1
                    s = rev.get("status", "Pending")
                    status_counts[s] = status_counts.get(s, 0) + 1
            lead_tiles.append({
                "name": lead,
                "emp_count": len(emps),
                "team_avg": round(total_avg / rated, 1) if rated else 0,
                "status_counts": status_counts,
            })
        return render_template("director_dashboard.html", lead_tiles=lead_tiles)

    lead = session["lead"]
    emp_info, lead_emps = load_org()
    reviews = load_all_lead_reviews(lead)
    rev_map = {r["employee"]: r for r in reviews}
    employees = []
    for emp in lead_emps.get(lead, []):
        rev = rev_map.get(emp)
        employees.append({
            "name": emp,
            "info": emp_info.get(emp, {"role": "Employee", "lead": lead}),
            "status": rev.get("status", "Pending") if rev else "Pending",
            "avg_rating": compute_avg(rev) if rev else 0,
        })
    shared = get_shared_employees(lead)
    return render_template("dashboard.html", lead=lead, employees=employees, shared=shared)


@app.route("/director/team/<lead_name>")
def director_team(lead_name):
    if "lead" not in session or session.get("role") != "director":
        flash("Access denied.")
        return redirect(url_for("dashboard"))
    emp_info, lead_emps = load_org()
    reviews = load_all_lead_reviews(lead_name)
    rev_map = {r["employee"]: r for r in reviews}
    employees = []
    for emp in lead_emps.get(lead_name, []):
        rev = rev_map.get(emp, {})
        notes_raw = rev.get("notes", "") or ""
        notes_text = notes_raw
        if notes_raw.startswith("__TP__"):
            try:
                notes_text = notes_raw.split("__END__", 1)[1]
            except Exception:
                pass
        employees.append({
            "name": emp,
            "info": emp_info.get(emp, {"role": "Employee"}),
            "status": rev.get("status", "Pending"),
            "avg_rating": compute_avg(rev) if rev else 0,
            "ratings": {c: rev.get(c, 0) or 0 for c in RATING_CATEGORIES},
            "notes": notes_text,
        })
    return render_template(
        "director_team.html",
        lead_name=lead_name,
        employees=employees,
        categories=RATING_CATEGORIES,
    )


@app.route("/review/<emp_name>", methods=["GET", "POST"])
def review(emp_name):
    if "lead" not in session:
        return redirect(url_for("login"))
    lead = session["lead"]
    role = session.get("role", "lead")

    if role == "director":
        flash("View-only access — use the director panel.")
        return redirect(url_for("dashboard"))

    emp_info, _ = load_org()
    info = emp_info.get(emp_name, {})
    owner_lead = info.get("lead")
    is_owner = (lead == owner_lead)

    if not is_owner:
        rev_check = load_review(owner_lead, emp_name) if owner_lead else None
        if not rev_check or lead not in rev_check.get("shared_with", []):
            flash("Access denied.")
            return redirect(url_for("dashboard"))

    review_data = load_review(owner_lead, emp_name) if owner_lead else {}
    if not review_data:
        review_data = {"employee": emp_name, "status": "Pending", "comments": [], "shared_with": []}
    all_leads = [l for l in LEADS if l != owner_lead]

    if request.method == "POST" and is_owner:
        action = request.form.get("action")
        if action == "save_review":
            for cat in RATING_CATEGORIES:
                try:
                    review_data[cat] = int(request.form.get(cat, 0))
                except ValueError:
                    review_data[cat] = 0
            review_data["notes"] = request.form.get("notes", "")
            review_data["status"] = request.form.get("status", "Pending")
            save_review(owner_lead, emp_name, review_data)
            flash("Review saved.")
            return redirect(url_for("review", emp_name=emp_name))
        elif action == "share":
            review_data["shared_with"] = request.form.getlist("share_with")
            save_review(owner_lead, emp_name, review_data)
            flash("Sharing updated.")
            return redirect(url_for("review", emp_name=emp_name))

    notes_raw = review_data.get("notes", "") or ""
    selected_points, notes_text = [], notes_raw
    if notes_raw.startswith("__TP__"):
        try:
            parts = notes_raw.split("__END__", 1)
            selected_points = json.loads(parts[0].replace("__TP__", ""))
            notes_text = parts[1] if len(parts) > 1 else ""
        except Exception:
            pass

    return render_template(
        "review.html",
        lead=lead,
        emp_name=emp_name,
        emp_info=info,
        review=review_data,
        is_owner=is_owner,
        owner_lead=owner_lead,
        categories=RATING_CATEGORIES,
        talking_points=TALKING_POINTS,
        selected_points=selected_points,
        notes_text=notes_text,
        all_leads=all_leads,
    )


# ── JSON APIs ─────────────────────────────────────────────────────────────────
@app.route("/api/save_review", methods=["POST"])
def api_save_review():
    if "lead" not in session:
        return jsonify({"ok": False}), 401
    if session.get("role") == "director":
        return jsonify({"ok": False, "error": "View-only"}), 403
    lead = session["lead"]
    data = request.get_json()
    emp_name = data.get("emp_name")
    emp_info, _ = load_org()
    owner_lead = emp_info.get(emp_name, {}).get("lead")
    if lead != owner_lead:
        return jsonify({"ok": False, "error": "Not authorized"}), 403
    review_data = load_review(lead, emp_name) or {}
    for cat in RATING_CATEGORIES:
        if cat in data:
            review_data[cat] = data[cat]
    if "notes" in data:
        review_data["notes"] = data["notes"]
    if "status" in data:
        review_data["status"] = data["status"]
    if "talking_points" in data:
        notes = data.get("notes", review_data.get("notes", "") or "")
        if isinstance(notes, str) and notes.startswith("__TP__"):
            try:
                notes = notes.split("__END__", 1)[1]
            except Exception:
                pass
        review_data["notes"] = f"__TP__{json.dumps(data['talking_points'])}__END__{notes}"
    review_data.setdefault("employee", emp_name)
    save_review(lead, emp_name, review_data)
    return jsonify({"ok": True})


@app.route("/api/add_comment", methods=["POST"])
def api_add_comment():
    if "lead" not in session:
        return jsonify({"ok": False}), 401
    if session.get("role") == "director":
        return jsonify({"ok": False, "error": "View-only"}), 403
    lead = session["lead"]
    data = request.get_json()
    emp_name = data.get("emp_name")
    comment_text = data.get("comment", "").strip()
    emp_info, _ = load_org()
    owner_lead = emp_info.get(emp_name, {}).get("lead")
    is_owner = (lead == owner_lead)
    if not is_owner:
        rev_check = load_review(owner_lead, emp_name)
        if not rev_check or lead not in rev_check.get("shared_with", []):
            return jsonify({"ok": False, "error": "Access denied"}), 403
    review_data = load_review(owner_lead, emp_name) or {}
    comments = review_data.get("comments", [])
    if isinstance(comments, str):
        try:
            comments = json.loads(comments)
        except Exception:
            comments = []
    new_comment = {
        "author": lead,
        "text": comment_text,
        "time": datetime.now().strftime("%b %d, %Y %H:%M"),
    }
    comments.append(new_comment)
    review_data["comments"] = comments
    review_data.setdefault("employee", emp_name)
    save_review(owner_lead, emp_name, review_data)
    return jsonify({"ok": True, "comment": new_comment})


@app.route("/api/update_sharing", methods=["POST"])
def api_update_sharing():
    if "lead" not in session:
        return jsonify({"ok": False}), 401
    if session.get("role") == "director":
        return jsonify({"ok": False}), 403
    lead = session["lead"]
    data = request.get_json()
    emp_name = data.get("emp_name")
    emp_info, _ = load_org()
    owner_lead = emp_info.get(emp_name, {}).get("lead")
    if lead != owner_lead:
        return jsonify({"ok": False}), 403
    review_data = load_review(lead, emp_name) or {}
    review_data["shared_with"] = data.get("shared_with", [])
    review_data.setdefault("employee", emp_name)
    save_review(lead, emp_name, review_data)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
