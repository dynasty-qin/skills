"""Core logic for the Fund Investment Skill.

This module is intentionally conservative:
- It never executes trades.
- It lowers recommendation strength when data quality is weak.
- It prefers portfolio allocation discipline over short-term performance chasing.

Configuration discovery order:
  1. If config/obsidian_path.yaml exists and is valid, read/write from Obsidian vault.
  2. Otherwise, fall back to skill-local config/*.yaml (example data) and local reports/.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

SKILL_DIR = Path(__file__).resolve().parents[1]

# ── 中文映射 ────────────────────────────────────────────
ROLE_CN = {
    "core": "宽基核心",
    "satellite": "行业卫星",
    "hedge": "黄金对冲",
    "defense": "债基防守",
}

CATEGORY_CN = {
    "a500": "中证A500",
    "gold": "黄金",
    "bond": "债券",
    "new_energy_vehicle": "新能源车",
    "baijiu": "白酒",
    "medical": "医疗健康",
    "robotics": "机器人",
}

CONFIDENCE_CN = {
    "medium_high": "中高",
    "medium": "中",
    "low": "低",
    "unknown": "未知",
}

DATA_QUALITY_CN = {
    "high": "高",
    "medium": "中",
    "low": "低",
    "manual": "手动",
    "unknown": "未知",
}

STATUS_CN = {
    "holding": "持有",
    "candidate": "候选",
}

FUND_TYPE_CN = {
    "etf_linked": "ETF联接",
    "commodity_linked": "商品联接",
    "bond_rolling": "滚动持有债基",
    "index_lof": "指数LOF",
    "active_equity": "主动权益",
    "passive_index": "被动指数",
    "enhanced_index": "指数增强",
    "passive_sector": "行业指数",
    "active_sector": "主动行业",
}

RISK_PROFILE_CN = {
    "balanced_growth": "均衡成长",
    "conservative": "保守",
    "aggressive": "激进",
}


def role_cn(key: str) -> str:
    return ROLE_CN.get(key, key)


def category_cn(key: str) -> str:
    return CATEGORY_CN.get(key, key)


def confidence_cn(key: str) -> str:
    return CONFIDENCE_CN.get(key, key)


def data_quality_cn(key: str) -> str:
    return DATA_QUALITY_CN.get(key, key)


def status_cn(key: str) -> str:
    return STATUS_CN.get(key, key)


def fund_type_cn(key: str) -> str:
    return FUND_TYPE_CN.get(key, key)


def risk_profile_cn(key: str) -> str:
    return RISK_PROFILE_CN.get(key, key)
# ────────────────────────────────────────────────────────


def _resolve_obsidian_root() -> Optional[Path]:
    """Try to load obsidian_path.yaml and return the 基金投研/ root.

    Returns None if obsidian_path.yaml is missing, empty, or points to a
    non-existent directory.
    """
    obsidian_cfg = SKILL_DIR / "config" / "obsidian_path.yaml"
    if not obsidian_cfg.exists():
        return None
    with obsidian_cfg.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    vault_raw = cfg.get("vault", "")
    if not vault_raw or not vault_raw.strip():
        return None
    vault = Path(vault_raw.strip())
    fund_root = vault / "基金投研"
    if not fund_root.exists():
        return None
    return fund_root


def _obsidian_root() -> Optional[Path]:
    """Cached lookup for the Obsidian 基金投研/ root."""
    if not hasattr(_obsidian_root, "_cache"):
        _obsidian_root._cache = _resolve_obsidian_root()  # type: ignore[attr-defined]
    return _obsidian_root._cache  # type: ignore[attr-defined]


def config_dir() -> Path:
    """Return the active config directory."""
    obs = _obsidian_root()
    if obs:
        return obs / "config"
    return SKILL_DIR / "config"


def data_dir() -> Path:
    """Return the active data directory."""
    obs = _obsidian_root()
    if obs:
        return obs / "data"
    return SKILL_DIR / "data"


def reports_dir() -> Path:
    """Return the active reports root directory."""
    obs = _obsidian_root()
    if obs:
        return obs / "reports"
    return SKILL_DIR / "reports"


def load_yaml(filename: str) -> Dict[str, Any]:
    """Load a YAML file from the active config directory.

    filename should be just the basename, e.g. 'portfolio.yaml'.
    """
    # Preference: try Obsidian first. If the file doesn't exist there or
    # Obsidian is not configured, fall back to skill-local config.
    obs = _obsidian_root()
    candidates = []
    if obs:
        candidates.append(obs / "config" / filename)
    candidates.append(SKILL_DIR / "config" / filename)
    # Also try .example fallback for local-only runs.
    if not obs:
        example = SKILL_DIR / "config" / f"{Path(filename).stem}.example{Path(filename).suffix}"
        if example.exists():
            candidates.append(example)

    for path in candidates:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    return {}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def pct(value: Optional[float], digits: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.{digits}f}%"


def money(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value:,.2f}元"


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


@dataclass
class FundPosition:
    code: str
    name: str
    category: str
    role: str
    fund_type: str
    invested: float
    holding_return: float
    current_value: float
    target_min: float
    target_max: float
    confidence: str
    notes: str = ""


def load_positions() -> List[FundPosition]:
    raw = load_yaml("portfolio.yaml")
    positions: List[FundPosition] = []
    for item in raw.get("funds", []):
        invested = safe_float(item.get("invested"))
        holding_return = safe_float(item.get("holding_return"))
        current_value = invested * (1 + holding_return)
        positions.append(
            FundPosition(
                code=str(item.get("code")),
                name=str(item.get("name")),
                category=str(item.get("category")),
                role=str(item.get("role")),
                fund_type=str(item.get("fund_type", "unknown")),
                invested=invested,
                holding_return=holding_return,
                current_value=current_value,
                target_min=safe_float(item.get("target_min")),
                target_max=safe_float(item.get("target_max")),
                confidence=str(item.get("confidence", "unknown")),
                notes=str(item.get("notes", "")),
            )
        )
    return positions


def portfolio_totals(positions: List[FundPosition]) -> Dict[str, float]:
    total_invested = sum(p.invested for p in positions)
    total_value = sum(p.current_value for p in positions)
    total_pnl = total_value - total_invested
    total_return = total_pnl / total_invested if total_invested else 0.0
    return {
        "total_invested": total_invested,
        "total_value": total_value,
        "total_pnl": total_pnl,
        "total_return": total_return,
    }


def position_rows(positions: List[FundPosition]) -> List[Dict[str, Any]]:
    totals = portfolio_totals(positions)
    total_value = totals["total_value"] or 1
    rows = []
    for p in positions:
        rows.append(
            {
                "code": p.code,
                "name": p.name,
                "category": p.category,
                "role": p.role,
                "fund_type": p.fund_type,
                "invested": p.invested,
                "holding_return": p.holding_return,
                "current_value": p.current_value,
                "pnl": p.current_value - p.invested,
                "weight": p.current_value / total_value,
                "target_min": p.target_min,
                "target_max": p.target_max,
                "confidence": p.confidence,
                "notes": p.notes,
            }
        )
    return rows


def role_weights(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    weights: Dict[str, float] = {}
    for r in rows:
        weights[r["role"]] = weights.get(r["role"], 0.0) + r["weight"]
    return weights


def category_weights(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    weights: Dict[str, float] = {}
    for r in rows:
        weights[r["category"]] = weights.get(r["category"], 0.0) + r["weight"]
    return weights


def load_market_snapshot() -> Dict[str, Any]:
    snap = load_yaml("market_snapshot.yaml")
    items = {}
    for item in snap.get("items", []):
        items[str(item.get("code"))] = item
    return {
        "as_of": snap.get("as_of", "unknown"),
        "data_quality": snap.get("data_quality", "manual"),
        "items": items,
    }


def load_proxy_exposure() -> Dict[str, float]:
    ds = load_yaml("data_sources.yaml")
    out: Dict[str, float] = {}
    for code, info in (ds.get("fund_proxy_map") or {}).items():
        out[str(code)] = safe_float(info.get("exposure"), 1.0)
    return out


def estimate_daily_changes(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    snap = load_market_snapshot()
    exposure = load_proxy_exposure()
    estimated_rows: List[Dict[str, Any]] = []
    missing: List[str] = []
    quality_counts = {"high": 0, "medium": 0, "low": 0, "unknown": 0}

    for r in rows:
        item = snap["items"].get(r["code"])
        if not item:
            missing.append(r["code"])
            daily_change = None
            quality = "unknown"
        else:
            raw_change = safe_float(item.get("daily_change"), 0.0)
            # For bond funds, manual snapshot is treated as already direct.
            factor = exposure.get(r["code"], 1.0)
            if r["fund_type"].startswith("bond"):
                daily_change = raw_change
            else:
                daily_change = raw_change * factor
            quality = str(item.get("quality", "unknown"))
        quality_counts[quality if quality in quality_counts else "unknown"] += 1
        estimated_pnl = r["current_value"] * daily_change if daily_change is not None else None
        estimated_rows.append({**r, "estimated_daily_change": daily_change, "estimated_daily_pnl": estimated_pnl, "market_quality": quality})

    if missing:
        overall_quality = "low"
    elif quality_counts["low"] > 0 or snap.get("data_quality") == "manual":
        overall_quality = "medium"
    else:
        overall_quality = "high"

    meta = {
        "as_of": snap.get("as_of"),
        "overall_quality": overall_quality,
        "missing": missing,
        "quality_counts": quality_counts,
    }
    return estimated_rows, meta


def target_status(row: Dict[str, Any]) -> str:
    w = row["weight"]
    if row["target_min"] and w < row["target_min"]:
        return "低于目标"
    if row["target_max"] and w > row["target_max"]:
        return "高于目标"
    return "目标区间内"


def generate_recommendations(est_rows: List[Dict[str, Any]], meta: Dict[str, Any]) -> List[str]:
    recs: List[str] = []
    rows_by_code = {r["code"]: r for r in est_rows}
    rows_by_cat = {r["category"]: r for r in est_rows}

    def _lookup(category: str) -> tuple[str, str]:
        """Dynamically get fund code and name from a category."""
        r = rows_by_cat.get(category)
        if r:
            return r["code"], r["name"]
        return "???", "未知基金"

    data_quality = meta.get("overall_quality")
    if data_quality == "low":
        return ["数据质量为低：今日不输出明确买卖建议，只建议补充行情数据后再判断。"]

    # Core A500
    a500 = rows_by_cat.get("a500")
    if a500:
        code, name = _lookup("a500")
        chg = a500.get("estimated_daily_change")
        if a500["weight"] < 0.15:
            if chg is not None and chg < -0.01:
                recs.append(f"{code} {name} 核心宽基仓占比低于15%，且今日A500代理资产跌幅超过1%：如有新增资金，可考虑买入500-800元。")
            elif chg is not None and -0.01 <= chg <= 0.005:
                recs.append(f"{code} {name} 核心宽基仓占比低于15%，且今日A500处于小涨小跌区间：如有新增资金，可考虑买入300-500元。")
            elif chg is not None and chg > 0.015:
                recs.append(f"{code} {name} 核心宽基仓占比低于15%，但今日A500涨幅超过1.5%：不追高，保留定投计划。")
            else:
                recs.append(f"{code} {name} 核心宽基仓占比低于15%：优先通过后续新增资金继续建设核心仓。")
        elif a500["weight"] < a500["target_min"]:
            recs.append(f"{code} {name} 核心仓仍低于目标下限：后续新增资金仍优先配置A500。")

    # Gold
    gold = rows_by_cat.get("gold")
    if gold:
        code, name = _lookup("gold")
        if gold["weight"] > 0.30:
            recs.append(f"{code} {name} 黄金占比超过30%：暂停新增黄金，优先用新增资金稀释黄金占比。")
        elif gold["weight"] > 0.25:
            recs.append(f"{code} {name} 黄金占比仍偏高：不新增，等待后续再平衡。")
        if gold["weight"] > 0.25 and gold["holding_return"] > -0.03:
            recs.append(f"{code} {name} 若收益率修复到-3%以内且仓位仍高于25%，可考虑分批降低10%-20%的黄金仓位。")

    # Bond
    bond = rows_by_cat.get("bond")
    if bond and bond["weight"] < 0.20:
        code, name = _lookup("bond")
        recs.append(f"{code} {name} 债基/防守仓低于20%：新增资金中建议保留20%-30%补债基或现金类。")

    # Satellites
    for r in est_rows:
        if r["role"] != "satellite":
            continue
        if r["weight"] > 0.10:
            recs.append(f"{r['code']} {r['name']} 卫星仓占比超过10%：暂停新增该主题。")
        chg = r.get("estimated_daily_change")
        if chg is not None and chg > 0.03:
            recs.append(f"{r['code']} {r['name']} 今日估算涨幅超过3%：不追高。")
        if r["holding_return"] < -0.20 and r["weight"] < 0.08:
            recs.append(f"{r['code']} {r['name']} 亏损超过20%但仓位不高：只允许小额分批观察，不建议一次性重仓补仓。")

    # New energy special
    nev = rows_by_cat.get("new_energy_vehicle")
    if nev and nev["weight"] > 0.18 and nev["holding_return"] > 0.15:
        recs.append(f"{nev['code']} {nev['name']} 新能源车占比超过18%且收益率超过15%：可考虑止盈10%-20%。")

    if not recs:
        recs.append("今日未触发明确操作规则：建议观察，不因单日波动操作。")
    return recs


def table_md(headers: List[str], rows: Iterable[Iterable[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def generate_daily_report(report_date: Optional[str] = None) -> Path:
    if report_date is None:
        report_date = date.today().isoformat()
    positions = load_positions()
    rows = position_rows(positions)
    est_rows, meta = estimate_daily_changes(rows)
    totals = portfolio_totals(positions)
    recs = generate_recommendations(est_rows, meta)
    estimated_total_pnl = sum((r.get("estimated_daily_pnl") or 0.0) for r in est_rows)
    estimated_total_change = estimated_total_pnl / totals["total_value"] if totals["total_value"] else 0.0

    conclusion = recs[0] if recs else "今日建议观察。"

    fund_table = table_md(
        ["代码", "基金", "角色", "当前市值", "占比", "持有收益", "今日估算", "估算盈亏", "状态", "置信度"],
        [
            [
                r["code"],
                r["name"],
                role_cn(r["role"]),
                money(r["current_value"]),
                pct(r["weight"]),
                pct(r["holding_return"]),
                pct(r.get("estimated_daily_change")),
                money(r.get("estimated_daily_pnl")),
                target_status(r),
                confidence_cn(str(r.get("market_quality", r.get("confidence", "unknown")))),
            ]
            for r in est_rows
        ],
    )

    role_table = table_md(
        ["角色", "当前占比"],
        [[role_cn(role), pct(w)] for role, w in sorted(role_weights(est_rows).items())],
    )

    cat_table = table_md(
        ["类别", "当前占比"],
        [[category_cn(cat), pct(w)] for cat, w in sorted(category_weights(est_rows).items())],
    )

    content = f"""# 基金组合日报 - {report_date}

## 一、今日结论

{conclusion}

## 二、数据质量

- 行情快照时间：{meta.get('as_of')}
- 整体数据质量：{data_quality_cn(str(meta.get('overall_quality', 'unknown')))}
- 缺失数据：{', '.join(meta.get('missing') or []) if meta.get('missing') else '无'}

> 估算净值和估算盈亏仅供个人参考，不等于基金公司公布的正式净值。

## 三、组合概况

- 总投入：{money(totals['total_invested'])}
- 当前估算市值：{money(totals['total_value'])}
- 当前总盈亏：{money(totals['total_pnl'])}
- 当前总收益率：{pct(totals['total_return'])}
- 今日组合估算涨跌：{pct(estimated_total_change)}
- 今日组合估算盈亏：{money(estimated_total_pnl)}

## 四、持仓与今日估算

{fund_table}

## 五、角色占比

{role_table}

## 六、类别占比

{cat_table}

## 七、规则触发情况与今日建议

"""
    for rec in recs:
        content += f"- {rec}\n"

    content += """
## 八、风险提醒

- 每日任务只用于估值和操作纪律检查，不用于换基。
- 主动基金、债基估值置信度较低，不建议按盘中估值频繁操作。
- 如果数据来自手动快照，建议在操作前再次核对行情。
- 所有买卖决策由用户自行承担。
"""
    out_dir = reports_dir() / "daily"
    ensure_dir(out_dir)
    out_path = out_dir / f"{report_date}.md"
    out_path.write_text(content, encoding="utf-8")
    return out_path


def generate_weekly_report(report_date: Optional[str] = None) -> Path:
    if report_date is None:
        today = date.today()
        report_date = f"{today.isocalendar().year}-W{today.isocalendar().week:02d}"
    positions = load_positions()
    rows = position_rows(positions)
    totals = portfolio_totals(positions)
    recs = generate_recommendations(*estimate_daily_changes(rows))

    allocation_policy = load_yaml("allocation_policy.yaml").get("allocation", {})
    role_w = role_weights(rows)
    allocation_lines = []
    for role, policy in allocation_policy.items():
        current = role_w.get(role, 0.0)
        tmin = safe_float(policy.get("target_min"))
        tmax = safe_float(policy.get("target_max"))
        if current < tmin:
            status = "低于目标，新增资金优先补足" if role == "core" else "低于目标"
        elif current > tmax:
            status = "高于目标，暂停新增或等待再平衡"
        else:
            status = "目标区间内"
        allocation_lines.append([policy.get("name", role), pct(current), f"{pct(tmin)} - {pct(tmax)}", status])

    content = f"""# 基金组合周报 - {report_date}

## 一、本周结论

当前组合最需要关注的仍是：核心宽基仓是否不足、黄金仓位是否偏高、行业卫星仓是否超过目标。周报主要用于安排下周新增资金，不做激进换基。

## 二、组合表现

- 总投入：{money(totals['total_invested'])}
- 当前估算市值：{money(totals['total_value'])}
- 当前总盈亏：{money(totals['total_pnl'])}
- 当前总收益率：{pct(totals['total_return'])}

## 三、资产配置偏离

{table_md(['资产角色', '当前占比', '目标区间', '状态'], allocation_lines)}

## 四、下周新增资金分配建议

"""
    for rec in recs:
        content += f"- {rec}\n"
    content += """

## 五、纪律提醒

- 周报只解决仓位和新增资金分配，不因短期涨跌换基。
- 如果准备新增资金，优先修正偏离最大的资产类别。
- 如果没有新增资金，优先观察，避免为了调仓而频繁赎回。
"""
    out_dir = reports_dir() / "weekly"
    ensure_dir(out_dir)
    out_path = out_dir / f"{report_date}.md"
    out_path.write_text(content, encoding="utf-8")
    return out_path


def read_fund_metrics() -> List[Dict[str, Any]]:
    path = data_dir() / "fund_metrics.csv"
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def metric_score(row: Dict[str, Any]) -> Optional[float]:
    """Calculate a generic 0-100 score from optional metrics.

    This is intentionally simple. If the user or OpenClaw enriches data/fund_metrics.csv,
    monthly reports become more informative. Missing data returns None instead of inventing a score.
    """
    required_any = ["return_1y", "max_drawdown_1y", "volatility_1y", "scale_score", "fee_score"]
    if not any(row.get(k) not in (None, "") for k in required_any):
        return None
    ret = safe_float(row.get("return_1y"), 0.0)
    mdd = abs(safe_float(row.get("max_drawdown_1y"), 0.0))
    vol = abs(safe_float(row.get("volatility_1y"), 0.0))
    scale_score = safe_float(row.get("scale_score"), 60.0)
    fee_score = safe_float(row.get("fee_score"), 60.0)
    tracking_score = safe_float(row.get("tracking_score"), 60.0)
    manager_score = safe_float(row.get("manager_score"), 60.0)

    # Convert raw return/drawdown/volatility to bounded scores.
    return_score = max(0, min(100, 50 + ret * 200))
    drawdown_score = max(0, min(100, 100 - mdd * 250))
    volatility_score = max(0, min(100, 100 - vol * 200))

    fund_type = row.get("fund_type", "")
    if "enhanced" in fund_type:
        weights = [(return_score, 0.25), (drawdown_score, 0.20), (tracking_score, 0.15), (volatility_score, 0.15), (scale_score, 0.10), (fee_score, 0.10), (manager_score, 0.05)]
    elif "active" in fund_type:
        weights = [(return_score, 0.20), (drawdown_score, 0.20), (volatility_score, 0.15), (manager_score, 0.20), (scale_score, 0.10), (fee_score, 0.05), (tracking_score, 0.10)]
    elif "bond" in fund_type:
        weights = [(drawdown_score, 0.30), (volatility_score, 0.25), (return_score, 0.20), (scale_score, 0.10), (fee_score, 0.10), (manager_score, 0.05)]
    else:
        weights = [(tracking_score, 0.30), (fee_score, 0.20), (scale_score, 0.20), (drawdown_score, 0.10), (volatility_score, 0.10), (return_score, 0.10)]
    return sum(v * w for v, w in weights)


def generate_monthly_report(report_month: Optional[str] = None) -> Path:
    if report_month is None:
        today = date.today()
        report_month = f"{today.year}-{today.month:02d}"
    pool = load_yaml("fund_pool.yaml").get("categories", {})
    metrics = {m.get("code"): m for m in read_fund_metrics()}

    lines = []
    watch = []
    replace = []
    for cat, info in pool.items():
        candidates = info.get("candidates", [])
        for c in candidates:
            code = str(c.get("code"))
            m = metrics.get(code, {})
            if m:
                c = {**c, **m}
            score = metric_score(c)
            status = c.get("status", "candidate")
            score_text = "数据不足" if score is None else f"{score:.1f}"
            suggestion = "继续观察"
            if score is None:
                suggestion = "需补充指标后再评分"
            elif status == "holding" and score < 60:
                suggestion = "进入观察名单"
                watch.append(code)
            elif status == "candidate" and score >= 75:
                suggestion = "优质候选，需与当前持有同类比较"
            lines.append([info.get("display_name", cat), code, c.get("name", ""), c.get("type", ""), status_cn(status), score_text, suggestion])

    if not metrics:
        conclusion = "本月未找到 data/fund_metrics.csv 中的有效指标，不能给出换基建议；建议先执行数据抓取或手动补充基金池指标。"
    elif watch:
        conclusion = "部分持有基金评分偏低，进入观察名单；尚不建议立即替换，需连续多个周期确认。"
    else:
        conclusion = "本月未触发明确换基规则。"

    content = f"""# 月度基金优选报告 - {report_month}

## 一、本月结论

{conclusion}

## 二、基金池评分

{table_md(['类别', '代码', '基金', '类型', '状态', '综合评分', '建议'], lines)}

## 三、观察名单

{', '.join(watch) if watch else '暂无'}

## 四、淘汰名单

暂无。淘汰需要连续多个季度低评分、同类明显跑输、风格漂移或重大风险事件确认。

## 五、是否建议替换

当前不建议仅凭单月数据替换基金。若需要换基，必须满足 replacement_rules.md 中的观察、淘汰、冷却和分批切换规则。

## 六、下月观察重点

- 补充候选基金池的规模、费率、回撤、收益、跟踪误差、基金经理稳定性等指标。
- A500类基金重点比较被动联接与增强基金的长期稳定性，不因近一年表现直接全量切换。
- 主动医疗基金重点关注基金经理、风格稳定性和同类排名。
"""
    out_dir = reports_dir() / "monthly"
    ensure_dir(out_dir)
    out_path = out_dir / f"{report_month}.md"
    out_path.write_text(content, encoding="utf-8")
    return out_path


def generate_quarterly_report(report_quarter: Optional[str] = None) -> Path:
    today = date.today()
    if report_quarter is None:
        q = (today.month - 1) // 3 + 1
        report_quarter = f"{today.year}-Q{q}"
    positions = load_positions()
    rows = position_rows(positions)
    totals = portfolio_totals(positions)
    role_w = role_weights(rows)

    content = f"""# 季度策略复盘 - {report_quarter}

## 一、季度结论

季度复盘用于检查策略本身是否需要调整。当前版本优先检查资产配置、行业保留价值、基金池更新和操作纪律。

## 二、当前组合概况

- 总投入：{money(totals['total_invested'])}
- 当前估算市值：{money(totals['total_value'])}
- 当前总收益率：{pct(totals['total_return'])}

## 三、资产配置检查

{table_md(['角色', '当前占比'], [[role_cn(role), pct(w)] for role, w in sorted(role_w.items())])}

## 四、策略检查问题清单

- A500核心仓是否已经达到25%-35%？
- 黄金是否已经降到10%-20%？
- 债基/现金是否保持25%-30%？
- 新能源、医疗、白酒、机器人等行业主题是否仍符合长期配置逻辑？
- 本季度是否出现过度交易、追涨杀跌或违反规则的操作？
- 候选基金池是否需要新增或剔除基金？

## 五、下一季度建议

- 优先使用新增资金修正仓位，而不是频繁赎回切换。
- 月度基金评分连续异常后，再考虑换基。
- 若行业长期逻辑发生变化，应先调整行业目标仓位，再考虑具体基金替换。
"""
    out_dir = reports_dir() / "quarterly"
    ensure_dir(out_dir)
    out_path = out_dir / f"{report_quarter}.md"
    out_path.write_text(content, encoding="utf-8")
    return out_path


# ── Obsidian 配置同步 ───────────────────────────────────

def sync_obsidian_summary() -> Optional[Path]:
    """将 yaml/csv 配置同步为 Obsidian 可见的 Markdown 汇总文件。

    生成两个 md 文件到 Obsidian vault 的 基金投研/ 目录：
      - 组合配置总览.md  (所有 config/*.yaml 的汇总)
      - 操作日志.md       (data/operation_log.csv 的表格)

    仅当 obsidian_path.yaml 存在且有效时才执行。
    """
    obs = _obsidian_root()
    if not obs:
        return None

    # ── 1. 组合配置总览 ──
    portfolio = load_yaml("portfolio.yaml")
    alloc = load_yaml("allocation_policy.yaml")
    fund_pool = load_yaml("fund_pool.yaml")
    prefs = load_yaml("user_preferences.yaml")
    alerts = load_yaml("alert_rules.yaml")
    watchlist = load_yaml("watchlist.yaml")
    blacklist = load_yaml("blacklist.yaml")
    snapshot = load_yaml("market_snapshot.yaml")

    as_of = portfolio.get("as_of", "未知")

    # 持仓表
    fund_rows = []
    for f in portfolio.get("funds", []):
        invested = safe_float(f.get("invested"))
        ret = safe_float(f.get("holding_return"))
        val = invested * (1 + ret)
        fund_rows.append([
            str(f.get("code", "")),
            str(f.get("name", "")),
            role_cn(str(f.get("role", ""))),
            category_cn(str(f.get("category", ""))),
            money(invested),
            money(val),
            pct(ret),
            confidence_cn(str(f.get("confidence", ""))),
            str(f.get("notes", "")),
        ])
    fund_table = table_md(
        ["代码", "基金", "角色", "类别", "投入", "当前市值", "收益", "置信度", "备注"],
        fund_rows,
    )

    # 目标资产配置
    alloc_rows = []
    for role, pol in (alloc.get("allocation") or {}).items():
        alloc_rows.append([
            str(pol.get("name", role)),
            f"{pct(safe_float(pol.get('target_min')))}" + " – " + f"{pct(safe_float(pol.get('target_max')))}",
            str(pol.get("description", "")),
        ])
    alloc_table = table_md(["资产角色", "目标区间", "说明"], alloc_rows)

    # 单基金限制
    limits = alloc.get("single_fund_limits", {})
    limits_rows = [
        ["宽基核心单只上限", pct(safe_float(limits.get("core_max")))],
        ["黄金单只上限", pct(safe_float(limits.get("hedge_max")))],
        ["债基单只上限", pct(safe_float(limits.get("bond_max")))],
        ["卫星仓单只上限", pct(safe_float(limits.get("satellite_single_max")))],
        ["高波动主题上限", pct(safe_float(limits.get("high_volatility_single_max")))],
    ]
    limits_table = table_md(["限制项", "阈值"], limits_rows)

    # 候选基金池
    pool_lines = []
    for cat, info in (fund_pool.get("categories") or {}).items():
        pool_lines.append(f"### {info.get('display_name', cat)}")
        pool_lines.append(f"> 策略：{info.get('strategy', '')}")
        pool_lines.append("")
        cand_rows = []
        for c in info.get("candidates", []):
            cand_rows.append([
                str(c.get("code", "")),
                str(c.get("name", "")),
                fund_type_cn(str(c.get("type", ""))),
                status_cn(str(c.get("status", ""))),
                str(c.get("note", "")),
            ])
        if cand_rows:
            pool_lines.append(table_md(["代码", "基金", "类型", "状态", "备注"], cand_rows))
        pool_lines.append("")
    pool_section = "\n".join(pool_lines)

    # 告警规则
    conc = alerts.get("alerts", {}).get("concentration", {})
    mkt = alerts.get("alerts", {}).get("market_move", {})
    qual = alerts.get("alerts", {}).get("fund_quality", {})
    dataq = alerts.get("alerts", {}).get("data_quality", {})

    alert_rows = [
        ["黄金仓位告警", f">{pct(safe_float(conc.get('gold_weight_above')))} 暂停新增"],
        ["卫星仓单只告警", f">{pct(safe_float(conc.get('satellite_single_above')))} 暂停新增"],
        ["核心仓偏低告警", f"<{pct(safe_float(conc.get('core_below')))} 优先补仓"],
        ["债基偏低告警", f"<{pct(safe_float(conc.get('bond_below')))} 保留资金补债基"],
        ["追高抑制线", f"日涨幅>{pct(safe_float(mkt.get('avoid_chasing_if_daily_up_above')))} 不追"],
        ["加仓信号线", f"日跌幅<{pct(safe_float(mkt.get('consider_more_core_if_daily_down_below')))} 可加"],
        ["卫星不追线", f"日涨幅>{pct(safe_float(mkt.get('satellite_avoid_chasing_if_daily_up_above')))} 不追"],
        ["观察评分线", f"<{safe_float(qual.get('watch_score_below')):.0f}分"],
        ["淘汰评分线", f"<{safe_float(qual.get('replace_score_below')):.0f}分"],
        ["替代候选线", f">{safe_float(qual.get('replacement_candidate_score_above')):.0f}分"],
        ["最小分差", f"{safe_float(qual.get('min_score_gap_for_replacement')):.0f}分"],
        ["观察季度数", f"{safe_float(qual.get('watch_consecutive_quarters')):.0f}个季度"],
        ["淘汰季度数", f"{safe_float(qual.get('replace_consecutive_quarters')):.0f}个季度"],
        ["最低数据质量", data_quality_cn(str(dataq.get('min_quality_for_action', '')))],
    ]
    alert_table = table_md(["规则", "阈值"], alert_rows)

    # 用户偏好
    prefs_rows = [
        ["风险画像", risk_profile_cn(str(prefs.get("risk_profile", "")))],
        ["默认买入单位", money(safe_float(prefs.get("default_buy_unit")))],
        ["小额买入单位", money(safe_float(prefs.get("small_buy_unit")))],
        ["单日买入上限", money(safe_float(prefs.get("max_single_day_buy")))],
        ["单次切换上限", pct(safe_float(prefs.get("max_single_switch_ratio")))],
        ["换基冷却天数", f"{safe_float(prefs.get('cooling_days_before_replacement')):.0f}天"],
        ["优先新增资金再平衡", "是" if prefs.get("prefer_new_cash_rebalance") else "否"],
        ["禁止自动交易", "是" if prefs.get("avoid_auto_trading") else "否"],
    ]
    prefs_table = table_md(["偏好", "设置"], prefs_rows)

    # 观察/黑名单
    wl = watchlist.get("watchlist", [])
    bl = blacklist.get("blacklist", [])

    # 行情快照
    snap_items = snapshot.get("items", [])
    snap_rows = []
    for s in snap_items:
        snap_rows.append([
            str(s.get("code", "")),
            str(s.get("name", "")),
            pct(safe_float(s.get("daily_change"))),
            data_quality_cn(str(s.get("quality", ""))),
        ])
    snap_table = table_md(["代码", "基金/代理", "今日涨跌", "质量"], snap_rows) if snap_rows else "（暂无手动快照数据）"

    content = f"""# 📊 组合配置总览

> 由脚本自动生成，数据来源：`config/*.yaml`。更新时间：`{as_of}`

## 一、当前持仓

{fund_table}

## 二、目标资产配置

{alloc_table}

### 单基金仓位限制

{limits_table}

### 配置优先级

"""
    for p in alloc.get("priority", []):
        content += f"- {p}\n"

    content += f"""
## 三、候选基金池

{pool_section}

## 四、告警规则

{alert_table}

## 五、用户偏好

{prefs_table}

## 六、观察名单

{', '.join(str(x) for x in wl) if wl else '暂无'}

## 七、黑名单

{', '.join(str(x) for x in bl) if bl else '暂无'}

## 八、手动行情快照

{snap_table}
"""

    out_path = obs / "📊 组合配置总览.md"
    out_path.write_text(content, encoding="utf-8")

    # ── 2. 操作日志 ──
    log_path = data_dir() / "operation_log.csv"
    log_content = """# 📋 操作日志

> 由脚本自动生成，数据来源：`data/operation_log.csv`。

"""
    if log_path.exists():
        with log_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            log_rows = []
            for row in reader:
                log_rows.append([
                    str(row.get("date", "")),
                    str(row.get("fund_code", "")),
                    str(row.get("action", "")),
                    str(row.get("amount", "")),
                    str(row.get("reason", "")),
                    str(row.get("rule_triggered", "")),
                    str(row.get("note", "")),
                ])
            if log_rows:
                log_content += table_md(
                    ["日期", "基金代码", "操作", "金额", "原因", "触发规则", "备注"],
                    log_rows,
                )
            else:
                log_content += "暂无操作记录。\n"
    else:
        log_content += "暂无操作记录文件。\n"

    log_out = obs / "📋 操作日志.md"
    log_out.write_text(log_content, encoding="utf-8")

    return out_path


# ── Cron 自检 ─────────────────────────────────────────

# 四个必需的 cron 任务定义
CRON_JOBS = [
    {
        "name": "fund-daily",
        "description": "基金组合日报 - 每个 A 股交易日 14:30",
        "schedule": {"kind": "cron", "expr": "30 14 * * 1-5", "tz": "Asia/Shanghai"},
        "payload": {
            "kind": "agentTurn",
            "message": (
                "你是基金投研助手。生成今日基金组合日报。\n\n"
                "## 执行步骤\n\n"
                "### 第一步：读取持仓\n"
                "读取 E:\\MyVault\\基金投研\\📊 组合配置总览.md 获取所有持仓基金代码。\n\n"
                "### 第二步：抓取实时估值\n"
                "对每只基金用 web_fetch 并行抓取天天基金估值：\n"
                "https://fundgz.1234567.com.cn/js/{code}.js\n\n"
                "解析返回的 jsonpgz({...}) JSONP 数据，提取：fundcode/name/jzrq/dwjz/gsz/gszzl/gztime。\n"
                "将结果写入 E:\\MyVault\\基金投研\\config\\market_snapshot.yaml：\n"
                "- as_of: 当前时间\n"
                "- data_quality: \"high\"（全部成功）或 \"medium\"（部分失败）\n"
                "- items: 每只基金的 code/name/daily_change（gszzl÷100）/source/quality\n\n"
                "### 第三步：运行报告脚本\n"
                "执行 python F:\\AI\\skills\\fund-investment-skill"
                "\\scripts\\run_fund_skill.py --mode daily\n\n"
                "### 第四步：发送摘要\n"
                "读取 E:\\MyVault\\基金投研\\reports\\daily\\ 下最新生成的日报，"
                "提取关键信息（今日结论、规则触发、建议），以简洁格式发送给我。"
            ),
            "timeoutSeconds": 180,
            "toolsAllow": ["exec", "read", "write", "sessions_send", "web_fetch"],
        },
        "sessionTarget": "isolated",
        "delivery": {"mode": "announce", "channel": "feishu", "to": "user:ou_21ee891c7fdf54b0e45d8a3e31a0ed8f"},
    },
    {
        "name": "fund-weekly",
        "description": "基金组合周报 - 每周五 20:00",
        "schedule": {"kind": "cron", "expr": "0 20 * * 5", "tz": "Asia/Shanghai"},
        "payload": {
            "kind": "agentTurn",
            "message": (
                "你是基金投研助手。生成本周基金组合周报。\n\n"
                "## 执行步骤\n\n"
                "### 第一步：读取持仓\n"
                "读取 E:\\MyVault\\基金投研\\📊 组合配置总览.md 获取所有持仓基金代码。\n\n"
                "### 第二步：抓取当日估值（盘后为实际净值）\n"
                "对每只基金用 web_fetch 并行抓取天天基金估值：\n"
                "https://fundgz.1234567.com.cn/js/{code}.js\n\n"
                "解析 jsonpgz 数据并写入 E:\\MyVault\\基金投研\\config\\market_snapshot.yaml。\n\n"
                "### 第三步：运行周报脚本\n"
                "执行 python F:\\AI\\skills\\fund-investment-skill"
                "\\scripts\\run_fund_skill.py --mode weekly\n\n"
                "### 第四步：发送摘要\n"
                "读取 E:\\MyVault\\基金投研\\reports\\weekly\\ 下最新生成的周报，"
                "提取关键信息（仓位偏离、下周资金分配建议），以简洁格式发送给我。"
            ),
            "timeoutSeconds": 180,
            "toolsAllow": ["exec", "read", "write", "sessions_send", "web_fetch"],
        },
        "sessionTarget": "isolated",
        "delivery": {"mode": "announce", "channel": "feishu", "to": "user:ou_21ee891c7fdf54b0e45d8a3e31a0ed8f"},
    },
    {
        "name": "fund-monthly",
        "description": "基金组合月报 - 每月最后一天 20:00",
        "schedule": {"kind": "cron", "expr": "0 20 L * *", "tz": "Asia/Shanghai"},
        "payload": {
            "kind": "agentTurn",
            "message": (
                "你是基金投研助手。生成本月基金优选月报。\n\n"
                "## 执行步骤\n\n"
                "### 第一步：尝试补充基金指标数据\n"
                "检查 E:\\MyVault\\基金投研\\data\\fund_metrics.csv 是否存在且包含近期数据。"
                "如果缺失或过期，尝试用 web_fetch 从天天基金/晨星等公开页面获取各持仓基金的"
                "近1年收益、最大回撤等指标，补充到 csv 中。如果获取失败，标注数据不足并继续。\n\n"
                "### 第二步：运行月报脚本\n"
                "执行 python F:\\AI\\skills\\fund-investment-skill"
                "\\scripts\\run_fund_skill.py --mode monthly\n\n"
                "### 第三步：发送摘要\n"
                "读取 E:\\MyVault\\基金投研\\reports\\monthly\\ 下最新生成的月报，"
                "提取关键信息（基金评分、观察名单、换基建议），以简洁格式发送给我。"
            ),
            "timeoutSeconds": 300,
            "toolsAllow": ["exec", "read", "write", "sessions_send", "web_fetch"],
        },
        "sessionTarget": "isolated",
        "delivery": {"mode": "announce", "channel": "feishu", "to": "user:ou_21ee891c7fdf54b0e45d8a3e31a0ed8f"},
    },
    {
        "name": "fund-quarterly",
        "description": "基金投研季度复盘 - 每季度末最后一天 20:00",
        "schedule": {"kind": "cron", "expr": "0 20 L 3,6,9,12 *", "tz": "Asia/Shanghai"},
        "payload": {
            "kind": "agentTurn",
            "message": (
                "你是基金投研助手。生成本季度基金策略复盘季报。\n\n"
                "## 执行步骤\n\n"
                "### 第一步：读取配置快照\n"
                "读取 E:\\MyVault\\基金投研\\📊 组合配置总览.md 和 "
                "E:\\MyVault\\基金投研\\📋 操作日志.md 获取当前持仓和操作历史。\n\n"
                "### 第二步：运行季报脚本\n"
                "执行 python F:\\AI\\skills\\fund-investment-skill"
                "\\scripts\\run_fund_skill.py --mode quarterly\n\n"
                "### 第三步：发送摘要\n"
                "读取 E:\\MyVault\\基金投研\\reports\\quarterly\\ 下最新生成的季报，"
                "提取关键信息（资产配置是否仍合适、行业主题是否保留、操作纪律复盘），以简洁格式发送给我。"
            ),
            "timeoutSeconds": 180,
            "toolsAllow": ["exec", "read", "write", "sessions_send"],
        },
        "sessionTarget": "isolated",
        "delivery": {"mode": "announce", "channel": "feishu", "to": "user:ou_21ee891c7fdf54b0e45d8a3e31a0ed8f"},
    },
]


def sync_cron_jobs() -> bool:
    """Check if cron jobs exist by writing a status marker.

    The OpenClaw gateway cron API is not accessible via HTTP from localhost;
    cron management is handled by the AI agent (via SKILL.md instructions).

    This function writes a marker file that the AI reads on next invocation.
    Returns True (always succeeds at writing the signal).
    """
    import json

    marker_path = config_dir() / ".cron_status.json"
    marker = {
        "checked_at": datetime.now().isoformat(),
        "expected_jobs": [j["name"] for j in CRON_JOBS],
    }
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8")
    return True
# ────────────────────────────────────────────────────────
