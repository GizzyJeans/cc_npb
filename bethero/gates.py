"""推薦門檻。沒有通過全部門檻的選項，一律降級為「觀察」或「不下注」。

這個模組是整條流程的煞車: 資料不足時，`DataReadiness` 會讓
`grade()` 不可能回傳 `RECOMMEND`。模型算得再漂亮也一樣。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

MIN_EV = 0.04
"""模型 EV 至少 +4%。"""

MIN_EDGE_PP = 3.0
"""模型機率與市場去水後機率至少差 3 個百分點。"""


class Grade(str, Enum):
    RECOMMEND = "推薦"
    OBSERVE = "觀察"
    NO_BET = "不下注"


@dataclass
class DataReadiness:
    """一場比賽的資料完整度。每個欄位都是「是否已取得可信資料」。"""

    line_type_confirmed: bool = False
    """盤型與結算規則已確認。"""

    starters_confirmed: bool = False
    """預告先發已確認。"""

    prices_verified: bool = False
    """本場要下的那個賠率是 **當下、可覆核** 的報價。

    這是硬性條件，不是軟性的。EV 是賠率的函數: 賠率若無法覆核，
    算出來的 EV 就沒有意義，再漂亮的模型機率也不能拿來下注。
    與 `market_prices_known` 分開 —— 後者問的是「有沒有開盤價與跨莊家
    比價可以參考」(軟性)，這一項問的是「手上這個數字本身可不可信」。
    """

    lineups_confirmed: bool = False
    """正式先發打線已公布。"""

    bullpen_usage_known: bool = False
    """牛棚近三日使用量可查。"""

    team_rates_known: bool = False
    """球隊進攻/投手率統計可查。"""

    park_factor_known: bool = False
    """該球場當季得分因子可查。"""

    weather_known: bool = False
    """天氣/風向 (室內球場視為已知)。"""

    injuries_known: bool = False
    """傷病與一軍登錄/抹消名單可查。"""

    market_prices_known: bool = False
    """開盤價、目前盤與多家莊家報價可比對。"""

    notes: list[str] = field(default_factory=list)

    waived: frozenset[str] = frozenset()
    """使用者明確放棄的門檻欄位名。

    放棄是使用者的決定，但必須留下紀錄 —— `waived_reasons()` 會把它們
    印進報告，不會靜靜消失。軟性門檻不可放棄 (放棄了模型也算不出東西)。
    """

    # 缺了會直接讓比賽無法下注的硬性條件
    HARD_REQUIREMENTS = (
        ("line_type_confirmed", "盤型與結算規則未確認"),
        ("starters_confirmed", "預告先發未確認"),
        ("lineups_confirmed", "正式先發打線尚未公布"),
        ("prices_verified", "賠率無法覆核（非當下可查證的報價）"),
    )

    # 影響模型可信度的軟性條件
    SOFT_REQUIREMENTS = (
        ("bullpen_usage_known", "牛棚近三日使用量不明"),
        ("team_rates_known", "球隊進攻/投手率統計無法取得"),
        ("park_factor_known", "球場得分因子無法取得"),
        ("weather_known", "天氣資訊不明"),
        ("injuries_known", "傷病與登錄異動不明"),
        ("market_prices_known", "無法取得開盤價/多家報價比對"),
    )

    def blocking_reasons(self) -> list[str]:
        return [
            msg
            for attr, msg in self.HARD_REQUIREMENTS
            if not getattr(self, attr) and attr not in self.waived
        ]

    def waived_reasons(self) -> list[str]:
        """使用者放棄的門檻 —— 報告必須揭露。"""
        return [
            f"{msg}（使用者明示放棄）"
            for attr, msg in self.HARD_REQUIREMENTS
            if not getattr(self, attr) and attr in self.waived
        ]

    def soft_gaps(self) -> list[str]:
        return [msg for attr, msg in self.SOFT_REQUIREMENTS if not getattr(self, attr)]

    def completeness(self) -> float:
        fields = self.HARD_REQUIREMENTS + self.SOFT_REQUIREMENTS
        got = sum(1 for attr, _ in fields if getattr(self, attr))
        return got / len(fields)

    def sufficient(self) -> bool:
        """資料完整度足夠 = 硬性條件全過，且軟性條件至少過 2/3。"""
        return not self.blocking_reasons() and len(self.soft_gaps()) <= 2


@dataclass
class GradedBet:
    grade: Grade
    reasons: list[str]

    @property
    def is_recommended(self) -> bool:
        return self.grade is Grade.RECOMMEND


def grade(
    ev: float,
    edge_pp: float,
    readiness: DataReadiness,
    min_ev: float = MIN_EV,
    min_edge_pp: float = MIN_EDGE_PP,
) -> GradedBet:
    """把一個投注選項分級。

    只有 EV、edge、以及全部資料門檻同時通過才是「推薦」。
    資料門檻沒過但數值面有優勢 -> 「觀察」。
    數值面沒有優勢 -> 「不下注」。
    """
    blocking = readiness.blocking_reasons()
    reasons: list[str] = []

    edge_ok = ev >= min_ev and edge_pp >= min_edge_pp
    if ev < min_ev:
        reasons.append(f"EV {ev * 100:+.1f}% 未達 +{min_ev * 100:.0f}% 門檻")
    if edge_pp < min_edge_pp:
        reasons.append(f"模型與市場差 {edge_pp:+.1f}pp，未達 {min_edge_pp:.0f}pp 門檻")

    if not edge_ok:
        reasons.extend(blocking)
        return GradedBet(Grade.NO_BET, reasons)

    if blocking:
        return GradedBet(Grade.OBSERVE, blocking + readiness.soft_gaps())

    if not readiness.sufficient():
        return GradedBet(
            Grade.OBSERVE,
            ["資料完整度不足"] + readiness.soft_gaps(),
        )

    return GradedBet(
        Grade.RECOMMEND,
        [f"EV {ev * 100:+.1f}%、優勢 {edge_pp:+.1f}pp，資料門檻全數通過"],
    )


__all__ = [
    "MIN_EV",
    "MIN_EDGE_PP",
    "Grade",
    "DataReadiness",
    "GradedBet",
    "grade",
]
