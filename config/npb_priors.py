"""NPB 模型先驗參數與 **校準狀態**。

2026-08-13 更新: npb.jp 這次可以連線，聯盟層級與球場層級的參數
已用 2026 當季 618 場實際比分校準完成，數值放在
`config.calibration_2026`，本檔只保留「校準狀態」與**已知偏誤**。

先前那一版的警語 (資料來源全被出口政策擋下) 已經不成立 ——
被擋的只剩天氣來源 (api.open-meteo.com / weather.yahoo.co.jp)。

⚠️ 仍未校準的是 **投手個人層級** 與 **和局／分差分布**，
後者是結構性偏誤，見 `KNOWN_BIASES` 第一項。
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
    value=3.6019,
    source="npb.jp 2026 逐場比分 618 場 (2026-03-27~08-12) 實測",
    as_of="2026-08-13",
    calibrated=True,
    note="舊先驗 3.85 高估了 6.9%。央聯 3.5217 / 洋聯 3.8288，"
    "已分別記在 config.calibration_2026。",
)

DISPERSION_K = Prior(
    value=6.0,
    source="以 618 場總分標準差 4.047 掃參數選出",
    as_of="2026-08-13",
    calibrated=True,
    note="k=6 時模型總分標準差 3.94，最接近實測 4.05。",
)

HOME_EDGE = Prior(
    value=1.0264,
    source="618 場主客得分比 3.696/3.508 = 1.0535 開根號",
    as_of="2026-08-13",
    calibrated=True,
    note="實測主場勝率 (排除和局) .5453。",
)

EXTRAS_RESOLVE_RATE = Prior(
    value=0.80,
    source="與 dispersion_k 一起掃出的最適值",
    as_of="2026-08-13",
    calibrated=True,
    note="⚠️ 這個值是在遷就一個結構性偏誤: 模型九局和局率過高，"
    "只能靠調高延長分出勝負比例把和局率壓回實測的 1.78%。"
    "副作用是把多餘的機率倒進 ±1 分差，見 KNOWN_BIASES。",
)


# ---------------------------------------------------------------------------
# 球場得分因子
# ---------------------------------------------------------------------------

_PF_SOURCE = (
    "npb.jp 2026 逐場比分 618 場，迭代比例配適同時解出球隊強弱與球場係數，"
    "再依場次數做經驗貝氏收縮 (w≈0.65-0.71)"
)

PARK_FACTORS: dict[str, Prior] = {
    "バンテリンドーム ナゴヤ": Prior(
        0.9619, source=_PF_SOURCE, as_of="2026-08-13", calibrated=True,
        note="舊先驗 0.85 過低。原始場均得分 6.64 之所以低，"
        "有一半是中日打線弱 (off 0.96) 而非球場。",
    ),
    "東京ドーム": Prior(
        1.0217, source=_PF_SOURCE, as_of="2026-08-13", calibrated=True,
        note="舊先驗 0.92 偏低; 2026 實際略偏打者。",
    ),
    "明治神宮野球場": Prior(
        1.1825, source=_PF_SOURCE, as_of="2026-08-13", calibrated=True,
        note="全聯盟最偏打者的球場，且比舊先驗 1.08 更極端。"
        "原始場均 8.13 反而低估 —— 因為主場的養樂多打線是全聯盟最弱 (0.79)。",
    ),
    "みずほPayPayドーム": Prior(
        1.0109, source=_PF_SOURCE, as_of="2026-08-13", calibrated=True,
        note="原始場均得分 8.39 是全聯盟最高，但那是軟銀打線 (1.36) 造成的，"
        "球場本身接近中性。這是「原始場均 ≠ 球場係數」最明顯的例子。",
    ),
    "エスコンフィールド北海道": Prior(
        1.0811, source=_PF_SOURCE, as_of="2026-08-13", calibrated=True,
    ),
    "楽天モバイルパーク宮城": Prior(
        1.0698, source=_PF_SOURCE, as_of="2026-08-13", calibrated=True,
    ),
}


def park_factor(venue: str) -> Optional[Prior]:
    return PARK_FACTORS.get(venue)


# ---------------------------------------------------------------------------
# 已知偏誤 — 模型輸出時必須一起揭露
# ---------------------------------------------------------------------------

KNOWN_BIASES = [
    (
        "分差分布在 ±1 分嚴重堆積 —— 讓分盤不可用",
        "2026-08-13 用 618 場做全季回測，模型 vs 實際:\n"
        "  P(分差 = +1): 模型 23.76% vs 實際 17.80%  (+5.96pp)\n"
        "  P(分差 = -1): 模型 18.64% vs 實際 11.33%  (+7.31pp)\n"
        "  P(分差 =  0): 模型  3.13% vs 實際  1.78%  (+1.35pp)\n"
        "多出來的機率是從 |分差| >= 4 的尾端borrow來的。"
        "掃描 k ∈ [6, 60] × extras_resolve ∈ [0.62, 0.95] 共 24 組，"
        "一分差比例的範圍只有 38.8%-44.4%，**沒有任何一組能接近實測的 29.1%**。"
        "這是 Poisson 混合模型的結構性問題，不是調參可以解決的。",
        "後果: **全場讓分盤一律不可下注**。看板的 N±XX 正好結算在整數 N 上，"
        "而 N=0 與 N=1 就是偏誤最大的兩點; 6-7pp 的定價誤差遠大於"
        "gates 要求的 3pp 優勢門檻，算出來的 EV 全是雜訊。",
    ),
    (
        "大小分方向已驗證可用",
        "同一份 618 場回測，總分的累積分布誤差在每個關鍵整數都 < 1pp:\n"
        "  P(總分 > 6): 模型 51.99% vs 實際 52.27%\n"
        "  P(總分 > 7): 模型 40.36% vs 實際 40.45%\n"
        "  P(總分 > 8): 模型 32.84% vs 實際 32.69%\n"
        "卡方 (期望值 > 5 的格) = 9.9。依模型預測總分分十組，"
        "最低組預測 5.99/實際 6.02，最高組預測 8.61/實際 8.70，"
        "回歸斜率 1.21 (>1 代表模型的分散度若有偏差是偏保守)。",
        "後果: 大小分可以定價。但上述回測是 **樣本內** "
        "(球隊係數就是用同一批比賽配適的)，所以那是技巧的上界而非下界。",
    ),
    (
        "個別投手樣本過小且對球場調整粗糙",
        "先發係數用 R*9/IP 向聯盟平均收縮 60 局，但 (a) 22-38 局的樣本"
        "(下村 22 局、西舘 31 局) 收縮後仍殘留大量雜訊; "
        "(b) 球場調整用的是該投手所屬球隊的平均球場曝險，不是他本人的"
        "登板球場; (c) 完全沒有用到左右打對位與休息天數。",
        "後果: 單場的預期總分對這些選擇很敏感。實例: 球場係數的收縮方式"
        "從全域改成逐球場後 (兩者都合理)，6 場裡有 2 場的 EV 跨過了 4% 門檻、"
        "另 2 場跨回來。這種不穩定本身就說明這些邊際優勢在模型雜訊之內。",
    ),
]


CALIBRATION_TARGETS = {
    # 實測值 (618 場, 2026-03-27~08-12)，取代先前的概略區間
    "全季和局率": "1.78%",
    "一分差比例": "29.13%",
    "主場勝率 (排除和局)": "54.53%",
    "平均總分": "7.204",
    "總分標準差": "4.047",
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
