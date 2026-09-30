"""第六個候選機制: 模型與盤口的分歧，是不是大多是模型自己的誤差？

執行: ``python3 -m analysis.validate_market_shrinkage``

為什麼現在問 —— 追蹤中的訊號到了門檻
------------------------------------
「已下注 vs 未下注」的偏誤差距在 2026-09-30 結算時到了 2 個標準誤
（scorecard 以今天的校準重算 1.97；以定價當時凍結的模型值算 **2.02**）。
事先寫好的規則是: 到門檻時 **先找到機制才動模型**。前五個候選
（過度發散、同日共同因子、誤差集中於大分歧、先發投球長度、牛棚疲勞）
都已檢驗且不成立。

⚠️ 這一個是 **事後** 提出的: 在訊號到門檻之後才決定要測它。它是下注模型
選擇偏誤最標準的解釋（winner's curse / 市場有效性），不是從資料裡挖出來的
怪現象，但仍然不是事前登記，解讀要打折扣。

假說
----
若盤口含有模型沒有的資訊，則

    E[實際 − 模型 | 模型 − 盤口 = d] = −β·d

β = 0: 分歧全是盤口的錯（模型更準）; β = 1: 分歧全是模型的錯（跟盤口一樣就好）。
等價的另一面: 「實際 − 盤口」對 d 的斜率是 1 − β —— 也就是
**模型的分歧對結果有沒有預測力**。模型要有優勢，這個斜率必須是正的。

我們押的正是 |d| 大的場次（EV 門檻），所以 β 若接近 1，下注場次就會系統性地
「實際 − 模型」偏向 d 的反方向 —— 正是追蹤中那個訊號的樣子。

它和前面兩個機制不一樣
----------------------
* 候選 1（`validate_calibration_slope`）問的是要不要往 **聯盟平均** 收縮;
  這裡問的是要不要往 **盤口** 收縮。
* 候選 3（`validate_disagreement_strata`）只看 **已下注** 場次、依 |d| 分層。
  下注場次的 |d| 都已經過了門檻，範圍被截斷，看不到整條關係。
  這裡用 **全部有定價的場次**（含未下注），d 從負到正都有。

量法
----
* 模型值用 **定價當時** 的值 —— 從每天的報告 ``analysis/<日期>.md`` 解析
  「模型預期總分」。slate 在 import 時讀的是當下的校準，重算會把那些比賽
  本身的結果放進係數（樣本內），低估模型當時的誤差。
* 盤口用等效盤口 ``game.total.effective``。
* 中止的比賽排除。
"""

from __future__ import annotations

import importlib
import math
import re
from pathlib import Path

from analysis.settle import LEDGER

ROOT = Path(__file__).resolve().parent


def collect() -> list[dict]:
    rows = []
    for date in sorted(LEDGER):
        spec = LEDGER[date]
        slate = importlib.import_module(spec["module"])
        md = (ROOT / f"{date}.md").read_text(encoding="utf-8")
        for game in slate.GAMES:
            final = spec["finals"][game.home_team]
            if final is None:
                continue
            sec = re.search(rf"### {re.escape(game.matchup)}(.*?)(?=\n### |\n## |\Z)",
                            md, re.S)
            m = sec and re.search(r"模型預期總分 (\d+\.\d+)", sec.group(1))
            if not m:
                raise SystemExit(f"{date} {game.matchup}: 報告裡找不到定價當時的模型值")
            rows.append({
                "date": date,
                "frozen": float(m.group(1)),
                "now": slate.build_model(game).distributions().expected_total(),
                "line": float(game.total.effective),
                "actual": sum(final),
                "bet": spec["positions"][game.home_team][2] > 0,
            })
    return rows


def ols(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """回傳 (截距, 斜率, 斜率標準誤)。"""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    s2 = sum((y - a - b * x) ** 2 for x, y in zip(xs, ys)) / (n - 2)
    return a, b, math.sqrt(s2 / sxx)


def model_side_won(r: dict) -> float:
    """模型那一邊（模型 < 盤口 → 小分）對等效盤口的勝負; 剛好落在盤口算 0.5。"""
    diff = r["actual"] - r["line"]
    if abs(diff) < 1e-9:
        return 0.5
    return 1.0 if (diff < 0) == (r["frozen"] < r["line"]) else 0.0


def main() -> None:
    rows = collect()
    n = len(rows)
    print("# 第六個候選機制：模型與盤口的分歧是不是大多是模型的誤差\n")
    print(f"樣本 **{n} 場**（所有已開打且有定價的比賽；已下注 "
          f"{sum(r['bet'] for r in rows)}、未下注 {sum(not r['bet'] for r in rows)}）。"
          "⚠️ 這個假說是在追蹤訊號到門檻 **之後** 才提出的，不是事前登記。\n")

    print("## 主要檢定：實際 − 模型 對 (模型 − 盤口) 的斜率\n")
    print("斜率 = −β。β = 1 代表分歧全是模型的誤差。\n")
    print("| 模型值 | 斜率 | 標準誤 | 個標準誤 | β 估計 |")
    print("|---|---|---|---|---|")
    res = {}
    for key, label in (("frozen", "定價當時（凍結）"), ("now", "今天的校準重算（樣本內）")):
        d = [r[key] - r["line"] for r in rows]
        y = [r["actual"] - r[key] for r in rows]
        _, b, se = ols(d, y)
        res[key] = (b, se)
        print(f"| {label} | {b:+.3f} | {se:.3f} | **{abs(b) / se:.2f}** | {-b:.2f} |")
    print("\n- 決策是用定價當時的值做的，所以 **凍結值才是對的量法**。"
          "重算值用了含這些比賽在內的係數，會系統性地讓舊誤差看起來比較小。")

    d = [r["frozen"] - r["line"] for r in rows]
    yl = [r["actual"] - r["line"] for r in rows]
    _, b_line, se_line = ols(d, yl)
    print(f"\n## 同一件事的另一面：模型的分歧有沒有預測力\n")
    print(f"「實際 − 盤口」對 (模型 − 盤口) 的斜率 = 1 − β = **{b_line:+.3f}**，"
          f"標準誤 {se_line:.3f}。")
    print(f"- 模型要有優勢，這個斜率必須 **明顯大於 0**。"
          f"95% 區間約 {b_line - 1.96 * se_line:+.2f} ~ {b_line + 1.96 * se_line:+.2f}。")

    print("\n## 依分歧分三層（凍結值）\n")
    print("| 層 | 場數 | 模型 − 盤口 | 實際 − 模型 | 實際 − 盤口 | 模型那一邊勝率 | 已下注 |")
    print("|---|---|---|---|---|---|---|")
    srt = sorted(rows, key=lambda r: r["frozen"] - r["line"])
    k = n // 3
    for i, grp in enumerate((srt[:k], srt[k:2 * k], srt[2 * k:])):
        dd = [r["frozen"] - r["line"] for r in grp]
        e = [r["actual"] - r["frozen"] for r in grp]
        el = [r["actual"] - r["line"] for r in grp]
        m = sum(e) / len(e)
        s = (sum((x - m) ** 2 for x in e) / (len(e) - 1) / len(e)) ** 0.5
        w = [model_side_won(r) for r in grp]
        p = sum(w) / len(w)
        print(f"| {i + 1} | {len(grp)} | {sum(dd) / len(dd):+.2f}（{min(dd):+.2f}~{max(dd):+.2f}） "
              f"| {m:+.2f} ± {s:.2f} | {sum(el) / len(el):+.2f} "
              f"| {p:.1%} ± {(p * (1 - p) / len(w)) ** 0.5:.1%} | {sum(r['bet'] for r in grp)} |")
    print("\n- 勝率是模型那一邊（模型 < 盤口 → 小分）對等效盤口的勝負，"
          "不計部分結算; 0.930 的損益兩平約 51.8%。")

    print("\n## 穩健性：是不是被幾場爆分帶動\n")
    base_t = abs(res["frozen"][0]) / res["frozen"][1]
    trimmed = []
    for cap in (14, 12):
        y = [min(r["actual"], cap) - r["frozen"] for r in rows]
        _, b, se = ols(d, y)
        trimmed.append(abs(b) / se)
        print(f"- 實際總分截到 ≤ {cap}：斜率 {b:+.3f}，**{abs(b) / se:.2f} 個標準誤**。")
    if min(trimmed) >= base_t * 0.9:
        print("- 截尾後沒有變弱 —— **不是 9/15（15 分）那類爆分場帶出來的**。")
    else:
        print("- ⚠️ 截尾後明顯變弱，結果有一部分是少數爆分場帶出來的。")

    print("\n## 分期：是不是舊版模型的問題\n")
    print("季中修過好幾次模型（校準管線、上半場比例等），凍結值混了不同版本。\n")
    print("| 期間 | 場數 | 斜率 | 個標準誤 | β | 1 − β |")
    print("|---|---|---|---|---|---|")
    for label, lo, hi in (("8/13–8/31", "", "2026-09-01"),
                          ("9/1 以後", "2026-09-01", "9999"),
                          ("9/15 以後（新校準管線）", "2026-09-15", "9999")):
        g = [r for r in rows if lo <= r["date"] < hi]
        if len(g) < 10:
            continue
        gd = [r["frozen"] - r["line"] for r in g]
        _, b, se = ols(gd, [r["actual"] - r["frozen"] for r in g])
        _, bl, sel = ols(gd, [r["actual"] - r["line"] for r in g])
        print(f"| {label} | {len(g)} | {b:+.2f} ± {se:.2f} | {abs(b) / se:.1f} "
              f"| {-b:.2f} | {bl:+.2f} ± {sel:.2f} |")
    print("\n- 前後兩半的 β 若相近，就不是早期舊版模型造成的。"
          "新校準管線之後的場次太少，單獨看測不出任何東西。")

    b, se = res["frozen"]
    print("\n## 結論\n")
    if abs(b) / se >= 2 and b < 0:
        print(f"- 用定價當時的模型值，β 估計 **{-b:.2f}**、{abs(b) / se:.1f} 個標準誤。"
              "模型與盤口的分歧 **幾乎全是模型的誤差**，"
              f"對結果沒有測得出的預測力（1 − β = {b_line:+.2f}）。")
        print("- 這 **解釋得了** 追蹤中的「已下注 vs 未下注」訊號: 我們押的正是分歧大的場次，"
              "而分歧大的場次正是模型錯得最多的場次。")
        print("- 含意: 模型算出的 EV（例如 +10% 以上）大部分來自它和盤口的分歧，"
              "而那個分歧沒有預測力 —— **這些 EV 不可信**。")
        print("- ⚠️ 事後提出、樣本 169 場。它符合下注模型最常見的失敗型態"
              "（市場比模型準），但仍需要 **往後的新比賽** 驗證。")
        print("- **不自動改模型。** 要不要改、怎麼改（往盤口收縮多少、或停止下注），"
              "是使用者的決定。")
    else:
        print(f"- 用定價當時的模型值只有 {abs(b) / se:.1f} 個標準誤，未達門檻，不成立。")


if __name__ == "__main__":
    main()
