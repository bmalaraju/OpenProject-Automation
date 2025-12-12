# Influx Source + Delta Router (WPR Agent)

This document explains how to use the Influx source in the Router graph, automate ingestion of the latest Excel, and expose HTTP endpoints for serverless triggers.

## Overview

- **Ingestion**: Resolve latest Excel → normalize → write rows to Influx `wpr_input` with `batch_id`, `file_hash`, `source_filename`. A summary point is written to `ingestion_run` per run.
- **Delta Apply (Graph)**: Read from Influx → group by Product→Order → for each order compare the latest input point time with a per‑order checkpoint → compile→validate→apply only orders with new data. On success, persist the latest input time as the checkpoint.
- **Serverless**: Minimal FastAPI/Flask app routes to trigger ingestion and delta runs.

## Components

- **Influx Store**: `src/wpr_agent/state/influx_store.py`
  - `get_last_row_time(product, order_id, since=None, batch_id=None)` from measurement `wpr_input`.
  - `get_last_processed_time/set_last_processed_time` on measurement `order_checkpoint`.
  - `register_ingestion_run` on measurement `ingestion_run`.

- **Uploader**: `src/wpr_agent/cli/upload_excel_to_influx.py`
  - Use `--dir`/`--pattern` for latest file ingestion. Adds `batch_id`, `file_hash`, `source_filename`.
  - Skips duplicates (same `file_hash`).

- **Router Types/CLI/Graph**:
  - **Types**: `src/wpr_agent/router/types.py` → `source`, `since`, `batch_id`, `delta_only`.
  - **CLI**: `src/wpr_agent/cli/router.py` → flags for Influx and delta‑only.
  - **Graph**: `src/wpr_agent/router/graph.py`
    - Nodes: `read_influx`, `group_product_order_influx`, `filter_delta_orders`.
    - Applies only validation‑allowed ∩ orders with new input timestamps when `delta_only`.
    - Persists per‑order checkpoint time on successful online apply.

- **One‑shot Script**: `src/wpr_agent/cli/ingest_then_router.py`
  - Ingests latest (or a given) Excel, then runs the graph with Influx source + delta‑only.

- **Serverless App/Handlers**:
  - **Handlers**: `src/wpr_agent/serverless/handlers.py` → `handle_ingest_latest`, `handle_delta_apply`, `handle_op_webhook`.
  - **HTTP App**: `src/wpr_agent/serverless/app.py` → `/ingest-latest`, `/delta-apply`, `/op-webhook`, `/healthz`.

## Commands

### Ingest latest Excel into Influx

- From a directory:
  `python src/wpr_agent/cli/upload_excel_to_influx.py --dir C:\data\wpr --pattern "work_packages*.xlsx" --sheet Sheet1`
- Explicit file:
  `python src/wpr_agent/cli/upload_excel_to_influx.py --file work_packages.xlsx --sheet Sheet1`

Expected: `ok: uploaded N rows … (batch_id=YYYYMMDDHHMMSS)`.

### Run the Router graph with Influx source (delta‑only)

- Window based:
  `python src/wpr_agent/cli/router.py --source influx --since 12h --delta-only --online --registry src/wpr_agent/config/product_project_registry.json --artifact-dir artifacts --report artifacts/router_report.json --summary artifacts/router_summary.txt`
- Specific ingestion batch:
  `python src/wpr_agent/cli/router.py --source influx --batch-id 20241104T080000 --delta-only --online --registry src/wpr_agent/config/product_project_registry.json`

Use `--offline --dry-run` to preview without OpenProject writes. You may pass `--since 12h` to restrict the read window when using Influx as source.

### One‑shot: Ingest then Router

`python src/wpr_agent/cli/ingest_then_router.py --dir C:\data\wpr --pattern "work_packages*.xlsx" --sheet Sheet1 --registry src/wpr_agent/config/product_project_registry.json --online`

### Serverless HTTP (local)

Requires `fastapi` or `flask` and `uvicorn` in your environment.

- Start: `uvicorn src.wpr_agent.serverless.app:app --host 0.0.0.0 --port 8080`
- POST `/ingest-latest`:
  - Body: `{ "dir": "C:\\data\\wpr", "pattern": "work_packages*.xlsx", "sheet": "Sheet1" }`
- POST `/delta-apply`:
  - Body: `{ "since": "12h", "registry": "src/wpr_agent/config/product_project_registry.json", "online": true }`
- POST `/op-webhook`:
  - Include `X-OP-Secret` if configured; webhook is an ack and intended trigger, not a data source.

## Environment

Required:
- Influx: `INFLUX_URL`, `INFLUX_TOKEN`, `INFLUX_ORG`, `INFLUX_BUCKET`
- OpenProject: `OPENPROJECT_BASE_URL`, `OPENPROJECT_API_KEY` (Username not strictly required for API Key auth)

Optional:
- Ingestion: `INGEST_SOURCE_DIR`, `INGEST_FILE_PATTERN`, `INGEST_SHEET`, `INGEST_SKIP_DUPLICATE`
- Webhook: `OP_WEBHOOK_SECRET`

## Test Checklist

1. Ingest a sample Excel (directory or file). Confirm `wpr_input` points with `batch_id`, `file_hash`, and `ingestion_run` summary.
2. Run Router graph (offline, dry‑run) with `--source influx --delta-only --since 7d`. Confirm report shows orders and changed counts.
3. Run online apply. Confirm OpenProject work packages are created/updated; check `order_checkpoint` contains last processed timestamps for applied orders.
4. Re‑run delta apply without changes; changed count should be 0 (idempotent run).
5. Update a row in the Excel and re‑ingest; confirm only affected orders are applied.

## Notes

- The graph persists per‑order processed checkpoints (`order_checkpoint.last_ts`) — along with per‑issue fingerprints in `issue_map.last_hash` — act as guards against no‑op updates.

