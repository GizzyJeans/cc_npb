"""NPB 模型先驗參數與 **校準狀態**。

⚠️ 重要: 本檔目前的數值是 *先驗*，不是校準值。
2026-08-13 這次執行時，npb.jp / baseball-data.com / baseballdata.jp /
baseball.yahoo.co.jp 等資料來源全部被網路出口政策擋下，
因此無法取得當季實際數字。凡 `calibrated=False` 的參數，
下游 `gates` 會把 `team_rates_known` / `park_factor_known` 視為 False。

不要把這些數字當成事實引用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Prior:
    value: float
    source: str
    as_of: str = ""
    calibrated: bool = False
    note: str = ""


# ---------------------------------------------------------------------------
# 聯盟得分環境
# ---------------------------------------------------------------------------

LEAGUE_RPG = Prior(
    value=3.85,
    source="近年 NPB 單隊每場得分的長期概略值",
    calibrated=False,
    note="必須以 2026 當季 npb.jp 官方 tmb_c / tmb_p 的得分 ÷ 場次覆蓋。"
    "央聯與洋聯需分開 (洋聯採 DH，得分通常略高)。",
)

DISPERSION_K = Prior(
    value=9.0,
    source="以總分標準差 ~3.7 反推",
    calibrated=False,
    note="共享環境 Gamma 因子的形狀參數。",
)

HOME_EDGE = Prior(
    value=1.030,
    source="NPB 主場勝率約 .530 (排除和局) 反推",
    calibrated=False,
)

EXTRAS_RESOLVE_RATE = Prior(
    value=0.62,
    source="延長 10-12 局分出勝負的概略比例",
    calibrated=False,
)


# ---------------------------------------------------------------------------
# 球場得分因子
# ---------------------------------------------------------------------------

PARK_FACTORS: dict[str, Prior] = {
    "バンテリンドーム ナゴヤ": Prior(
        0.85,
        source="baseball-stats.jp / note.com 2025 年 PF 整理 (得分 PF 0.85)",
        as_of="2025",
        calibrated=False,
        note="NPB 最壓抑得分的球場，長年約 0.85。2026 當季值未取得。",
    ),
    "東京ドーム": Prior(
        0.92,
        source="baseball-stats.jp 2025 年 PF 整理 (得分 PF 0.92、全壘打 PF 1.11)",
        as_of="2025",
        calibrated=False,
        note="全壘打多但整體得分不高 — 大小分不可只看 HR PF。",
    ),
    "明治神宮野球場": Prior(
        1.08,
        source="長期印象值，**未經 2026 資料驗證**",
        calibrated=False,
        note="公認打者球場，但 1.08 這個數字沒有來源支撐，不可用於下注。",
    ),
    "みずほPayPayドーム": Prior(
        0.97, source="長期印象值，未驗證", calibrated=False
    ),
    "エスコンフィールド北海道": Prior(
        1.00, source="長期印象值，未驗證", calibrated=False
    ),
    "楽天モバイルパーク宮城": Prior(
        1.00, source="長期印象值，未驗證", calibrated=False
    ),
}


def park_factor(venue: str) -> Optional[Prior]:
    return PARK_FACTORS.get(venue)


# ---------------------------------------------------------------------------
# 已知偏誤 — 模型輸出時必須一起揭露
# ---------------------------------------------------------------------------

KNOWN_BIASES = [
    (
        "九局和局率偏高",
        "模型算出九局打平約 15-17%，NPB 實際約 9-10%。Poisson 系列的得分"
        "模型加上共享環境因子後，兩隊同分的機率被系統性高估，且此偏誤"
        "對 dispersion_k 不敏感 (k 由 3 掃到 15 只從 17.1% 降到 15.0%)。",
        "後果: **整數讓分盤的走盤率被高估**，因此整數盤的過盤率被低估；"
        "一分差比例同樣偏高 (模型 40% vs 實際約 33-35%)。"
        "整數讓分盤與整數大小盤的模型定價在校準前不可下注。",
    ),
    (
        "球場因子多數未驗證",
        "六個球場中只有バンテリン與東京ドーム有可追溯的 2025 年來源，"
        "其餘四座是印象值。",
        "後果: 大小分定價在那四座球場沒有意義。",
    ),
    (
        "缺少投手個人層級輸入",
        "TeamInput.def_factor 目前需要人工填入，沒有從先發投手的 "
        "FIP / 對左右打分割 / 休息天數自動推導。",
        "後果: 先發投手對位這個最大的單一變因目前無法量化。",
    ),
]


CALIBRATION_TARGETS = {
    "九局後和局率": "9-10%",
    "全季和局率": "3-5%",
    "一分差比例": "33-35%",
    "主場勝率 (排除和局)": "52.5-53.5%",
    "總分標準差": "3.6-4.0",
}


def uncalibrated() -> list[str]:
    """列出所有尚未校準的參數 — 供 gates 與報告使用。"""
    out = [
        name
        for name, prior in (
            ("league_rpg", LEAGUE_RPG),
            ("dispersion_k", DISPERSION_K),
            ("home_edge", HOME_EDGE),
            ("extras_resolve_rate", EXTRAS_RESOLVE_RATE),
        )
        if not prior.calibrated
    ]
    out += [f"park:{v}" for v, p in PARK_FACTORS.items() if not p.calibrated]
    return out


__all__ = [
    "Prior",
    "LEAGUE_RPG",
    "DISPERSION_K",
    "HOME_EDGE",
    "EXTRAS_RESOLVE_RATE",
    "PARK_FACTORS",
    "park_factor",
    "KNOWN_BIASES",
    "CALIBRATION_TARGETS",
    "uncalibrated",
]
