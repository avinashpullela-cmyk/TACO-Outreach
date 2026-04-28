"""Google Sheets read/write for the TACO Outreach Tracker tab.

Uses requests directly to avoid httplib2 SSL issues in proxy environments.
"""

import json
from datetime import datetime
from urllib.parse import quote

import requests

SHEET_TAB = "TACO Outreach Tracker"
SHEETS_BASE = "https://sheets.googleapis.com/v4/spreadsheets"


def _get_token(cfg: dict) -> str:
    token_path = cfg.get("google_token_path", "google_token.json")
    with open(token_path) as f:
        tok = json.load(f)

    # Refresh if needed (best-effort; token may still be valid)
    try:
        r = requests.post(tok["token_uri"], data={
            "client_id": tok["client_id"],
            "client_secret": tok["client_secret"],
            "refresh_token": tok["refresh_token"],
            "grant_type": "refresh_token",
        }, timeout=15)
        if r.status_code == 200:
            new_token = r.json()["access_token"]
            tok["token"] = new_token
            with open(token_path, "w") as f:
                json.dump(tok, f, indent=2)
            return new_token
    except Exception:
        pass

    return tok.get("token") or tok.get("access_token", "")


def _headers(cfg: dict) -> dict:
    return {"Authorization": f"Bearer {_get_token(cfg)}", "Content-Type": "application/json"}


def _range_url(sheet_id: str, range_: str) -> str:
    return f"{SHEETS_BASE}/{sheet_id}/values/{quote(range_, safe='')}"


def get_existing_companies(cfg: dict) -> set[str]:
    """Return lowercase set of company names already in the TACO Outreach Tracker."""
    sheet_id = cfg["google_sheet_id"]
    range_ = f"'{SHEET_TAB}'!B:B"
    r = requests.get(_range_url(sheet_id, range_), headers=_headers(cfg), timeout=20)
    r.raise_for_status()
    values = r.json().get("values", [])
    companies = set()
    for row in values[1:]:
        if row:
            companies.add(row[0].strip().lower())
    return companies


def get_followup_rows(cfg: dict) -> list[dict]:
    """Return rows where Status is Sent/Followed Up, Next_Followup <= today, Followup_Count < 3."""
    sheet_id = cfg["google_sheet_id"]
    range_ = f"'{SHEET_TAB}'!A:N"
    r = requests.get(_range_url(sheet_id, range_), headers=_headers(cfg), timeout=20)
    r.raise_for_status()
    values = r.json().get("values", [])
    if len(values) < 2:
        return []

    today = datetime.now().date()
    due_rows = []
    for i, row in enumerate(values[1:], start=2):
        row = row + [""] * (14 - len(row))
        status = row[9].strip()
        next_fu = row[12].strip()
        fu_count = row[11].strip()

        if status not in ("Sent", "Followed Up"):
            continue
        try:
            fu_count_int = int(fu_count) if fu_count else 0
        except ValueError:
            fu_count_int = 0
        if fu_count_int >= 3:
            continue
        try:
            fu_date = datetime.strptime(next_fu, "%Y-%m-%d").date()
        except ValueError:
            continue
        if fu_date > today:
            continue

        due_rows.append({
            "row_index": i,
            "date_sent": row[0], "company": row[1], "sector": row[2],
            "contact_name": row[3], "title": row[4], "email": row[5],
            "linkedin": row[6], "country": row[7], "email_subject": row[8],
            "status": status, "notes": row[10],
            "followup_count": fu_count_int, "next_followup": next_fu,
            "followup_notes": row[13],
        })
    return due_rows


def append_lead_rows(cfg: dict, rows: list[list]) -> None:
    """Append new rows to the TACO Outreach Tracker tab."""
    sheet_id = cfg["google_sheet_id"]
    range_ = f"'{SHEET_TAB}'!A:N"
    url = _range_url(sheet_id, range_) + ":append?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS"
    r = requests.post(url, headers=_headers(cfg), json={"values": rows}, timeout=20)
    r.raise_for_status()


def update_row(cfg: dict, row_index: int, row_data: list) -> None:
    """Overwrite a specific row (1-based) in the TACO Outreach Tracker."""
    sheet_id = cfg["google_sheet_id"]
    range_ = f"'{SHEET_TAB}'!A{row_index}:N{row_index}"
    url = _range_url(sheet_id, range_) + "?valueInputOption=USER_ENTERED"
    r = requests.put(url, headers=_headers(cfg), json={"values": [row_data]}, timeout=20)
    r.raise_for_status()


def mark_bounced(cfg: dict, email_addr: str, bounce_date: str) -> bool:
    """Find a row by email and mark it as bounced. Returns True if found."""
    sheet_id = cfg["google_sheet_id"]
    range_ = f"'{SHEET_TAB}'!A:N"
    r = requests.get(_range_url(sheet_id, range_), headers=_headers(cfg), timeout=20)
    r.raise_for_status()
    values = r.json().get("values", [])

    for i, row in enumerate(values[1:], start=2):
        row = row + [""] * (14 - len(row))
        if row[5].strip().lower() == email_addr.lower():
            row[9] = "Email Invalid — Bounced"
            row[10] = f"Bounce received {bounce_date}. Email address incorrect — do not retry."
            update_row(cfg, i, row)
            return True
    return False
