# MCP Integration for WPR Agent (OpenProject)

## Overview
- Introduces a Model Context Protocol (MCP) server for WPR Agent operations.
- Provides tools for:
    - **Ingestion**: `wpr.upload_excel_to_influx`
    - **State**: `wpr.get_source_hash`, `wpr.update_source_hash`, `wpr.resolve_identity`, `wpr.register_identity`
    - **OpenProject**: `openproject.discover_fieldmap`, `openproject.apply_openproject_plan`
    - **Observability**: `observability.tracing_config_summary`

## Client Configuration
- Enable MCP: set `MCP_WPR_TRANSPORT` to `stdio` or `ws` (or `http`/`https`).
- **stdio** (default/local):
    - `MCP_WPR_CMD`: Command to run the server (e.g., `uvicorn wpr_agent.mcp.servers.http_app_wpr:app` or internal).
    - *Note*: The client adapter currently supports in-process `stdio` automatically if `MCP_WPR_TRANSPORT=stdio` without a command, using `wpr_agent.mcp.servers.wpr_server.build_server`.
- **http/ws** (remote):
    - `MCP_WPR_URL`: URL to the MCP server (e.g., `http://localhost:8766/sse`).

## Server
- **File**: `src/wpr_agent/mcp/servers/wpr_server.py`
- **Tools**:
    - `wpr.upload_excel_to_influx(file_path, sheet, batch_id)`
    - `wpr.get_source_hash(project_key, order_id)`
    - `wpr.update_source_hash(project_key, order_id, src_hash)`
    - `wpr.resolve_identity(project_key, order_id, issue_type)`
    - `wpr.register_identity(project_key, order_id, issue_key, issue_type, ...)`
    - `openproject.discover_fieldmap(project_key)`
    - `openproject.apply_openproject_plan(project_key, items)`
- **Transport**:
    - **In-Process**: Used by default in CLI scripts.
    - **HTTP (SSE)**: `src/wpr_agent/mcp/servers/http_app_wpr.py`. Run with `uvicorn`.

## Runbook (Dev/Local)
1. **Start Server (HTTP)**:
   ```bash
   uvicorn wpr_agent.mcp.servers.http_app_wpr:app --host 0.0.0.0 --port 8766
   ```
2. **Configure Client**:
   ```bash
   set MCP_WPR_TRANSPORT=http
   set MCP_WPR_URL=http://localhost:8766/sse
   ```

## Dependencies
- `fastmcp`
- `uvicorn` (for HTTP server)




