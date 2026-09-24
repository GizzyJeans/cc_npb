"""前一天的牛棚負擔會不會預測模型誤差？

執行: ``python3 -m analysis.validate_bullpen_fatigue``

這個假說和前四個不一樣 —— 它是 **事前寫下的**
-----------------------------------------------
2026-09-15 的報告在開賽前就寫了這段:

    ⚠️ 巨人與 DeNA 的牛棚昨晚打滿 12 局被榨乾（巨人用 10 人／牛棚 144 球，
    DeNA 用 9 人／牛棚 105 球）。模型的牛棚係數是整季平均，完全不知道
    這件事 —— 今天的實際失分很可能高於模型預期，方向偏大分。

然後我 **在那一場押了小分**，理由是「只有機制、沒有量測」。
結果那場開出 **15 分**，是當日最高、也是本季最大的單場誤差（模型 6.18）。

前四個候選機制（預測過度發散、同日共同因子、誤差集中於大分歧、
先發投球長度）都是 **看到虧損之後** 才想到的，所以要用嚴格的門檻
防止事後合理化。這一個不同: 它在結果出現前就白紙黑字寫下了方向，
而且方向對了。**事前登記的預測值得認真檢定，不是拿來當成證據就是拿來否決。**

但一場就是一場。所以這支腳本用全樣本檢定它。

怎麼量
------
* **事前可得**: 定價時前一天的 box.html 已經公開，牛棚用了幾人、幾球
  都查得到。這是它和「先發投球長度」最關鍵的差別 ——
  後者要等比賽打完才知道，就算成立也不可操作。
* **指標**: 兩隊「前一天牛棚投球數」的合計。用球數比人次好，
  因為 1 局 30 球和 1 局 8 球的消耗完全不同。
* **對照**: 同時看「前兩天合計」，以及只看人次的版本。

判讀
----
假說預測 **正斜率**: 前一天牛棚用得越兇，今天實際得分越高於模型。
門檻與前四個一致，**2 個標準誤**。

2026-09-21 覆檢: 樣本加大後，反證變強了
----------------------------------------
9/20 又出現一次「事前標了牛棚吃緊、結果真的開高」的案例 ——
中日 9/19 以 1-14 慘敗、牛棚四人吃 112 球（當日全聯盟最重），
9/20 該場開出 13 分，而我押的是小分。**兩次軼事都指向同一個方向。**

正因如此才要重跑，而不是讓軼事累積成信念。樣本由 88 場加到 110 場後:

    前一天牛棚投球數   斜率 0.8 個標準誤（原 0.3），**方向仍與假說相反**

分層結果現在是 **四層單調、而且單調的方向是反的**:

    層  場數  牛棚球數  實際−模型
    1   27   56       +0.74    <- 最輕
    2   27   86       +0.82
    3   27   110      -0.32
    4   29   160      -0.48    <- 最重
    最重 − 最輕 = **-1.21 分**，1.3 個標準誤

也就是說: 前一天牛棚用得越兇，今天模型越傾向 **高估** 得分，
不是低估。這和假說要的方向完全相反，而且比 9/16 那次更清楚。

**兩次軼事、兩次都「說中」，全樣本卻越看越反向。** 這正是軼事的用途
（提出假說）與極限（不能驗證假說）的教科書案例。維持不調整。

2026-09-24 覆檢: 第三次軼事，反證變弱但方向沒變
----------------------------------------------
9/23 阪神 @ 養樂多: 賽前寫明「兩隊牛棚前一天合計 317 球」（本資料集最重），
押小分，開出 12 分（模型 7.11）。**三次事前標記，三次都開大分**
（9/15、9/20、9/23）。樣本 110 → 113 場:

    前一天牛棚投球數   0.8 → **0.3 個標準誤**，方向仍與假說相反
    最重層 − 最輕層     -1.21 → -0.93 分（1.0 個標準誤）

反證變弱了（317 那場 +4.8 分的誤差槓桿很大），但沒有翻到假說的方向，
離正方向的 2 個標準誤更遠。

「會不會只在極端吃緊時才成立？」也查了。前一天合計最重的三場:

    317   +4.82   9/23 阪神 @ 養樂多（已下注）
    268   -1.64   9/6  巨人 @ 廣島（未下注）  <- 第二重，開小分
    249   +8.75   9/15 巨人 @ DeNA（已下注）

最重 10 場平均 +0.78 分（標準誤 1.30），與其餘 103 場的 +0.18 分分不開。
「極端就開大」不成立。

三次軼事都是 **我有下注、所以事前寫了筆記** 的場次。9/6 那場同樣極端吃緊，
沒下注、沒寫筆記、開小分 —— 它不會變成軼事。這就是軼事的選擇性記憶。
維持不調整。
"""

from __future__ import annotations

import datetime as dt
import importlib
import json
import math
from pathlib import Path

from analysis.settle import LEDGER

DATA = Path(__file__).with_name("bullpen_by_date.json")
"""{日期: {隊名: {pen_pitches, pen_count, total_pitchers}}}，由 box.html 解析。"""


def collect() -> list[dict]:
    pen = json.loads(DATA.read_text(encoding="utf-8"))
    rows = []
    for date in sorted(LEDGER):
        spec = LEDGER[date]
        slate = importlib.import_module(spec["module"])
        if not hasattr(slate, "JP"):
            continue
        try:
            day = dt.date.fromisoformat(date)
        except ValueError:
            continue                      # 08-22b 這類同日第二盤
        prev1 = (day - dt.timedelta(days=1)).isoformat()
        prev2 = (day - dt.timedelta(days=2)).isoformat()
        for game in slate.GAMES:
            final = spec["finals"].get(game.home_team)
            if final is None:
                continue
            home, away = slate.JP[game.home_team], slate.JP[game.away_team]
            # 兩隊前一天都要有紀錄，否則無法比較 (休兵日 = 0 球，也算有紀錄)
            d1 = pen.get(prev1, {})
            if home not in d1 or away not in d1:
                continue
            d2 = pen.get(prev2, {})
            pred = slate.build_model(game).distributions().expected_total()
            rows.append({
                "date": date, "game": game.matchup,
                "p1": d1[home]["pen_pitches"] + d1[away]["pen_pitches"],
                "n1": d1[home]["pen_count"] + d1[away]["pen_count"],
                "p2": (d1[home]["pen_pitches"] + d1[away]["pen_pitches"]
                       + d2.get(home, {}).get("pen_pitches", 0)
                       + d2.get(away, {}).get("pen_pitches", 0)),
                "err": sum(final) - pred,
                "bet": spec["positions"][game.home_team][2] > 0,
            })
    return rows


def regress(xs: list[float], ys: list[float]) -> tuple[float, float]:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, float("inf")
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    s2 = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys)) / (n - 2)
    return b, math.sqrt(s2 / sxx)


def mean_se(v: list[float]) -> tuple[float, float]:
    m = sum(v) / len(v)
    return m, (sum((x - m) ** 2 for x in v) / (len(v) - 1) / len(v)) ** 0.5


def main() -> None:
    rows = collect()
    n = len(rows)
    print("# 前一天的牛棚負擔會不會預測模型誤差？\n")
    print(f"樣本 **{n} 場**（已結算、且兩隊前一天的 box.html 都解析得到）。")
    print("「牛棚投球數」不含先發，休兵日計為 0。\n")

    print("## 這個假說是事前寫下的\n")
    print("2026-09-15 的報告在開賽前就寫明巨人與 DeNA 的牛棚前一晚被榨乾、"
          "「方向偏大分」，而我仍在那場押了小分。該場開出 **15 分**"
          "（模型 6.18），是本季最大的單場誤差。\n")
    print("前四個候選機制都是看到虧損之後才想到的; 這一個在結果出現前"
          "就寫下了方向。**所以它值得認真檢定** —— 但一場就是一場。\n")

    for key, label in (("p1", "前一天牛棚投球數"),
                       ("p2", "前兩天牛棚投球數合計"),
                       ("n1", "前一天牛棚人次")):
        xs = [float(r[key]) for r in rows]
        ys = [r["err"] for r in rows]
        b, se = regress(xs, ys)
        mx = sum(xs) / n
        sdx = (sum((x - mx) ** 2 for x in xs) / n) ** 0.5
        print(f"### {label}\n")
        print(f"- 平均 {mx:.0f}、標準差 {sdx:.0f}。")
        print(f"- 斜率 **{b * 100:+.3f} 分／100 球**"
              if key != "n1" else
              f"- 斜率 **{b:+.3f} 分／人次**", end="")
        print(f"，標準誤 {(se * 100 if key != 'n1' else se):.3f} → "
              f"**{abs(b) / se:.1f} 個標準誤**"
              f"（假說預測正值，實際{'為正' if b > 0 else '為負'}）\n")

    # 分層看最吃緊的那一端
    print("## 依前一天牛棚投球數分層\n")
    srt = sorted(rows, key=lambda r: r["p1"])
    size = n // 4
    print("| 層 | 場數 | 牛棚球數範圍 | 平均 | 實際−模型 | 標準誤 |")
    print("|---|---|---|---|---|---|")
    tiers = [srt[i * size:(i + 1) * size if i < 3 else n] for i in range(4)]
    for i, grp in enumerate(tiers):
        m, s = mean_se([r["err"] for r in grp])
        print(f"| {i + 1}{'（最輕）' if i == 0 else '（最重）' if i == 3 else ''} "
              f"| {len(grp)} | {grp[0]['p1']}–{grp[-1]['p1']} "
              f"| {sum(r['p1'] for r in grp) / len(grp):.0f} | {m:+.2f} | {s:.2f} |")

    lo, hi = tiers[0], tiers[-1]
    ml, sl = mean_se([r["err"] for r in lo])
    mh, sh = mean_se([r["err"] for r in hi])
    se_d = (sl ** 2 + sh ** 2) ** 0.5
    n_se = abs(mh - ml) / se_d if se_d else 0.0
    print(f"\n- 最重層 − 最輕層 的「實際−模型」差距 **{mh - ml:+.2f} 分**，"
          f"標準誤 {se_d:.2f} → **{n_se:.1f} 個標準誤**。")

    print("\n## 結論\n")
    b1, se1 = regress([float(r["p1"]) for r in rows], [r["err"] for r in rows])
    strong = abs(b1) / se1 >= 2 and b1 > 0
    if strong:
        print("- **達到門檻且方向正確。** 前一天的牛棚負擔確實預測模型低估得分。")
        print("- 這是四個機制之外 **第一個站得住的**，而且 **事前可得** —— "
              "定價時前一天的 box.html 已經公開，可以直接算。")
        print("- 下一步是決定怎麼用: 最保守的做法是把它當成一道 **揭露**"
              "（像現在這樣印在風險欄），其次是調整當日牛棚係數，"
              "最激進的是直接修 EV。**在只有一個球季的樣本下，先做揭露。**")
    else:
        print(f"- **{abs(b1) / se1:.1f} 個標準誤，未達門檻。**"
              f"{'方向與假說一致但強度不足。' if b1 > 0 else '而且方向與假說相反。'}")
        print("- 9/15 那場（模型 6.18、實際 15）是真實發生的，"
              "但全樣本看不出這個效應 —— **它比較可能是那一場的運氣，"
              "而不是可重複的規律**。")
        print("- 事前登記讓這個假說值得檢定，但 **事前登記不等於正確**。"
              "檢定的結論和前四個一樣: 不動模型。")
    print(f"- 門檻與前四個機制一致（2 個標準誤），不因為它「說中了一場」而放寬。")


if __name__ == "__main__":
    main()
