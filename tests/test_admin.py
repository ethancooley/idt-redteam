"""The admin API: personal codes for the lab, and the usage they show. Needs the attack database."""
from __future__ import annotations

import pytest

from idt_copilot.chart.repository import ChartRepository

from idt_redteam import lab, loader
from idt_redteam.admin import handle_admin

from scripted import GullibleClaude

ADMIN = "Bearer admin-test"


@pytest.fixture()
def env(attack_db, monkeypatch):
    loader.load("clean", attack_db)
    monkeypatch.setenv("DATABASE_URL", attack_db)
    monkeypatch.setenv("REDTEAM_ADMIN_TOKEN", "admin-test")
    monkeypatch.setenv("REDTEAM_ACCESS_CODE", "owner-test")
    from idt_copilot.chart import server
    server.repo.close()
    server.repo.database_url = attack_db
    conn = ChartRepository(attack_db).conn
    conn.execute("DROP TABLE IF EXISTS lab_runs")
    from idt_copilot.api import codes
    codes.ensure_schema(conn)  # created once per process, so empty it rather than drop it
    conn.execute("TRUNCATE access_codes RESTART IDENTITY CASCADE")
    return attack_db


def test_admin_is_off_without_a_token(env, monkeypatch):
    monkeypatch.delenv("REDTEAM_ADMIN_TOKEN")
    assert handle_admin("GET", "/api/admin/codes", ADMIN)[0] == 503


def test_wrong_password_is_refused(env):
    assert handle_admin("GET", "/api/admin/codes", "Bearer nope")[0] == 401
    assert handle_admin("GET", "/api/admin/codes", None)[0] == 401


@pytest.mark.parametrize("body", [
    {"label": "", "max_runs": 3, "max_cost_usd": 1},
    {"label": "x", "max_runs": 0, "max_cost_usd": 1},
    {"label": "x", "max_runs": 3, "max_cost_usd": 0},
    {"label": "x", "max_runs": "lots", "max_cost_usd": 1},
])
def test_bad_codes_are_refused(env, body):
    assert handle_admin("POST", "/api/admin/codes", ADMIN, body)[0] == 400


def test_make_use_change_and_turn_off_a_code(env):
    status, made = handle_admin("POST", "/api/admin/codes", ADMIN,
                                {"label": "Instructor", "max_runs": 2, "max_cost_usd": 0.5, "expires_in_days": 14})
    assert status == 201 and made["code"].startswith("IDT-") and made["record"]["state"] == "active"
    code_id = made["record"]["id"]

    # A lab run on the code shows up in its usage and in the run log.
    pid = sorted(lab.lab_data()["participants"])[0]
    ticket = lab.open_lab_run({"access_code": made["code"], "participant_id": pid, "attack": "backdating"},
                              "9.9.9.9", make_client=GullibleClaude)
    assert isinstance(ticket, lab.LabRun)
    ticket.make_client = GullibleClaude
    assert list(lab.stream_lab_run(ticket))[-1]["type"] == "done"

    codes = handle_admin("GET", "/api/admin/codes", ADMIN)[1]["codes"]
    mine = next(c for c in codes if c["id"] == code_id)
    assert mine["runs_used"] == 1 and mine["cost_used_usd"] > 0 and mine["last_used_at"]
    runs = handle_admin("GET", "/api/admin/runs", ADMIN)[1]
    assert runs["today"]["runs"] == 1 and runs["all_time"]["runs"] == 1
    assert runs["runs"][0]["code_label"] == "Instructor" and runs["runs"][0]["attack"] == "backdating"
    assert runs["runs"][0]["participant"]

    status, changed = handle_admin("POST", f"/api/admin/codes/{code_id}/update", ADMIN,
                                   {"max_runs": 5, "max_cost_usd": 1, "expires": "never"})
    assert status == 200 and changed["record"]["max_runs"] == 5 and changed["record"]["expires_at"] is None

    assert handle_admin("POST", f"/api/admin/codes/{code_id}/revoke", ADMIN)[1]["record"]["state"] == "revoked"
    assert handle_admin("POST", f"/api/admin/codes/{code_id}/update", ADMIN,
                        {"max_runs": 5, "max_cost_usd": 1})[0] == 409
    refused = lab.open_lab_run({"access_code": made["code"], "participant_id": pid, "attack": "backdating"}, "9.9.9.9")
    assert isinstance(refused, tuple) and refused[0] in (401, 403)


def test_unknown_routes_and_ids(env):
    assert handle_admin("GET", "/api/admin/nothing", ADMIN)[0] == 404
    assert handle_admin("POST", "/api/admin/codes/999/revoke", ADMIN)[0] == 404


def test_http_routes(env):
    import importlib.util

    from fastapi.testclient import TestClient
    spec = importlib.util.spec_from_file_location("lab_api", "api/lab.py")
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    client = TestClient(api.app)
    assert client.get("/api/admin/codes").status_code == 401
    r = client.post("/api/admin/codes", json={"label": "Demo", "max_runs": 1, "max_cost_usd": 0.2},
                    headers={"Authorization": ADMIN})
    assert r.status_code == 201 and r.headers["cache-control"] == "no-store"
    assert client.get("/api/admin/codes", headers={"Authorization": ADMIN}).json()["codes"][0]["label"] == "Demo"
