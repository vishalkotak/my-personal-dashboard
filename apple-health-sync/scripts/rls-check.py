#!/usr/bin/env python3
"""
Adversarial check of the Supabase Row-Level Security setup.

Pretends to be an attacker who extracted the publishable key from the app:
creates a throwaway anonymous account and tries to read, forge, modify and delete
other people's rows. Every line should say PASS.

Side effect: leaves ONE extra anonymous user in Authentication → Users (delete it there).
Its test rows are removed at the end.

Run:  python3 -I scripts/rls-check.py
"""
import json, pathlib, re, urllib.error, urllib.request, uuid

cfg = (pathlib.Path(__file__).resolve().parent.parent / "Config/Secrets.xcconfig").read_text()
URL = re.search(r"SUPABASE_URL\s*=\s*(\S+)", cfg).group(1).replace("$()", "")
KEY = re.search(r"SUPABASE_PUBLISHABLE_KEY\s*=\s*(\S+)", cfg).group(1)
TABLE = "/rest/v1/health_samples"


def call(method, path, body=None, token=None, headers=None):
    h = {"apikey": KEY, "Content-Type": "application/json", **(headers or {})}
    if token:
        h["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(URL + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def check(name, ok, detail):
    print(f"{'PASS' if ok else 'FAIL'}  {name}  ({detail[:120]})")


def row(**extra):
    return {"hk_uuid": str(uuid.uuid4()), "type": "rls-check", "unit": "x", "value": 1,
            "start_date": "2026-01-01T00:00:00Z", "end_date": "2026-01-01T00:00:00Z", **extra}


status, body = call("GET", TABLE + "?select=id&limit=1")
check("no session cannot read", status in (401, 403), body)

status, body = call("POST", "/auth/v1/signup", {})
token, me = json.loads(body)["access_token"], json.loads(body)["user"]["id"]
print(f"      attacker account: {me}")

status, body = call("GET", TABLE + "?select=user_id&user_id=neq." + me, token=token)
check("cannot read other users' rows", status == 200 and json.loads(body) == [], body)

status, body = call("POST", TABLE, row(user_id=str(uuid.uuid4())), token=token)
check("cannot insert as another user", status in (401, 403), body)

status, body = call("PATCH", TABLE + "?id=gt.0", {"value": 999}, token=token)
check("cannot update any row", status in (401, 403), body)

status, body = call("DELETE", TABLE + "?user_id=neq." + me, token=token, headers={"Prefer": "return=representation"})
check("cannot delete other users' rows", status in (200, 204) and body in ("", "[]"), body)

status, body = call("POST", TABLE, row(metadata={"junk": "A" * 200_000}), token=token)
check("oversized row rejected", status == 400, body)

call("DELETE", TABLE + "?user_id=eq." + me, token=token)
print("      cleaned up test rows; delete the attacker user in Authentication → Users")
