"""亞洲盤盤口解析與結算規則 (NPB / 棒球)。

本模組只做兩件事:
1. 把中文盤口看板上的字串 (例如 ``7+25``、``8平``、``1-25``) 解析成數字盤口。
2. 給定盤口與比賽結果 (或結果的機率分布)，算出每一單位注碼的結算損益。

設計原則: **看不懂的盤口不猜**。解析器會標記信心度，`UNCONFIRMED`
的盤口在下游會被 gates 擋掉，不可能變成推薦。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from typing import Iterable, Mapping


class Confidence(str, Enum):
    """盤口解析的信心度。"""

    CONFIRMED = "confirmed"
    """字串格式明確，且數值落在標準亞洲盤階梯上。"""

    UNCONFIRMED = "unconfirmed"
    """字串可以解析，但數值不是標準盤口 — 可能是 OCR 誤判或平台自訂刻度。"""

    UNREADABLE = "unreadable"
    """字串無法解析。"""


# 標準亞洲盤階梯: 0 / 0.25 / 0.5 / 0.75 / 1 ... 以 0.25 為級距。
_QUARTER = Fraction(1, 4)


def _is_standard(value: Fraction) -> bool:
    return value >= 0 and (value % _QUARTER) == 0


@dataclass(frozen=True)
class Line:
    """一個盤口數值。

    `value` 一律為非負數，方向由使用端 (讓分方 / 大小分) 決定。
    """

    value: Fraction
    raw: str
    confidence: Confidence
    note: str = ""

    @property
    def is_usable(self) -> bool:
        return self.confidence is Confidence.CONFIRMED

    def __str__(self) -> str:
        return f"{float(self.value):g}"

    def legs(self) -> tuple[Fraction, ...]:
        """把盤口拆成實際結算的腳。

        整數盤與半球盤只有一隻腳；.25 / .75 的走盤 (quarter) 盤口拆成兩隻
        各半注的腳，例如 0.75 -> (0.5, 1.0)。
        """
        eighth = self.value % Fraction(1, 2)
        if eighth == 0:
            return (self.value,)
        return (self.value - _QUARTER, self.value + _QUARTER)


# ``8平`` / ``7+25`` / ``7-25`` / ``6.5`` / ``0``
_BOARD_RE = re.compile(
    r"""^\s*
    (?P<base>\d+)
    (?:
        (?P<flat>平)
      | (?P<sign>[+\-])(?P<frac>\d{1,2})
      | \.(?P<dec>\d{1,2})
    )?
    \s*$""",
    re.VERBOSE,
)


def parse_board_line(raw: str) -> Line:
    """解析中文看板的盤口字串。

    看板慣例 (由 ``平`` 這個記號錨定):

    * ``8平``  -> 8.0        (``平`` = 整數盤，沒有小數部分)
    * ``7+25`` -> 7.25       (整數 + 小數位移)
    * ``7-25`` -> 6.75       (整數 - 小數位移)
    * ``6.5``  -> 6.5        (直接小數)

    ``平`` 明確代表「沒有小數」，因此 ``+``/``-`` 只能是相對整數的位移，
    這個推論對大小分欄位完全自洽。但同一張看板的讓分欄位常出現
    ``1-60`` / ``1+80`` 這類位移後不落在 0.25 級距的數值 — 那些會被標成
    ``UNCONFIRMED``，交由人工確認，不會自行猜測。
    """
    if raw is None:
        return Line(Fraction(0), "", Confidence.UNREADABLE, "空值")

    text = raw.strip()
    if not text:
        return Line(Fraction(0), raw, Confidence.UNREADABLE, "空值")

    match = _BOARD_RE.match(text)
    if not match:
        return Line(Fraction(0), raw, Confidence.UNREADABLE, "無法解析的盤口格式")

    base = Fraction(int(match.group("base")))

    if match.group("flat") or (
        match.group("sign") is None and match.group("dec") is None
    ):
        value = base
    elif match.group("dec") is not None:
        digits = match.group("dec")
        value = base + Fraction(int(digits), 10 ** len(digits))
    else:
        digits = match.group("frac")
        offset = Fraction(int(digits), 10 ** len(digits))
        value = base + offset if match.group("sign") == "+" else base - offset

    if value < 0:
        return Line(
            value,
            raw,
            Confidence.UNCONFIRMED,
            "位移後為負值 — 讓分欄的 +/- 可能是「方向標記」而非「小數位移」，"
            "兩種讀法都說得通，需人工確認平台定義",
        )
    if not _is_standard(value):
        return Line(
            value,
            raw,
            Confidence.UNCONFIRMED,
            f"位移後為 {float(value):g}，不在 0.25 級距的標準亞洲盤階梯上",
        )
    return Line(value, raw, Confidence.CONFIRMED)


def settle_handicap(line: Line, favourite_margin: int) -> Fraction:
    """讓分盤結算，回傳每 1 單位注碼的損益 (站在讓分方)。

    `favourite_margin` = 讓分方得分 - 受讓方得分 (可為負)。
    回傳值域 {-1, -0.5, 0, +0.5, +1} 乘上賠率前的比例。
    +1 代表全贏 (再乘上賠率)、-1 代表全輸本金、0 代表走盤退回。
    """
    return _settle(line.legs(), lambda leg: _cmp(Fraction(favourite_margin) - leg))


def settle_total(line: Line, total_runs: int, side: str) -> Fraction:
    """大小分結算，回傳每 1 單位注碼的損益比例。

    `side` 為 ``"over"`` (大) 或 ``"under"`` (小)。
    """
    if side not in ("over", "under"):
        raise ValueError(f"side 必須是 'over' 或 'under'，收到 {side!r}")
    sign = 1 if side == "over" else -1
    return _settle(
        line.legs(), lambda leg: _cmp(sign * (Fraction(total_runs) - leg))
    )


def _cmp(diff: Fraction) -> Fraction:
    """單腳結算: 贏 +1 / 走盤 0 / 輸 -1。"""
    if diff > 0:
        return Fraction(1)
    if diff < 0:
        return Fraction(-1)
    return Fraction(0)


def _settle(legs: tuple[Fraction, ...], resolve) -> Fraction:
    return sum(resolve(leg) for leg in legs) / len(legs)


# ---------------------------------------------------------------------------
# 由機率分布計算結算結果的分布
# ---------------------------------------------------------------------------


def handicap_outcome_probs(
    line: Line, margin_pmf: Mapping[int, float]
) -> dict[Fraction, float]:
    """給定讓分方淨勝分的機率分布，回傳各結算比例的機率。"""
    out: dict[Fraction, float] = {}
    for margin, prob in margin_pmf.items():
        result = settle_handicap(line, margin)
        out[result] = out.get(result, 0.0) + prob
    return out


def total_outcome_probs(
    line: Line, total_pmf: Mapping[int, float], side: str
) -> dict[Fraction, float]:
    """給定總得分的機率分布，回傳各結算比例的機率。"""
    out: dict[Fraction, float] = {}
    for total, prob in total_pmf.items():
        result = settle_total(line, total, side)
        out[result] = out.get(result, 0.0) + prob
    return out


def cover_rate(outcome_probs: Mapping[Fraction, float]) -> float:
    """過盤率: 全贏 + 半贏 (半贏以 0.5 計)，走盤不計入分母之外的調整。

    這是回報導向的「有效過盤率」，方便和市場去水後機率直接比較。
    """
    win = 0.0
    for result, prob in outcome_probs.items():
        if result > 0:
            win += prob * float(result)
    push = sum(prob for result, prob in outcome_probs.items() if result == 0)
    denom = 1.0 - push
    return win / denom if denom > 1e-12 else 0.0


def push_rate(outcome_probs: Mapping[Fraction, float]) -> float:
    """走盤 (全額退回) 機率。"""
    return sum(p for r, p in outcome_probs.items() if r == 0)


def describe_settlement(line: Line, market: str) -> str:
    """用中文說明這個盤口怎麼結算 — 報告要能自我稽核用。"""
    value = line.value
    frac = value % 1
    if market == "handicap":
        if frac == 0 and value == 0:
            return "平手盤: 和局全額退回，勝負依實際結果。"
        if frac == 0:
            return f"整數盤 {value}: 讓分方剛好贏 {value} 分走盤退回。"
        if frac == Fraction(1, 2):
            return f"半球盤 {float(value):g}: 無走盤，一翻兩瞪眼。"
        low, high = line.legs()
        return (
            f"半一/一輸二贏型 {float(value):g}: 注碼各半掛在 {float(low):g} 與 "
            f"{float(high):g}，讓分方剛好贏 {int(high)} 分時半贏半走。"
        )
    if frac == 0:
        return f"整數大小盤 {value}: 總分剛好 {value} 走盤退回。"
    if frac == Fraction(1, 2):
        return f"半球大小盤 {float(value):g}: 無走盤。"
    low, high = line.legs()
    return (
        f"走盤型大小盤 {float(value):g}: 注碼各半掛在 {float(low):g} 與 "
        f"{float(high):g}。"
    )


__all__ = [
    "Confidence",
    "Line",
    "parse_board_line",
    "settle_handicap",
    "settle_total",
    "handicap_outcome_probs",
    "total_outcome_probs",
    "cover_rate",
    "push_rate",
    "describe_settlement",
]
