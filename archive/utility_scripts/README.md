# Utility Scripts Archive

**Archived:** December 2, 2025
**Reason:** One-time setup and diagnostic scripts no longer needed for operations

---

## Purpose

This archive contains utility scripts used during development for setup, diagnostics, and troubleshooting. The project now has operational tools in `/utils/` for ongoing use.

---

## Folder Structure

### 📁 setup/
**One-time configuration scripts**
- `extract_products.py` - Created initial product_project_registry.json → Registry complete
- `compare_pkgs.py` - Validated requirements.txt completeness → Environment validated

### 📁 diagnostics/  
**Troubleshooting and inspection tools**
- `find_batch_id.py` - Find InfluxDB batch ID by filename → Batch IDs now documented
- `count_influx_records.py` - Count records for batch validation → Ingestion validated
- `find_updated_order.py` - Find orders with update dates → Update testing complete
- `parse_log.py` - Simple log pattern search → Use standard grep/findstr instead

### 📁 deprecated/
**Superseded tools**
- `clear_influx_v2.py` - InfluxDB v2 API clear (old) → Superseded by clear_influx_identity.py (v3)

---

## Active Operational Tools

The following tools are kept active in `/utils/` for ongoing operations:

1. `utils/check_story_duplicates.py` - Data quality validation
2. `utils/clear_influx_identity.py` - Cache management
3. `delete_all_work_packages.py` (root) - Cleanup tool

See HANDOFF_GUIDE.md for usage instructions.

---

## Status

✅ **All setup tasks complete**
✅ **Environment validated**  
✅ **Diagnostic needs met**

These scripts are for historical reference and can serve as templates for similar future needs.
