"""Minimal Clerk Backend API authentication for the Python API."""
from __future__ import annotations
import base64, json
import requests
from tuton import config

API = "https://api.clerk.com/v1"
SECRET = config.env("CLERK_SECRET_KEY")


def _payload(token: str) -> dict:
    try:
        part = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    except (IndexError, ValueError, json.JSONDecodeError):
        return {}


def authenticate(token: str) -> dict | None:
    if not SECRET or not token:
        return None
    sid = _payload(token).get("sid")
    if not sid:
        return None
    try:
        r = requests.get(f"{API}/sessions/{sid}", headers={"Authorization": f"Bearer {SECRET}"}, timeout=10)
        if not r.ok:
            return None
        session = r.json()
        if session.get("status") != "active":
            return None
        uid = session.get("user_id")
        u = requests.get(f"{API}/users/{uid}", headers={"Authorization": f"Bearer {SECRET}"}, timeout=10)
        if not u.ok:
            return None
        data = u.json()
        emails = data.get("email_addresses") or []
        email = next((x.get("email_address", "") for x in emails if x.get("id") == data.get("primary_email_address_id")), "")
        return {"id": uid, "email": email, "name": " ".join(x for x in [data.get("first_name"), data.get("last_name")] if x)}
    except requests.RequestException:
        return None
