# AGENT INFRASTRUCTURE ARCHIVE

**Archived:** December 2, 2025  
**Reason:** Not used by backfill/delta apply workflows  
**Total Files Archived:** ~45 files

---

## PURPOSE

This archive contains the agent/LLM/MCP infrastructure that was built for autonomous routing but is not used by the backfill and delta apply processes. All files have been preserved for potential future use.

---

## ARCHIVE LOCATION MAP

### 📁 archive/agent_infrastructure/

```
agent_infrastructure/
├── agent/                    (1 file)
├── router_core/              (3 files)
├── mcp_server/               (7+ files)
├── async_services/           (3 files)
├── router_tools/             (5 files)
├── other_infrastructure/     (25+ files)
└── README.md                 (this file)
```

---

## DETAILED FILE INVENTORY

### 1. Agent Wrapper (1 file)
**Location:** `archive/agent_infrastructure/agent/`

| Original Path | Archived As | Purpose |
|---------------|-------------|---------|
| `src/wpr_agent/agent.py` | `agent/agent.py` | CLI autopilot wrapper around router |

**Dependencies:** router.py (also archived)  
**Used By:** Nothing in backfill/delta path

---

### 2. Router Core Infrastructure (3 files)
**Location:** `archive/agent_infrastructure/router_core/`

| Original Path | Archived As | Purpose |
|---------------|-------------|---------|
| `src/wpr_agent/cli/router.py` | `router_core/router.py` | LangGraph orchestration CLI |
| `src/wpr_agent/router/graph.py` | `router_core/graph.py` | LangGraph state machine |
| `src/wpr_agent/router/types.py` | `router_core/types.py` | RouterConfig, AgentState types |

**Dependencies:** langgraph, langgraph-checkpoint-sqlite  
**What Backfill/Delta Use Instead:** Direct tool imports, bypass router entirely

---

### 3. MCP Server Infrastructure (7+ files)
**Location:** `archive/agent_infrastructure/mcp_server/`

| Original Path | Archived As | Purpose |
|---------------|-------------|---------|
| `src/wpr_agent/mcp/client.py` | `mcp_server/client.py` | MCP client for remote tools |
| `src/wpr_agent/mcp/config.py` | `mcp_server/config.py` | MCP configuration |
| `src/wpr_agent/mcp/openproject_client.py` | `mcp_server/openproject_client.py` | MCP wrapper for OpenProject |
| `src/wpr_agent/mcp/servers/wpr_server.py` | `mcp_server/servers/wpr_server.py` | FastMCP server definition |
| `src/wpr_agent/mcp/servers/jira_server.py` | `mcp_server/servers/jira_server.py` | JIRA MCP server (legacy) |
| `src/wpr_agent/mcp/__init__.py` | `mcp_server/__init__.py` | Package init |
| `run_wpr_server.py` | `mcp_server/run_wpr_server.py` | Server runner script |

**Dependencies:** mcp, fastmcp, starlette  
**What Backfill/Delta Use Instead:** Direct OpenProject client calls

---

### 4. Async Services (3 files)
**Location:** `archive/agent_infrastructure/async_services/`

| Original Path | Archived As | Purpose |
|---------------|-------------|---------|
| `src/wpr_agent/services/openproject_async_client.py` | `async_services/openproject_async_client.py` | Async HTTP client |
| `src/wpr_agent/services/openproject_service_async.py` | `async_services/openproject_service_async.py` | Async service layer |
| `src/wpr_agent/router/tools/apply_async.py` | `async_services/apply_async.py` | Async apply implementation |

**Dependencies:** httpx, asyncio  
**What Backfill/Delta Use Instead:** openproject_service_v2.py (synchronous)

---

### 5. Router-Specific Tools (5 files)
**Location:** `archive/agent_infrastructure/router_tools/`

| Original Path | Archived As | Purpose |
|---------------|-------------|---------|
| `src/wpr_agent/router/tools/apply.py` | `router_tools/apply.py` | Router version of apply (unused) |
| `src/wpr_agent/router/tools/excel.py` | `router_tools/excel.py` | Excel reading for router |
| `src/wpr_agent/router/tools/llm.py` | `router_tools/llm.py` | LLM summarization tools |
| `src/wpr_agent/router/tools/provision.py` | `router_tools/provision.py` | Provis provisioning (stub) |
| `src/wpr_agent/router/tools/report.py` | `router_tools/report.py` | Report aggregation |

**What Backfill/Delta Use Instead:** cli/apply_plan.py directly

---

### 6. Other Infrastructure (25+ files)
**Location:** `archive/agent_infrastructure/other_infrastructure/`

**Orchestration:**
- `orchestration/__init__.py`
- `orchestration/[files]`

**Planner:**
- `planner/__init__.py`
- `planner/[files]`

**Serverless:**
- `serverless/__init__.py`
- `serverless/[files]`

**Tools (Agent-specific):**
- `tools/__init__.py`
- `tools/[4 files]`

**Validator:**
- `validator/__init__.py`
- `validator/[files]`

**Auth:**
- `auth/__init__.py`
- `auth/[files]`

**Purpose:** Agent-specific infrastructure not used by backfill/delta

---

## HOW TO RETRIEVE IF NEEDED

### Scenario 1: Want to Use Agent/Router Features

**If you decide to use the agent/router infrastructure:**

```powershell
# Restore agent wrapper
Copy-Item archive\agent_infrastructure\agent\agent.py -Destination src\wpr_agent\

# Restore router core
Copy-Item archive\agent_infrastructure\router_core\router.py -Destination src\wpr_agent\cli\
Copy-Item archive\agent_infrastructure\router_core\graph.py -Destination src\wpr_agent\router\
Copy-Item archive\agent_infrastructure\router_core\types.py -Destination src\wpr_agent\router\

# Install dependencies
pip install langgraph langgraph-checkpoint-sqlite
```

---

### Scenario 2: Want to Use MCP Server

**If you want to enable MCP remote tool execution:**

```powershell
# Restore MCP infrastructure
Copy-Item archive\agent_infrastructure\mcp_server\* -Destination src\wpr_agent\mcp\ -Recurse
Copy-Item archive\agent_infrastructure\mcp_server\run_wpr_server.py -Destination .

# Install dependencies
pip install mcp fastmcp starlette

# Run server
python run_wpr_server.py
# OR
uvicorn run_wpr_server:app --port 8000
```

---

### Scenario 3: Want Async Services

**If you need async/concurrent operations:**

```powershell
# Restore async services
Copy-Item archive\agent_infrastructure\async_services\*.py -Destination src\wpr_agent\services\
Copy-Item archive\agent_infrastructure\async_services\apply_async.py -Destination src\wpr_agent\router\tools\

# Install dependencies
pip install httpx

# Update imports in your code
from wpr_agent.services.openproject_service_async import OpenProjectServiceAsync
```

---

### Scenario 4: Want Specific Router Tool

**If you need a specific router tool:**

```powershell
# Example: Restore LLM summarization
Copy-Item archive\agent_infrastructure\router_tools\llm.py -Destination src\wpr_agent\router\tools\

# Install dependencies
pip install openai

# Set environment variable
$env:OPENAI_API_KEY="your-key-here"
```

---

## WHAT REMAINS ACTIVE

### ✅ Still in src/ (Used by Backfill/Delta)

- `src/wpr_agent/services/openproject_service_v2.py` ✅ (sync)
- `src/wpr_agent/services/provider.py` ✅
- `src/wpr_agent/clients/openproject_client.py` ✅

**State & Models:**
- `src/wpr_agent/state/influx_store.py` ✅
- `src/wpr_agent/state/catalog.py` ✅
- `src/wpr_agent/models.py` ✅

---

## PYTHON DEPENDENCIES CLEANUP

### Can Remove from requirements.txt:

```txt
# Agent/Graph
langgraph
langgraph-checkpoint-sqlite

# MCP
mcp
fastmcp
starlette  # (if only used by MCP)

# Async (if not used elsewhere)
httpx
```

### Must Keep:

```txt
influxdb-client-3
pandas
python-dotenv
requests
openpyxl
```

---

## TESTING AFTER ARCHIVAL

### Verify Backfill Still Works:

```powershell
# Set environment
$env:PYTHONPATH="src"

# Test backfill
python src/wpr_agent/cli/backfill.py --help

# Test delta apply
python src/wpr_agent/cli/delta_apply_influx.py --help --dry-run
```

### Expected: Should work without errors

If you get import errors for archived modules, it means something is still referencing them. Check the error and either:
1. Fix the import (remove reference to archived code)
2. Restore the needed file from archive

---

## ARCHIVE STATISTICS

**Files Archived:** ~45 files  
**Directories Archived:** 6 categories  
**Original Size:** ~500KB of Python code  
**Dependencies Removed:** 5+ packages

**Codebase Simplification:**
- Before: ~150 files
- After: ~105 files  
- Reduction: ~30% cleaner codebase

---

## RELATED DOCUMENTATION

See `/docs/stakeholder_review_analysis.md` for:
- Complete import analysis
- Dependency trees
- Detailed explanation of what's used vs unused
- Code tracing evidence

---

## QUESTIONS?

**Q: Can I safely delete these archived files?**  
A: Yes, but keep archive for 6 months in case you need agent features later.

**Q: Will backfill/delta break without these files?**  
A: No. These files are NOT imported or used by backfill/delta apply.

**Q: How do I know what's safe to restore?**  
A: See "HOW TO RETRIEVE" section above for specific scenarios.

**Q: What if I get import errors after archival?**  
A: Check which file is trying to import archived code. Either fix the import or restore the archive file.

---

**Last Updated:** December 2, 2025  
**Archive Status:** ✅ Complete and documented
