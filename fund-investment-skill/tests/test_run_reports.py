from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_daily_report_generation():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_fund_skill.py"), "--mode", "daily", "--date", "2099-01-01"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    report = ROOT / "reports" / "daily" / "2099-01-01.md"
    assert report.exists()
    assert "基金组合日报" in report.read_text(encoding="utf-8")
    assert "022459" in report.read_text(encoding="utf-8")
