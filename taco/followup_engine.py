"""Step 6: Follow-up engine — drafts follow-ups for due rows in the tracker."""

from datetime import date, timedelta

from .sheet_manager import get_followup_rows, update_row
from .email_generator import generate_followup
from .draft_saver import save_draft


def _next_business_day(d: date, n: int) -> date:
    """Return date n business days after d."""
    current = d
    added = 0
    while added < n:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon–Fri
            added += 1
    return current


def run_followups(cfg: dict) -> list[dict]:
    """Generate follow-up drafts for all due rows. Returns list of follow-up records."""
    due_rows = get_followup_rows(cfg)
    results = []

    for row in due_rows:
        contact = {
            "name": row["contact_name"],
            "first_name": row["contact_name"].split()[0] if row["contact_name"] else "",
            "email": row["email"],
            "title": row["title"],
        }
        company = row["company"]
        fu_count = row["followup_count"]

        email_draft = generate_followup(contact, company, fu_count + 1)
        saved = save_draft(cfg, contact["email"], email_draft["subject"], email_draft["body"])

        new_fu_count = fu_count + 1
        new_next_fu = _next_business_day(date.today(), 5).strftime("%Y-%m-%d")
        existing_notes = row.get("followup_notes", "")
        note_entry = f"FU{new_fu_count} drafted {date.today().strftime('%Y-%m-%d')}"
        new_notes = f"{existing_notes}; {note_entry}".lstrip("; ")

        updated_row = [
            row["date_sent"], row["company"], row["sector"], row["contact_name"],
            row["title"], row["email"], row["linkedin"], row["country"],
            row["email_subject"], "Followed Up", row["notes"],
            str(new_fu_count), new_next_fu, new_notes,
        ]
        update_row(cfg, row["row_index"], updated_row)

        results.append({
            "company": company,
            "contact": contact["name"],
            "email": contact["email"],
            "followup_number": new_fu_count,
            "draft_saved": saved,
        })

    return results
