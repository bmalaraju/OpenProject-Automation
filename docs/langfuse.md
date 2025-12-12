Langfuse Observability (Dev on WSL)

Overview
- Optional, fail-open tracing for Router + MCP (OpenProject server).
- Default disabled; enable by setting env vars.

Run Langfuse on WSL
- Prereqs: WSL2 + Docker Desktop with WSL integration.
- In WSL shell: clone the Langfuse self-host repo and `docker compose up -d`.
- Open http://localhost:3000, create admin + project, generate keys.

Environment (.env)
- LANGFUSE_ENABLED=0 (set to 1 to enable)
- LANGFUSE_HOST=http://localhost:3000
- LANGFUSE_PUBLIC_KEY=...
- LANGFUSE_SECRET_KEY=...
- LANGFUSE_SAMPLE_RATE=0.25
- LANGFUSE_ERROR_SAMPLE_RATE=1.0
- LANGFUSE_MAX_QUEUE=1000
- LANGFUSE_FLUSH_INTERVAL_MS=1000
- LANGFUSE_MASK_FIELDS=email,username,customer,summary,description

What is captured
- Router: traces for Influx read, compile+validate, apply per domain.
- MCP server (OpenProject): per-tool traces; apply trace includes counts and basic timings.
- Errors are recorded as events with type and message.

Privacy
- No sensitive payloads are sent by default. Only safe attributes.
- Redaction is controlled via LANGFUSE_MASK_FIELDS. Do not include tokens.

Enable in Dev
1) Ensure Langfuse is reachable at LANGFUSE_HOST.
2) Set LANGFUSE_ENABLED=1 in your shell or .env.
3) Run a short router command (offline or online). Example:

```
$env:LANGFUSE_ENABLED = '1'
$env:PYTHONPATH = (Resolve-Path .).Path + ';' + (Resolve-Path .\wp-jira-agent).Path
python agent_v2\scripts\router.py --source excel --file work_packages.xlsx --sheet AN --offline --registry agent_v2\config\product_project_registry.json --dry-run
```

Dashboards / Queries (Langfuse UI)
- Filter by name: `router.apply`, `router.compile_validate`, `router.influx.read`, `mcp.openproject.apply`, `mcp.openproject.discover_fieldmap`.
- Track p95 latency and error rates.

Troubleshooting
- No traces: verify LANGFUSE_ENABLED=1 and keys/host set; app continues without tracing.
- Network errors to Langfuse: traces are dropped; app unaffected.
- Excess volume: lower LANGFUSE_SAMPLE_RATE or disable temporarily.

