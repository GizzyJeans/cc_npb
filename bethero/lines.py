"""亞洲盤盤口解析與結算規則 (NPB / 棒球)。

盤口記法 (2026-08-13 經使用者確認)
----------------------------------
看板的盤口寫成 ``N``、``N平``、``N+XX``、``N-XX``:

* ``N`` 是 **關鍵整數** —— 讓分盤是淨勝分，大小盤是總得分。
* 兩位數字 ``XX`` 是 **結算百分比**，不是小數位移。
* 符號決定該百分比對「主方」是贏還是輸:

  =========  ==================================================
  ``N平``    落在 N 時走盤，全額退回
  ``N-XX``   落在 N 時主方 **輸 XX% 本金**，副方贏 XX% 賠金
  ``N+XX``   落在 N 時主方 **贏 XX% 賠金**，副方輸 XX% 本金
  =========  ==================================================

「主方」讓分盤是 **讓分方**，大小盤是 **大分**。

使用者原話:

    0-50 就是平手時讓分方輸 50% 本金，受讓方贏 50% 賠金
    1-60 就是讓分方贏一分輸 60% 本金，受讓方贏 60% 賠金

所以這是一個 **連續內插** 的盤口系統: 標準亞洲盤只能跳 0.25，
這裡可以用 XX 在兩個相鄰半球盤之間任意取值。等效盤口為::

    effective = N - s / 2          (s 為帶號的結算比例)

驗證: ``0-50`` -> 0 - (-0.5)/2 = 0.25 (標準的 0/0.5 盤)；
``1+50`` -> 1 - 0.5/2 = 0.75 (標準的 0.5/1 盤)；
``1-60`` -> 1.30 (標準階梯做不出來的盤口)。

另外「一輸二贏」= 讓/受讓 1.5 分 (贏 1 分輸、贏 2 分贏)，
在本模組即 ``base=1, s=-1``，等效 1.5，見 `ICHI_YU_NI_EI`。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from typing import Mapping


class Confidence(str, Enum):
    """盤口解析的信心度。"""

    CONFIRMED = "confirmed"
    UNCONFIRMED = "unconfirmed"
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class Line:
    """一個盤口。

    Attributes
    ----------
    base:
        關鍵整數 (淨勝分或總得分)。
    edge:
        落在 `base` 時，**主方** 每 1 單位本金的結算比例。
        負值 = 主方輸該比例的本金; 正值 = 主方贏該比例的賠金; 0 = 走盤。
    """

    base: int
    edge: Fraction
    raw: str
    confidence: Confidence
    note: str = ""

    @property
    def effective(self) -> Fraction:
        """等效的標準亞洲盤盤口。"""
        return Fraction(self.base) - self.edge / 2

    @property
    def is_usable(self) -> bool:
        return self.confidence is Confidence.CONFIRMED

    def settle(self, outcome: int) -> Fraction:
        """主方每 1 單位本金的結算比例。

        `outcome` 讓分盤填讓分方淨勝分，大小盤填總得分。
        """
        if outcome > self.base:
            return Fraction(1)
        if outcome < self.base:
            return Fraction(-1)
        return self.edge

    def __str__(self) -> str:
        return f"{float(self.effective):g}"


ICHI_YU_NI_EI = Line(
    base=1,
    edge=Fraction(-1),
    raw="一輸二贏",
    confidence=Confidence.CONFIRMED,
    note="讓/受讓 1.5 分: 讓分方贏 1 分算輸、贏 2 分算贏。",
)
"""「一輸二贏」= 1.5 分讓分盤。"""


_BOARD_RE = re.compile(
    r"""^\s*
    (?P<base>\d+)
    (?:
        (?P<flat>平)
      | (?P<sign>[+\-])(?P<pct>\d{1,3})
      | \.(?P<dec>\d{1,2})
    )?
    \s*$""",
    re.VERBOSE,
)


def parse_board_line(raw: str) -> Line:
    """解析看板盤口字串。

    ``N平`` / ``N`` -> 走盤盤；``N-XX`` / ``N+XX`` -> 帶結算比例的盤。
    純小數 (如 ``6.5``) 不是這張看板的慣用寫法，會標為待確認 ——
    它可能是 ``6-50`` 或 ``6+50`` 的呈現，兩者等效盤口差 0.5 分。
    """
    if raw is None:
        return Line(0, Fraction(0), "", Confidence.UNREADABLE, "空值")

    text = raw.strip()
    if not text:
        return Line(0, Fraction(0), raw, Confidence.UNREADABLE, "空值")

    match = _BOARD_RE.match(text)
    if not match:
        return Line(0, Fraction(0), raw, Confidence.UNREADABLE, "無法解析的盤口格式")

    base = int(match.group("base"))

    if match.group("dec") is not None:
        digits = match.group("dec")
        return Line(
            base,
            Fraction(0),
            raw,
            Confidence.UNCONFIRMED,
            f"純小數寫法與看板慣用的 N平/N±XX 不一致 —— 可能是 "
            f"{base}-{digits}0 或 {base}+{digits}0，等效盤口相差 "
            f"{float(Fraction(int(digits), 10 ** len(digits))):g} 分，需確認",
        )

    if match.group("flat") or match.group("sign") is None:
        return Line(base, Fraction(0), raw, Confidence.CONFIRMED)

    pct = int(match.group("pct"))
    if pct > 100:
        return Line(
            base, Fraction(0), raw, Confidence.UNREADABLE, f"結算比例 {pct}% 超過 100%"
        )
    edge = Fraction(pct, 100)
    if match.group("sign") == "-":
        edge = -edge
    return Line(base, edge, raw, Confidence.CONFIRMED)


def settle_handicap(line: Line, favourite_margin: int) -> Fraction:
    """讓分盤結算，站在 **讓分方**。`favourite_margin` = 讓分方淨勝分。"""
    return line.settle(favourite_margin)


def settle_total(line: Line, total_runs: int, side: str) -> Fraction:
    """大小分結算。`side` 為 ``"over"`` (大，主方) 或 ``"under"`` (小)。"""
    if side not in ("over", "under"):
        raise ValueError(f"side 必須是 'over' 或 'under'，收到 {side!r}")
    result = line.settle(total_runs)
    return result if side == "over" else -result


# ---------------------------------------------------------------------------
# 由機率分布計算結算結果的分布
# ---------------------------------------------------------------------------


def handicap_outcome_probs(
    line: Line, margin_pmf: Mapping[int, float]
) -> dict[Fraction, float]:
    """給定讓分方淨勝分分布，回傳 {結算比例: 機率}。"""
    out: dict[Fraction, float] = {}
    for margin, prob in margin_pmf.items():
        result = settle_handicap(line, margin)
        out[result] = out.get(result, 0.0) + prob
    return out


def total_outcome_probs(
    line: Line, total_pmf: Mapping[int, float], side: str
) -> dict[Fraction, float]:
    """給定總得分分布，回傳 {結算比例: 機率}。"""
    out: dict[Fraction, float] = {}
    for total, prob in total_pmf.items():
        result = settle_total(line, total, side)
        out[result] = out.get(result, 0.0) + prob
    return out


def cover_rate(outcome_probs: Mapping[Fraction, float]) -> float:
    """有效過盤率: 部分贏按比例計，走盤排除在分母外。"""
    win = sum(p * float(r) for r, p in outcome_probs.items() if r > 0)
    push = sum(p for r, p in outcome_probs.items() if r == 0)
    denom = 1.0 - push
    return win / denom if denom > 1e-12 else 0.0


def push_rate(outcome_probs: Mapping[Fraction, float]) -> float:
    """全額退回的機率 (只有 ``N平`` 型盤口才有)。"""
    return sum(p for r, p in outcome_probs.items() if r == 0)


def describe_settlement(line: Line, market: str) -> str:
    """用中文說明這個盤口怎麼結算。"""
    primary = "讓分方" if market == "handicap" else "大分"
    counter = "受讓方" if market == "handicap" else "小分"
    where = f"淨勝 {line.base} 分" if market == "handicap" else f"總分 {line.base}"
    eff = float(line.effective)

    if line.edge == 0:
        return f"{where}時走盤，雙方本金全額退回。等效讓分 {eff:g}。"
    pct = abs(float(line.edge)) * 100
    if line.edge < 0:
        return (
            f"{where}時 {primary} 輸 {pct:g}% 本金、{counter} 贏 {pct:g}% 賠金。"
            f"等效讓分 {eff:g}。"
        )
    return (
        f"{where}時 {primary} 贏 {pct:g}% 賠金、{counter} 輸 {pct:g}% 本金。"
        f"等效讓分 {eff:g}。"
    )


__all__ = [
    "Confidence",
    "Line",
    "ICHI_YU_NI_EI",
    "parse_board_line",
    "settle_handicap",
    "settle_total",
    "handicap_outcome_probs",
    "total_outcome_probs",
    "cover_rate",
    "push_rate",
    "describe_settlement",
]
