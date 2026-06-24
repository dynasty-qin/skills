#!/usr/bin/env python3
"""Optional data fetcher for fund metrics.

This script tries to use AKShare to fetch public fund NAV history and writes
`data/fund_metrics.csv`. It is intentionally best-effort because free/open data
sources may change. If fetching fails, the rest of the Skill can still run using
manual snapshots and user-supplied metrics.

Install optional dependencies:
    pip install akshare pandas

Run:
    python scripts/fetch_fund_data.py
"""

from __future__ import annotations

import csv
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Import shared path resolution from fund_skill_core.
from fund_skill_core import config_dir, data_dir

SKILL_DIR = Path(__file__).resolve().parents[1]


def load_yaml(path: str) -> Dict[str, Any]:
    p = SKILL_DIR / path
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def safe_float(x: Any) -> Optional[float]:
    try:
        if x is None or x == "":
            return None
        return float(str(x).replace("%", ""))
    except Exception:
        return None


def max_drawdown(values: List[float]) -> Optional[float]:
    if not values:
        return None
    peak = values[0]
    mdd = 0.0
    for v in values:
        peak = max(peak, v)
        if peak:
            mdd = min(mdd, v / peak - 1)
    return mdd


def simple_volatility(returns: List[float]) -> Optional[float]:
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(var) * math.sqrt(252)


def get_candidates() -> List[Dict[str, Any]]:
    pool = load_yaml("config/fund_pool.yaml").get("categories", {})
    out = []
    for cat, info in pool.items():
        for c in info.get("candidates", []):
            out.append({"category": cat, **c})
    return out


def fetch_nav_with_akshare(code: str):
    import akshare as ak  # type: ignore

    # Open fund historical NAV. This covers many open-end funds and ETF link funds.
    # AKShare source fields may change; we normalize common column names below.
    df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
    return df


def normalize_nav_rows(df) -> List[Dict[str, Any]]:
    # Common AKShare columns: 净值日期, 单位净值, 日增长率
    date_col = None
    nav_col = None
    change_col = None
    for col in df.columns:
        if "日期" in str(col):
            date_col = col
        if "单位净值" in str(col):
            nav_col = col
        if "增长率" in str(col):
            change_col = col
    rows = []
    if date_col is None or nav_col is None:
        return rows
    for _, r in df.iterrows():
        rows.append(
            {
                "date": str(r[date_col]),
                "nav": safe_float(r[nav_col]),
                "daily_return": (safe_float(r[change_col]) / 100.0 if change_col and safe_float(r[change_col]) is not None else None),
            }
        )
    rows = [r for r in rows if r["nav"] is not None]
    rows.sort(key=lambda x: x["date"])
    return rows


def calculate_metrics(nav_rows: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    if not nav_rows:
        return {}
    navs = [float(r["nav"]) for r in nav_rows]
    latest = navs[-1]
    result: Dict[str, Optional[float]] = {"latest_nav": latest}

    def ret_by_days(days: int) -> Optional[float]:
        if len(navs) <= days:
            return None
        base = navs[-days - 1]
        return latest / base - 1 if base else None

    result["return_1m"] = ret_by_days(21)
    result["return_3m"] = ret_by_days(63)
    result["return_6m"] = ret_by_days(126)
    result["return_1y"] = ret_by_days(252)

    recent_navs = navs[-252:] if len(navs) >= 20 else navs
    result["max_drawdown_1y"] = max_drawdown(recent_navs)

    daily_returns = []
    for i in range(1, len(recent_navs)):
        if recent_navs[i - 1]:
            daily_returns.append(recent_navs[i] / recent_navs[i - 1] - 1)
    result["volatility_1y"] = simple_volatility(daily_returns)
    return result


def main() -> int:
    candidates = get_candidates()
    out_path = data_dir() / "fund_metrics.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "code", "name", "category", "fund_type", "status", "data_status", "latest_nav",
        "return_1m", "return_3m", "return_6m", "return_1y", "max_drawdown_1y", "volatility_1y",
        "tracking_score", "scale_score", "fee_score", "manager_score",
    ]
    records = []
    try:
        import akshare  # noqa: F401
    except Exception as exc:
        print(f"AKShare not available: {exc}")
        print("Create data/fund_metrics.csv manually using data/fund_metrics.template.csv.")
        return 1

    for c in candidates:
        code = str(c.get("code"))
        record = {
            "code": code,
            "name": c.get("name", ""),
            "category": c.get("category", ""),
            "fund_type": c.get("type", ""),
            "status": c.get("status", "candidate"),
            "data_status": "missing",
            "tracking_score": "",
            "scale_score": "",
            "fee_score": "",
            "manager_score": "",
        }
        try:
            df = fetch_nav_with_akshare(code)
            nav_rows = normalize_nav_rows(df)
            metrics = calculate_metrics(nav_rows)
            for k, v in metrics.items():
                record[k] = "" if v is None else f"{v:.6f}"
            record["data_status"] = "ok" if metrics else "empty"
        except Exception as exc:
            record["data_status"] = f"error: {exc}"[:120]
        records.append(record)

    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
