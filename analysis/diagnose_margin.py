"""讓分盤到底卡在哪裡 —— 分差分布的結構診斷。

執行: ``python3 -m analysis.diagnose_margin``（約 3-5 分鐘）

先前只知道「分差分布在結算整數上高估 5-6pp，調 k 沒用」。
那是 **觀察**，不是 **原因**。這支腳本給出原因，並量化修好它要什麼。

一、為什麼調 k 在數學上就不可能有用
------------------------------------
模型的結構是: 給定共享環境因子 G 後，兩隊得分條件獨立 Poisson。
於是

    Var(分差) = λh + λa + (λh - λa)^2 * Var(G)
    Var(總分) = λh + λa + (λh + λa)^2 * Var(G)

λh ≈ λa（同一場比賽兩隊實力接近，差距遠小於水位），所以
``(λh - λa)^2 ≈ 0`` —— **Var(分差) 幾乎與 Var(G) 無關，也就是與 k 無關**。
而 Var(總分) 的係數是 ``(λh + λa)^2``，完全由 k 控制。

實測完全符合: k 從 6 掃到 10^9，模型 Var(分差) 只在 **6.92 - 6.96** 之間動，
而實測 Var(分差) 是 **16.2**（全季 674 場）。模型的分差分布窄了約 2.3 倍。

這解釋了 2026-08-19 那次重測「k=6 5.90pp → k=14 5.98pp 毫無改善」——
不是調得不夠好，是這個旋鈕根本沒接到那個輸出上。

二、共享因子的前提本身就沒有資料支持
------------------------------------
model.py 的說明寫「兩隊得分帶正相關 —— 這正是球場、天氣、主審好球帶
造成的效果」。實測 (674 場):

    corr(主隊得分, 客隊得分) = -0.0023，95% 信賴區間 [-0.078, +0.073]

**相關性是零。** Var(分差) 16.24 與 Var(總分) 16.16 幾乎相等，
也正是零相關才會有的結果（兩者差 4*cov）。

但每隊各自的得分是 **嚴重過度離散** 的: var/mean 主 2.32、客 2.18
（Poisson 是 1.00）。也就是說變異來自「每隊各自打爆或被完封」，
而不是「當天兩隊一起高分或一起低分」。

模型目前用共享因子去補總分的變異數，數字對得上（總分只在乎變異數大小，
不在乎來源），但一到分差就露餡 —— 分差在乎的正好是相關性本身。

三、把離散度改成每隊獨立，能修多少？
------------------------------------
把「給定 G 後的 Poisson」換成「給定 G 後的負二項」，多一個每隊獨立的
離散參數 v（Var = mean + v * mean^2），其餘（九局下不打、延長局分勝負）
全部保留。時序切分驗證（4-6 月配適、7 月後 240 場驗證）:

    v=0.00 k=14   分差 6.04pp   大小 3.59pp   <- 現行模型
    v=0.45 k=inf  分差 4.09pp   大小 8.58pp   <- 訓練期 minimax 最佳

方向是對的（分差 6.04 → 4.09pp，確認診斷無誤），但兩件事同時發生:

1. **仍然過不了 3pp 的門檻。**
2. **大小分被弄壞了**（3.59 → 8.58pp）。同一個 v 同時餵給分差與總分，
   兩邊要的量不一樣，一個參數服務不了兩個市場。

而且 v=0.45/k=inf 在訓練期是 3.56/1.58pp、驗證期變成 4.09/8.58pp ——
**訓練期漂亮、驗證期崩掉**，跟當初 k=6 踩到的是同一個坑。

四、所以要什麼才能跑讓分盤
--------------------------
見模組尾端的 REQUIREMENTS。
"""

from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bethero.model as _M
from bethero.model import GameModel, NPBEnvironment, TeamInput
from config import calibration_2026 as cal
from analysis.validate_oos import SPLIT, fit, load_games

SETTLE_INTEGERS = range(-3, 4)
"""看板的 N±XX 就結算在這些整數上，所以只有這幾個點的機率有用。"""

TOTAL_LINES = range(5, 11)

_ORIG_POISSON = _M._poisson_pmf
_V = {"v": 0.0}
_PMF_CACHE: dict = {}


def _negbin(mean: float, n: int) -> list[float]:
    """E = mean、Var = mean + v*mean^2。v=0 時退回原本的 Poisson。"""
    v = _V["v"]
    if v <= 1e-12:
        return _ORIG_POISSON(mean, n)
    key = (round(mean, 5), n, v)
    hit = _PMF_CACHE.get(key)
    if hit is not None:
        return hit
    r = 1.0 / v
    p = r / (r + mean)
    out = [p ** r]
    for i in range(1, n + 1):
        out.append(out[-1] * (r + i - 1) / i * (1.0 - p))
    _PMF_CACHE[key] = out
    return out


def _install_patches() -> None:
    """把條件 Poisson 換成條件負二項，並快取 Gamma 節點。"""
    _M._poisson_pmf = _negbin
    orig_nodes = GameModel._gamma_nodes
    cache: dict = {}
    GameModel._gamma_nodes = (
        lambda self, n=24: cache.setdefault((self.env.dispersion_k, n),
                                            orig_nodes(self, n))
    )


def empirical_moments(games: list[dict]) -> dict:
    n = len(games)
    hs = [g["hs"] for g in games]
    as_ = [g["as"] for g in games]
    mh, ma = sum(hs) / n, sum(as_) / n
    vh = sum((x - mh) ** 2 for x in hs) / n
    va = sum((x - ma) ** 2 for x in as_) / n
    cov = sum((x - mh) * (y - ma) for x, y in zip(hs, as_)) / n
    r = cov / (vh * va) ** 0.5
    z = 0.5 * math.log((1 + r) / (1 - r))
    se = 1.0 / math.sqrt(n - 3)
    return {
        "n": n, "mh": mh, "ma": ma, "vh": vh, "va": va, "cov": cov, "corr": r,
        "corr_lo": math.tanh(z - 1.96 * se), "corr_hi": math.tanh(z + 1.96 * se),
        "var_margin": vh + va - 2 * cov, "var_total": vh + va + 2 * cov,
        "disp_h": vh / mh, "disp_a": va / ma,
    }


def evaluate(games, v, k, lg, home, off, dfn, pf) -> tuple[float, float, float]:
    """回傳 (分差最大偏離, 大小最大偏離, 模型 var(分差))。"""
    _V["v"] = v
    _PMF_CACHE.clear()
    env = NPBEnvironment(league_rpg=lg, dispersion_k=k, home_edge=home,
                         extras_resolve_rate=cal.EXTRAS_RESOLVE_RATE)
    margin: dict = defaultdict(float)
    total: dict = defaultdict(float)
    for g in games:
        d = GameModel(
            home=TeamInput(g["home"], off[g["home"]], dfn[g["home"]]),
            away=TeamInput(g["away"], off[g["away"]], dfn[g["away"]]),
            env=env, park_factor=pf[g["place"]],
        ).distributions()
        for m, p in d.margin_pmf.items():
            margin[m] += p
        for t, p in d.total_pmf.items():
            total[t] += p

    n = len(games)
    mass_m, mass_t = sum(margin.values()), sum(total.values())
    emp_m: dict = defaultdict(int)
    for g in games:
        emp_m[g["hs"] - g["as"]] += 1
    m_worst = max(abs(margin[m] / mass_m - emp_m[m] / n) for m in SETTLE_INTEGERS)

    totals = sorted(g["hs"] + g["as"] for g in games)
    t_worst = max(
        abs(sum(p for t, p in total.items() if t > line) / mass_t
            - sum(1 for x in totals if x > line) / n)
        for line in TOTAL_LINES
    )
    mu = sum(m * p for m, p in margin.items()) / mass_m
    var = sum(p * (m - mu) ** 2 for m, p in margin.items()) / mass_m
    return m_worst, t_worst, var


REQUIREMENTS = [
    ("分差要有自己的模型，不能跟大小分共用一組離散參數",
     "實測: 同一個 v 調到讓分差最好時，大小分從 3.59pp 惡化到 8.58pp。"
     "兩個市場對變異來源的要求相衝突 —— 大小分只在乎變異數大小，"
     "分差在乎的是相關性。必須是兩個各自校準、各自驗證的模型。"),
    ("必須是時序切分的樣本外檢定，且結算整數 -3..+3 全部 < 3pp",
     "現行 6.04pp、加獨立離散度後最佳 4.09pp，都還不夠。"
     "不接受樣本內數字 —— v=0.45/k=inf 在訓練期是 3.56pp、驗證期 4.09pp，"
     "大小分更是 1.58pp 變 8.58pp，這正是 2026-08-13 用樣本內回測時踩過的坑。"),
    ("需要「比分狀態相依」的機制，這是目前完全沒有的東西",
     "資料要的是: 比賽被打開之後會滾雪球（落後方換上收尾投手、分差繼續拉大），"
     "而接近的比賽會被壓縮（領先方派出最強後援）。這是逐局、依領先幅度變化的"
     "過程，不是任何一組靜態的兩隊得分分布能表達的。"
     "手上有 336 場逐局比分，夠 **看到** 這個效果，大概不夠 **配適** 它。"),
    ("需要多季資料",
     "本季 674 場。分差要在約 7 個整數上各自估準，驗證期每個整數只有 8-50 場，"
     "而門檻是 3pp。要穩定分辨 3pp 的差異，實務上需要好幾季。"
     "2023-2025 的逐場比分是投入產出比最高的一項輸入。"),
]


def main() -> None:
    _install_patches()
    games = load_games()
    print("# 讓分盤的結構診斷\n")

    m = empirical_moments(games)
    print(f"## 一、實測（全季 {m['n']} 場）\n")
    print(f"- corr(主隊得分, 客隊得分) = **{m['corr']:+.4f}**，"
          f"95% 信賴區間 [{m['corr_lo']:+.4f}, {m['corr_hi']:+.4f}] "
          f"—— **相關性是零**，共享環境因子的前提沒有資料支持。")
    print(f"- Var(分差) **{m['var_margin']:.2f}**、Var(總分) **{m['var_total']:.2f}**"
          f"，兩者幾乎相等（零相關才會這樣）。")
    print(f"- 每隊各自的離散度 var/mean：主 **{m['disp_h']:.2f}**、"
          f"客 **{m['disp_a']:.2f}**（Poisson 是 1.00）—— "
          f"變異來自各隊自己打爆／被完封，不是兩隊一起高低。")

    train_all = [g for g in games if g["date"] < SPLIT]
    lg, home, off, dfn, pf = fit(train_all)
    train = [g for g in train_all if g["home"] in off and g["place"] in pf]
    test = [g for g in games
            if g["date"] >= SPLIT and g["home"] in off and g["place"] in pf]

    print(f"\n## 二、調 k 為什麼沒用（驗證期 {len(test)} 場）\n")
    print("| dispersion_k | 模型 Var(分差) | 分差最大偏離 |")
    print("|---|---|---|")
    for k in (6.0, 14.0, 40.0, 1e9):
        mw, _, var = evaluate(test, 0.0, k, lg, home, off, dfn, pf)
        label = "∞" if k > 1e8 else f"{k:g}"
        print(f"| {label} | {var:.2f} | {100 * mw:.2f}pp |")
    print(f"\nk 掃過四個量級，模型 Var(分差) 幾乎不動，"
          f"實測是 {m['var_margin']:.2f}。"
          f"因為 Var(分差) = λh + λa + (λh−λa)²·Var(G)，而 λh ≈ λa，"
          f"**Var(G) 這一項被乘掉了**。旋鈕沒接到輸出上。")

    print("\n## 三、改成每隊獨立離散度能修多少\n")
    print("| v（每隊獨立離散度） | k | 訓練期 分差/大小 | 驗證期 分差/大小 |")
    print("|---|---|---|---|")
    for v, k in ((0.0, 14.0), (0.32, 40.0), (0.45, 1e9)):
        trm, trt, _ = evaluate(train, v, k, lg, home, off, dfn, pf)
        tem, tet, _ = evaluate(test, v, k, lg, home, off, dfn, pf)
        label = "∞" if k > 1e8 else f"{k:g}"
        note = "　← 現行模型" if v == 0.0 else ""
        print(f"| {v:.2f} | {label} | {100 * trm:.2f}pp / {100 * trt:.2f}pp "
              f"| **{100 * tem:.2f}pp** / **{100 * tet:.2f}pp**{note} |")
    print("\n方向確認正確（分差明顯改善），但仍過不了 3pp，"
          "而且同一個參數會把大小分弄壞 —— 一個旋鈕服務不了兩個市場。")

    print("\n## 四、要能跑讓分盤，必須同時滿足\n")
    for i, (head, body) in enumerate(REQUIREMENTS, 1):
        print(f"{i}. **{head}**\n   - {body}\n")
    print("在這四項都到位之前，讓分盤維持不定價。"
          "這不是保守，是這個模型的分差分布窄了兩倍以上，"
          "算出來的 EV 會是雜訊而不是優勢。")


if __name__ == "__main__":
    main()
