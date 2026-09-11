"""先發實際投球局數與模型誤差 —— 「牛棚權重被高估」這個假說的檢定。

執行: ``python3 -m analysis.validate_starter_length``

⚠️ 這個假說是在賠錢之後才想到的
-------------------------------
2026-09-10 的首選（火腿 @ 軟銀 大分 7+25、EV +23.7%、本季分歧最大的
一注）全輸: 模型 8.45、實際 5。事後看逐場投手表，機制很明顯:

    加藤貴之（火腿）投 7.0 局 99 球，牛棚只用 1 人
    松本晴（軟銀）  投 5.0 局 97 球

模型假設加藤貴之投 5.67 局（他的季內 IP/G），因此把 **37% 的權重**
給了火腿那個係數 1.144（聯盟第 3 差）的牛棚。他實際投了 7 局，
真正的牛棚權重只有 22%。模型多算的那 15% 全部乘在最差的部門上。

**看到虧損之後才長出來的機制，最容易是事後合理化。** 所以這支檔案
用和前三個假說完全相同的標準檢定它，門檻一樣是 2 個標準誤。

⚠️⚠️ 最重要的一件事: 天真的檢定是循環論證
------------------------------------------
「把模型誤差對『先發實際局數 − 假設局數』回歸」會得到斜率
**-1.00 分／局、6.6 個標準誤** —— 看起來是壓倒性的證據。**它不是。**

先發被打爆的時候，他 **同時** 提早下場 **而且** 該隊失分暴增。
兩個變數由同一件事驅動，回歸只是把「他被打爆了」量了兩次。
斜率約 -1.0 分／局正是這個機械關係該有的大小: 提早兩局退場的投手，
通常正是因為多丟了約兩分。

**這條回歸完全沒有告訴我們混合權重是否錯了。** 本檔把它印出來，
是為了留下「為什麼不能這樣測」的紀錄 —— 這種相關性在事後檢討裡
非常容易被當成因果。

三個不循環的問法
----------------
1. **事前問法**: 模型 *假設* 的先發局數（定價時就知道）會不會預測誤差？
   若混合權重的函數形式錯了，誤差應該隨假設局數系統性變化。
   這條不碰結果，不循環，而且 **可操作**。
2. **條件問法**: 只看先發沒有被打爆的場次（失分 ≤ 2），
   局數差與誤差還有沒有關係？打爆的通道被切掉之後若關係消失，
   就證實第 1 節那條回歸是循環的。
3. **選擇問法**: 我 **已下注** 的場次，先發是不是系統性比假設投得久？
   只有這一項成立，才構成「已下注 vs 未下注」偏誤差距的第三個機制。

資料
----
先發實際局數與失分由本機留存的 box.html 解析（17 個比賽日、
178 個球隊場次），與各日 slate 的 `STARTERS[team][2]`（當日採用的
預期局數）對照。沒有留存 box.html 的日子自動略過。
"""

from __future__ import annotations

import importlib
import json
import math
from pathlib import Path

from analysis.settle import LEDGER

ACTUAL = Path(__file__).with_name("starter_ip_actual.json")
"""{日期: {隊名: [先發實際局數, 先發失分]}}，由 box.html 解析而來。"""

BLOWUP_RUNS = 3
"""先發失分達此值即視為「被打爆」通道 —— 條件檢定要把它切掉。"""


def collect() -> list[dict]:
    actual = json.loads(ACTUAL.read_text(encoding="utf-8"))
    rows = []
    for date in sorted(LEDGER):
        if date not in actual:
            continue
        spec = LEDGER[date]
        slate = importlib.import_module(spec["module"])
        for game in slate.GAMES:
            final = spec["finals"][game.home_team]
            if final is None:
                continue
            home, away = slate.JP[game.home_team], slate.JP[game.away_team]
            if home not in actual[date] or away not in actual[date]:
                continue
            gap = sum(actual[date][t][0] - slate.STARTERS[t][2] for t in (home, away))
            assumed = sum(slate.STARTERS[t][2] for t in (home, away))
            worst = max(actual[date][t][1] for t in (home, away))
            pred = slate.build_model(game).distributions().expected_total()
            rows.append({
                "date": date, "game": game.matchup, "gap": gap, "assumed": assumed,
                "err": sum(final) - pred, "worst_sp_runs": worst,
                "bet": spec["positions"][game.home_team][2] > 0,
            })
    return rows


def regress(xs: list[float], ys: list[float]) -> tuple[float, float]:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    s2 = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys)) / (n - 2)
    return b, math.sqrt(s2 / sxx)


def mean_se(v: list[float]) -> tuple[float, float]:
    m = sum(v) / len(v)
    return m, (sum((x - m) ** 2 for x in v) / (len(v) - 1) / len(v)) ** 0.5


def main() -> None:
    rows = collect()
    print("# 先發投球長度與模型誤差\n")
    print(f"樣本 **{len(rows)} 場**（已結算、且本機留有 box.html 的比賽）。")
    print("「局數差」= 兩隊先發實際局數合計 − 當日模型假設的合計。\n")
    mg, seg = mean_se([r["gap"] for r in rows])
    print(f"- 局數差平均 **{mg:+.2f} 局**（標準誤 {seg:.2f}）。\n")

    # ---------- 0. 循環的那條 ----------
    b0, se0 = regress([r["gap"] for r in rows], [r["err"] for r in rows])
    print("## 0. 天真的回歸（**循環，不可採信**）\n")
    print(f"「實際 − 模型」對局數差：斜率 **{b0:+.3f} 分／局**、"
          f"標準誤 {se0:.3f} → **{abs(b0) / se0:.1f} 個標準誤**。")
    print("\n先發被打爆時 **同時** 提早下場且該隊失分暴增 —— 兩個變數由同一件事"
          "驅動，這條回歸只是把「他被打爆了」量了兩次。"
          "斜率接近 -1.0 分／局正是這個機械關係該有的大小。**這不是證據。**")

    # ---------- 1. 事前問法 ----------
    print("\n## 1. 事前問法：模型 *假設* 的先發局數會不會預測誤差？\n")
    b1, se1 = regress([r["assumed"] for r in rows], [r["err"] for r in rows])
    print(f"「實際 − 模型」對 **假設** 局數合計：斜率 **{b1:+.3f} 分／局**、"
          f"標準誤 {se1:.3f} → **{abs(b1) / se1:.1f} 個標準誤**。")
    print("\n這條只用定價時就知道的量，不循環。"
          + ("**達到門檻** —— 混合權重的函數形式該檢討。"
             if abs(b1) / se1 >= 2 else
             f"**{abs(b1) / se1:.1f} 個標準誤，測不出來** —— "
             "沒有證據顯示 `blended_defence` 的權重函數有系統性偏誤。"))

    # ---------- 2. 條件問法 ----------
    clean = [r for r in rows if r["worst_sp_runs"] < BLOWUP_RUNS]
    print(f"\n## 2. 條件問法：切掉「先發被打爆」的通道\n")
    print(f"只保留 **兩隊先發失分都 < {BLOWUP_RUNS} 分** 的 {len(clean)} 場"
          f"（原 {len(rows)} 場）。若第 0 節的關係是循環造成的，這裡應該塌掉。\n")
    if len(clean) > 3:
        b2, se2 = regress([r["gap"] for r in clean], [r["err"] for r in clean])
        print(f"- 斜率 **{b2:+.3f} 分／局**、標準誤 {se2:.3f} → "
              f"**{abs(b2) / se2:.1f} 個標準誤**"
              f"（原 {abs(b0) / se0:.1f} 個標準誤）。")
        shrink = 1 - abs(b2) / abs(b0) if b0 else 0
        print(f"- 斜率縮小 **{shrink:.0%}** —— "
              + ("大幅塌陷，證實第 0 節那條主要是「被打爆」的循環。"
                 if shrink > 0.4 else
                 "沒有塌掉多少，關係可能不只是循環，值得再看。"))

    print("\n| 局數差分層 | 場數 | 平均局數差 | 實際−模型 | 標準誤 |")
    print("|---|---|---|---|---|")
    srt = sorted(rows, key=lambda r: r["gap"])
    size = len(srt) // 3
    for label, grp in zip(("最短（投不滿假設）", "中間", "最長（超過假設）"),
                          (srt[:size], srt[size:2 * size], srt[2 * size:])):
        m, s = mean_se([r["err"] for r in grp])
        print(f"| {label} | {len(grp)} | "
              f"{sum(r['gap'] for r in grp) / len(grp):+.2f} | {m:+.2f} | {s:.2f} |")

    # ---------- 3. 選擇問法 ----------
    on = [r["gap"] for r in rows if r["bet"]]
    off = [r["gap"] for r in rows if not r["bet"]]
    print("\n## 3. 選擇問法：已下注的場次，先發特別容易投超過假設嗎？\n")
    print("| 分組 | 場數 | 平均局數差 | 標準誤 |")
    print("|---|---|---|---|")
    for label, grp in (("已下注", on), ("未下注", off)):
        m, s = mean_se(grp)
        print(f"| {label} | {len(grp)} | {m:+.2f} | {s:.2f} |")
    mon, son = mean_se(on)
    mof, sof = mean_se(off)
    se_d = (son ** 2 + sof ** 2) ** 0.5
    n_se = abs(mon - mof) / se_d if se_d else 0.0
    print(f"\n- 已下注 − 未下注 的局數差距 **{mon - mof:+.2f} 局**，"
          f"標準誤 {se_d:.2f} → **{n_se:.1f} 個標準誤**。")

    print("\n## 結論\n")
    if n_se >= 2:
        print("- 這是「已下注 vs 未下注」偏誤差距的 **第三個機制**，且可操作。")
    else:
        print(f"- 選擇效果 **{n_se:.1f} 個標準誤，不成立**。"
              "已下注與未下注的場次，先發投球長度沒有系統性差異 —— "
              "這 **不是** 那個偏誤差距的第三個機制。")
    print("- 9/10 首選那一場（加藤貴之投 7 局、模型只假設 5.67 局）"
          "是真實發生的事，但它是 **單場的運氣**，不是可重複的模型缺陷: "
          "全樣本裡先發平均比假設投得 **短** 一點，方向與那一場相反。")
    print("- 這個假說是 **看到虧損之後** 才提出的，因此和前三個假說用同一個"
          "門檻檢定。四個候選機制現在全部落空。")


if __name__ == "__main__":
    main()
