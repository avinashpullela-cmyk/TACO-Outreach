"""Google Sheets read/write for the TACO Outreach Tracker tab."""

import json
import os
from datetime import datetime

import requests
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


SHEET_TAB = "TACO Outreach Tracker"
COLUMNS = [
    "Date Sent", "Company", "Sector", "Contact Name", "Title",
    "Email", "LinkedIn", "Country", "Email Subject", "Status",
    "Notes", "Followup_Count", "Next_Followup", "Followup_Notes",
]


def _load_creds(cfg: dict) -> Credentials:
    token_path = cfg.get("google_token_path", "google_token.json")
    with open(token_path) as f:
        token_data = json.load(f)

    creds = Credentials(
        token=token_data.get("token") or token_data.get("access_token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_data.get("client_id"),
        client_secret=token_data.get("client_secret"),
        scopes=token_data.get("scopes", ["https://www.googleapis.com/auth/spreadsheets"]),
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_data["token"] = creds.token
        token_data["access_token"] = creds.token
        with open(token_path, "w") as f:
            json.dump(token_data, f, indent=2)

    return creds


def _service(cfg: dict):
    return build("sheets", "v4", credentials=_load_creds(cfg), cache_discovery=False)


def get_existing_companies(cfg: dict) -> set[str]:
    """Return set of company names already in the TACO Outreach Tracker (column B)."""
    sheet_id = cfg["google_sheet_id"]
    svc = _service(cfg)
    result = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{SHEET_TAB}'!B:B",
    ).execute()
    values = result.get("values", [])
    companies = set()
    for row in values[1:]:  # skip header
        if row:
            companies.add(row[0].strip().lower())
    return companies


def get_followup_rows(cfg: dict) -> list[dict]:
    """Return rows where Status is Sent/Followed Up, Next_Followup <= today, Followup_Count < 3."""
    sheet_id = cfg["google_sheet_id"]
    svc = _service(cfg)
    result = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{SHEET_TAB}'!A:N",
    ).execute()
    values = result.get("values", [])
    if len(values) < 2:
        return []

    today = datetime.now().date()
    due_rows = []
    for i, row in enumerate(values[1:], start=2):  # row index 1-based, skip header
        row = row + [""] * (14 - len(row))  # pad to 14 columns
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
            "date_sent": row[0],
            "company": row[1],
            "sector": row[2],
            "contact_name": row[3],
            "title": row[4],
            "email": row[5],
            "linkedin": row[6],
            "country": row[7],
            "email_subject": row[8],
            "status": status,
            "notes": row[10],
            "followup_count": fu_count_int,
            "next_followup": next_fu,
            "followup_notes": row[13],
        })
    return due_rows


def append_lead_rows(cfg: dict, rows: list[list]) -> None:
    """Append new rows to the TACO Outreach Tracker tab."""
    sheet_id = cfg["google_sheet_id"]
    svc = _service(cfg)
    svc.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"'{SHEET_TAB}'!A:N",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()


def update_row(cfg: dict, row_index: int, row_data: list) -> None:
    """Overwrite a specific row (1-based index) in the TACO Outreach Tracker."""
    sheet_id = cfg["google_sheet_id"]
    svc = _service(cfg)
    range_notation = f"'{SHEET_TAB}'!A{row_index}:N{row_index}"
    svc.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=range_notation,
        valueInputOption="USER_ENTERED",
        body={"values": [row_data]},
    ).execute()


def mark_bounced(cfg: dict, email_addr: str, bounce_date: str) -> bool:
    """Find a row by email and update Status + Notes for bounce. Returns True if found."""
    sheet_id = cfg["google_sheet_id"]
    svc = _service(cfg)
    result = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{SHEET_TAB}'!A:N",
    ).execute()
    values = result.get("values", [])

    for i, row in enumerate(values[1:], start=2):
        row = row + [""] * (14 - len(row))
        if row[5].strip().lower() == email_addr.lower():
            row[9] = "Email Invalid — Bounced"
            row[10] = f"Bounce received {bounce_date}. Email address incorrect — do not retry."
            update_row(cfg, i, row)
            return True
    return False
