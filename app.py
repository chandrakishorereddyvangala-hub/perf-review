import os
import json
import time
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify

load_dotenv()  # reads .env locally; ignored on Vercel (uses dashboard env vars)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "perfreview_secret_2024")

# ── Google Sheets config ─────────────────────────────────────────────────────
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_gc = None

def get_client():
    global _gc
    if _gc is not None:
        return _gc
    raw = os.environ.get("GOOGLE_CREDENTIALS", "")
    if raw:
        info = json.loads(raw)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        _gc = gspread.authorize(creds)
    elif os.path.exists("credentials.json"):
        _gc = gspread.service_account(filename="credentials.json")
    else:
        raise RuntimeError("No Google credentials found.")
    return _gc

def get_spreadsheet():
    return get_client().open_by_key(SPREADSHEET_ID)


# ── Simple 30-second in-memory cache ─────────────────────────────────────────
# Keeps the app snappy without hammering the Sheets API on every page load.
# Any change you make in the spreadsheet reflects in the app within 30 seconds.
_cache: dict = {}
CACHE_TTL = 300  # seconds — warm invocations reuse the process; cold starts bypass anyway

def _cached(key, loader_fn):
    now = time.time()
    entry = _cache.get(key)
    if entry and (now - entry["ts"]) < CACHE_TTL:
        return entry["data"]
    data = loader_fn()
    _cache[key] = {"data": data, "ts": now}
    return data

def bust_cache(*keys):
    for k in keys:
        _cache.pop(k, None)


# ── Users — manage logins here directly ──────────────────────────────────────
# To add a user:    "username": {"password": "yourpass", "role": "lead"}
# To add director:  "username": {"password": "yourpass", "role": "director"}
# To remove:        delete the line
# Usernames are case-insensitive (always stored lowercase)
USERS = {
    "Chandra":   {"password": "pass123",    "role": "lead"},
    "Uma":       {"password": "pass123",    "role": "lead"},
    "Vinoth":    {"password": "pass123",    "role": "lead"},
    "Tejas":     {"password": "pass123",    "role": "lead"},
    "Suresh":    {"password": "pass123",    "role": "lead"},
    "Aishwarya": {"password": "pass123",    "role": "lead"},
    "Dheeraj":   {"password": "pass123",    "role": "lead"},
    "Drushya":   {"password": "pass123",    "role": "lead"},
    "NaveenR":   {"password": "pass123",    "role": "lead"},
    "Naveen":    {"password": "pass123",    "role": "director"},
}
LEADS = [u for u, d in USERS.items() if d["role"] == "lead"]

# ── Constants ─────────────────────────────────────────────────────────────────
RATING_CATEGORIES = [
    "Collaboration & Communication",
    "Continuous Improvement & Learning",
    "Compliance & Professional Conduct",
    "Ownership & Value Addition",
    "Stakeholder Satisfaction",
    "Exceptional Contribution",
    "Feedback & Improvement",
    "Work Discipline & Professional Practice",
    "SLA & Deadline Adherence",
    "Automation & Tools",
    "Quality Metrics & Reporting",
]
REV_HEADERS = (
    ["employee", "status"]
    + RATING_CATEGORIES
    + ["notes", "lead_comments", "comments", "shared_with"]
)


# ── Sheet initialisation (once on first request) ──────────────────────────────
_sheet_ready = False

def _migrate_lead_sheet(ws):
    """Rewrite ws to match REV_HEADERS, preserving any column that kept its name."""
    all_data = ws.get_all_values()
    if not all_data:
        ws.update('A1', [REV_HEADERS])
        return
    old_headers = all_data[0]
    if old_headers == REV_HEADERS:
        return  # already current
    rows = all_data[1:]
    new_data = [REV_HEADERS]
    for row in rows:
        old_rec = _zip(old_headers, row)
        if not old_rec.get("employee"):
            continue  # skip blank rows
        new_row = [old_rec.get(h, "") for h in REV_HEADERS]
        new_data.append(new_row)
    ws.clear()
    time.sleep(0.3)
    ws.update('A1', new_data)

def _init_sheets():
    global _sheet_ready
    if _sheet_ready:
        return
    sh = get_spreadsheet()
    existing = {ws.title for ws in sh.worksheets()}

    # users tab — the master list of logins & roles
    if "users" not in existing:
        ws = sh.add_worksheet("users", rows=100, cols=4)
        time.sleep(0.8)
        ws.append_row(["username", "password", "role"])
        defaults = [
            ("chandra",   "pass123", "lead"),
            ("uma",       "pass123", "lead"),
            ("vinoth",    "pass123", "lead"),
            ("tejas",     "pass123", "lead"),
            ("suresh",    "pass123", "lead"),
            ("aishwarya", "pass123", "lead"),
            ("dheeraj",   "pass123", "lead"),
            ("drushya",   "pass123", "lead"),
            ("naveen",    "pass123", "director"),
        ]
        for row in defaults:
            ws.append_row(list(row))
            time.sleep(0.2)

    # org tab — resource → lead mapping
    if "org" not in existing:
        ws = sh.add_worksheet("org", rows=200, cols=5)
        time.sleep(0.8)
        ws.append_row(["employee", "lead", "role"])

    # migrate all lead sheets to current REV_HEADERS (reuse worksheets list)
    all_ws = {ws.title.lower(): ws for ws in sh.worksheets()}
    for lead in LEADS:
        ws = all_ws.get(lead.lower())
        if ws:
            try:
                _migrate_lead_sheet(ws)
                time.sleep(0.3)
            except Exception:
                pass

    _sheet_ready = True




# ── Dynamic loaders (everything comes from the sheet) ────────────────────────

def load_org():
    """Load org structure from the 'org' sheet. Cached 30 s."""
    def _load():
        sh = get_spreadsheet()
        try:
            ws = sh.worksheet("org")
        except gspread.WorksheetNotFound:
            return {}, {}
        headers, rows = _parse_ws(ws)
        emp_info, lead_emps = {}, {}
        for row in rows:
            rec = _zip(headers, row)
            emp  = rec.get("employee", "").strip()
            lead = rec.get("lead", "").strip().lower()
            role = rec.get("role", "Employee").strip() or "Employee"
            if emp and lead:
                emp_info[emp] = {"lead": lead, "role": role}
                lead_emps.setdefault(lead, []).append(emp)
        return emp_info, lead_emps
    return _cached("org", _load)


# ── Sheet helpers ─────────────────────────────────────────────────────────────

def _parse_ws(ws):
    data = ws.get_all_values()
    if not data:
        return [], []
    return data[0], data[1:]

def _zip(headers, row):
    padded = row + [""] * max(0, len(headers) - len(row))
    return dict(zip(headers, padded))

def _to_rec(headers, row):
    rec = _zip(headers, row)
    for field in ["comments", "shared_with"]:
        try:
            rec[field] = json.loads(rec.get(field) or "[]")
        except Exception:
            rec[field] = []
    for cat in RATING_CATEGORIES:
        try:
            rec[cat] = float(rec.get(cat) or 0)
        except (ValueError, TypeError):
            rec[cat] = 0.0
    rec["notes"] = _clean_notes(rec.get("notes", ""))
    try:
        lc = rec.get("lead_comments", "")
        rec["lead_comments"] = json.loads(lc) if lc else {}
    except Exception:
        rec["lead_comments"] = {}
    return rec

def _get_ws_ci(sh, name):
    """Case-insensitive worksheet lookup. Raises WorksheetNotFound if missing."""
    for ws in sh.worksheets():
        if ws.title.lower() == name.lower():
            return ws
    raise gspread.WorksheetNotFound(name)

def _ensure_lead_sheet(sh, lead):
    """Get or create a lead's worksheet on demand (case-insensitive match).
    Also syncs the header row if categories have changed."""
    try:
        ws = _get_ws_ci(sh, lead)
        if ws.row_values(1) != REV_HEADERS:
            ws.update('A1', [REV_HEADERS])
        return ws
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(lead, rows=200, cols=len(REV_HEADERS))
        time.sleep(0.8)
        ws.append_row(REV_HEADERS)
        return ws

def _clean_notes(raw):
    """Strip legacy __TP__....__END__ encoding — return plain text only."""
    if not raw:
        return ""
    if raw.startswith("__TP__"):
        try:
            return raw.split("__END__", 1)[1]
        except Exception:
            return ""
    return raw

def compute_avg(review):
    ratings = [review.get(c, 0) or 0 for c in RATING_CATEGORIES]
    return round(sum(ratings) / len(ratings), 1) if any(ratings) else 0


def load_review(lead, emp_name):
    sh = get_spreadsheet()
    try:
        ws = _get_ws_ci(sh, lead)
    except gspread.WorksheetNotFound:
        return None
    headers, rows = _parse_ws(ws)
    for row in rows:
        if row and row[0] == emp_name:
            return _to_rec(headers, row)
    return None


def load_all_lead_reviews(lead):
    """Read all reviews for a lead in one API call."""
    sh = get_spreadsheet()
    try:
        ws = _get_ws_ci(sh, lead)
    except gspread.WorksheetNotFound:
        return []
    headers, rows = _parse_ws(ws)
    return [_to_rec(headers, row) for row in rows if row and row[0]]


def save_review(lead, emp_name, data):
    sh = get_spreadsheet()
    ws = _ensure_lead_sheet(sh, lead)
    all_data = ws.get_all_values()
    headers = all_data[0] if all_data else REV_HEADERS

    def serial(val):
        if isinstance(val, (list, dict)):
            return json.dumps(val)
        return val if val is not None else ""

    values = [serial(data.get(h, "")) for h in headers]
    end_col = chr(ord("A") + len(headers) - 1)

    for i, row in enumerate(all_data[1:], start=2):
        if row and row[0] == emp_name:
            ws.update(f"A{i}:{end_col}{i}", [values])  # gspread 6.x: range first
            return

    ws.append_row(values)  # new employee row


def get_shared_employees(lead):
    sh = get_spreadsheet()
    all_ws = {ws.title.lower(): ws for ws in sh.worksheets()}  # lowercase keys
    shared = []
    for owner_lead in LEADS:
        ol_lower = owner_lead.lower()
        if ol_lower == lead or ol_lower not in all_ws:
            continue
        headers, rows = _parse_ws(all_ws[ol_lower])
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
                    "review": _to_rec(headers, row),
                })
    return shared


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET", "POST"])
def login():
    if "lead" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username_input = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        # Case-insensitive username match
        matched_key = next((k for k in USERS if k.lower() == username_input.lower()), None)
        user = USERS.get(matched_key) if matched_key else None
        if user and user["password"] == password:
            session["lead"] = matched_key.lower()
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
        _, lead_emps = load_org()
        lead_tiles = []
        for lead in LEADS:
            reviews = load_all_lead_reviews(lead)
            rev_map = {r["employee"]: r for r in reviews}
            emps = lead_emps.get(lead, [])
            rated, total_avg = 0, 0.0
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
        employees.append({
            "name": emp,
            "info": emp_info.get(emp, {"role": "Employee"}),
            "status": rev.get("status", "Pending"),
            "avg_rating": compute_avg(rev) if rev else 0,
            "ratings": {c: rev.get(c, 0) or 0 for c in RATING_CATEGORIES},
            "notes": rev.get("notes", ""),
            "lead_comments": rev.get("lead_comments", ""),
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
        review_data = {
            "employee": emp_name, "status": "Pending",
            "comments": [], "shared_with": [],
        }
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

    notes_text = review_data.get("notes", "") or ""

    return render_template(
        "review.html",
        lead=lead, emp_name=emp_name, emp_info=info,
        review=review_data, is_owner=is_owner, owner_lead=owner_lead,
        categories=RATING_CATEGORIES,
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
    try:
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
            review_data["notes"] = _clean_notes(data["notes"])
        if "lead_comments" in data:
            review_data["lead_comments"] = data["lead_comments"]
        if "status" in data:
            review_data["status"] = data["status"]
        review_data.setdefault("employee", emp_name)
        save_review(lead, emp_name, review_data)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/add_comment", methods=["POST"])
def api_add_comment():
    if "lead" not in session:
        return jsonify({"ok": False}), 401
    if session.get("role") == "director":
        return jsonify({"ok": False, "error": "View-only"}), 403
    lead = session["lead"]
    try:
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
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/update_sharing", methods=["POST"])
def api_update_sharing():
    if "lead" not in session:
        return jsonify({"ok": False}), 401
    if session.get("role") == "director":
        return jsonify({"ok": False}), 403
    lead = session["lead"]
    try:
        data = request.get_json()
        emp_name = data.get("emp_name")
        emp_info, _ = load_org()
        owner_lead = emp_info.get(emp_name, {}).get("lead")
        if lead != owner_lead:
            return jsonify({"ok": False, "error": "Not authorized"}), 403
        review_data = load_review(lead, emp_name) or {}
        review_data["shared_with"] = data.get("shared_with", [])
        review_data.setdefault("employee", emp_name)
        save_review(lead, emp_name, review_data)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/delete_review", methods=["POST"])
def api_delete_review():
    if "lead" not in session:
        return jsonify({"ok": False}), 401
    if session.get("role") == "director":
        return jsonify({"ok": False, "error": "View-only"}), 403
    lead = session["lead"]
    try:
        data = request.get_json()
        emp_name = data.get("emp_name")
        emp_info, _ = load_org()
        owner_lead = emp_info.get(emp_name, {}).get("lead")
        if lead != owner_lead:
            return jsonify({"ok": False, "error": "Not authorized"}), 403
        sh = get_spreadsheet()
        ws = _get_ws_ci(sh, lead)
        all_data = ws.get_all_values()
        for i, row in enumerate(all_data[1:], start=2):
            if row and row[0] == emp_name:
                ws.delete_rows(i)
                return jsonify({"ok": True})
        return jsonify({"ok": True})  # already gone
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/healthz")
def healthz():
    errors = []
    info = {}
    if not os.environ.get("GOOGLE_CREDENTIALS") and not os.path.exists("credentials.json"):
        errors.append("GOOGLE_CREDENTIALS env var not set and credentials.json not found")
    if not os.environ.get("SPREADSHEET_ID"):
        errors.append("SPREADSHEET_ID env var not set")
    try:
        get_client()
        info["auth"] = "ok"
    except Exception as e:
        errors.append(f"Google auth failed: {e}")
    try:
        sh = get_spreadsheet()
        tabs = [ws.title for ws in sh.worksheets()]
        info["spreadsheet_tabs"] = tabs
    except Exception as e:
        errors.append(f"Spreadsheet open failed: {e}")
    try:
        emp_info, lead_emps = load_org()
        info["org_employees"] = len(emp_info)
        info["org_leads"] = list(lead_emps.keys())
    except Exception as e:
        errors.append(f"load_org failed: {e}")
    if errors:
        return jsonify({"ok": False, "errors": errors, "info": info}), 500
    return jsonify({"ok": True, "info": info})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
