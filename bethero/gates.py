"""推薦門檻。沒有通過全部門檻的選項，一律降級為「觀察」或「不下注」。

這個模組是整條流程的煞車: 資料不足時，`DataReadiness` 會讓
`grade()` 不可能回傳 `RECOMMEND`。模型算得再漂亮也一樣。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

MIN_EV = 0.04
"""模型 EV 至少 +4%。"""

OPEN_AIR_MIN_EV = MIN_EV
"""露天球場的 EV 門檻。**2026-09-02 由 0.07 降回 0.04（= 一般門檻）。**

沿革與撤除理由
--------------
2026-08-16 使用者決定: 露天球場不再因為缺當日天氣而直接封鎖，改成要求
更高的 EV (+7%)。當時的論證是「球場係數已內含該球場的常態風況，缺的只是
今日偏離常態多少 —— 那是增加變異而非造成偏誤」，用較高門檻補償。

那個論證是先驗的，沒有資料。從 8/25 起 scorecard 逐日追蹤它的依據
(露天與巨蛋的模型誤差是否真的有差)，結果一路走向零並翻負:

    08-25  露天 +0.32 (n=25) vs 巨蛋 -0.03 (n=28)   差 +0.34   0.4 個標準誤
    08-26  露天 +0.35 (n=28) vs 巨蛋 +0.13 (n=31)   差 +0.22   0.2 個標準誤
    08-27  露天 +0.38 (n=31) vs 巨蛋 +0.38 (n=33)   差 +0.00   0.0 個標準誤
    09-01  露天 -0.08 (n=43) vs 巨蛋 +0.25 (n=45)   差 -0.33   0.4 個標準誤

88 場之後，露天的模型誤差不但沒有比較大，還略小。繼續加收 3 個百分點
等於對一個查無實據的風險收費。

**這不是因為它讓我們少賺才撤。** 回溯檢驗 (analysis/backtest_open_air_threshold.py)
顯示這個改動在歷史上只會多開 2 個部位、兩注都輸、淨 -2,000。撤除的理由
是門檻的 *前提* 不成立，不是它的 *損益*。用 2 注的輸贏決定一條規則，
和當初用零證據設立它，是同一個錯誤。

⚠️ 一個回溯檢驗才看得到的事實
-----------------------------
同一份檢驗顯示: 有 5 場符合新門檻，但其中 3 場 **即使降門檻也不會下注** ——
當天已有三個 EV 更高的部位把 3,000 單日額度用完了。
**真正的約束是單日額度，不是這道門檻。** 門檻只在「當天合格部位少於三個」
的日子才會實際咬到，所以這個改動的影響遠比它看起來小。

天氣缺口仍照實記錄: 露天場的 `weather_known` 依然是 False，
依使用者 8/16 的決定放棄該門檻，並印在報告的「已放棄的門檻」欄。
放棄的是門檻，不是揭露。"""

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

    starter_stats_known: bool = False
    """兩隊先發投手都查得到本季成績。

    AGENT.md 的資料清單第 5 項要求「先發投手近期表現」，但先前沒有對應
    欄位。新人首度先發 (例如 2026-08-18 羅德的吉川悠斗，支配下登錄但
    本季 0 場登板) 時，模型最大的單一變因等於沒有輸入 —— 用聯盟平均
    當先驗不是造假，但不確定度遠大於有 100 局樣本的投手，必須記為缺口。
    """

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
    印進報告，不會靜靜消失。

    軟性門檻原則上 **不該** 放棄: 少了球隊得分率或球場係數，模型根本
    算不出東西，放棄等於自欺。唯一的例外是 `weather_known` ——
    球場係數本身是整季配適出來的，已經內含該球場的 **常態** 風況，
    缺的只是「今天偏離常態多少」。那是增加變異、不是造成偏誤，
    所以可以用「提高 EV 門檻」來補償，而不是一刀切掉整個露天市場。
    放棄它時務必同時調高 `min_ev`，見 `WAIVABLE_SOFT`。
    """

    WAIVABLE_SOFT = frozenset({"weather_known"})
    """唯一允許放棄的軟性門檻。其餘軟性門檻放棄了模型就沒有輸入可用。"""

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
        ("starter_stats_known", "先發投手本季成績查不到（新人或首度登板）"),
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
        """使用者放棄的門檻 —— 報告必須揭露 (硬性與軟性都算)。"""
        return [
            f"{msg}（使用者明示放棄）"
            for attr, msg in self.HARD_REQUIREMENTS + self.SOFT_REQUIREMENTS
            if not getattr(self, attr) and attr in self.waived
        ]

    def soft_gaps(self) -> list[str]:
        """尚未滿足、且未被放棄的軟性條件。

        只有 `WAIVABLE_SOFT` 裡的欄位放棄得掉; 放棄其他軟性欄位會被忽略，
        以免「放棄」變成繞過資料不足的萬用後門。
        """
        return [
            msg
            for attr, msg in self.SOFT_REQUIREMENTS
            if not getattr(self, attr)
            and not (attr in self.waived and attr in self.WAIVABLE_SOFT)
        ]

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
