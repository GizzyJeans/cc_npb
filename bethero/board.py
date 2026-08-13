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

    def audit(self) -> list[str]:
        """列出所有無法安心使用的欄位。"""
        problems = list(self.unresolved)
        for label, line in (
            ("全場讓分", self.handicap),
            ("全場大小", self.total),
            ("上半讓分", self.f5_handicap),
            ("上半大小", self.f5_total),
        ):
            if not line.raw.strip():
                continue
            if line.confidence is not Confidence.CONFIRMED:
                problems.append(f"{label} 「{line.raw}」: {line.note}")
        if not self.handicap_side:
            problems.append("讓分方向未確認 (看板上數字掛在哪一隊)")
        return problems

    def is_playable(self) -> bool:
        return not self.audit()


__all__ = ["SideOdds", "BoardGame"]
