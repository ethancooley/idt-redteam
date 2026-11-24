"""Admin API for the attack lab's personal access codes, modeled on IDT Prep Copilot's admin console.

Every request needs the admin password (REDTEAM_ADMIN_TOKEN) as a bearer token; admin is off entirely when it
isn't set. Codes live in the lab's own database and use IDT Prep Copilot's code system (idt_copilot.api.codes):
only a fingerprint of each code is stored, so a new code is shown once, when it is made.

    GET  /api/admin/codes                 every code with its usage (never the codes themselves)
    POST /api/admin/codes                 make one: {label, max_runs, max_cost_usd, expires_in_days}
    POST /api/admin/codes/<id>/update     change limits: {max_runs, max_cost_usd, expires: "keep" | "never" | days}
    POST /api/admin/codes/<id>/revoke     turn a code off for good
    GET  /api/admin/runs                  recent lab runs, totals for today, and spending by code
"""
from __future__ import annotations

import hmac
import os
import re
import time

from idt_copilot.api import codes
from idt_copilot.chart.repository import ChartRepository

from idt_redteam.lab import LAB_RUNS_DDL


def _authorized(authorization: str | None) -> tuple[int, dict] | None:
    expected = os.environ.get("REDTEAM_ADMIN_TOKEN")
    if not expected:
        return 503, {"error": "The admin page is turned off. Set REDTEAM_ADMIN_TOKEN on the server to turn it on."}
    given = (authorization or "").removeprefix("Bearer ").strip()
    if not given or not hmac.compare_digest(given.encode(), expected.encode()):
        time.sleep(0.5)  # slow down guessing
        return 401, {"error": "That admin password is not right."}
    return None


def _int(value, name: str, low: int, high: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a whole number.") from None
    if not low <= n <= high:
        raise ValueError(f"{name} must be between {low} and {high}.")
    return n


def _money(value, name: str) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a dollar amount.") from None
    if not 0 < x <= 50:
        raise ValueError(f"{name} must be more than $0 and at most $50.")
    return x


def handle_admin(method: str, path: str, authorization: str | None, body: dict | None = None,
                 repo: ChartRepository | None = None) -> tuple[int, dict]:
    refused = _authorized(authorization)
    if refused:
        return refused
    conn = (repo or ChartRepository(use_embeddings=False)).conn
    codes.ensure_schema(conn)
    conn.execute(LAB_RUNS_DDL)
    body = body or {}

    if method == "GET" and path == "/api/admin/codes":
        return 200, {"codes": codes.list_codes(conn)}

    if method == "POST" and path == "/api/admin/codes":
        try:
            label = " ".join(str(body.get("label", "")).split())[:80]
            if not label:
                raise ValueError("Say who the code is for.")
            days = body.get("expires_in_days")
            code, record = codes.create_code(conn, label, _int(body.get("max_runs", 5), "Runs", 1, 100),
                                             _money(body.get("max_cost_usd", 0.5), "Spending limit"),
                                             _int(days, "Days", 1, 365) if days not in (None, "", 0, "0") else None)
        except ValueError as e:
            return 400, {"error": str(e)}
        return 201, {"code": code, "record": record}

    if method == "POST" and (m := re.fullmatch(r"/api/admin/codes/(\d+)/update", path)):
        expires = str(body.get("expires", "keep"))
        try:
            record = codes.update_code(conn, int(m.group(1)), _int(body.get("max_runs"), "Runs", 1, 100),
                                       _money(body.get("max_cost_usd"), "Spending limit"),
                                       None if expires in ("keep", "never") else _int(expires, "Days", 1, 365),
                                       keep_expiry=expires == "keep")
        except codes.CodeRejected as e:
            return e.status, {"error": e.message}
        except ValueError as e:
            return 400, {"error": str(e)}
        return (200, {"record": record}) if record else (404, {"error": "No code with that id."})

    if method == "POST" and (m := re.fullmatch(r"/api/admin/codes/(\d+)/revoke", path)):
        record = codes.revoke_code(conn, int(m.group(1)))
        return (200, {"record": record}) if record else (404, {"error": "No code with that id."})

    if method == "GET" and path == "/api/admin/runs":
        rows = conn.execute("""
            SELECT r.created_at, r.status, r.cost_usd, r.seconds, r.defense, r.attack,
                   p.first_name || ' ' || p.last_name AS participant, c.label AS code_label
            FROM lab_runs r
            LEFT JOIN participants p ON p.id = r.participant_id
            LEFT JOIN access_codes c ON c.id = r.code_id
            ORDER BY r.created_at DESC LIMIT 50""").fetchall()
        today = conn.execute("""
            SELECT count(*) AS runs, COALESCE(sum(cost_usd), 0) AS cost_usd FROM lab_runs
            WHERE created_at >= date_trunc('day', now())""").fetchone()
        total = conn.execute("SELECT count(*) AS runs, COALESCE(sum(cost_usd), 0) AS cost_usd FROM lab_runs").fetchone()
        return 200, {
            "runs": [{**r, "created_at": r["created_at"].isoformat(), "code_label": r["code_label"] or "Owner code"}
                     for r in rows],
            "today": {"runs": today["runs"], "cost_usd": round(float(today["cost_usd"]), 4),
                      "limit": int(os.environ.get("REDTEAM_DAILY_LIMIT", "20"))},
            "all_time": {"runs": total["runs"], "cost_usd": round(float(total["cost_usd"]), 4)},
        }

    return 404, {"error": "Not found"}
