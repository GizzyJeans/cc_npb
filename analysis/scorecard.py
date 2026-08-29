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
            park = slate.PARK_KEY[game.venue]
            rows.append({
                "date": date, "game": game.matchup, "side": side,
                "stake": stake, "hk": hk, "status": status,
                "pred": pred, "line": line,
                "open_air": park in getattr(slate, "OPEN_AIR", set()),
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

    # ---------- 水位偏誤 vs 選擇偏誤 ----------
    # 「模型整體低估得分」和「模型與市場分歧的那些場次剛好是模型錯的」
    # 是兩件事，補救方式完全不同: 前者調 league_rpg，後者調 league_rpg
    # 完全無效。用「已下注 vs 未下注」切開 —— 未下注的場次是對照組，
    # 它們的偏誤才是乾淨的水位訊號。
    print("\n## 水位偏誤 vs 選擇偏誤\n")
    print("| 分組 | 場數 | 實際−模型 | 標準誤 | 實際−盤口 |")
    print("|---|---|---|---|---|")
    split = {}
    for label, want in (("已下注", True), ("未下注", False)):
        grp = [r for r in played if (r["stake"] > 0) is want]
        split[label] = grp
        if not grp:
            continue
        e = [r["actual"] - r["pred"] for r in grp]
        el = [r["actual"] - r["line"] for r in grp]
        mean = sum(e) / len(e)
        sd = (sum((x - mean) ** 2 for x in e) / len(e)) ** 0.5
        print(f"| {label} | {len(grp)} | {mean:+.2f} | {sd / len(e) ** 0.5:.2f} "
              f"| {sum(el) / len(el):+.2f} |")

    on, off = split.get("已下注", []), split.get("未下注", [])
    if len(on) > 1 and len(off) > 1:
        eon = [r["actual"] - r["pred"] for r in on]
        eoff = [r["actual"] - r["pred"] for r in off]
        mon, moff = sum(eon) / len(eon), sum(eoff) / len(eoff)
        von = sum((x - mon) ** 2 for x in eon) / (len(eon) - 1)
        voff = sum((x - moff) ** 2 for x in eoff) / (len(eoff) - 1)
        se = (von / len(eon) + voff / len(eoff)) ** 0.5
        n_se = abs(mon - moff) / se if se else 0.0
        print(f"\n- 已下注 − 未下注 的偏誤差距 **{mon - moff:+.2f} 分**，"
              f"標準誤 {se:.2f} → **{n_se:.1f} 個標準誤**。")
        off_line = sum(r["actual"] - r["line"] for r in off) / len(off)
        print(f"- **未下注場次是乾淨的對照組**：它們的「實際 − 盤口」"
              f"平均 {off_line:+.2f} 分。")
        if abs(off_line) < 0.3:
            print("  - 接近零，代表 **聯盟得分水位沒有問題**；"
                  "調 `league_rpg` 救不了已下注場次的偏誤。")
        if n_se >= 2:
            print("- 已達 2 個標準誤：**這是選擇問題**。該查的是"
                  "「模型在哪些情境下最容易與市場分歧且分歧方向是錯的」，"
                  "不是得分水位。")
        else:
            print("- 尚未達 2 個標準誤，還不能斷定是選擇問題，但方向值得追蹤。")

    print("\n| 模型方向 | 場數 | 實際−模型 | 實際−盤口 |")
    print("|---|---|---|---|")
    for side, label in (("under", "押小分"), ("over", "押大分")):
        grp = [r for r in played if r["side"] == side]
        if not grp:
            continue
        e = [r["actual"] - r["pred"] for r in grp]
        el = [r["actual"] - r["line"] for r in grp]
        print(f"| {label} | {len(grp)} | {sum(e) / len(e):+.2f} "
              f"| {sum(el) / len(el):+.2f} |")

    # ---------- 露天 vs 巨蛋 ----------
    # +7% 的露天 EV 門檻是用來補償「拿不到當日天氣」的。這個門檻的高度
    # 只有在露天的誤差真的比較大時才站得住，所以要持續追蹤，不能只在
    # 露天場出現大失誤的那天才臨時查一次。
    print("\n## 露天 vs 巨蛋（露天 EV 門檻 +7% 的依據）\n")
    print("| 球場類型 | 場數 | 平均誤差 | 平均絕對誤差 | 標準誤 |")
    print("|---|---|---|---|---|")
    groups = {}
    for label, want in (("露天", True), ("巨蛋", False)):
        grp = [r for r in played if r["open_air"] is want]
        groups[label] = grp
        if not grp:
            continue
        e = [r["actual"] - r["pred"] for r in grp]
        mean = sum(e) / len(e)
        sd = (sum((x - mean) ** 2 for x in e) / len(e)) ** 0.5
        print(f"| {label} | {len(grp)} | {mean:+.2f} | "
              f"{sum(abs(x) for x in e) / len(e):.2f} | {sd / len(e) ** 0.5:.2f} |")

    o, d = groups.get("露天", []), groups.get("巨蛋", [])
    if len(o) > 1 and len(d) > 1:
        eo = [r["actual"] - r["pred"] for r in o]
        ed = [r["actual"] - r["pred"] for r in d]
        mo, md = sum(eo) / len(eo), sum(ed) / len(ed)
        vo = sum((x - mo) ** 2 for x in eo) / (len(eo) - 1)
        vd = sum((x - md) ** 2 for x in ed) / (len(ed) - 1)
        se = (vo / len(eo) + vd / len(ed)) ** 0.5
        n_se = abs(mo - md) / se if se else 0.0
        print(f"\n- 露天 − 巨蛋 的平均誤差差距 **{mo - md:+.2f} 分**，"
              f"標準誤 {se:.2f} → **{n_se:.1f} 個標準誤**。")
        print("- " + ("**尚無證據**顯示露天的模型誤差比較大。露天場出現大失誤時，"
                     "預設解釋是單場變異（總分標準差 4.03），不是球場類型。"
                     if n_se < 2 else
                     "**已超過 2 個標準誤**，露天的模型誤差確實較大，"
                     "應重新檢討 +7% 門檻的高度。"))

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
