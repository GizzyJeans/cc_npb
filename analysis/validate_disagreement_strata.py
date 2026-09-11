"""分歧幅度會不會預測模型誤差？—— 檢驗預先寫下的補救方案。

執行: ``python3 -m analysis.validate_disagreement_strata``

背景
----
scorecard 追蹤的「已下注 vs 未下注」偏誤差距自 2026-08-28 起走勢:

    1.7 → 0.9 → 0.9 → 1.2 → 1.5 → 1.6 → 1.8 → 1.8

行動門檻設在 2 個標準誤。為了避免屆時臨時決定，2026-09-09 的報告
預先寫下了到門檻時要做的事:

    把已下注場次按「模型 − 盤口」的絕對值分層，檢查誤差是否集中在
    分歧最大的那一層；若是，最直接的補救是對分歧幅度設上限。

理由是 8/27（石川雅規）與 8/29（大川慈英）兩次大分歧都被證明是
「模型缺資料而市場有」—— 若這個模式普遍成立，砍掉大分歧就能止血。

⚠️ 結果推翻了這個計畫
--------------------
2026-09-10 先跑了一次當預覽（跑診斷不等於行動），55 場已下注部位分三層:

    層  場數  分歧範圍      平均分歧  實際−模型  ROI
    1   18   0.01-0.36    0.20     +1.18     +4.8%
    2   18   0.36-0.79    0.57     +0.32     -6.1%
    3   19   0.79-1.83    1.08     +0.61     **+36.1%**

    最高層 − 最低層 的「實際−模型」差距 -0.22 分，**0.2 個標準誤**

兩件事同時成立:

1. **誤差完全沒有集中在高分歧層。** 三層的「實際−模型」都是正的
   (+1.18 / +0.32 / +0.61)，而且最低分歧層反而最高。
2. **最高分歧層的 ROI 是 +36.1%，遠優於另外兩層。**

也就是說「對分歧幅度設上限」會砍掉獲利最好的三分之一部位。
**預先寫下的計畫是錯的，已作廢。**

那 8/27 和 8/29 呢？
-------------------
那兩次的共通點不是「分歧大」，是 **先發投手查無成績**——
石川雅規本季零登板、大川慈英 0.2 局。那個模式已經有專門的門檻
(`starter_stats_known`) 在擋，而且擋對了。把它推廣成「分歧大就不下」
是過度推論，本檔就是這個推論的反例。

2026-09-11 的壓力測試: 最大分歧的一注賠了錢，結論仍成立
--------------------------------------------------------
9/10 的首選（火腿 @ 軟銀 大分、EV +23.7%）是 **本季分歧最大的一注**
（+1.57 分），而且輸得很難看 —— 模型 8.45、實際只有 5 分。
9/9 的報告還特別引用本檔，說明「不因分歧大而打折」。

加入這場之後重跑，結論沒有翻轉:

    層  場數  分歧範圍      實際−模型  ROI
    3   20   0.76-1.83    +0.28     **+29.3%**（仍是三層最佳）
    最高層 − 最低層 差距 -0.87 分，**0.7 個標準誤**（仍測不出來）

最高分歧層的 ROI 由 +36.1% 降到 +29.3%，但仍遠優於另外兩層。
**一次虧損不會推翻一個 20 場的分層結果** —— 如果因為最大的一注輸了
就回頭設分歧上限，那是被單場結果牽著走，正是本檔一開始要避免的事。

目前的狀態
----------
「已下注 vs 未下注」這個訊號的 **四個** 候選機制都已檢驗、都不成立:

* **模型預測過度發散** —— 2026-09-08 用校準斜率檢定，模型與市場的
  斜率都測不出來 (需約 2,000 場)。見 validate_calibration_slope.py。
* **同日共同因子** —— 2026-09-03 單因子隨機效果 ANOVA，ICC = 0。
  見 validate_day_effect.py。
* **誤差集中在高分歧場次** —— 本檔，0.7 個標準誤，且方向相反。
* **先發投球長度使牛棚權重失準** —— 2026-09-11，事前問法 0.5 個標準誤、
  選擇問法 0.3 個標準誤。見 validate_starter_length.py。
  （天真的回歸看似 6.6 個標準誤，但那是循環論證。）

四個機制都落空，而訊號本身也從 1.8 退到 **1.5 個標準誤** ——
往門檻的反方向走。應該進一步調低「它反映了某個可修的東西」這個先驗。
在找到第五個具體機制之前，不宜為了「做點什麼」而改模型 ——
那比不動更危險。訊號繼續追蹤，門檻維持 2 個標準誤。
"""

from __future__ import annotations

import importlib

from bethero.lines import settle_total
from analysis.settle import LEDGER, payout

STRATA = 3


def collect() -> list[dict]:
    """已下注且已開打的部位: 分歧幅度、模型誤差、損益。"""
    rows = []
    for date in sorted(LEDGER):
        spec = LEDGER[date]
        slate = importlib.import_module(spec["module"])
        for game in slate.GAMES:
            final = spec["finals"][game.home_team]
            if final is None:
                continue
            _, side, stake, hk, _ = spec["positions"][game.home_team]
            if stake <= 0:
                continue
            pred = slate.build_model(game).distributions().expected_total()
            line = float(game.total.effective)
            actual = sum(final)
            rows.append({
                "date": date, "game": game.matchup,
                "gap": abs(pred - line), "err": actual - pred,
                "pl": payout(settle_total(game.total, actual, side), stake, hk),
                "stake": stake,
            })
    return rows


def main() -> None:
    rows = sorted(collect(), key=lambda r: r["gap"])
    n = len(rows)
    size = n // STRATA

    print("# 分歧幅度分層：誤差會集中在大分歧的場次嗎？\n")
    print(f"已下注且已開打 **{n} 場**，依 |模型 − 盤口| 由小到大分 {STRATA} 層。\n")
    print("| 層 | 場數 | 分歧範圍 | 平均分歧 | 實際−模型 | 標準誤 | 損益 | ROI |")
    print("|---|---|---|---|---|---|---|---|")
    groups = []
    for i in range(STRATA):
        lo = i * size
        hi = n if i == STRATA - 1 else (i + 1) * size
        grp = rows[lo:hi]
        groups.append(grp)
        errs = [r["err"] for r in grp]
        mean = sum(errs) / len(errs)
        sd = (sum((x - mean) ** 2 for x in errs) / len(errs)) ** 0.5
        pl = sum(r["pl"] for r in grp)
        st = sum(r["stake"] for r in grp)
        print(f"| {i + 1} | {len(grp)} | {grp[0]['gap']:.2f}–{grp[-1]['gap']:.2f} "
              f"| {sum(r['gap'] for r in grp) / len(grp):.2f} | {mean:+.2f} "
              f"| {sd / len(grp) ** 0.5:.2f} | {pl:+,.0f} | {100 * pl / st:+.1f}% |")

    lo_g, hi_g = groups[0], groups[-1]
    el = [r["err"] for r in lo_g]
    eh = [r["err"] for r in hi_g]
    ml, mh = sum(el) / len(el), sum(eh) / len(eh)
    vl = sum((x - ml) ** 2 for x in el) / (len(el) - 1)
    vh = sum((x - mh) ** 2 for x in eh) / (len(eh) - 1)
    se = (vl / len(el) + vh / len(eh)) ** 0.5
    n_se = abs(mh - ml) / se if se else 0.0

    print(f"\n- 最高分歧層 − 最低分歧層 的「實際−模型」差距 **{mh - ml:+.2f} 分**，"
          f"標準誤 {se:.2f} → **{n_se:.1f} 個標準誤**。")

    print("\n## 解讀\n")
    if n_se >= 2 and mh > ml:
        print("- 誤差確實集中在高分歧層 → 對 |模型 − 盤口| 設上限是有依據的補救。")
    else:
        print("- **誤差沒有集中在高分歧層。** 三層的「實際−模型」全為正，"
              "最低分歧層甚至最高 —— 分歧幅度不預測模型誤差。")
        best = max(range(STRATA),
                   key=lambda i: sum(r["pl"] for r in groups[i])
                   / sum(r["stake"] for r in groups[i]))
        if best == STRATA - 1:
            print("- 而且 **最高分歧層的 ROI 最好** —— "
                  "「對分歧幅度設上限」會砍掉獲利最好的那一層。"
                  "2026-09-09 預先寫下的補救方案 **已作廢**。")
        print("- 8/27（石川雅規）與 8/29（大川慈英）的共通點不是「分歧大」，"
              "而是 **先發查無成績**。那個模式已由 `starter_stats_known` 擋住且擋對了；"
              "把它推廣成「分歧大就不下」是過度推論，本檔即是反例。")
        print("- 「已下注 vs 未下注」訊號的兩個候選機制"
              "（預測過度發散、誤差集中於大分歧）皆已檢驗且皆不成立，"
              "應調低「該訊號反映了某個可修的東西」這個先驗。"
              "在找到第三個具體機制之前，不宜為了「做點什麼」而改模型。")


if __name__ == "__main__":
    main()
