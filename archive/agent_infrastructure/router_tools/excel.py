from __future__ import annotations

"""
Excel tools for Step 11 Router (Phase 2).

Tools
- read_excel_normalize_tool(file, sheet) -> DataFrame
  Read Excel; ensure required columns; canonicalize Domain using Domain1 fallback when empty.

- group_domain_bp_tool(df) -> list[(domain, [(bp_id, subdf)])]
  Group normalized DataFrame by Domain→BP (BP ID).
"""

from typing import List, Tuple

import pandas as pd

from wpr_agent.tools.excel_tools import ensure_columns, group_by_domain_then_bp
from wpr_agent.router.utils import log_kv


def read_excel_normalize_tool(file: str, sheet: str = "Sheet1") -> pd.DataFrame:
    """Read and normalize Excel for planning.

    Inputs
    - file: Path to the Excel workbook
    - sheet: Worksheet name (default 'Sheet1')

    Returns
    - pandas.DataFrame with required columns ensured and Domain canonicalized

    Side effects
    - Logs row/column counts; indicates that canonicalization has been applied
    """
    df = pd.read_excel(file, sheet_name=sheet, engine="openpyxl").fillna("")
    before_cols = list(df.columns)
    df = ensure_columns(df)
    after_cols = list(df.columns)
    log_kv("excel_read", rows=len(df), cols=len(after_cols), sheet=sheet)
    if len(after_cols) != len(before_cols):
        log_kv("excel_fill", added_cols=len(set(after_cols) - set(before_cols)))
    return df



def group_product_order_tool(df: pd.DataFrame) -> List[Tuple[str, List[Tuple[str, pd.DataFrame]]]]:
    """Group normalized DataFrame by Product + WPR WP Order ID.

    Inputs
    - df: normalized DataFrame (ensure_columns already applied)

    Returns
    - list of (product, [(order_id, subdf)]) pairs

    Side effects
    - Logs product count and total orders across all products
    """
    work = df.copy()
    result: List[Tuple[str, List[Tuple[str, pd.DataFrame]]]] = []
    total_orders = 0
    for prod_val, prod_df in work.groupby("Product", dropna=False):
        orders = [(str(oid or ""), sub) for oid, sub in prod_df.groupby("WP Order ID", dropna=False)]
        total_orders += len(orders)
        result.append((str(prod_val or ""), orders))
    log_kv("group_product_order", products=len(result), total_orders=total_orders)
    return result


def group_domain_bp_tool(df: pd.DataFrame) -> List[Tuple[str, List[Tuple[str, pd.DataFrame]]]]:
    """Group normalized DataFrame by Domain→BP.

    Inputs
    - df: normalized DataFrame (ensure_columns already applied)

    Returns
    - list of (domain, [(bp_id, subdf)]) pairs

    Notes
    - Legacy route helper (no logging emitted here to reduce noise).
    """
    grouped = group_by_domain_then_bp(df)
    return grouped

