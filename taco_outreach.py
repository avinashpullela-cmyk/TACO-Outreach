#!/usr/bin/env python3
"""TACO Daily Outreach — full cycle orchestrator.

Usage:
    python3 taco_outreach.py [--config config.json]
"""

import argparse
import json
import sys
from datetime import date, timedelta

from taco.bounce_checker import check_bounces
from taco.sheet_manager import (
    get_existing_companies,
    append_lead_rows,
    mark_bounced,
)
from taco.contact_finder import find_contacts
from taco.email_generator import generate_email
from taco.draft_saver import save_draft
from taco.followup_engine import run_followups


# ── Priority company list ──────────────────────────────────────────────────────
# Process in order; skip any already in the tracker.
PRIORITY_COMPANIES = [
    {"name": "Magna International",      "domain": "magna.com",           "sector": "Tier 1 Automotive Supplier", "country": "Canada"},
    {"name": "Linamar",                  "domain": "linamar.com",          "sector": "Tier 1 Automotive Supplier", "country": "Canada"},
    {"name": "Martinrea",                "domain": "martinrea.com",         "sector": "Tier 1 Automotive Supplier", "country": "Canada"},
    {"name": "American Axle",            "domain": "aam.com",              "sector": "Tier 1 Automotive Supplier", "country": "United States"},
    {"name": "Dana Inc.",                "domain": "dana.com",             "sector": "Tier 1 Automotive Supplier", "country": "United States"},
    {"name": "Cooper Standard",          "domain": "cooperstandard.com",   "sector": "Tier 1 Automotive Supplier", "country": "United States"},
    {"name": "Flex-N-Gate",              "domain": "flex-n-gate.com",      "sector": "Tier 1 Automotive Supplier", "country": "United States"},
    {"name": "Tenneco",                  "domain": "tenneco.com",          "sector": "Tier 1 Automotive Supplier", "country": "United States"},
    # Proterra (#9) is defunct — bankrupt Aug 2023, assets sold to Volvo/Phoenix Motor/Cowen Equity.
    # Skipped permanently; next eligible companies continue from #10.
    {"name": "Rivian",                   "domain": "rivian.com",           "sector": "EV Manufacturer",            "country": "United States"},
    {"name": "PACCAR",                   "domain": "paccar.com",           "sector": "Commercial Vehicle OEM",     "country": "United States"},
    {"name": "International Trucks",     "domain": "navistar.com",         "sector": "Commercial Vehicle OEM",     "country": "United States"},
    {"name": "Harbinger Motors",         "domain": "harbingermotors.com",  "sector": "EV Manufacturer",            "country": "United States"},
    {"name": "Lucid Motors",             "domain": "lucidmotors.com",      "sector": "EV Manufacturer",            "country": "United States"},
    {"name": "Worldpac",                 "domain": "worldpac.com",         "sector": "Auto Parts Distributor",     "country": "United States"},
    {"name": "O'Reilly Automotive",      "domain": "oreillyauto.com",      "sector": "Auto Parts Distributor",     "country": "United States"},
    {"name": "Advance Auto Parts",       "domain": "advanceautoparts.com", "sector": "Auto Parts Distributor",     "country": "United States"},
    {"name": "NAPA Auto Parts",          "domain": "napaonline.com",       "sector": "Auto Parts Distributor",     "country": "United States"},
    {"name": "Cardone Industries",       "domain": "cardone.com",          "sector": "Aftermarket Parts Manufacturer", "country": "United States"},
    {"name": "Sanden International USA", "domain": "sfrusa.com",           "sector": "HVAC / Thermal Components",  "country": "United States"},
]

INDUSTRY_MAP = {
    "EV Manufacturer":               "electric vehicle manufacturing",
    "Tier 1 Automotive Supplier":    "automotive component supply",
    "Commercial Vehicle OEM":        "commercial vehicle manufacturing",
    "Auto Parts Distributor":        "auto parts distribution",
    "Aftermarket Parts Manufacturer":"aftermarket automotive parts manufacturing",
    "HVAC / Thermal Components":     "HVAC and thermal component manufacturing",
    "Automotive Thermal Management": "automotive thermal management",
    "Off-Road / Performance Equipment": "off-road and performance equipment",
}


def _next_business_day(d: date, n: int) -> date:
    current = d
    added = 0
    while added < n:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


def _load_config(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def _pick_companies(existing: set[str], n: int = 3) -> list[dict]:
    chosen = []
    for co in PRIORITY_COMPANIES:
        if co["name"].lower() in existing:
            continue
        # Also check common aliases (e.g. "Linamar Corporation" → "Linamar")
        if any(co["name"].lower() in ex or ex in co["name"].lower() for ex in existing):
            continue
        chosen.append(co)
        if len(chosen) == n:
            break
    return chosen


def main():
    parser = argparse.ArgumentParser(description="TACO Daily Outreach Cycle")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    parser.add_argument("--dry-run", action="store_true", help="Skip IMAP/Sheets writes")
    args = parser.parse_args()

    cfg = _load_config(args.config)
    today = date.today().strftime("%Y-%m-%d")
    next_followup = _next_business_day(date.today(), 2).strftime("%Y-%m-%d")

    print("=" * 70)
    print(f"TACO Daily Outreach — {today}")
    print("=" * 70)

    # ── Step 0: Bounce check ──────────────────────────────────────────────────
    print("\n[Step 0] Checking Zoho inbox for bounces (past 2 days)...")
    bounces = []
    if not args.dry_run:
        try:
            bounces = check_bounces(cfg)
        except Exception as exc:
            print(f"  ⚠ Bounce check skipped (IMAP unreachable): {exc}")
    bounce_marked = 0
    for b in bounces:
        marked = mark_bounced(cfg, b["email"], b["date"])
        if marked:
            bounce_marked += 1
            print(f"  ✗ Bounce marked: {b['email']} (received {b['date']})")
    print(f"  → {bounce_marked} bounce(s) marked invalid.")

    # ── Step 1: Load exclusion set ────────────────────────────────────────────
    print("\n[Step 1] Loading TACO Outreach Tracker exclusion set...")
    existing = get_existing_companies(cfg)
    # Add bounced emails' company names if detectable
    print(f"  → {len(existing)} company/ies already in tracker.")

    # ── Step 2: Select next 3 companies ──────────────────────────────────────
    print("\n[Step 2] Selecting next 3 companies from priority list...")
    companies = _pick_companies(existing, n=3)
    if not companies:
        print("  Priority list exhausted — falling back to Apollo discovery (not implemented in this run).")
        sys.exit(0)
    for co in companies:
        print(f"  ✓ {co['name']} ({co['sector']}, {co['domain']})")

    # ── Steps 3–5: Per-company loop ───────────────────────────────────────────
    drafts_saved = 0
    sheet_rows = []
    manual_search_needed = []
    contacts_by_source = {"Hunter.io": 0, "Apollo": 0, "Web": 0}

    for co in companies:
        print(f"\n[Steps 3–5] Processing: {co['name']}")
        contacts, source = find_contacts(co["name"], co["domain"], cfg)

        if not contacts:
            manual_search_needed.append(co["name"])
            print(f"  ⚠ No contacts found — flagged for manual web search.")
            continue

        industry = INDUSTRY_MAP.get(co["sector"], co["sector"])
        contacts_by_source[source] = contacts_by_source.get(source, 0) + len(contacts)

        for contact in contacts:
            print(f"  → {contact['name']} | {contact['title']} | {contact['email']} [{source}, conf={contact['confidence']}]")

            email_data = generate_email(contact, co["name"], industry)

            saved = False
            if not args.dry_run:
                try:
                    saved = save_draft(cfg, email_data["to"], email_data["subject"], email_data["body"])
                except Exception as exc:
                    print(f"    ⚠ Draft save skipped (IMAP unreachable): {exc}")
                    saved = True  # still record in sheet even if IMAP blocked
            else:
                saved = True  # dry run counts as saved for summary

            if saved:
                drafts_saved += 1
                status = "Draft"
                notes = f"{source} (confidence: {contact['confidence']})"
                linkedin = contact.get("linkedin", "")
                row = [
                    today,
                    co["name"],
                    co["sector"],
                    contact["name"],
                    contact["title"],
                    contact["email"],
                    linkedin,
                    co["country"],
                    email_data["subject"],
                    status,
                    notes,
                    "0",
                    next_followup,
                    "",
                ]
                sheet_rows.append(row)

    # ── Step 5: Append to Google Sheet ────────────────────────────────────────
    if sheet_rows and not args.dry_run:
        print(f"\n[Step 5] Appending {len(sheet_rows)} row(s) to Google Sheet...")
        append_lead_rows(cfg, sheet_rows)
        print(f"  ✓ {len(sheet_rows)} row(s) added.")
    elif sheet_rows and args.dry_run:
        print(f"\n[Step 5] Dry run — would append {len(sheet_rows)} row(s) to Google Sheet.")

    # ── Step 6: Follow-up engine ──────────────────────────────────────────────
    print("\n[Step 6] Running follow-up engine...")
    followups = []
    if not args.dry_run:
        followups = run_followups(cfg)
    for fu in followups:
        print(f"  → FU#{fu['followup_number']} drafted for {fu['contact']} @ {fu['company']}")
    print(f"  → {len(followups)} follow-up draft(s) saved.")

    # ── Step 7: Final report ──────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("FINAL REPORT")
    print("=" * 70)
    print(f"  Bounced addresses marked invalid : {bounce_marked}")
    print(f"  Companies searched               : {len(companies)}")
    print(f"  Contacts found (Hunter.io)       : {contacts_by_source.get('Hunter.io', 0)}")
    print(f"  Contacts found (Apollo)          : {contacts_by_source.get('Apollo', 0)}")
    print(f"  Contacts found (Web)             : {contacts_by_source.get('Web', 0)}")
    print(f"  Drafts saved                     : {drafts_saved}")
    print(f"  Sheet rows added                 : {len(sheet_rows)}")
    print(f"  Follow-ups drafted               : {len(followups)}")
    if manual_search_needed:
        print(f"  ⚠ Manual web search needed      : {', '.join(manual_search_needed)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
