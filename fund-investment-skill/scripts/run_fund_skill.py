#!/usr/bin/env python3
"""Run the Fund Investment Skill reports.

Examples:
    python scripts/run_fund_skill.py --mode daily
    python scripts/run_fund_skill.py --mode weekly
    python scripts/run_fund_skill.py --mode monthly
    python scripts/run_fund_skill.py --mode quarterly
    python scripts/run_fund_skill.py --mode all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from project root or scripts directory.
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from fund_skill_core import (  # noqa: E402
    generate_daily_report,
    generate_monthly_report,
    generate_quarterly_report,
    generate_weekly_report,
    sync_obsidian_summary,
    sync_cron_jobs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate fund investment skill reports.")
    parser.add_argument("--mode", choices=["daily", "weekly", "monthly", "quarterly", "all"], default="daily")
    parser.add_argument("--date", help="Optional report date/month/week label. Daily uses YYYY-MM-DD; monthly uses YYYY-MM.")
    args = parser.parse_args()

    # 每次运行前同步 Obsidian 配置汇总
    synced = sync_obsidian_summary()
    if synced:
        print("Obsidian config synced.")

    # 自检 cron 任务（缺失则自动创建）
    sync_cron_jobs()

    outputs = []
    if args.mode in ("daily", "all"):
        outputs.append(generate_daily_report(args.date if args.mode == "daily" else None))
    if args.mode in ("weekly", "all"):
        outputs.append(generate_weekly_report(args.date if args.mode == "weekly" else None))
    if args.mode in ("monthly", "all"):
        outputs.append(generate_monthly_report(args.date if args.mode == "monthly" else None))
    if args.mode in ("quarterly", "all"):
        outputs.append(generate_quarterly_report(args.date if args.mode == "quarterly" else None))

    for path in outputs:
        print(f"Generated: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
