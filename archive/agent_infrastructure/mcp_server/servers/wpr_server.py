from __future__ import annotations

"""
Lean MCP server exposing WPR ingest/query/checkpoint + OpenProject helpers.
"""

from typing import Any, Dict

try:
    from fastmcp.server.server import FastMCP  # type: ignore
except Exception as ex:  # pragma: no cover
    raise RuntimeError(f"fastmcp not installed: {ex}")

from wpr_agent.shared import influx_helpers, op_metadata, op_status_mapping


def build_server() -> Any:
    app = FastMCP("wpr_router_mcp")  # type: ignore

    @app.tool("wpr.upload_excel_to_influx")  # type: ignore
    def upload_excel_to_influx(payload: Dict[str, Any]) -> Dict[str, Any]:
        path = (payload or {}).get("file_path")
        sheet = (payload or {}).get("sheet") or "Sheet1"
        batch_id = (payload or {}).get("batch_id")
        if not path:
            return {"ok": False, "error": "file_path_required"}
        try:
            from pathlib import Path
            res = influx_helpers.ingest_excel_to_influx(Path(str(path)), sheet=str(sheet), batch_id=(str(batch_id) if batch_id else None))
            return res if isinstance(res, dict) else {"ok": True, "result": res}
        except Exception as ex:  # pragma: no cover
            return {"ok": False, "error": str(ex)}

    @app.tool("wpr.get_source_hash")  # type: ignore
    def get_source_hash(payload: Dict[str, Any]) -> Dict[str, Any]:
        project_key = (payload or {}).get("project_key")
        order_id = (payload or {}).get("order_id")
        if not project_key or not order_id:
            return {"ok": False, "error": "project_key_and_order_id_required"}
        try:
            h = influx_helpers.get_source_hash(str(project_key), str(order_id))
            return {"ok": True, "src_hash": h}
        except Exception as ex:  # pragma: no cover
            return {"ok": False, "error": str(ex)}

    @app.tool("wpr.update_source_hash")  # type: ignore
    def update_source_hash(payload: Dict[str, Any]) -> Dict[str, Any]:
        project_key = (payload or {}).get("project_key")
        order_id = (payload or {}).get("order_id")
        src_hash = (payload or {}).get("src_hash")
        if not project_key or not order_id or src_hash is None:
            return {"ok": False, "error": "project_key_order_id_src_hash_required"}
        try:
            influx_helpers.set_source_hash(str(project_key), str(order_id), str(src_hash))
            return {"ok": True}
        except Exception as ex:  # pragma: no cover
            return {"ok": False, "error": str(ex)}

    @app.tool("wpr.resolve_identity")  # type: ignore
    def resolve_identity(payload: Dict[str, Any]) -> Dict[str, Any]:
        project_key = (payload or {}).get("project_key")
        order_id = (payload or {}).get("order_id")
        issue_type = (payload or {}).get("issue_type") or "Epic"
        instance = (payload or {}).get("instance")
        if not project_key or not order_id:
            return {"ok": False, "error": "project_key_and_order_id_required"}
        try:
            key = influx_helpers.resolve_identity(str(project_key), str(order_id), str(issue_type), int(instance) if instance is not None else None)
            return {"ok": True, "issue_key": key}
        except Exception as ex:  # pragma: no cover
            return {"ok": False, "error": str(ex)}

    @app.tool("wpr.register_identity")  # type: ignore
    def register_identity(payload: Dict[str, Any]) -> Dict[str, Any]:
        project_key = (payload or {}).get("project_key")
        order_id = (payload or {}).get("order_id")
        issue_key = (payload or {}).get("issue_key")
        issue_type = (payload or {}).get("issue_type") or "Epic"
        instance = (payload or {}).get("instance")
        last_hash = (payload or {}).get("last_hash")
        if not project_key or not order_id or not issue_key:
            return {"ok": False, "error": "project_key_order_id_issue_key_required"}
        try:
            influx_helpers.register_identity(
                str(project_key),
                str(order_id),
                str(issue_key),
                str(issue_type),
                int(instance) if instance is not None else None,
                str(last_hash) if last_hash else None,
            )
            return {"ok": True}
        except Exception as ex:  # pragma: no cover
            return {"ok": False, "error": str(ex)}

    @app.tool("wpr.get_issue_map")  # type: ignore
    def get_issue_map(payload: Dict[str, Any]) -> Dict[str, Any]:
        project_key = (payload or {}).get("project_key")
        issue_type = (payload or {}).get("issue_type") or "Epic"
        order_id = (payload or {}).get("order_id")
        instance = (payload or {}).get("instance")
        if not project_key or not order_id:
            return {"ok": False, "error": "project_key_and_order_id_required"}
        try:
            from wpr_agent.state.influx_store import InfluxStore  # type: ignore
            from wpr_agent.shared.config_loader import InfluxConfig

            cfg = InfluxConfig.load()
            store = InfluxStore(url=cfg.url, token=cfg.token, org=cfg.org, bucket=cfg.bucket)
            if str(issue_type).strip().lower() == "story":
                key = store.resolve_story(str(project_key), str(order_id), int(instance or 0))
            else:
                key = store.resolve_epic(str(project_key), str(order_id))
            return {"ok": True, "issue_key": key}
        except Exception as ex:  # pragma: no cover
            return {"ok": False, "error": str(ex)}

    @app.tool("wpr.update_issue_map")  # type: ignore
    def update_issue_map(payload: Dict[str, Any]) -> Dict[str, Any]:
        project_key = (payload or {}).get("project_key")
        issue_type = (payload or {}).get("issue_type") or "Epic"
        order_id = (payload or {}).get("order_id")
        instance = (payload or {}).get("instance")
        issue_key = (payload or {}).get("issue_key")
        last_hash = (payload or {}).get("last_hash")
        if not project_key or not order_id or not issue_key:
            return {"ok": False, "error": "project_key_order_id_issue_key_required"}
        try:
            from wpr_agent.state.influx_store import InfluxStore  # type: ignore
            from wpr_agent.shared.config_loader import InfluxConfig

            cfg = InfluxConfig.load()
            store = InfluxStore(url=cfg.url, token=cfg.token, org=cfg.org, bucket=cfg.bucket)
            if str(issue_type).strip().lower() == "story":
                store.register_story(str(project_key), str(order_id), int(instance or 0), str(issue_key), last_hash=str(last_hash) if last_hash is not None else None)
            else:
                store.register_epic(str(project_key), str(order_id), str(issue_key), last_hash=str(last_hash) if last_hash is not None else None)
            return {"ok": True}
        except Exception as ex:  # pragma: no cover
            return {"ok": False, "error": str(ex)}

    @app.tool("wpr.query_wpr_orders")  # type: ignore
    def query_wpr_orders(payload: Dict[str, Any]) -> Dict[str, Any]:
        since = (payload or {}).get("since")
        batch_id = (payload or {}).get("batch_id")
        measurement = (payload or {}).get("measurement") or "wpr_input"
        try:
            df = influx_helpers.query_wpr_rows(since=since, batch_id=batch_id, measurement=str(measurement))
            # Return rows as list of dicts to keep transport simple
            rows = []
            try:
                if df is not None:
                    rows = df.to_dict(orient="records")  # type: ignore[attr-defined]
            except Exception:
                rows = []
            return {"ok": True, "rows": rows, "count": len(rows)}
        except Exception as ex:  # pragma: no cover
            return {"ok": False, "error": str(ex)}

    @app.tool("wpr.get_order_checkpoint")  # type: ignore
    def get_order_checkpoint(payload: Dict[str, Any]) -> Dict[str, Any]:
        project_key = (payload or {}).get("project_key")
        order_id = (payload or {}).get("order_id")
        if not project_key or not order_id:
            return {"ok": False, "error": "project_key_and_order_id_required"}
        try:
            ts = influx_helpers.get_order_checkpoint(str(project_key), str(order_id))
            return {"ok": True, "last_ts": ts}
        except Exception as ex:  # pragma: no cover
            return {"ok": False, "error": str(ex)}

    @app.tool("wpr.update_order_checkpoint")  # type: ignore
    def update_order_checkpoint(payload: Dict[str, Any]) -> Dict[str, Any]:
        project_key = (payload or {}).get("project_key")
        order_id = (payload or {}).get("order_id")
        last_ts = (payload or {}).get("last_ts")
        if not project_key or not order_id or not last_ts:
            return {"ok": False, "error": "project_key_order_id_last_ts_required"}
        try:
            influx_helpers.set_order_checkpoint(str(project_key), str(order_id), str(last_ts))
            return {"ok": True}
        except Exception as ex:  # pragma: no cover
            return {"ok": False, "error": str(ex)}

    @app.tool("openproject.discover_fieldmap")  # type: ignore
    def discover_fieldmap(payload: Dict[str, Any]) -> Dict[str, Any]:
        project_key = (payload or {}).get("project_key")
        if not project_key:
            return {"ok": False, "error": "project_key_required"}
        try:
            fmap = op_metadata.discover_fieldmap(str(project_key))
            return {"ok": True, "fieldmap": fmap}
        except Exception as ex:  # pragma: no cover
            return {"ok": False, "error": str(ex)}

    @app.tool("openproject.map_wpr_status")  # type: ignore
    def map_wpr_status(payload: Dict[str, Any]) -> Dict[str, Any]:
        status = (payload or {}).get("wpr_status")
        if status is None:
            return {"ok": False, "error": "wpr_status_required"}
        try:
            res = op_status_mapping.map_wpr_status_to_openproject(str(status))
            return {"ok": True, **res}
        except Exception as ex:  # pragma: no cover
            return {"ok": False, "error": str(ex)}

    @app.tool("openproject.apply_openproject_plan")  # type: ignore
    def apply_openproject_plan(payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Best-effort apply for a LangGraph-style plan.

        Expected payload:
        {
          "project_key": "<project>",
          "items": [
            {
              "id": optional(OP work package id),
              "subject": str,
              "description": str,
              "type": str (e.g., "Epic", "User Story", "Task"),
              "status": str (optional),
              "custom_fields": { "customField99": value, ... }
            },
            ...
          ]
        }
        """
        project_key = (payload or {}).get("project_key")
        items = (payload or {}).get("items") or []
        if not project_key:
            return {"ok": False, "error": "project_key_required"}
        created: list = []
        updated: list = []
        errors: list = []
        try:
            from wpr_agent.services.openproject_service_v2 import OpenProjectServiceV2  # type: ignore

            svc = OpenProjectServiceV2()

            # Helpers to resolve type/status hrefs
            def _type_href(tname: str) -> str | None:
                try:
                    tid = svc._type_id(project_key, tname)  # type: ignore[attr-defined]
                    return f"/api/v3/types/{tid}" if tid else None
                except Exception:
                    return None

            def _status_href(sname: str) -> str | None:
                try:
                    statuses = svc.client.list_statuses() or {}  # type: ignore[attr-defined]
                    low = (sname or "").strip().lower()
                    for v in (statuses or {}).values():
                        try:
                            nm = str((v.get("name") or v.get("title") or "")).strip()
                            href = v.get("href") or (f"/api/v3/statuses/{v.get('id')}" if v.get("id") else None)
                            if nm and href and nm.lower() == low:
                                return href
                        except Exception:
                            continue
                except Exception:
                    return None
                return None

            for it in items:
                try:
                    subj = (it or {}).get("subject") or ""
                    desc = (it or {}).get("description") or ""
                    typ = (it or {}).get("type") or ""
                    status_name = (it or {}).get("status") or ""
                    cf = (it or {}).get("custom_fields") or {}
                    payload_wp: Dict[str, Any] = {
                        "subject": str(subj),
                        "description": {"raw": str(desc), "format": "markdown"},
                        "_links": {
                            "project": {"href": f"/api/v3/projects/{svc._project_id(project_key)}"}  # type: ignore[attr-defined]
                        },
                    }
                    th = _type_href(str(typ))
                    if th:
                        payload_wp["_links"]["type"] = {"href": th}
                    sh = _status_href(str(status_name)) if status_name else None
                    if sh:
                        payload_wp["_links"]["status"] = {"href": sh}
                    # Attach custom fields directly when provided
                    if isinstance(cf, dict):
                        for k, v in cf.items():
                            payload_wp[k] = v
                    wp_id = (it or {}).get("id")
                    if wp_id:
                        # Update requires lockVersion; fetch current
                        lock = 0
                        try:
                            cur = svc.client.work_package(wp_id)  # type: ignore[attr-defined]
                            lock = int((cur or {}).get("lockVersion") or 0)
                        except Exception:
                            lock = 0
                        payload_wp["lockVersion"] = lock
                        status_code, body = svc.client.update_work_package(wp_id, payload_wp)  # type: ignore[attr-defined]
                        if status_code in (200, 204):
                            updated.append({"id": str(wp_id), "status": status_code})
                        else:
                            errors.append({"id": str(wp_id), "error": f"update_failed:{status_code}", "body": body})
                    else:
                        status_code, body = svc.client.create_work_package(payload_wp)  # type: ignore[attr-defined]
                        if status_code in (200, 201):
                            new_id = str(body.get("id") or "")
                            if not new_id:
                                try:
                                    href = ((body.get("_links") or {}).get("self") or {}).get("href")
                                    if href:
                                        new_id = href.rstrip("/").split("/")[-1]
                                except Exception:
                                    pass
                            created.append({"id": new_id or body, "status": status_code, "subject": subj})
                        else:
                            errors.append({"id": None, "error": f"create_failed:{status_code}", "body": body})
                except Exception as ex:  # per-item guard
                    errors.append({"id": (it or {}).get("id"), "error": str(ex)})
            return {"ok": len(errors) == 0, "created": created, "updated": updated, "errors": errors}
        except Exception as ex:  # pragma: no cover
            return {"ok": False, "error": str(ex)}

    @app.tool("observability.tracing_config_summary")  # type: ignore
    def tracing_config_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
        from wpr_agent.shared.config_loader import TracingConfig

        cfg = TracingConfig.load()
        return {
            "ok": True,
            "enabled": cfg.enabled,
            "host": cfg.host or "",
            "has_public_key": bool(cfg.public_key),
            "has_secret_key": bool(cfg.secret_key),
        }

    @app.tool("openproject.apply_product_order")  # type: ignore
    def apply_product_order(payload: Dict[str, Any]) -> Dict[str, Any]:
        domain = (payload or {}).get("bundle_domain")
        project_key = (payload or {}).get("project_key")
        fieldmap_dict = (payload or {}).get("fieldmap")
        bp_plan = (payload or {}).get("bp_plan")
        max_retries = (payload or {}).get("max_retries", 3)
        backoff_base = (payload or {}).get("backoff_base", 0.5)
        dry_run = (payload or {}).get("dry_run", False)

        if not project_key or not bp_plan:
            return {"ok": False, "error": "project_key_and_bp_plan_required"}

        try:
            from wpr_agent.services.openproject_service_v2 import OpenProjectServiceV2  # type: ignore
            from wpr_agent.cli.apply_plan import apply_bp  # type: ignore
            from wpr_agent.models import TrackerFieldMap

            svc = OpenProjectServiceV2()
            
            # Reconstruct FieldMap
            fmap = TrackerFieldMap()
            if fieldmap_dict:
                for k, v in fieldmap_dict.items():
                    if hasattr(fmap, k):
                        setattr(fmap, k, v)

            created, warnings, errors, stats, timings = apply_bp(
                svc,
                bundle_domain=str(domain or ""),
                project_key=str(project_key),
                fieldmap=fmap,
                bp_plan=bp_plan,
                max_retries=int(max_retries),
                backoff_base=float(backoff_base),
                dry_run=bool(dry_run),
            )
            
            return {
                "ok": True,
                "created": created,
                "warnings": warnings,
                "errors": errors,
                "stats": stats,
                "timings": timings,
                "updated": created.get("updated", [])
            }
        except Exception as ex:  # pragma: no cover
            return {"ok": False, "error": str(ex)}

    @app.tool("openproject.apply_bp")  # type: ignore
    def apply_bp_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
        return apply_product_order(payload)

    return app
