# WPR Backfill Agent - Handoff Guide

## 1. Overview
This system automates the backfill of historical product orders from Excel into OpenProject. It reads order data, processes it into a "Plan Bundle," and then creates or updates corresponding **Epics** (Orders) and **User Stories** (Line Items) in OpenProject.

### Key Capabilities
- **Excel Ingestion**: Reads raw order reports.
- **Multithreaded Processing**: Uses parallel workers for high performance.
- **Idempotency**: Can run multiple times without creating duplicates (when configured correctly).
- **Resilience**: Handles API rate limits and network errors automatically.

---

## 2. Quick Start (How-To)

### Prerequisites
- Python 3.10+
- OpenProject API Key (configured in `.env` or `config/working_openproject_config.json`)
- Source Excel file (e.g., `08.21.WP Orders...xlsx`)

### Running a Full Backfill
To process all orders from the Excel file:

```powershell
$env:PYTHONPATH='src'
python src/wpr_agent/cli/backfill.py `
  --file "path/to/your/excel_file.xlsx" `
  --sheet "WP_Overall_Order_Report" `
  --batch-id "backfill-run-v1" `
  --workers 10 `
  --skip-ingest
```

**Arguments:**
- `--file`: Path to the source Excel file.
- `--sheet`: Name of the sheet containing order data.
- `--batch-id`: Unique identifier for this run (used for logging/reporting).
- `--workers`: Number of parallel threads (Recommended: 10-20).
- `--skip-ingest`: Skips re-importing Excel to InfluxDB if already done (saves time).

### Running a Dry Run
To see what *would* happen without making changes:
Add the `--dry-run` flag.

```powershell
python src/wpr_agent/cli/backfill.py ... --dry-run
```

---

## 3. Maintenance & Cleanup

### Duplicate Cleanup Tool
If a backfill run is interrupted or misconfigured, it might create duplicate records. Use the built-in cleanup tool to fix this.

**Location:** `src/wpr_agent/cli/cleanup_duplicates.py`

**Usage:**

1.  **Dry Run (Check only):**
    ```powershell
    python src/wpr_agent/cli/cleanup_duplicates.py
    ```

2.  **Execute Cleanup (Delete duplicates):**
    ```powershell
    python src/wpr_agent/cli/cleanup_duplicates.py --delete
    ```

**How it works:**
- Scans all Epics and Stories in target projects.
- Groups them by `WPR Order ID` (and `Subject` for Stories).
- If duplicates are found, it keeps the **newest** one (highest ID) and deletes the others.

---

## 4. Troubleshooting

### Common Errors

#### 1. "Parent does not exist"
**Symptom:** Stories fail to create because the Epic cannot be found.
**Cause:** The local cache (InfluxDB) maps the Order ID to an OpenProject Epic ID that no longer exists (e.g., was deleted manually).
**Fix:**
Set the environment variable `IGNORE_INFLUX_IDENTITY=1` to force the script to ignore the stale cache and look up the Epic by name/field in OpenProject.

```powershell
$env:IGNORE_INFLUX_IDENTITY='1'
python src/wpr_agent/cli/backfill.py ...
```

#### 2. "429 Too Many Requests"
**Symptom:** The script pauses frequently or fails with 429 errors.
**Cause:** OpenProject API rate limits.
**Fix:**
- Reduce the number of workers (e.g., `--workers 5`).
- The script has built-in backoff and retry logic, so it should recover automatically.

#### 3. Duplicate Records Created
**Symptom:** You see multiple Epics for the same Order ID.
1.  **Ingest**: Excel -> InfluxDB (Raw Data)
2.  **Compile**: InfluxDB -> Plan Bundle (Logical representation of Epics/Stories)
3.  **Apply**: Plan Bundle -> OpenProject API (Actual creation/update)
**Cause:** Running the script multiple times without proper identity tracking.
**Fix:** Use the cleanup tool (see Section 3 above).

---

## 5. Delta Apply - Incremental Updates

The **delta apply** script (`delta_apply_influx.py`) processes incremental updates using **hash-based change detection**. It only processes orders whose data has actually changed since the last run.

### Step-by-Step Workflow

#### Step 1: Always Start with Dry Run

```powershell
$env:PYTHONPATH='src'
python src/wpr_agent/cli/delta_apply_influx.py `
  --batch-id 20251202172311 `
  --registry config/product_project_registry.json `
  --dry-run
```

**What This Does:**
- Shows which orders have changed
- Previews what will be created/updated
- Identifies any issues BEFORE making changes
- **No changes are made to OpenProject**

#### Step 2: Review Dry Run Output

Look for these key metrics in the output:

```json
{
  "orders": 2498,           // Total orders in batch
  "orders_changed": 5,      // Orders that will be processed
  "created": 4,             // New work packages (Epics + Stories)
  "updated": 2,             // Existing work packages to update
  "failures": 0,            // ✅ Should be 0
  "warnings": 215           // Unmapped products (OK if expected)
}
```

**Success Indicators:**
- `failures: 0` - No errors detected
- `orders_changed` makes sense for your data update
- Per-product breakdown shows expected projects

#### Step 3: Run Online Mode

If dry run looks good, run in online mode to apply changes:

```powershell
$env:PYTHONPATH='src'
python src/wpr_agent/cli/delta_apply_influx.py `
  --batch-id 20251202172311 `
  --registry config/product_project_registry.json `
  --online `
  --workers 10
```

**Arguments:**
- `--batch-id`: The InfluxDB batch ID to process
- `--registry`: Path to product-project mapping file
- `--online`: Actually make changes (omit for dry-run)
- `--workers`: Parallel threads (default: 5, recommended: 10-20)

### Understanding the Output

#### Processing Messages

```
[1/5] Processed order WPO00182554: epics=0, stories=2
[2/5] Processed order WPO00182556: epics=1, stories=3
```

**What It Means:**
- `epics=0` - Epic already exists, was **updated**
- `epics=1` - Epic didn't exist, was **created**
- `stories=N` - Number of Stories created/updated for this order
- No `errors=` line means **success!**

#### Final Totals

After processing completes, check the totals:

```json
{
  "orders_changed": 5,
  "created": 7,        // 1 new Epic + 6 new Stories
  "updated": 4,        // 4 existing Epics updated
  "failures": 0        // ✅ Zero failures = complete success
}
```

**Key Formula:**
- Total work done = `created` + `updated`
- Should roughly match expectations based on `orders_changed`
- `failures: 0` confirms all orders processed successfully

### Force Processing Specific Orders

If you need to reprocess specific orders (e.g., to refresh data after a fix):

**Edit** `src/wpr_agent/cli/delta_apply_influx.py` around **line 196**:

```python
if "WPO00187674" in oid or "WPO00187539" in oid:
    changed.add(oid)
    print(f"DEBUG: Forcing change for {oid}")
```

Add your order IDs to force them to process regardless of hash changes.

> **Remember:** Remove these after use to return to normal hash-based detection.

### Common Scenarios

#### Scenario 1: No Changes Detected

```
Found 0 changed orders out of 2498 total.
```

**Meaning:** No data has changed since last run - this is normal!

**Actions:** None needed. System is working correctly.

#### Scenario 2: Many Orders Changed

```
Found 150 changed orders out of 2498 total.
```

**Meaning:** 150 orders have data updates.

**Actions:** 
1. Run dry-run to preview
2. Verify changes make sense
3. Run online mode

#### Scenario 3: All Orders Failed/Warnings

```
failures: 50
warnings: 200
```

**Meaning:** Configuration or permission issues.

**Common Causes:**
- Missing product mappings in registry
- OpenProject authentication failure
- Custom field configuration missing

**Fix:** Check Section 6 (Custom Field Config) and Section 7 (Product Registry)

---

## 6. Custom Field Configuration

### Critical Configuration Files

The system requires two configuration files for OpenProject custom fields:

1. **`config/op_field_id_overrides.json`** - Maps custom field names to IDs
2. **`config/op_custom_option_overrides.json`** - Maps field values to option IDs

### Common Issue: "Custom field can't be blank" Errors

**Symptom:** All work packages fail to create with errors like "WPR Product can't be blank".

**Root Cause:** Custom field mappings are not loaded correctly.

**Fix:** Verify that both config files exist and contain the correct mappings (22 fields total).

---

## 7. Product-to-Project Registry

### What is it?

The `config/product_project_registry.json` file maps **product names** (from Excel data) to **OpenProject project keys**.

### Why Products Get Skipped (Warnings)

**Symptom:** Summary shows `warnings=215` and many products with `[None]`:

**Explanation:**
- These products exist in the batch data
- They do NOT have mappings in `product_project_registry.json`
- The script cannot determine which OpenProject project to use
- All orders for these products are **skipped** with 1 warning per product

**To Process These Products:**
1. Create corresponding projects in OpenProject
2. Add mappings to `product_project_registry.json`
3. Re-run the delta apply

**Important:** Only orders for products WITH mappings will be processed. The warning count equals the number of unmapped products in your data.

**Example Registry Structure:**

```json
{
  "registry": {
    "FlowOne": "FlowOne",
    "Flowone": "FlowOne",        // Case variations map to same project
    "Flow One": "FlowOne",
    "Session Border Controller": "Session Border Controller",
    "NIAM": "NIAM"
  }
}
```

**Note:** Product names are case-sensitive in the source data but the registry handles common variations.

---

## 8. Data Flow
1.  **Ingest**: Excel  InfluxDB (Raw Data)
2.  **Compile**: InfluxDB  Plan Bundle (Logical representation of Epics/Stories)
3.  **Apply**: Plan Bundle  OpenProject API (Actual creation/update)
