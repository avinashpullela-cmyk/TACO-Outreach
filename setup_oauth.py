#!/usr/bin/env python3
"""One-time OAuth setup — generates google_token.json with both Sheets AND Gmail scopes.

Run this ONCE from your local machine (needs a browser):
    python3 setup_oauth.py

After running, taco_outreach.py saves drafts to Gmail automatically on every run.

Reads client_id and client_secret from config.json (never committed to git).
"""

import json
import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://mail.google.com/",
]

with open("config.json") as f:
    cfg = json.load(f)

client_secrets = {
    "installed": {
        "client_id": cfg["google_client_id"],
        "client_secret": cfg["google_client_secret"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
    }
}

with open("_client_secrets_tmp.json", "w") as f:
    json.dump(client_secrets, f)

try:
    flow = InstalledAppFlow.from_client_secrets_file("_client_secrets_tmp.json", SCOPES)
    creds = flow.run_local_server(port=0)

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes),
    }
    with open("google_token.json", "w") as f:
        json.dump(token_data, f, indent=2)
    print("\n✓ google_token.json saved with Sheets + Gmail scopes.")
    print("  taco_outreach.py will now save drafts to Gmail automatically.")
finally:
    if os.path.exists("_client_secrets_tmp.json"):
        os.remove("_client_secrets_tmp.json")
