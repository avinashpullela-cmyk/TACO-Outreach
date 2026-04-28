"""Step 5: Save email drafts.

Strategy (tried in order):
  1. Gmail API (HTTPS, port 443) — works everywhere.
     Requires google_token.json to include https://mail.google.com/ scope.
     Run setup_oauth.py once to generate a combined Sheets+Gmail token.
  2. Zoho IMAP (port 993) — fallback when running locally.

When Claude executes the daily cycle directly, Gmail drafts are created via
the Gmail MCP tool in Claude's context — this file is used for standalone runs.
"""

import base64
import email.utils
import imaplib
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone

import requests

GMAIL_SCOPE = "https://mail.google.com/"


# ── Gmail API ──────────────────────────────────────────────────────────────────

def _gmail_access_token(cfg: dict) -> str | None:
    """Return a fresh Gmail access token, or None if scope not available."""
    token_path = cfg.get("google_token_path", "google_token.json")
    try:
        with open(token_path) as f:
            tok = json.load(f)
    except FileNotFoundError:
        return None

    if GMAIL_SCOPE not in tok.get("scopes", []):
        return None  # token not consented for Gmail — run setup_oauth.py

    r = requests.post(tok["token_uri"], data={
        "client_id": tok["client_id"],
        "client_secret": tok["client_secret"],
        "refresh_token": tok["refresh_token"],
        "grant_type": "refresh_token",
    }, timeout=15)
    if r.status_code != 200:
        return None
    new_token = r.json()["access_token"]
    tok["token"] = new_token
    with open(token_path, "w") as f:
        json.dump(tok, f, indent=2)
    return new_token


def _save_gmail_draft(cfg: dict, to_addr: str, subject: str, body: str) -> bool:
    token = _gmail_access_token(cfg)
    if not token:
        return False

    from_addr = cfg.get("from_email", cfg.get("zoho_email", ""))
    msg = MIMEText(body, "plain", "utf-8")
    msg["To"] = to_addr
    msg["From"] = from_addr
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    r = requests.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/drafts",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"message": {"raw": raw}},
        timeout=15,
    )
    if r.status_code in (200, 201):
        return True
    print(f"  [draft_saver] Gmail API {r.status_code}: {r.text[:100]}")
    return False


# ── Zoho IMAP ─────────────────────────────────────────────────────────────────

def _build_mime(from_addr: str, to_addr: str, subject: str, body: str) -> bytes:
    msg = MIMEMultipart("alternative")
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid()
    msg.attach(MIMEText(body, "plain", "utf-8"))
    return msg.as_bytes()


def _save_zoho_draft(cfg: dict, to_addr: str, subject: str, body: str) -> bool:
    host = cfg.get("zoho_imap_host", "imappro.zoho.com")
    port = int(cfg.get("zoho_imap_port", 993))
    user = cfg["zoho_email"]
    password = cfg["zoho_app_password"]
    from_addr = cfg.get("from_email", user)

    raw = _build_mime(from_addr, to_addr, subject, body)
    flags = r"(\Draft)"
    imap_date = imaplib.Time2Internaldate(datetime.now(timezone.utc).timestamp())
    try:
        mail = imaplib.IMAP4_SSL(host, port, timeout=10)
        mail.login(user, password)
        drafts_folder = _find_drafts_folder(mail)
        mail.append(drafts_folder, flags, imap_date, raw)
        mail.logout()
        return True
    except Exception as exc:
        print(f"  [draft_saver] Zoho IMAP error: {exc}")
        return False


def _find_drafts_folder(mail: imaplib.IMAP4_SSL) -> str:
    _, folders = mail.list()
    for f in folders:
        decoded = f.decode("utf-8", errors="replace") if isinstance(f, bytes) else f
        if "draft" in decoded.lower():
            parts = decoded.split('"')
            return parts[-2] if len(parts) >= 3 else "Drafts"
    return "Drafts"


# ── Public entry point ────────────────────────────────────────────────────────

def save_draft(cfg: dict, to_addr: str, subject: str, body: str) -> bool:
    """Save draft via Gmail API first, then Zoho IMAP as fallback."""
    if _save_gmail_draft(cfg, to_addr, subject, body):
        print(f"    ✓ Draft saved to Gmail")
        return True
    if _save_zoho_draft(cfg, to_addr, subject, body):
        print(f"    ✓ Draft saved to Zoho")
        return True
    print(f"    ⚠ Could not save draft (run setup_oauth.py to enable Gmail API)")
    return False
