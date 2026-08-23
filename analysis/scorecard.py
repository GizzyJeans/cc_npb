"""跨日累計對帳與 **模型偏誤診斷**。

執行: ``python3 -m analysis.scorecard``

單日的損益幾乎沒有資訊量 (單場總分標準差 4.03)。真正該追蹤的是有沒有
**系統性** 偏誤 —— 例如模型是不是每天都偏向小分。這支腳本把所有日子
的下注單、模型預期總分與市場等效盤口放在一起看。
"""

from __future__ import annotations

import importlib
from fractions import Fraction

from bethero.lines import settle_total
from analysis.settle import LEDGER, payout


def main() -> None:
    rows = []
    for date in sorted(LEDGER):
        spec = LEDGER[date]
        slate = importlib.import_module(spec["module"])
        for game in slate.GAMES:
            sel, side, stake, hk, status = spec["positions"][game.home_team]
            final = spec["finals"][game.home_team]
            pred = slate.build_model(game).distributions().expected_total()
            line = float(game.total.effective)
            rows.append({
                "date": date, "game": game.matchup, "side": side,
                "stake": stake, "hk": hk, "status": status,
                "pred": pred, "line": line,
                "actual": None if final is None else sum(final),
                "ratio": None if final is None
                else settle_total(game.total, sum(final), side),
            })

    print("# 跨日累計對帳與模型偏誤診斷\n")

    # ---------- 損益 ----------
    print("## 逐日損益\n")
    print("| 日期 | 下注場數 | 下注金額 | 損益 |")
    print("|---|---|---|---|")
    total_pl = total_stake = 0.0
    for date in sorted(LEDGER):
        day = [r for r in rows if r["date"] == date and r["stake"] > 0]
        pl = sum(payout(r["ratio"], r["stake"], r["hk"])
                 for r in day if r["ratio"] is not None)
        # 中止退回本金的部位沒有實際承擔風險，不計入下注總額 (否則 ROI 被稀釋)
        st = sum(r["stake"] for r in day if r["ratio"] is not None)
        total_pl += pl
        total_stake += st
        print(f"| {date} | {len(day)} | {st:,.0f} | {pl:+,.0f} |")
    print(f"| **累計** | | **{total_stake:,.0f}** | **{total_pl:+,.0f}** |")
    if total_stake:
        print(f"\n總下注 {total_stake:,.0f} 單位，損益 {total_pl:+,.0f}"
              f"（ROI {total_pl / total_stake:+.1%}、本金 {total_pl / 100000:+.2%}）")

    # ---------- 方向偏誤 ----------
    played = [r for r in rows if r["actual"] is not None]
    unders = sum(1 for r in played if r["side"] == "under")
    print(f"\n## 模型的方向偏好\n")
    print(f"- 已開打 **{len(played)}** 場中，模型偏好 **小分 {unders} 場、"
          f"大分 {len(played) - unders} 場**。")

    diffs = [r["pred"] - r["line"] for r in played]
    mean_diff = sum(diffs) / len(diffs)
    below = sum(1 for d in diffs if d < 0)
    print(f"- 模型預期總分 vs 市場等效盤口：平均 **{mean_diff:+.2f} 分**，"
          f"{below}/{len(diffs)} 場低於盤口。")

    act_err = [r["actual"] - r["pred"] for r in played]
    mean_err = sum(act_err) / len(act_err)
    print(f"- 實際總分 − 模型預期：平均 **{mean_err:+.2f} 分**"
          f"（正值代表模型系統性低估得分）。")

    act_line = [r["actual"] - r["line"] for r in played]
    print(f"- 實際總分 − 市場盤口：平均 **{sum(act_line) / len(act_line):+.2f} 分**"
          f"（市場自己的偏誤，作為對照）。")

    print("\n| 日期 | 比賽 | 模型 | 盤口 | 實際 | 模型−盤口 | 實際−模型 |")
    print("|---|---|---|---|---|---|---|")
    for r in played:
        print(f"| {r['date'][5:]} | {r['game']} | {r['pred']:.2f} | {r['line']:.3f} "
              f"| {r['actual']} | {r['pred'] - r['line']:+.2f} "
              f"| {r['actual'] - r['pred']:+.2f} |")

    # ---------- 解讀 ----------
    n = len(diffs)
    sd = (sum((e - mean_err) ** 2 for e in act_err) / n) ** 0.5
    se = sd / n ** 0.5
    print(f"\n## 這些數字代表什麼\n")
    print(f"- 「實際 − 模型」的標準差 {sd:.2f} 分，{n} 場的標準誤 {se:.2f} 分。"
          f"平均偏誤 {mean_err:+.2f} 分 = **{abs(mean_err) / se:.1f} 個標準誤**。")
    if abs(mean_err) < 2 * se:
        print("- 尚未達到 2 個標準誤，**還不能斷定模型有系統性低估**；"
              "但方向一致性（幾乎每場都押小分）值得繼續追蹤。")
    else:
        print("- 已超過 2 個標準誤，**模型系統性低估得分的證據已經成立**，"
              "應該回頭檢查 league_rpg、牛棚係數與先發收縮強度。")
    print("- 提醒: 這裡的球隊/球場係數是用含這些比賽在內的資料配適的，"
          "屬樣本內，真實誤差只會更大。")


if __name__ == "__main__":
    main()
