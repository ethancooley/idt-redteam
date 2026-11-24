"""Vercel Function for the attack lab: POST /api/lab/run streams the agent's progress as JSON lines.

    GET  /api/health      whether live runs are on
    POST /api/lab/run     {access_code, participant_id, defense, attack, note?} -> application/x-ndjson

Locally:  REDTEAM_ACCESS_CODE=letmein DATABASE_URL=... uvicorn api.lab:app --port 8788
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # the idt_redteam package

# The chart tools read DATABASE_URL. Vercel's Neon integration may have added the connection under a prefix
# (DATABASE_URL_...), so fall back to those names, preferring a direct (non-pooled) connection.
for _name in ("DATABASE_URL_POSTGRES_URL_NON_POOLING", "DATABASE_URL_DATABASE_URL_UNPOOLED",
              "DATABASE_URL_DATABASE_URL", "POSTGRES_URL_NON_POOLING", "DATABASE_URL_UNPOOLED"):
    if not os.environ.get("DATABASE_URL") and os.environ.get(_name):
        os.environ["DATABASE_URL"] = os.environ[_name]

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse, StreamingResponse  # noqa: E402

from idt_redteam.lab import open_lab_run, stream_lab_run  # noqa: E402

MAX_BODY = 10_000
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for") or request.headers.get("x-real-ip")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "live": bool(os.environ.get("REDTEAM_ACCESS_CODE"))}


@app.post("/api/lab/run")
async def lab_run(request: Request):
    raw = await request.body()
    if len(raw) > MAX_BODY:
        return JSONResponse({"error": "Request too large."}, status_code=413)
    try:
        body = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        return JSONResponse({"error": "Request body must be JSON."}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "Request body must be a JSON object."}, status_code=400)
    try:
        opened = open_lab_run(body, client_ip(request))
    except Exception:
        traceback.print_exc()
        return JSONResponse({"error": "Something went wrong on the server. Try again in a moment."}, status_code=500)
    if isinstance(opened, tuple):
        status, payload = opened
        return JSONResponse(payload, status_code=status)

    def lines():
        try:
            for event in stream_lab_run(opened):
                yield json.dumps(event) + "\n"
        except Exception:
            traceback.print_exc()
            yield json.dumps({"type": "error", "message": "The run stopped unexpectedly."}) + "\n"

    return StreamingResponse(lines(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
