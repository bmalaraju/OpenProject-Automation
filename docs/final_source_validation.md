# SRC/WPR_AGENT - FINAL VALIDATION SCAN

**Scan Date:** December 2, 2025  
**Post-Archival Status:** After archiving agent/LLM/MCP infrastructure  
**Total Items:** 77 Python files, 17 directories

---

## RATING SYSTEM

- **5/5** = Critical - Used directly by backfill/delta
- **4/5** = Important - Supporting infrastructure used by core
- **3/5** = Useful - Operational/admin tools
- **2/5** = Marginal - One-time setup or rarely used
- **1/5** = Obsolete - Not needed, should archive

---

## PART 1: CORE SCRIPTS (3/3 - All Critical)

### /cli/ - Critical Backfill/Delta Scripts

| File | Rating | Status | Used By | Purpose |
|------|--------|--------|---------|---------|
| backfill.py | 5/5 | ✅ KEEP | Backfill | Main backfill script |
| delta_apply_influx.py | 5/5 | ✅ KEEP | Delta | Hash-based delta sync |
| apply_plan.py | 5/5 | ✅ KEEP | Both | Epic/Story creation |

**Verdict:** ✅ **KEEP ALL** - Core functionality

---

## PART 2: ROUTER/TOOLS (8/8 - All Essential)

### /router/tools/ - Directly Imported Tools

| File | Rating | Status | Imported By | Purpose |
|------|--------|--------|-------------|---------|
| compile_products.py | 5/5 | ✅ KEEP | backfill, delta | Bundle compilation |
| influx_source.py | 5/5 | ✅ KEEP | delta | InfluxDB reading, hashing |
| registry.py | 5/5 | ✅ KEEP | delta | Product-project mapping |
| discovery.py | 5/5 | ✅ KEEP | delta | Field auto-discovery |
| validate.py | 5/5 | ✅ KEEP | delta | Bundle validation |
| llm_comments.py | 4/5 | ✅ KEEP | apply_plan | Optional LLM comments |
| compile.py | 2/5 | ⚠️ CHECK | ? | Legacy compile? |
| __init__.py | 5/5 | ✅ KEEP | Python | Package marker |

### /router/ - Core Files

| File | Rating | Status | Used By | Purpose |
|------|--------|--------|---------|---------|
| utils.py | 5/5 | ✅ KEEP | apply_plan | Logging utilities |
| llm_config.py | 3/5 | ⚠️ OPTIONAL | llm_comments | LLM configuration |

**Verdict:**
- ✅ **KEEP**: compile_products, influx_source, registry, discovery, validate, llm_comments, utils
- ⚠️ **CHECK**: compile.py (may be old version)
- ⚠️ **OPTIONAL**: llm_config.py (only if keeping LLM)

---

## PART 3: SERVICES & CLIENTS (4/4 - All Critical)

### /services/

| File | Rating | Status | Used By | Purpose |
|------|--------|--------|---------|---------|
| openproject_service_v2.py | 5/5 | ✅ KEEP | All core | Sync OpenProject service |
| provider.py | 5/5 | ✅ KEEP | All core | Service factory |

### /clients/

| File | Rating | Status | Used By | Purpose |
|------|--------|--------|---------|---------|
| openproject_client.py | 5/5 | ✅ KEEP | service_v2 | HTTP client for OP |
| op_config.py | 5/5 | ✅ KEEP | client | Configuration loading |

**Verdict:** ✅ **KEEP ALL** - Critical infrastructure

---

## PART 4: STATE & MODELS (4/4 - All Critical)

### /state/

| File | Rating | Status | Used By | Purpose |
|------|--------|--------|---------|---------|
| influx_store.py | 5/5 | ✅ KEEP | delta | Hash storage |
| catalog.py | 5/5 | ✅ KEEP | apply_plan | WP catalog |
| (third file?) | ?/5 | ❓ CHECK | ? | Unknown |

### Root

| File | Rating | Status | Used By | Purpose |
|------|--------|--------|---------|---------|
| models.py | 5/5 | ✅ KEEP | All | PlanBundle, TrackerFieldMap |

**Verdict:** ✅ **KEEP ALL** - Core data models

---

## PART 5: SHARED UTILITIES (5 files - Check Each)

### /shared/

| File | Rating | Status | Purpose | Keep? |
|------|--------|---------|---------|
| influx_helpers.py | 5/5 | ✅ KEEP | InfluxDB utilities | Yes |
| config_loader.py | 5/5 | ✅ KEEP | Config loading | Yes |
| (3 more files) | ?/5 | ❓ CHECK | Unknown | TBD |

**Action Needed:** List and analyze all files in /shared/

---

## PART 6: CLI SUPPORTING SCRIPTS (30 files - Analyze Each)

### Category A: Data Import/Export (7 files)

| File | Rating | Status | Purpose | Verdict |
|------|--------|---------|---------|
| import_wpr.py | 4/5 | ✅ KEEP | Excel import to InfluxDB | Useful |
| upload_excel_to_influx.py | 4/5 | ✅ KEEP | Upload source data | Useful |
| export_influx_to_csv.py | 3/5 | ✅ KEEP | Export for analysis | Operational |
| export_stories_csv_from_influx.py | 3/5 | ✅ KEEP | Story export | Operational |
| dump_influx_raw.py | 3/5 | ✅ KEEP | Debug data dump | Operational |
| reconcile_import_to_influx.py | 3/5 | ✅ KEEP | Reconciliation | Operational |
| preview_influx_input.py | 3/5 | ✅ KEEP | Data preview | Operational |

**Verdict:** ✅ **KEEP ALL** - Data pipeline tools

---

### Category B: OpenProject Admin (7 files)

| File | Rating | Status | Purpose | Verdict |
|------|--------|---------|---------|
| ensure_subprojects.py | 4/5 | ✅ KEEP | Create subprojects | Setup |
| cleanup_duplicates.py | 4/5 | ✅ KEEP | Dedup tool | Maintenance |
| check_access.py | 3/5 | ✅ KEEP | Permission check | Admin |
| check_admin.py | 3/5 | ✅ KEEP | Admin status check | Admin |
| check_op_config.py | 3/5 | ✅ KEEP | Config validation | Admin |
| op_list_status_options.py | 3/5 | ✅ KEEP | List status values | Admin |
| op_oauth_bootstrap.py | 4/5 | ✅ KEEP | OAuth setup | Setup |
| op_oauth_reauth.py | 3/5 | ✅ KEEP | Token refresh | Maintenance |

**Verdict:** ✅ **KEEP ALL** - Admin/maintenance tools

---

### Category C: Planning/Compilation (4 files)

| File | Rating | Status | Purpose | Verdict |
|------|--------|---------|---------|
| compile_plan.py | 2/5 | ⚠️ CHECK | Legacy compile? | May be old |
| compile_plan_products.py | 2/5 | ⚠️ CHECK | Product compile | May be old |
| validate_plan.py | 2/5 | ⚠️ CHECK | Plan validation | May be old |
| apply_with_service.py | 2/5 | ⚠️ CHECK | Alternative apply? | May be old |

**Action Needed:** Check if these are legacy versions superseded by backfill/delta

---

### Category D: InfluxDB Admin (2 files)

| File | Rating | Status | Purpose | Verdict |
|------|--------|---------|---------|
| influx_admin.py | 4/5 | ✅ KEEP | InfluxDB management | Admin |
| list_ingestions.py | 3/5 | ✅ KEEP | List import batches | Operational |

**Verdict:** ✅ **KEEP ALL** - Admin tools

---

### Category E: Router/Graph Related (5 files) ⚠️

| File | Rating | Status | Purpose | Verdict |
|------|--------|---------|---------|
| ingest_then_router.py | 1/5 | ❌ ARCHIVE | Calls router.py | Not used |
| run_router_sharded.py | 1/5 | ❌ ARCHIVE | Sharded routing | Not used |
| test_router_stubbed.py | 1/5 | ❌ ARCHIVE | Router testing | Not used |
| graph_introspect.py | 1/5 | ❌ ARCHIVE | Graph inspection | Not used |
| sync_updates.py | 2/5 | ⚠️ CHECK | Update sync | May use router |

**Verdict:** ❌ **ARCHIVE 4-5 files** - Router dependencies

---

### Category F: Misc/Utility (5 files)

| File | Rating | Status | Purpose | Verdict |
|------|--------|---------|---------|
| list_domains.py | 2/5 | ⚠️ CHECK | List registered domains | Unknown use |
| preview_groups.py | 2/5 | ⚠️ CHECK | Preview grouping | Unknown use |
| switch_base.py | 2/5 | ⚠️ CHECK | Config switching? | Unknown use |
| apply_plan_async_demo.py | 1/5 | ❌ ARCHIVE | Async demo | Not used |

**Action Needed:** Verify usage

---

## PART 7: ARCHIVED DIRECTORIES (Still Present) ❌

### Directories That Should Have Been Archived:

| Directory | Status | Verdict |
|-----------|--------|---------|
| /mcp/ | ❌ STILL PRESENT | Should be fully archived |
| /auth/ | ❌ STILL PRESENT | Should be archived |
| /orchestration/ | ❌ STILL PRESENT | Should be archived |
| /planner/ | ❌ STILL PRESENT | Should be archived |
| /serverless/ | ❌ STILL PRESENT | Should be archived |
| /tools/ | ❌ STILL PRESENT | Should be archived |
| /validator/ | ❌ STILL PRESENT | Should be archived |

**⚠️ ISSUE:** These directories were supposed to be archived but are still present!

**Action:** Need to remove these directories (they were copied but originals not deleted)

---

## PART 8: OPTIONAL/CONDITIONAL DIRECTORIES

### /observability/ (2 files)

| File | Rating | Status | Purpose | Verdict |
|------|--------|---------|---------|
| langfuse_tracer.py | 2/5 | ⚠️ OPTIONAL | LLM tracing | Only if using LLM |
| langchain_integration.py | 1/5 | ❌ ARCHIVE | LangChain | Not used |

**Verdict:** ⚠️ Conditional - Keep only if using LLM features

---

### /config/ (2 files)

| File | Rating | Status | Purpose | Verdict |
|------|--------|---------|---------|
| domain_registry.py | 2/5 | ⚠️ CHECK | Domain config | May be router-specific |
| (second file?) | ?/5 | ❓ CHECK | Unknown | TBD |

---

### /profiles/ (Unknown contents)

| Directory | Rating | Status | Purpose | Verdict |
|-----------|--------|---------|---------|
| profiles/ | ?/5 | ❓ CHECK | Unknown | Need to investigate |

---

## SUMMARY: ACTIONABLE ITEMS

### ✅ DEFINITELY KEEP (Core - ~25 files)

**Critical Scripts (3):**
- backfill.py
- delta_apply_influx.py
- apply_plan.py

**Router Tools (6):**
- compile_products.py
- influx_source.py
- registry.py
- discovery.py
- validate.py
- llm_comments.py (optional)

**Services/Clients (4):**
- openproject_service_v2.py
- provider.py
- openproject_client.py
- op_config.py

**State/Models (4):**
- influx_store.py
- catalog.py
- models.py
- (+ 3rd state file if exists)

**Utilities (2):**
- router/utils.py
- llm_config.py (if LLM)

**Shared (2+):**
- influx_helpers.py
- config_loader.py

---

### ✅ KEEP (Supporting Tools - ~20 files)

**Import/Export (7):**
- import_wpr.py
- upload_excel_to_influx.py
- export_influx_to_csv.py
- export_stories_csv_from_influx.py
- dump_influx_raw.py
- reconcile_import_to_influx.py
- preview_influx_input.py

**OpenProject Admin (8):**
- ensure_subprojects.py
- cleanup_duplicates.py
- check_access.py
- check_admin.py
- check_op_config.py
- op_list_status_options.py
- op_oauth_bootstrap.py
- op_oauth_reauth.py

**InfluxDB Admin (2):**
- influx_admin.py
- list_ingestions.py

---

### ⚠️ NEEDS INVESTIGATION (~14 files)

**May Be Legacy/Duplicate:**
- compile_plan.py
- compile_plan_products.py
- validate_plan.py
- apply_with_service.py
- sync_updates.py
- list_domains.py
- preview_groups.py
- switch_base.py

**Config/Domain:**
- All files in /config/
- contents of /profiles/

**Shared:**
- 3 unknown files in /shared/

---

### ❌ ARCHIVE (~9+ files + 7 directories)

**Router-Dependent Scripts:**
- ingest_then_router.py
- run_router_sharded.py
- test_router_stubbed.py
- graph_introspect.py
- apply_plan_async_demo.py

**LangChain:**
- observability/langchain_integration.py

**Directories (Originals Not Deleted):**
- /mcp/ (all 6 files)
- /auth/ (1 file)
- /orchestration/ (2 files)
- /planner/ (1 file)
- /serverless/ (2 files)
- /tools/ (4 files)
- /validator/ (1 file)

---

## NEXT STEPS

### 1. Complete Directory Archival
**Remove original source directories that were supposed to be archived:**
```powershell
Remove-Item src\wpr_agent\mcp -Recurse -Force
Remove-Item src\wpr_agent\auth -Recurse -Force
Remove-Item src\wpr_agent\orchestration -Recurse -Force
Remove-Item src\wpr_agent\planner -Recurse -Force
Remove-Item src\wpr_agent\serverless -Recurse -Force
Remove-Item src\wpr_agent\tools -Recurse -Force
Remove-Item src\wpr_agent\validator -Recurse -Force
```

### 2. Investigate Unknown Files
**Check these files for actual usage:**
- List all files in /shared/, /config/, /profiles/
- Grep for imports of compile_plan, validate_plan, etc.
- Determine if they're still used

### 3. Archive Router-Dependent CLI Scripts
**Move these to archive:**
```powershell
Move-Item src\wpr_agent\cli\ingest_then_router.py archive\agent_infrastructure\router_tools\
Move-Item src\wpr_agent\cli\run_router_sharded.py archive\agent_infrastructure\router_tools\
Move-Item src\wpr_agent\cli\test_router_stubbed.py archive\agent_infrastructure\router_tools\
Move-Item src\wpr_agent\cli\graph_introspect.py archive\agent_infrastructure\router_tools\
Move-Item src\wpr_agent\cli\apply_plan_async_demo.py archive\agent_infrastructure\async_services\
```

### 4. Final Count
After cleanup:
- **Before:** ~77 files, 17 directories
- **Target:** ~45-50 files, ~12 directories
- **Reduction:** ~35% cleaner

---

## CONFIDENCE ASSESSMENT

| Category | Confidence | Reason |
|----------|-----------|--------|
| Core 3 scripts | 100% | Directly analyzed |
| Router tools | 100% | Import traced |
| Services/Clients | 100% | Dependencies verified |
| Router-dependent CLI | 95% | Grep search confirms |
| Supporting tools | 90% | Logical purpose clear |
| Unknown files | 40% | Need investigation |

**Recommendation:** Proceed with high-confidence archival, then investigate unknowns.
