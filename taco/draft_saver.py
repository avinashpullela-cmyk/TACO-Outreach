"""Step 5: Save email drafts to Zoho Mail via IMAP APPEND."""

import imaplib
import email.utils
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone


def _build_mime(from_addr: str, to_addr: str, subject: str, body: str) -> bytes:
    msg = MIMEMultipart("alternative")
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid()
    msg.attach(MIMEText(body, "plain", "utf-8"))
    return msg.as_bytes()


def save_draft(cfg: dict, to_addr: str, subject: str, body: str) -> bool:
    """Append one draft to the Zoho Drafts folder. Returns True on success."""
    host = cfg.get("zoho_imap_host", "imappro.zoho.com")
    port = int(cfg.get("zoho_imap_port", 993))
    user = cfg["zoho_email"]
    password = cfg["zoho_app_password"]
    from_addr = cfg.get("from_email", user)

    raw = _build_mime(from_addr, to_addr, subject, body)
    flags = r"(\Draft)"
    imap_date = imaplib.Time2Internaldate(datetime.now(timezone.utc).timestamp())

    try:
        mail = imaplib.IMAP4_SSL(host, port)
        mail.login(user, password)

        drafts_folder = _find_drafts_folder(mail)
        mail.append(drafts_folder, flags, imap_date, raw)
        mail.logout()
        return True
    except Exception as exc:
        print(f"  [draft_saver] Error saving draft to {to_addr}: {exc}")
        return False


def _find_drafts_folder(mail: imaplib.IMAP4_SSL) -> str:
    _, folders = mail.list()
    for f in folders:
        decoded = f.decode("utf-8", errors="replace") if isinstance(f, bytes) else f
        lower = decoded.lower()
        if "draft" in lower:
            # Extract folder name from pattern: (\HasNoChildren) "/" "Drafts"
            parts = decoded.split('"')
            name = parts[-2] if len(parts) >= 3 else "Drafts"
            return name
    return "Drafts"
