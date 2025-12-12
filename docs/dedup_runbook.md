# WPR Agent: Idempotent Daily Runs (No Duplicates)

This guide explains how to run the router primarily via the graph to avoid duplicates across runs and update only what changed.

## Concepts

- **Identity per item**
  - Epic identity: `EPIC::{project_key}::{order_id}`. Summary format: `{product} :: {order_id}` and custom field “WPR WP Order ID”.
  - Story identity: `STORY::{project_key}::{order_id}#{i}`. Summary format: `{order_id}-{i}` and custom field “WPR WP order id” = `order_id#i`.
  - Identity is persisted in the Influx identity store and reused on later runs (prevents re-create).

- **Delta detection**
  - Graph node `filter_delta_orders_node` compares the last data time for an order (from Influx) with the last processed time per project/order. Only changed orders are allowed when `--delta-only` is set.

- **Diff-then-update**
  - Sync apply path finds existing items (summary/identity), computes field diffs, and updates only changed values. No duplicates are created.

## First Full Load (create-only, fast)

Use the async create-only path to create items without searches, then persist identity. Recommended once on a fresh OpenProject project.

PowerShell example:

```powershell
$env:PYTHONPATH = (Resolve-Path .).Path + ';' + (Resolve-Path .\src).Path
$env:OP_STORY_WORKERS = '6'  # tune as needed; reduce if 409 conflicts
python src/wpr_agent/cli/router.py `
  --source influx --since 30d `
  --online `
  --registry src/wpr_agent/config/product_project_registry.json `
  --artifact-dir artifacts `
  --report artifacts/router_report.json `
  --summary artifacts/router_summary.txt `
  --async-create-only
```

**Notes**:
- If you wiped OpenProject before this run, use the async path for speed. Identity is recorded; subsequent runs should switch to sync + delta-only.
- Concurrency: if you see `UpdateConflict` (409) in failures, lower `$env:OP_STORY_WORKERS` (e.g., `2` or `1`).

## Daily Runs (no duplicates, only changed)

Use the sync graph path with `--delta-only` to apply only changed orders. This path finds, diffs, and updates existing items; it does not recreate.

PowerShell example:

```powershell
$env:PYTHONPATH = (Resolve-Path .).Path + ';' + (Resolve-Path .\src).Path
$env:OP_STORY_WORKERS = '6'
python src/wpr_agent/cli/router.py `
  --source influx --since 24h `
  --delta-only `
  --online `
  --registry src/wpr_agent/config/product_project_registry.json `
  --artifact-dir artifacts `
  --report artifacts/router_report.json `
  --summary artifacts/router_summary.txt
```

**What this does**:
- Reads rows from Influx (last 24h).
- Filters to orders that changed since the last processed time (per project/order) when `--delta-only`.
- Compiles, validates, then applies via sync service: finds existing → computes diff → updates only changed fields.

## Guardrails to Avoid Duplicates

- Do not set `IGNORE_INFLUX_IDENTITY=1` after the first load; it bypasses the mapping and can duplicate.
- Keep subjects stable (`{product} :: {order_id}` for Epics, `{order_id}-{i}` for Stories). The sync path uses this to find existing items.
- Ensure status mapping is configured. `src/wpr_agent/config/op_custom_option_overrides.json` contains option hrefs for “WPR WP Order Status” (e.g., Approved). This makes status writes deterministic.
- Concurrency: if 409 conflicts appear during Story creation, reduce `OP_STORY_WORKERS`.

## Validating the Run

- Preview input window:
```powershell
python src/wpr_agent/cli/preview_influx_input.py --since 24h
```
- Check outputs:
  - `artifacts/run_report.json` – totals per domain/project; failures/warnings.
  - `artifacts/router_summary.txt` – concise run summary.

**Expectations in steady state**:
- `created_epics` and `created_stories` typically 0.
- `issues_updated` > 0 only for changed orders.
- Failures near 0.

## Optional Policies (advanced)

- Terminal status freeze: define a list of statuses (e.g., Approved, Cancelled) to skip non-status updates once reached. This is optional; enable only if your process requires it.
- Sharded runner: for large cross-project runs without rate spikes:
```powershell
python src/wpr_agent/cli/run_router_sharded.py --since 24h --registry src/wpr_agent/config/product_project_registry.json --max-procs 2 --op-story-workers 4
```

## Troubleshooting

- Missing status option mapping → verify `src/wpr_agent/config/op_custom_option_overrides.json` and use `src/wpr_agent/cli/op_list_status_options.py` to inspect allowed values.
- No rows read from Influx → run `src/wpr_agent/cli/preview_influx_input.py --since 7d` and check recent batch_ids/counts.
- Duplicate-looking results → ensure you are not using `--async-create-only` for daily runs and that delta-only is enabled.

## Files & Components

- Router/Graph: `src/wpr_agent/router/graph.py`
- Influx reader/delta: `src/wpr_agent/router/tools/influx_source.py`
- Compile: `src/wpr_agent/router/tools/compile_products.py`
- Apply (sync): `src/wpr_agent/router/tools/apply.py` → `src/wpr_agent/cli/apply_plan.py`
- Apply (async first-run option): `src/wpr_agent/router/tools/apply_async.py`
- OpenProject service (sync): `src/wpr_agent/services/openproject_service_v2.py`
- OpenProject service (async): `src/wpr_agent/services/openproject_service_async.py`
- Status overrides: `src/wpr_agent/config/op_custom_option_overrides.json`


