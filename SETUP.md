# Setup Guide

## 1 — Google Cloud (one-time, 5 min)

1. Go to https://console.cloud.google.com
2. Create a new project (e.g. "perfreview")
3. Search for "Google Sheets API" → Enable it
4. Go to IAM & Admin → Service Accounts → Create Service Account
   - Name: perfreview-app
   - Skip optional steps → Done
5. Click the service account → Keys tab → Add Key → JSON
   - A file downloads — rename it `credentials.json`
   - Place it in this project folder (it's in .gitignore, never committed)

## 2 — Google Sheet (one-time, 2 min)

1. Go to https://sheets.google.com → create a blank spreadsheet
   - Name it "PerfReview Data" (or anything)
2. Copy the ID from the URL:
   https://docs.google.com/spreadsheets/d/  **THIS_PART**  /edit
3. Open `credentials.json` → find `"client_email"` value
4. In the spreadsheet → Share → paste that email → Editor role

The app will auto-create all tabs (org, chandra, uma, ...) on first run.

## 3 — Run locally

```bash
# Set your spreadsheet ID
set SPREADSHEET_ID=paste-your-id-here      # Windows
export SPREADSHEET_ID=paste-your-id-here   # Mac/Linux

venv/Scripts/python app.py                 # Windows
python app.py                              # Mac/Linux
```

Open http://localhost:5000

## 4 — Deploy to Railway (public URL)

1. Push this repo to GitHub (credentials.json is gitignored — safe)
2. Go to https://railway.app → New Project → Deploy from GitHub
3. Select this repo
4. Go to Variables tab → add these three:

   | Variable           | Value                                      |
   |--------------------|--------------------------------------------|
   | SPREADSHEET_ID     | your Google Sheet ID                       |
   | GOOGLE_CREDENTIALS | entire contents of credentials.json        |
   | SECRET_KEY         | any random string e.g. my-secret-abc-123  |

5. Railway auto-deploys → you get a public URL like `https://perfreview.up.railway.app`

## Logins

| Username   | Password | Role     |
|------------|----------|----------|
| chandra    | pass123  | Lead     |
| uma        | pass123  | Lead     |
| vinoth     | pass123  | Lead     |
| tejas      | pass123  | Lead     |
| suresh     | pass123  | Lead     |
| aishwarya  | pass123  | Lead     |
| dheeraj    | pass123  | Lead     |
| naveen     | pass123  | Director |

## Updating employee names

Open your Google Sheet → `org` tab → edit column A (employee name),
B (lead), C (role). The app picks up changes immediately — no restart needed.

## What Naveen / you see in the sheet

Every tab is a live table. You can:
- Filter by status, lead, rating
- Download as CSV / Excel
- Build charts directly in Google Sheets
- No one else has access — only the service account writes to it
