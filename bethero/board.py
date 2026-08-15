"""看板辨識結果的資料結構。

**這個模組刻意不做 OCR。** 影像辨識的結果由人 (或上游 OCR) 填進來，
每個欄位都帶信心度; 讀不準的欄位要標成 `UNCONFIRMED`，
`gates` 會據此擋掉推薦。寧可少下一注，也不要對盤型猜錯。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .lines import Confidence, Line, parse_board_line


@dataclass
class SideOdds:
    """一個投注選項的報價 (香港盤)。"""

    hk: Optional[float]
    confidence: Confidence = Confidence.CONFIRMED

    @property
    def usable(self) -> bool:
        return self.hk is not None and self.confidence is Confidence.CONFIRMED


@dataclass
class BoardGame:
    """看板上的一場比賽。"""

    date: str
    start_time: str
    away_team: str
    home_team: str
    away_starter: str = ""
    home_starter: str = ""
    venue: str = ""

    handicap_raw: str = ""
    handicap_side: str = ""
    """讓分方: ``"home"`` 或 ``"away"``。"""
    handicap_home_hk: Optional[float] = None
    handicap_away_hk: Optional[float] = None

    total_raw: str = ""
    over_hk: Optional[float] = None
    under_hk: Optional[float] = None

    f5_handicap_raw: str = ""
    f5_total_raw: str = ""

    moneyline_home_hk: Optional[float] = None
    moneyline_away_hk: Optional[float] = None

    unresolved: list[str] = field(default_factory=list)
    """辨識不確定、需要人工確認的欄位說明。"""

    attested_fields: frozenset[str] = frozenset()
    """使用者目視確認過的欄位名 (如 ``"total"``)，非慣用寫法也採用字面值。"""

    @property
    def handicap(self) -> Line:
        return parse_board_line(self.handicap_raw)

    @property
    def total(self) -> Line:
        return parse_board_line(self.total_raw, "total" in self.attested_fields)

    @property
    def f5_total(self) -> Line:
        return parse_board_line(self.f5_total_raw)

    @property
    def f5_handicap(self) -> Line:
        return parse_board_line(self.f5_handicap_raw)

    @property
    def matchup(self) -> str:
        return f"{self.away_team} @ {self.home_team}"

    MARKETS = {
        "handicap": "全場讓分",
        "total": "全場大小",
        "f5_handicap": "上半讓分",
        "f5_total": "上半大小",
    }

    def audit(self) -> list[str]:
        """列出所有無法安心使用的欄位 (整場，供報告揭露用)。"""
        problems = list(self.unresolved)
        for market, label in self.MARKETS.items():
            problems += self._line_problems(market, label)
        if not self.handicap_side:
            problems.append("讓分方向未確認 (看板上數字掛在哪一隊)")
        return problems

    def audit_for(self, market: str) -> list[str]:
        """只列出 **要下的那個市場** 無法安心使用的理由。

        `audit()` 是整場的揭露清單; 但門檻要問的是「我要下的這個盤能不能
        安心結算」。上半大小寫得不清楚，不該擋掉全場大小 —— 那是兩個
        獨立的盤口。`unresolved` 是人工註記的整場疑慮，一律計入。
        """
        if market not in self.MARKETS:
            raise ValueError(f"未知的市場 {market!r}")
        problems = list(self.unresolved)
        problems += self._line_problems(market, self.MARKETS[market])
        if market in ("handicap", "f5_handicap") and not self.handicap_side:
            problems.append("讓分方向未確認 (看板上數字掛在哪一隊)")
        return problems

    def _line_problems(self, market: str, label: str) -> list[str]:
        line = getattr(self, market)
        if not line.raw.strip():
            return []
        if line.confidence is Confidence.CONFIRMED:
            return []
        return [f"{label} 「{line.raw}」: {line.note}"]

    def is_playable(self) -> bool:
        return not self.audit()


__all__ = ["SideOdds", "BoardGame"]
