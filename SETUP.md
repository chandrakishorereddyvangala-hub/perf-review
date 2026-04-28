# Setup & Deployment Guide

## Step 1 — Google Cloud (one-time, ~5 min)

1. Go to https://console.cloud.google.com
2. Create a new project → name it anything (e.g. "perfreview")
3. Search "Google Sheets API" → click Enable
4. Go to **IAM & Admin → Service Accounts → Create Service Account**
   - Name: `perfreview-app` → Done (skip optional steps)
5. Click the service account → **Keys** tab → **Add Key → JSON**
   - A file downloads automatically
   - Rename it `credentials.json` and place it in this project folder
   - It is in `.gitignore` — it will never be committed to GitHub

---

## Step 2 — Google Sheet (one-time, ~2 min)

1. Go to https://sheets.google.com → create a blank spreadsheet
2. Copy the **Sheet ID** from the URL:
   ```
   https://docs.google.com/spreadsheets/d/  ← THIS PART →  /edit
   ```
3. Open `credentials.json` → find the `"client_email"` value (looks like `perfreview-app@project.iam.gserviceaccount.com`)
4. In the Google Sheet → **Share** → paste that email → set role to **Editor** → Send

The app will auto-create all tabs (org, chandra, uma, etc.) on first run.

---

## Step 3 — Deploy to Vercel (free forever, ~5 min)

### 3a — Push to GitHub
```bash
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/YOUR_USERNAME/perfreview.git
git push -u origin main
```

### 3b — Deploy on Vercel
1. Go to https://vercel.com → sign up free (use GitHub login)
2. Click **Add New Project** → Import your GitHub repo
3. Leave all build settings as-is → click **Environment Variables**
4. Add these three variables:

| Name                | Value                                              |
|---------------------|----------------------------------------------------|
| `SPREADSHEET_ID`    | The Sheet ID you copied in Step 2                 |
| `GOOGLE_CREDENTIALS`| Entire contents of `credentials.json` (paste all) |
| `SECRET_KEY`        | Any random string e.g. `xK9mP2qL8nR5vT1w`        |

5. Click **Deploy** → in ~60 seconds you get a public URL:
   ```
   https://perfreview.vercel.app
   ```
   Share this URL with your leads and Naveen.

---

## Running locally (for testing)

**Windows:**
```bash
set SPREADSHEET_ID=your-sheet-id-here
venv\Scripts\python app.py
```

**Mac / Linux:**
```bash
export SPREADSHEET_ID=your-sheet-id-here
python app.py
```

`credentials.json` is read automatically when running locally.
Open http://localhost:5000

---

## Logins

| Username   | Password | Role           |
|------------|----------|----------------|
| chandra    | pass123  | Lead           |
| uma        | pass123  | Lead           |
| vinoth     | pass123  | Lead           |
| tejas      | pass123  | Lead           |
| suresh     | pass123  | Lead           |
| aishwarya  | pass123  | Lead           |
| dheeraj    | pass123  | Lead           |
| naveen     | pass123  | Director       |

Change passwords in `app.py` → `USERS` dict before deploying.

---

## Updating employee names (org structure)

Open your Google Sheet → **org** tab → edit:
- Column A: employee name
- Column B: their lead's username
- Column C: their role/title

Changes are live immediately — no app restart needed.

---

## Your sheet as a metrics tool

Every tab is a live table you can:
- Filter by status, lead, rating score
- Download as Excel or CSV (File → Download)
- Build pivot tables and charts directly in Google Sheets
- Share as view-only with anyone for reporting

Nobody except the service account (the app) can write to it.
Only you (the owner) have editor access.
