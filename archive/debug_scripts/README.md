# Debug Scripts Archive

**Archived:** December 2, 2025
**Reason:** All bugs identified by these scripts have been fixed in core code

---

## Purpose

This archive contains debug scripts used during development to identify and fix bugs in the backfill and delta apply processes. All findings have been incorporated into the production code.

---

## Folder Structure

### 📁 bug_discovery/
**Scripts that identified bugs (ALL FIXED)**
- `debug_payload_generation.py` - Found custom fields dropped from payload → Fixed in openproject_service_v2.py:343-345
- `debug_influx_data.py` - Found STD field mapping issue → Fixed in openproject_service_v2.py:343-345  
- `debug_update_wpo00098660.py` - Found status field conversion failure → Fixed in openproject_service_v2.py:461-502
- `debug_order_status_2.py` - Found status normalization issues → Fixed in openproject_service_v2.py:461-502
- `debug_op_404.py` - Found stale InfluxDB cache → Documented workaround (IGNORE_INFLUX_IDENTITY=1)
- `debug_apply_direct.py` - End-to-end Epic creation testing → Benefits from all above fixes

### 📁 connectivity_tests/
**Scripts that tested connectivity (ALL WORKING)**
- `debug_influx_auth.py` - InfluxDB auth testing across ports
- `debug_influx_source.py` - InfluxDB read function test
- `debug_influx_v2.py` - InfluxDB v3 SQL query test
- `debug_import.py` - influxdb_client_3 package import test

### 📁 mcp_tests/
**Scripts that tested MCP features (NOT BACKFILL/DELTA RELATED)**
- `debug_mcp_health.py` - MCP server health check
- `debug_mcp_in_process.py` - MCP in-process testing
- `debug_mcp_query.py` - MCP tool discovery

---

## Status

✅ **All bugs discovered by these scripts have been FIXED in production code**

See `debug_fixes_verification.md` artifact for complete mapping of bugs → fixes.

---

## Usage

These scripts are for **historical reference only**. They are not needed for operating the backfill/delta apply system.

If you need to recreate similar debugging scenarios, these scripts provide good templates.
