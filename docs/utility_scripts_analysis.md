# UTILITY INVESTIGATION SCRIPTS ANALYSIS

**Analysis Date:** December 2, 2025  
**Total Utility Scripts:** 11 files
**Classification:** Operational Tools vs One-Time Use

---

## CATEGORY 1: OPERATIONAL TOOLS (Keep - 3 files)

### 1. check_story_duplicates.py ✅ KEEP
**Purpose:** Find duplicate Stories in OpenProject
**What It Does:**
```python
# Scans multiple projects for Stories
# Groups by Order ID + Subject
# Identifies duplicates
# Reports WP IDs for cleanup
```

**Value:**
- **Data quality tool**
- Useful for post-backfill validation  
- Can run periodically to check for duplicates
- Helps identify misconfigured runs

**Use Cases:**
- After backfill runs to verify no duplicates
- Troubleshooting duplicate creation issues
- Regular data quality checks

**Recommendation:** ✅ **Keep in /utils/** - Operational maintenance tool

---

### 2. clear_influx_identity.py ✅ KEEP  
**Purpose:** Clear Influx DB identity cache
**What It Does:**
```python
# Drops wpr_issue_map table (Epic ID cache)
# Drops order_checkpoint table  
# Forces fresh Epic lookups on next run
# Used with IGNORE_INFLUX_IDENTITY=1
```

**Value:**
- **Critical maintenance tool**
- Fixes stale cache issues
- Required when Epics deleted manually
- Supports fresh re-imports

**Use Cases:**
- After deleting work packages from OpenProject
- When switching data sources
- Troubleshooting "parent does not exist" errors
- Fresh backfill after cleanup

**Recommendation:** ✅ **Keep in /utils/** - Essential maintenance tool
**Documented:** HANDOFF_GUIDE.md Section 4.1

---

### 3. delete_all_work_packages.py ✅ KEEP  
**Location:** `/utils/delete_all_work_packages.py`  
**Purpose:** Delete all work packages from OpenProject projects
**What It Does:**
```python
# Deletes ALL work packages from specified projects
# Preserves project structure
# Dry-run support
# Dangerous but necessary for clean slate
```

**Value:**
- **Critical cleanup tool**
- Used before fresh backfill runs
- Enables testing from clean state
- Carefully designed with safety checks

**Use Cases:**
- Clean slate before production run
- Testing backfill from scratch
- Recovering from bad backfill run

**Recommendation:** ✅ **Keep in /utils/** - Critical cleanup tool

---

## CATEGORY 2: ONE-TIME SETUP TOOLS (Archive - 4 files)

### 4. extract_products.py 📝 ARCHIVE  
**Purpose:** Extract unique products from Excel to create registry template
**What It Does:**
```python
# Reads Excel file
# Extracts unique Product values
# Creates JSON mapping template
# One-time registry setup
```

**Original Use:**
- Creating initial product_project_registry.json
- Setup task completed

**Recommendation:** 📝 **Archive to archive/utility_scripts/setup/**  
**Reason:** Registry already created, one-time use completed

---

###5. compare_pkgs.py 📝 ARCHIVE
**Purpose:** Compare installed packages vs requirements.txt
**What It Does:**
```python
# Lists missing packages
# Identifies version mismatches
# Shows extra installed packages
# Package audit tool
```

**Original Use:**
- Validating requirements.txt completeness
- Checking for package conflicts
- Environment setup validation

**Recommendation:** 📝 **Archive to archive/utility_scripts/setup/**  
**Reason:** Environment setup complete, can use `pip list` instead

---

### 6. check_mcp.py 📝 ARCHIVE (or Remove with MCP)
**Purpose:** Verify MCP package installation
**What It Does:**
```python
# Imports mcp package
# Prints version
# Simple installation check
```

**Value:** Only if keeping MCP features

**Recommendation:** ⚠️ **Archive with MCP tests** OR **Delete with MCP**

---

## CATEGORY 3: DIAGNOSTIC/INSPECTION TOOLS (Archive - 5 files)

### 7. find_batch_id.py 📝 ARCHIVE
**Purpose:** Find InfluxDB batch ID for a given Excel filename
**What It Does:**
```python
# Queries InfluxDB for batch_id by filename
# Returns latest batch for file
# Helpful for finding correct batch ID
```

**Use Case:** Finding batch ID for delta apply commands

**Current Alternative:** Batch IDs now documented/known

**Recommendation:** 📝 **Archive to archive/utility_scripts/diagnostics/**  
**Reason:** Useful template but batch IDs are now known

---

### 8. count_influx_records.py 📝 ARCHIVE
**Purpose:** Count records in InfluxDB for a batch
**What It Does:**
```python
# Filters by product registry
# Counts total records for batch
# Shows data volume
```

**Use Case:** Validating ingestion completeness

**Recommendation:** 📝 **Archive to archive/utility_scripts/diagnostics/**  
**Reason:** Ingestion validated, one-time check

---

### 9. find_updated_order.py 📝 ARCHIVE  
**Purpose:** Find orders with Updated Date populated
**What It Does:**
```python
# Queries InfluxDB batch
# Finds rows with Updated Date
# Used during update testing
```

**Use Case:** Finding test data for update scenarios

**Recommendation:** 📝 **Archive to archive/utility_scripts/diagnostics/**  
**Reason:** Update testing complete

---

### 10. inspect_wpo00098660.py 📝 ARCHIVE
**Purpose:** Inspect specific work package WPO00098660
**What It Does:**
```python
# Finds specific Epic by Order ID
# Prints custom field values
# Checks if Updated Date populated
```

**Use Case:** Debugging specific Epic during development

**Recommendation:** 📝 **Archive to archive/debug_scripts/bug_discovery/**  
**Reason:** Specific debugging, already handled

---

### 11. inspect_wpo00098663.py 📝 ARCHIVE
**Purpose:** Inspect specific work package WPO00098663  
**What It Does:**
```python
# Finds Epic/Stories for order
# Shows parent relationships
# Displays custom fields
```

**Use Case:** Debugging specific order during development

**Recommendation:** 📝 **Archive to archive/debug_scripts/bug_discovery/**  
**Reason:** Specific debugging, already handled

---

### 12. parse_log.py 📝 ARCHIVE
**Purpose:** Parse log file for specific patterns
**What It Does:**
```python
# Simple grep-like search
# Filters log lines by keywords
# 13-line utility
```

**Use Case:** Quick log analysis

**Alternative:** Use grep, findstr, or Select-String

**Recommendation:** 📝 **Archive to archive/utility_scripts/diagnostics/**  
**Reason:** Simple script, standard tools better

---

### 13. clear_influx_v2.py 📝 CONDITIONAL KEEP/ARCHIVE
**Purpose:** Clear InfluxDB using v2 API (vs v3 in clear_influx_identity.py)
**What It Does:**
```python
# Uses influxdb_client (v2 API)
# Deletes wpr_issue_map, order_checkpoint, wpr_src_fp
# Alternative to v3 version
```

**Analysis:**
- We use InfluxDB v3 (SQL-based)
- `clear_influx_identity.py` uses v3 API
- This script uses OLD v2 API

**Recommendation:** 📝 **Archive to archive/utility_scripts/deprecated/**  
**Reason:** Superseded by clear_influx_identity.py (v3 version)

---

## SUMMARY TABLE

| File | Category | Value | Destination |
|------|----------|-------|-------------|
| check_story_duplicates.py | Operational | ✅ High | /utils/ |
| clear_influx_identity.py | Operational | ✅ High | /utils/ |
| delete_all_work_packages.py | Operational | ✅ High | root (keep) |
| extract_products.py | Setup | 📝 Low | archive/utility_scripts/setup/ |
| compare_pkgs.py | Setup | 📝 Low | archive/utility_scripts/setup/ |
| check_mcp.py | MCP | ⚠️ Conditional | archive with MCP |
| find_batch_id.py | Diagnostic | 📝 Medium | archive/utility_scripts/diagnostics/ |
| count_influx_records.py | Diagnostic | 📝 Low | archive/utility_scripts/diagnostics/ |
| find_updated_order.py | Diagnostic | 📝 Low | archive/utility_scripts/diagnostics/ |
| inspect_wpo00098660.py | Debugging | 📝 Low | archive/debug_scripts/bug_discovery/ |
| inspect_wpo00098663.py | Debugging | 📝 Low | archive/debug_scripts/bug_discovery/ |
| parse_log.py | Diagnostic | 📝 Low | archive/utility_scripts/diagnostics/ |
| clear_influx_v2.py | Deprecated | 📝 Low | archive/utility_scripts/deprecated/ |

---

## RECOMMENDED STRUCTURE

### Keep Active (3 files in /utils/):
```
/utils/
├── check_story_duplicates.py      ← Moved
├── clear_influx_identity.py        ← Moved
└── delete_all_work_packages.py     ← Moved
```

### Archive (10 files):
```
archive/
├── debug_scripts/
│   └── bug_discovery/
│       ├── inspect_wpo00098660.py  ← Move here
│       └── inspect_wpo00098663.py  ← Move here
└── utility_scripts/                ← NEW
    ├── README.md
    ├── setup/
    │   ├── extract_products.py
    │   └── compare_pkgs.py
    ├── diagnostics/
    │   ├── find_batch_id.py
    │   ├── count_influx_records.py
    │   ├── find_updated_order.py
    │   └── parse_log.py
    └── deprecated/
        └── clear_influx_v2.py
```

---

## KEEP vs ARCHIVE CRITERIA

### ✅ KEEP (Operational Tools):
- **Repeatable use** - Run multiple times
- **Maintenance value** - Required for operations
- **Data quality** - Validates system health
- **Documented** - Referenced in HANDOFF_GUIDE.md

### 📝 ARCHIVE (One-Time Use):
- **Setup complete** - Initial configuration done
- **Diagnostic only** - Troubleshooting specific issues
- **Superseded** - Better tools available
- **Historical** - Development artifacts

---

## CLEANUP IMPACT

**Scripts to Keep:** 3 operational tools + 1 delete script = 4 files
**Scripts to Archive:** 10 files  

**Root Directory Cleanup:**
- Remove ~10 utility scripts from root
- Organize 3 tools into /utils/ folder
- Keep delete_all_work_packages.py in root (per guide)

**Result:** Clean, professional structure with only active tools visible

---

## USAGE RECOMMENDATIONS

### For Ongoing Operations:

1. **check_story_duplicates.py** - Run after backfill to verify data quality
2. **clear_influx_identity.py** - Run before fresh backfill or after WP cleanup
3. **delete_all_work_packages.py** - Use for clean slate (CAUTION: deletes data!)

### For Reference (Archived):

- **find_batch_id.py** - Template for finding batches
- **extract_products.py** - Template for registry creation
- **inspect_wpo*.py** - Examples of WP inspection scripts

All archived scripts serve as templates/examples but aren't needed for day-to-day operations.
