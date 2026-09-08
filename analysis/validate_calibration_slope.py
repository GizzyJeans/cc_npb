"""模型的預期總分是不是「過度發散」？—— 以及這件事能不能測。

執行: ``python3 -m analysis.validate_calibration_slope``

為什麼要問
----------
scorecard 從 2026-09-02 起持續看到一個組合:

    押小分的場次  實際 − 模型  **+0.60**
    押大分的場次  實際 − 模型  **-1.07**
    全部場次      實際 − 模型  **+0.00**

整體無偏、但分方向看卻一高一低。這個組合的自然解釋是
**模型的預測值分布得比實際寬** —— 模型說會高分的實際沒那麼高、
說會低分的實際沒那麼低。如果屬實，修法很單純: 把預期總分往聯盟平均收縮。

正確的量法
----------
「押大分/押小分」是個很粗的估計式 —— 它把連續的預測值切成兩堆，
而且切點是「我押了哪一邊」，本身就帶選擇效果。

正確的量是 **校準斜率**: 把實際總分對模型預期總分做回歸

    actual = a + b * pred

b = 1 代表模型的預測幅度剛好; b < 1 代表預測太極端、該往平均收縮。
它用到全部樣本，也不依賴我選了哪一邊。

結果 (n=106)
------------
    模型:     b = 0.825，標準誤 0.382  ->  (b-1)/SE = **-0.46**
    市場盤口: b = 1.451，標準誤 0.512  ->  (b-1)/SE = **+0.88**

**兩個都測不出來。** 斜率的點估計看似支持「模型過度發散」(0.825 < 1)，
但標準誤 0.382 大到讓這個數字沒有任何意義。

原因是訊噪比
------------
    模型預期總分的標準差  0.92
    市場等效盤口的標準差  0.68
    實際總分的標準差      3.67

預測值的變異只有結果變異的四分之一。回歸斜率的標準誤是

    SE(b) = sd(殘差) / (sqrt(n) * sd(預測值))

分母裡的 sd(預測值) 這麼小，n 就得非常大才壓得下 SE。
要把 SE 從 0.382 壓到 0.0875 (才能在 2 個標準誤下分辨 b=0.825 與 b=1)，
需要 **約 2,000 場** —— 大約三個球季、每天每場都定價。

結論
----
1. **「模型過度發散」這個假說在這個樣本量下無法檢定**，
   不論斜率點估計看起來多像。停止用它解釋押大分/押小分的差異。
2. 那個分組差異本身，最可能的解釋是 **雜訊 + 選擇效果**，
   而不是一個可以靠收縮修好的模型缺陷。
3. 這不影響另一個追蹤中的訊號 ——「已下注 vs 未下注」的偏誤差距 ——
   那是 **兩組平均數的差**，估計效率比斜率高得多，
   1.6 個標準誤是有意義的讀數。

順帶一提，市場盤口的斜率 1.451 同樣測不出來 —— 這不是模型獨有的限制，
是「用低變異的預測值去解釋高變異的結果」本來就需要巨量樣本。
"""

from __future__ import annotations

import importlib
import math

from analysis.settle import LEDGER

TARGET_SE = 0.0875
"""要在 2 個標準誤下分辨 b=0.825 與 b=1，所需的斜率標準誤。"""


def collect() -> list[tuple[float, int, float, bool]]:
    """(模型預期總分, 實際總分, 市場等效盤口, 是否已下注)。"""
    out = []
    for date in sorted(LEDGER):
        spec = LEDGER[date]
        slate = importlib.import_module(spec["module"])
        for game in slate.GAMES:
            final = spec["finals"][game.home_team]
            if final is None:
                continue
            pred = slate.build_model(game).distributions().expected_total()
            out.append((pred, sum(final), float(game.total.effective),
                        spec["positions"][game.home_team][2] > 0))
    return out


def regress(xs: list[float], ys: list[float]) -> tuple[float, float, float, float]:
    """回傳 (斜率, 斜率標準誤, 截距, 預測值標準差)。"""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    a = my - b * mx
    resid = [y - (a + b * x) for x, y in zip(xs, ys)]
    s2 = sum(r * r for r in resid) / (n - 2)
    return b, math.sqrt(s2 / sxx), a, (sxx / n) ** 0.5


def main() -> None:
    rows = collect()
    n = len(rows)
    preds = [r[0] for r in rows]
    acts = [float(r[1]) for r in rows]
    lines = [r[2] for r in rows]
    my = sum(acts) / n
    sd_act = (sum((y - my) ** 2 for y in acts) / n) ** 0.5

    print("# 校準斜率檢定：模型的預期總分是否過度發散\n")
    print(f"樣本 **{n} 場**（所有已開打且曾定價的比賽，含未下注）\n")

    print("| 預測來源 | 斜率 b | 標準誤 | (b−1)/SE | 預測值標準差 |")
    print("|---|---|---|---|---|")
    results = {}
    for label, xs in (("模型預期總分", preds), ("市場等效盤口", lines)):
        b, se, _, sd_x = regress(xs, acts)
        results[label] = (b, se, sd_x)
        print(f"| {label} | {b:.3f} | {se:.3f} | {(b - 1) / se:+.2f} | {sd_x:.2f} |")
    print(f"\n實際總分的標準差 **{sd_act:.2f}**。\n")

    b, se, sd_x = results["模型預期總分"]
    print("## 為什麼測不出來\n")
    print(f"- 模型的斜率點估計 {b:.3f} 看似支持「過度發散」（b < 1），"
          f"但標準誤 {se:.3f} 大到讓它沒有意義："
          f"距離 b=1 只有 **{abs(b - 1) / se:.2f} 個標準誤**。")
    print(f"- 根因是訊噪比：預測值的標準差只有 {sd_x:.2f}，"
          f"而結果的標準差是 {sd_act:.2f} —— 相差約 {sd_act / sd_x:.1f} 倍。")
    print("- 斜率標準誤 SE(b) = sd(殘差) / (√n × sd(預測值))，"
          "分母裡的 sd(預測值) 這麼小，n 就得非常大。")
    need = int(round(n * (se / TARGET_SE) ** 2, -2))
    print(f"- 要把 SE 壓到 {TARGET_SE:.4f}（才能在 2 個標準誤下分辨 "
          f"b={b:.3f} 與 b=1），需要 **約 {need:,} 場** —— "
          "大約三個球季、每天每場都定價。")

    print("\n## 結論\n")
    print("1. **「模型過度發散」這個假說在目前的樣本量下無法檢定**，"
          "不論斜率點估計看起來多像。停止用它解釋押大分／押小分的差異。")
    print("2. 那個分組差異最可能是 **雜訊加上選擇效果**，"
          "不是一個能靠收縮預測值修好的模型缺陷。")
    print("3. 這 **不影響** 另一個追蹤中的訊號 ——「已下注 vs 未下注」的"
          "偏誤差距。那是兩組平均數的差，估計效率遠高於斜率，"
          "1.6 個標準誤是有意義的讀數，行動門檻仍是 2 個標準誤。")
    bl, sel, _ = results["市場等效盤口"]
    print(f"4. 對照組：市場盤口的斜率 {bl:.3f} 同樣測不出來"
          f"（{abs(bl - 1) / sel:.2f} 個標準誤）。"
          "這不是模型獨有的限制，是「用低變異的預測值解釋高變異的結果」"
          "本來就需要巨量樣本。")


if __name__ == "__main__":
    main()
