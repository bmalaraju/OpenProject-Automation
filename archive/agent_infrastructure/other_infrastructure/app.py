from __future__ import annotations

"""
Minimal serverless web app wiring HTTP routes to serverless handlers.

Endpoints:
- GET /healthz → { ok: true }
- POST /ingest-latest → handle_ingest_latest(payload)
- POST /delta-apply → handle_delta_apply(payload)
- POST /op-webhook → handle_op_webhook(payload, headers)

This module supports FastAPI (preferred) and falls back to Flask if FastAPI
is unavailable. Use `uvicorn wpr_agent.serverless.app:app --reload` for local dev.
"""

from typing import Any, Dict

from wpr_agent.serverless.handlers import (
    handle_ingest_latest,
    handle_delta_apply,
    handle_op_webhook,
)


app = None  # populated below

try:
    # Preferred: FastAPI
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse

    app = FastAPI()

    @app.get("/healthz")
    async def healthz() -> Dict[str, Any]:
        return {"ok": True}

    @app.post("/ingest-latest")
    async def ingest_latest(request: Request):
        payload = await request.json()
        res = handle_ingest_latest(payload)
        return JSONResponse(res)

    @app.post("/delta-apply")
    async def delta_apply(request: Request):
        payload = await request.json()
        res = handle_delta_apply(payload)
        return JSONResponse(res)

    @app.post("/op-webhook")
    async def op_webhook(request: Request):
        payload = await request.json()
        headers = dict(request.headers)
        res = handle_op_webhook(payload, headers)
        status = int(res.get("status", 200))
        return JSONResponse(res, status_code=status)

except Exception:
    # Fallback: Flask (if installed)
    try:
        from flask import Flask, request, jsonify

        app = Flask(__name__)

        @app.get("/healthz")
        def healthz_flask():  # type: ignore
            return jsonify({"ok": True})

        @app.post("/ingest-latest")
        def ingest_latest_flask():  # type: ignore
            payload = request.get_json(silent=True) or {}
            res = handle_ingest_latest(payload)
            return jsonify(res)

        @app.post("/delta-apply")
        def delta_apply_flask():  # type: ignore
            payload = request.get_json(silent=True) or {}
            res = handle_delta_apply(payload)
            return jsonify(res)

        @app.post("/op-webhook")
        def op_webhook_flask():  # type: ignore
            payload = request.get_json(silent=True) or {}
            res = handle_op_webhook(payload, dict(request.headers))
            status = int(res.get("status", 200))
            return jsonify(res), status

    except Exception:
        # As a last resort, expose a no-op object so importers don't fail
        class _Dummy:
            pass

        app = _Dummy()


if __name__ == "__main__":
    # Dev server for local testing if FastAPI/Flask is available
    try:
        import uvicorn  # type: ignore

        uvicorn.run("wpr_agent.serverless.app:app", host="0.0.0.0", port=8080, reload=False)
    except Exception:
        # Flask development server fallback
        try:
            app.run(host="0.0.0.0", port=8080)  # type: ignore[attr-defined]
        except Exception:
            print("No ASGI/WSGI framework available. Install fastapi or flask.")

