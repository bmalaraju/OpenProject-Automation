from __future__ import annotations

"""
Graph Introspect: print and render the Router graph structure (PNG).

Usage (IPython or plain Python):
  %run wpr_agent/scripts/graph_introspect.py

If LangGraph is installed, we confirm availability and render a static view of the
node wiring defined in graph.py (sufficient as a bird's‑eye reference). A PNG is
written to artifacts/graph/router_graph.png, and displayed with IPython.display
when available.
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BASE_DIR.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from wpr_agent.router.graph import build_router_graph  # type: ignore

try:
    from graphviz import Digraph  # type: ignore
except Exception:  # pragma: no cover
    Digraph = None  # type: ignore

try:
    from IPython.display import Image, display  # type: ignore
except Exception:  # pragma: no cover
    Image = None  # type: ignore
    display = None  # type: ignore


def _render_png_matplotlib(nodes: list[str], edges: list[tuple[str, str, str]]) -> Path | None:
    """Render a simple fixed-layout PNG using matplotlib (no Graphviz required)."""
    try:
        import matplotlib
        matplotlib.use("Agg")  # headless
        import matplotlib.pyplot as plt
    except Exception as ex:  # pragma: no cover
        print(f"matplotlib_unavailable: {ex}")
        return None

    # Fixed layout coordinates (left to right)
    coords = {
        "load_registry": (0.1, 0.7),
        "read_excel": (0.3, 0.7),
        "group_domain_bp": (0.5, 0.7),
        "compile_validate": (0.7, 0.85),
        "discover_compile_validate_apply": (0.7, 0.55),
        "aggregate_report": (0.9, 0.7),
    }
    # Figure
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.axis("off")
    # Draw nodes as rounded boxes
    def box(x, y, text):
        w, h = 0.16, 0.18
        rect = plt.Rectangle((x - w/2, y - h/2), w, h, linewidth=1.2, edgecolor="#5B6B7A",
                             facecolor="#EFF3F8", zorder=2)
        ax.add_patch(rect)
        ax.text(x, y, text, ha="center", va="center", fontsize=9, zorder=3)
    for n in nodes:
        if n in coords:
            box(*coords[n], n)
    # Draw arrows with labels
    def arrow(p1, p2, label=""):
        x1, y1 = coords[p1]
        x2, y2 = coords[p2]
        ax.annotate("", xy=(x2-0.02, y2), xytext=(x1+0.02, y1),
                    arrowprops=dict(arrowstyle="->", color="#5B6B7A", lw=1.2), zorder=1)
        if label:
            ax.text((x1+x2)/2, (y1+y2)/2 + 0.07*(1 if y2>y1 else -1), label, fontsize=9, color="#5B6B7A")
    for src, dst, lab in edges:
        if src in coords and dst in coords:
            arrow(src, dst, lab)

    out_dir = REPO_ROOT / "artifacts" / "graph"
    out_dir.mkdir(parents=True, exist_ok=True)
    png_path = out_dir / "router_graph.png"
    try:
        fig.tight_layout()
        fig.savefig(png_path, dpi=150)
        plt.close(fig)
        return png_path
    except Exception as ex:  # pragma: no cover
        print(f"matplotlib_render_error: {ex}")
        try:
            plt.close(fig)
        except Exception:
            pass
        return None


def _render_png(nodes: list[str], edges: list[tuple[str, str, str]]) -> Path | None:
    # Build a simple DOT and render to PNG if graphviz is available
    out_dir = REPO_ROOT / "artifacts" / "graph"
    out_dir.mkdir(parents=True, exist_ok=True)
    dot_path = out_dir / "router_graph.dot"
    png_path = out_dir / "router_graph.png"
    # 1) Try Graphviz if available
    if Digraph is not None:
        try:
            g = Digraph("router", format="png")
            g.attr(rankdir="LR", fontsize="10")
            g.attr("node", shape="box", style="rounded,filled", fillcolor="#EFF3F8", color="#5B6B7A")
            for n in nodes:
                g.node(n)
            for src, dst, label in edges:
                attrs = {"color": "#5B6B7A"}
                if label:
                    attrs["label"] = label
                    attrs["fontsize"] = "10"
                g.edge(src, dst, **attrs)
            g.save(filename=str(dot_path))
            g.render(filename=str(png_path.with_suffix("").as_posix()), cleanup=True)
            return png_path
        except Exception as ex:
            print(f"graphviz_render_error: {ex}")
            # fall through to matplotlib

    # 2) Try Matplotlib fallback
    mp = _render_png_matplotlib(nodes, edges)
    if mp is not None:
        return mp

    # 3) As a last resort, write a DOT for external tools
    lines = ["digraph router {"]
    for n in nodes:
        lines.append(f'  "{n}";')
    for src, dst, label in edges:
        if label:
            lines.append(f'  "{src}" -> "{dst}" [label="{label}"];')
        else:
            lines.append(f'  "{src}" -> "{dst}";')
    lines.append("}")
    dot_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote_dot_only: {dot_path}")
    return None


def main() -> None:
    app = build_router_graph(domain_concurrency=1)
    print("graph_build:", "available=True" if app is not None else "available=False")
    # Static reference structure as defined in graph.py
    nodes = [
        "load_registry",
        "read_excel",
        "group_domain_bp",
        "compile_validate",
        "discover_compile_validate_apply",
        "aggregate_report",
    ]
    edges = [
        ("load_registry", "read_excel", ""),
        ("read_excel", "group_domain_bp", ""),
        ("group_domain_bp", "compile_validate", "offline"),
        ("group_domain_bp", "discover_compile_validate_apply", "online"),
        ("compile_validate", "aggregate_report", ""),
        ("discover_compile_validate_apply", "aggregate_report", ""),
    ]
    print("nodes:")
    for n in nodes:
        print(" -", n)
    print("routes:")
    print(" load_registry -> read_excel -> group_domain_bp")
    print(" group_domain_bp -> offline: compile_validate -> aggregate_report")
    print(" group_domain_bp -> online:  discover_compile_validate_apply -> aggregate_report")

    # Render to PNG and display when possible
    png = _render_png(nodes, edges)
    if png and Image and display:
        try:
            display(Image(filename=str(png)))
        except Exception:
            print(f"png_written: {png}")
    elif png:
        print(f"png_written: {png}")


if __name__ == "__main__":
    main()
