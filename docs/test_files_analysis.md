# TEST FILES ANALYSIS & RECOMMENDATIONS

**Analysis Date:** December 2, 2025
**Total Test Files in Root:** 7 files
**Total Test Files in /tests/:** ~4 files (unit, integration)

---

## ROOT DIRECTORY TEST FILES

### CATEGORY 1: VALUABLE VALIDATION TESTS (Keep in /tests/)

#### 1. test_status_mapping.py ✅ KEEP
**Purpose:** Unit test for status field string-to-href conversion  
**What It Tests:**
```python
# Tests _canonical_wpr_status() function
# Tests _to_payload() with status field
# Validates "Approved" → {"href": "..."} conversion
# Uses mocks to avoid network calls
```

**Why It's Valuable:**
- **Validates recent fix** (Bug #4: status conversion)
- Regression test for critical functionality
- Well-structured unit test with mocks
- Tests configuration file loading

**Recommendation:** ✅ **Move to /tests/unit/**  
**Reason:** Valuable regression test for status field fixes

---

#### 2. test_cf_discovery.py ✅ KEEP  
**Purpose:** Test custom field discovery mechanism  
**What It Tests:**
```python
# Tests svc._cf_map() - custom field mapping
# Tests discover_fieldmap() - auto-discovery
# Compares override file vs. API discovery
```

**Why It's Valuable:**
- Validates custom field configuration
- Tests both file-based and API-based discovery
- Helps debug "can't be blank" errors

**Recommendation:** ✅ **Move to /tests/integration/**  
**Reason:** Integration test for field discovery system

---

#### 3. test_compile.py ✅ KEEP
**Purpose:** Test work package bundle compilation  
**What It Tests:**
```python
# Loads op_field_id_overrides.json
# Creates TrackerFieldMap
# Calls compile_product_bundle_tool()
# Validates Epic fields populated
```

**Why It's Valuable:**
- **Tests core compilation logic**
- Validates custom field mapping works
- Integration test for bundle generation
- Actually used during custom field debugging

**Recommendation:** ✅ **Move to /tests/integration/**  
**Reason:** Critical test for compilation pipeline

---

#### 4. test_create_epic.py ✅ KEEP
**Purpose:** End-to-end Epic creation test  
**What It Tests:**
```python
# Builds Epic payload using build_epic_fields()
# Calls create_issue_resilient()
# Validates Epic creation in OpenProject
# Tests field discovery
```

**Why It's Valuable:**
- **E2E integration test**
- Tests actual OpenProject API
- Validates Epic creation works
- Good smoke test

**Recommendation:** ✅ **Move to /tests/integration/**  
**Reason:** End-to-end validation test

---

### CATEGORY 2: CONNECTIVITY SMOKE TESTS (Archive)

#### 5. test_influx.py 📝 ARCHIVE
**Purpose:** InfluxStore connectivity test  
**What It Tests:**
```python
# Initializes InfluxStore
# Tests simple Flux query
# Validates connectivity
```

**Why Archive:**
- Simple connectivity check
- Covered by debug_influx_*.py scripts
- InfluxStore is working
- No ongoing value

**Recommendation:** 📝 **Archive to archive/test_scripts/connectivity/**  
**Reason:** Connectivity confirmed, test obsolete

---

#### 6. test_influx_connection.py 📝 ARCHIVE
**Purpose:** InfluxDB v2 client connectivity test  
**What It Tests:**
```python
# Uses influxdb_client (v2 API)
# Tests health endpoint
# Tests Flux query and write
```

**Why Archive:**
- Uses OLD v2 client (we use v3)
- Superseded by test_influx3_connection.py
- Connectivity confirmed

**Recommendation:** 📝 **Archive to archive/test_scripts/connectivity/**  
**Reason:** Outdated - using v3 now

---

#### 7. test_influx3_connection.py 📝 ARCHIVE
**Purpose:** InfluxDB v3 client connectivity test  
**What It Tests:**
```python
# Uses influxdb_client_3 (current)
# Tests SQL query capability
# Tests write operations
# Hardcoded credentials for testing
```

**Why Archive:**
- One-time connectivity validation
- Contains hardcoded credentials (security issue)
- Connectivity confirmed working
- SQL queries validated

**Recommendation:** 📝 **Archive to archive/test_scripts/connectivity/**  
**Reason:** Connectivity confirmed, hardcoded credentials

---

#### 8. verify_influx_structure.py 📝 ARCHIVE
**Purpose:** Validate InfluxDB data schema  
**What It Tests:**
```python
# Reads InfluxDB batch data
# Checks for expected columns
# Validates data structure
```

**Why Archive:**
- One-time schema validation
- Data structure confirmed correct
- Similar to debug scripts

**Recommendation:** 📝 **Archive to archive/test_scripts/connectivity/**  
**Reason:** Schema validated, one-time use

---

## /tests/ DIRECTORY (Keep All)

### /tests/unit/
**Purpose:** Unit tests for isolated functions  
**Recommendation:** ✅ **Keep all** - proper test suite structure

### /tests/integration/
**Purpose:** Integration tests for system components  
**Recommendation:** ✅ **Keep all** - proper test suite structure

---

## SUMMARY TABLE

| File | Current Location | Category | Keep/Archive | Destination |
|------|-----------------|----------|--------------|-------------|
| test_status_mapping.py | Root | Validation | ✅ Keep | /tests/unit/ |
| test_cf_discovery.py | Root | Validation | ✅ Keep | /tests/integration/ |
| test_compile.py | Root | Validation | ✅ Keep | /tests/integration/ |
| test_create_epic.py | Root | Validation | ✅ Keep | /tests/integration/ |
| test_influx.py | Root | Connectivity | 📝 Archive | archive/test_scripts/connectivity/ |
| test_influx_connection.py | Root | Connectivity | 📝 Archive | archive/test_scripts/connectivity/ |
| test_influx3_connection.py | Root | Connectivity | 📝 Archive | archive/test_scripts/connectivity/ |
| verify_influx_structure.py | Root | Connectivity | 📝 Archive | archive/test_scripts/connectivity/ |

---

## RECOMMENDED STRUCTURE

### Keep in /tests/:
```
tests/
├── unit/
│   ├── (existing unit tests)
│   └── test_status_mapping.py       ← Move here
└── integration/
    ├── (existing integration tests)
    ├── test_cf_discovery.py          ← Move here
    ├── test_compile.py                ← Move here
    └── test_create_epic.py            ← Move here
```

### Archive:
```
archive/
├── debug_scripts/                    ← Already created
└── test_scripts/                     ← New
    ├── README.md
    └── connectivity/
        ├── test_influx.py
        ├── test_influx_connection.py
        ├── test_influx3_connection.py
        └── verify_influx_structure.py
```

---

## VALUE ASSESSMENT

### High Value (Keep - 4 files):
1. **test_status_mapping.py** - Regression test for Bug #4 fix
2. **test_cf_discovery.py** - Validates custom field system
3. **test_compile.py** - Tests core compilation logic
4. **test_create_epic.py** - E2E smoke test

**Why Keep:**
- Test recent fixes
- Prevent regressions  
- Document expected behavior
- Provide debugging templates

### Low Value (Archive - 4 files):
1. **test_influx.py** - Simple connectivity check
2. **test_influx_connection.py** - Old v2 client test
3. **test_influx3_connection.py** - One-time v3 validation (hardcoded credentials!)
4. **verify_influx_structure.py** - Schema validation done

**Why Archive:**
- One-time validation completed
- Connectivity confirmed
- Security concern (hardcoded credentials in #3)
- Covered by debug scripts

---

## SECURITY NOTE ⚠️

**test_influx3_connection.py contains HARDCODED credentials:**
```python
host = "http://212.2.245.85:8181"
token = "apiv3_cMe54DIsXtHFfMBNAAGBM_-6djfLM6aqDwnJUrtuc56Kkk_8QeHyusU0B-34CqW3FxMz5-iey-aH7WZIoFAu2w"
```

**Action Required:** Archive this file immediately to remove hardcoded credentials from active codebase.

---

## IMPLEMENTATION PLAN

### Phase 1: Move Valuable Tests to /tests/
```powershell
# Unit tests
Move-Item test_status_mapping.py tests/unit/

# Integration tests  
Move-Item test_cf_discovery.py tests/integration/
Move-Item test_compile.py tests/integration/
Move-Item test_create_epic.py tests/integration/
```

### Phase 2: Archive Connectivity Tests
```powershell
# Create archive structure
New-Item -ItemType Directory archive/test_scripts/connectivity -Force

# Move connectivity tests
Move-Item test_influx.py archive/test_scripts/connectivity/
Move-Item test_influx_connection.py archive/test_scripts/connectivity/
Move-Item test_influx3_connection.py archive/test_scripts/connectivity/
Move-Item verify_influx_structure.py archive/test_scripts/connectivity/

# Create README
# (document what's archived and why)
```

### Phase 3: Update .gitignore
```
# Ensure archived credentials are not committed
archive/test_scripts/connectivity/test_influx3_connection.py
```

---

## COMPARISON: Debug Scripts vs Test Scripts

| Aspect | Debug Scripts | Test Scripts |
|--------|--------------|--------------|
| **Purpose** | Find bugs | Prevent regressions |
| **Value** | One-time (bugs fixed) | Ongoing (regression prevention) |
| **Action** | Archive all | Keep valuable ones |
| **Archive %** | 100% (13/13) | 50% (4/8) |
| **Keep in production** | No | Yes (4 tests in /tests/) |

---

## FINAL RECOMMENDATION

### ✅ Keep & Organize (4 files):
Move to proper /tests/ directory structure with unit/integration separation

### 📝 Archive (4 files):
Move to archive/test_scripts/connectivity/ - simple smoke tests, connectivity confirmed

### ⚠️ Security:
Remove hardcoded credentials from active codebase by archiving test_influx3_connection.py

**Result:** Clean root directory + proper test organization + secure credential handling
