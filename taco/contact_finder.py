"""Step 3: Contact discovery via Hunter.io → Apollo.io → flag for manual search."""

import time
import requests

PROCUREMENT_TITLES = [
    "purchasing", "procurement", "supply chain", "sourcing",
    "vp", "vice president", "director", "manager", "buyer",
    "commodity", "global supply",
]

PERSON_TITLES_APOLLO = [
    "VP Purchasing", "VP Procurement", "VP Supply Chain",
    "Director of Purchasing", "Director of Procurement",
    "Director of Supply Chain", "Director of Sourcing",
    "Purchasing Manager", "Procurement Manager",
    "Supply Chain Manager", "Sourcing Manager",
    "Senior Manager Purchasing", "Senior Manager Procurement",
    "Global Supply Manager", "Commodity Manager",
]


def _is_procurement_title(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in PROCUREMENT_TITLES)


# ── Hunter.io ──────────────────────────────────────────────────────────────────

def _hunter_search(domain: str, api_key: str) -> list[dict]:
    url = "https://api.hunter.io/v2/domain-search"
    params = {"domain": domain, "api_key": api_key, "limit": 20, "type": "personal"}
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 429:
            return None  # rate limited — signal to fall through
        resp.raise_for_status()
        data = resp.json().get("data", {})
        emails = data.get("emails", [])
        contacts = []
        for e in emails:
            title = e.get("position") or ""
            if not _is_procurement_title(title):
                continue
            first = e.get("first_name", "")
            last = e.get("last_name", "")
            contacts.append({
                "name": f"{first} {last}".strip(),
                "first_name": first,
                "title": title,
                "email": e.get("value", ""),
                "linkedin": e.get("linkedin", ""),
                "confidence": e.get("confidence", 0),
                "source": "Hunter.io",
            })
        contacts.sort(key=lambda x: x["confidence"], reverse=True)
        return contacts[:2]
    except Exception as exc:
        print(f"  [hunter] Error for {domain}: {exc}")
        return []


# ── Apollo.io ──────────────────────────────────────────────────────────────────

def _apollo_search(company_name: str, api_key: str) -> list[dict]:
    headers = {"Content-Type": "application/json", "x-api-key": api_key}

    search_url = "https://api.apollo.io/api/v1/mixed_people/api_search"
    payload = {
        "q_organization_name": company_name,
        "person_titles": PERSON_TITLES_APOLLO,
        "page": 1,
        "per_page": 10,
    }
    try:
        resp = requests.post(search_url, json=payload, headers=headers, timeout=20)
        resp.raise_for_status()
        people = resp.json().get("people", [])
    except Exception as exc:
        print(f"  [apollo] Search error for {company_name}: {exc}")
        return []

    company_lower = company_name.lower()
    candidates = []
    for p in people:
        org = p.get("organization", {}) or {}
        if company_lower not in (org.get("name") or "").lower():
            continue
        if not p.get("has_email"):
            continue
        candidates.append(p)

    contacts = []
    for p in candidates[:4]:
        pid = p.get("id")
        if not pid:
            continue
        match_url = "https://api.apollo.io/api/v1/people/match"
        try:
            mr = requests.post(match_url, json={"id": pid}, headers=headers, timeout=15)
            mr.raise_for_status()
            person = mr.json().get("person", {})
            email_addr = person.get("email", "")
            if not email_addr:
                continue
            first = person.get("first_name", "")
            last = person.get("last_name", "")
            title = person.get("title", "")
            linkedin = ""
            for acct in person.get("account", {}).get("linkedin_uid", ""):
                pass
            linkedin_url = person.get("linkedin_url", "")
            contacts.append({
                "name": f"{first} {last}".strip(),
                "first_name": first,
                "title": title,
                "email": email_addr,
                "linkedin": linkedin_url,
                "confidence": 85,
                "source": "Apollo",
            })
            if len(contacts) >= 2:
                break
            time.sleep(0.5)
        except Exception as exc:
            print(f"  [apollo] Match error for person {pid}: {exc}")

    return contacts


# ── Public entry point ─────────────────────────────────────────────────────────

def find_contacts(company_name: str, domain: str, cfg: dict) -> tuple[list[dict], str]:
    """Return (contacts_list, source_used). Falls back Hunter → Apollo → flag."""
    hunter_key = cfg.get("hunter_api_key", "")
    apollo_key = cfg.get("apollo_api_key", "")

    # Priority 1: Hunter.io
    if hunter_key:
        result = _hunter_search(domain, hunter_key)
        if result is None:
            print(f"  [hunter] Rate limited for {domain}, trying Apollo")
        elif result:
            return result, "Hunter.io"

    # Priority 2: Apollo.io
    if apollo_key:
        result = _apollo_search(company_name, apollo_key)
        if result:
            return result, "Apollo"

    # Priority 3: flag for manual search
    return [], "needs_manual"
