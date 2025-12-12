from __future__ import annotations

"""
Run router per project shard concurrently (API-only fallback path).

Usage:
  python wpr_agent/scripts/run_router_sharded.py --since 7d --registry wpr_agent/config/product_project_registry.json --max-procs 3 --op-story-workers 8
  python wpr_agent/scripts/run_router_sharded.py --batch-id 20251104232022 --registry wpr_agent/config/product_project_registry.json --max-procs 2 --op-story-workers 6

Notes:
  - Spawns one process per project key up to --max-procs.
  - Sets OP_STORY_WORKERS per child.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List

from dotenv import load_dotenv
try:
    from wpr_agent.observability.langfuse_tracer import get_tracer  # type: ignore
except Exception:  # pragma: no cover
    def get_tracer():  # type: ignore
        return None

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)
load_dotenv(BASE / ".env", override=False)

from wpr_agent.router.tools.registry import load_product_registry_tool  # type: ignore


def main() -> None:
    ap = argparse.ArgumentParser(description="Run router per project shard concurrently")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--since")
    src.add_argument("--batch-id")
    ap.add_argument("--registry", required=True)
    ap.add_argument("--max-procs", type=int, default=2)
    ap.add_argument("--op-story-workers", type=int, default=6)
    ap.add_argument("--artifact-dir", default="artifacts")
    args = ap.parse_args()

    reg = load_product_registry_tool(args.registry)
    projects = sorted(set(reg.values()))
    if not projects:
        print("no_projects: registry empty")
        sys.exit(2)

    procs: List[subprocess.Popen] = []
    py = sys.executable
    env_base = os.environ.copy()
    env_base["PYTHONPATH"] = str((ROOT / "wp-jira-agent").resolve())
    env_base["MCP_FALLBACK_LOCAL_ON_ERROR"] = env_base.get("MCP_FALLBACK_LOCAL_ON_ERROR", "1")
    env_base["OP_STORY_WORKERS"] = str(int(args.op_story_workers))

    tracer = get_tracer()
    run_span = None
    try:
        if tracer:
            run_span = tracer.start_trace("sharded.run", input={"projects": len(projects), "since": args.since or "", "batch_id": args.batch_id or "", "max_procs": int(args.max_procs)})
    except Exception:
        run_span = None

    for p in projects:
        while len(procs) >= int(args.max_procs):
            # Wait for one to finish
            code = procs[0].poll()
            if code is not None:
                procs.pop(0)
            else:
                procs[0].wait()
                procs.pop(0)
        cmd = [
            py,
            str((BASE / "scripts" / "router.py").resolve()),
            "--source",
            "influx",
            "--online",
            "--registry",
            args.registry,
            "--artifact-dir",
            args.artifact_dir,
        ]
        if args.since:
            cmd.extend(["--since", args.since])
        if args.batch_id:
            cmd.extend(["--batch-id", args.batch_id])
        # run per project by filtering products mapped to this project
        # Note: router groups by product; we rely on registry mapping, so we don't pass domains.
        print("spawn:", " ".join(cmd), "for project=", p)
        try:
            if tracer and run_span:
                sp = tracer.start_span("shard.spawn", parent=run_span, project_key=p)
                if sp:
                    sp.end()
        except Exception:
            pass
        procs.append(subprocess.Popen(cmd, env=env_base))

    # Wait
    for p in procs:
        p.wait()
    print("sharded_run: complete")
    try:
        if run_span:
            run_span.end()
    except Exception:
        pass


if __name__ == "__main__":
    main()
