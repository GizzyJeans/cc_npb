"""校準過期防護。

為什麼有這支測試
----------------
每日重配適本來只靠排程指令裡的一句「記得跑」。2026-09-13 容器回收把
重配適管線弄丟之後，9/13 與 9/14 兩天就沿用了 9/11 的係數，沒有任何
東西擋下來 —— 因為那只是提醒。同一週 pytest 被管線吞掉結束狀態是
一樣的病: **靠記性的保證等於沒有保證。**

所以分兩層:

1. `cal.freshness_note()` 在 **定價的當下** 算落後天數並產生警告。
2. 本檔確保 **新寫的 slate 真的有接上那個警告** —— 不然第 1 層只是
   一個沒人呼叫的函式。
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from config import calibration_2026 as cal

SLATES = Path(__file__).resolve().parent.parent / "analysis"

ENFORCED_FROM = "2026-09-15"
"""這天(含)以後新增的 slate 才強制接上新鮮度檢查。

更早的 slate 是歷史紀錄，**不回頭改** —— 改了就不再是當天實際用的東西。
"""


class TestStaleness:
    def test_covers_previous_day_is_fresh(self):
        through = date.fromisoformat(cal.sample_through())
        assert cal.staleness_days((through + timedelta(days=1)).isoformat()) == 0
        assert cal.freshness_note((through + timedelta(days=1)).isoformat()) is None

    def test_lagging_days_counted(self):
        through = date.fromisoformat(cal.sample_through())
        for lag in (1, 3, 10):
            day = (through + timedelta(days=1 + lag)).isoformat()
            assert cal.staleness_days(day) == lag
            note = cal.freshness_note(day)
            assert note is not None and f"過期 {lag} 天" in note

    def test_ahead_of_schedule_is_not_a_warning(self):
        """校準比定價日還新 (例如補跑舊日期) 不該報警。"""
        through = date.fromisoformat(cal.sample_through())
        assert cal.staleness_days(through.isoformat()) == -1
        assert cal.freshness_note(through.isoformat()) is None

    def test_sample_through_matches_range(self):
        assert cal.SAMPLE_RANGE.endswith(cal.sample_through())


class TestSlatesWireItUp:
    """新 slate 必須真的呼叫 freshness_note，否則第一層等於沒接上。"""

    @staticmethod
    def _new_slates() -> list[Path]:
        out = []
        for p in sorted(SLATES.glob("slate_2026_*.py")):
            m = re.match(r"slate_(\d{4})_(\d{2})_(\d{2})\.py", p.name)
            if m and f"{m.group(1)}-{m.group(2)}-{m.group(3)}" >= ENFORCED_FROM:
                out.append(p)
        return out

    def test_new_slates_call_freshness_note(self):
        missing = [p.name for p in self._new_slates()
                   if "freshness_note" not in p.read_text(encoding="utf-8")]
        assert not missing, (
            "這些 slate 沒有接上校準新鮮度檢查: " + ", ".join(missing)
            + "。請在 build_report() 的 global_notes 最前面加入 "
            "cal.freshness_note(DATE)（非 None 時）。"
        )

    def test_enforcement_window_is_sane(self):
        """避免有人把 ENFORCED_FROM 往後推來躲掉這個測試。"""
        assert ENFORCED_FROM <= date.today().isoformat()
