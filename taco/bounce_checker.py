"""Step 0: Check Zoho IMAP for bounce/undeliverable messages from the past 2 days."""

import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta, timezone
import re


BOUNCE_KEYWORDS = [
    "undeliverable", "delivery failed", "delivery failure",
    "mail delivery failed", "returned mail", "mailer-daemon",
    "delivery status notification", "non-delivery", "bounce",
    "could not be delivered", "user unknown", "no such user",
    "address rejected", "invalid address",
]


def _decode_str(s):
    if isinstance(s, bytes):
        return s.decode("utf-8", errors="replace")
    return s or ""


def check_bounces(cfg) -> list[dict]:
    """Connect to Zoho IMAP and return list of bounced email addresses found in last 2 days."""
    host = cfg.get("zoho_imap_host", "imappro.zoho.com")
    port = int(cfg.get("zoho_imap_port", 993))
    user = cfg["zoho_email"]
    password = cfg["zoho_app_password"]

    cutoff = datetime.now(timezone.utc) - timedelta(days=2)
    bounced = []

    try:
        mail = imaplib.IMAP4_SSL(host, port)
        mail.login(user, password)
        mail.select("INBOX")

        since_date = cutoff.strftime("%d-%b-%Y")
        _, msg_ids = mail.search(None, f'(SINCE "{since_date}")')

        for mid in (msg_ids[0].split() if msg_ids[0] else []):
            _, data = mail.fetch(mid, "(RFC822)")
            raw = data[0][1] if data and data[0] else None
            if not raw:
                continue

            msg = email.message_from_bytes(raw)
            subject = _decode_str(decode_header(msg.get("Subject", ""))[0][0])
            from_addr = _decode_str(msg.get("From", "")).lower()

            subject_lower = subject.lower()
            is_bounce = (
                "mailer-daemon" in from_addr
                or any(kw in subject_lower for kw in BOUNCE_KEYWORDS)
            )
            if not is_bounce:
                continue

            body = _extract_body(msg)
            original_to = _find_original_recipient(msg, body)
            if original_to:
                date_str = _parse_date(msg.get("Date", ""))
                bounced.append({"email": original_to, "date": date_str, "subject": subject})

        mail.logout()
    except Exception as exc:
        print(f"  [bounce_checker] IMAP error: {exc}")

    return bounced


def _extract_body(msg) -> str:
    parts = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() in ("text/plain", "message/delivery-status"):
                try:
                    parts.append(part.get_payload(decode=True).decode("utf-8", errors="replace"))
                except Exception:
                    pass
    else:
        try:
            parts.append(msg.get_payload(decode=True).decode("utf-8", errors="replace"))
        except Exception:
            pass
    return "\n".join(parts)


def _find_original_recipient(msg, body: str) -> str | None:
    # Check original-recipient / final-recipient headers in delivery-status parts
    patterns = [
        r"(?:final-recipient|original-recipient):\s*rfc822;\s*([\w.+\-]+@[\w.\-]+)",
        r"to:\s*([\w.+\-]+@[\w.\-]+)",
        r"<([\w.+\-]+@[\w.\-]+)>",
        r"([\w.+\-]+@[\w.\-]+)",
    ]
    # Prefer headers first
    for header in ("X-Failed-Recipients", "X-Original-To"):
        val = msg.get(header, "")
        if val:
            return val.strip().lower()

    for pattern in patterns:
        m = re.search(pattern, body, re.IGNORECASE)
        if m:
            addr = m.group(1).lower()
            if not addr.endswith(("zoho.com", "gmail.com", "mailer-daemon")):
                return addr
    return None


def _parse_date(date_str: str) -> str:
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")
