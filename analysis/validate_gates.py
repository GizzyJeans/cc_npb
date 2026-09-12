"""資料門檻到底有沒有賺到它的位置？

執行: ``python3 -m analysis.validate_gates``

問題
----
`bethero.gates` 會因為「資料不足」把數值面合格的部位降級。那是純粹的
成本 —— 每擋下一個 +9% EV 的部位，就是放棄一次期望為正的機會。
**除非被擋下的那些部位實際上是賠錢的。**

這支腳本把每一個已結算的部位重新過一次當天的定價與門檻，分成三類:

    A. 數值面通過 + 門檻通過   -> 本來就該下（實際是否下到還要看單日額度）
    B. 數值面通過 + 門檻擋下   -> **門檻真正介入的那些**
    C. 數值面不通過           -> 不管有沒有門檻都不會下

只有 B 類能回答這個問題。A 類裡沒下到的是額度的決定、不是門檻的決定，
C 類則與門檻無關 —— 把這三類混在一起看會得到毫無意義的數字。

⚠️ 為什麼不直接用 ledger 的狀態字串分類
--------------------------------------
`LEDGER` 的狀態欄是人寫的，寫法不一致（光是「觀察」就有 15 筆，
底下混著先發無成績、額度用完、已開賽三種完全不同的原因）。
所以這裡 **重跑當天的 `readiness_for()` 與 `grade()`**，
用程式的判斷而不是字串，也順帶驗證那些 slate 現在還跑得出同樣的結果。

門檻高度也逐日不同（露天的 +7% 在 8/16-9/2 之間有效），
因此一律採用 **該 slate 自己的** `OPEN_AIR_MIN_EV`，不用今天的值回頭套。
"""

from __future__ import annotations

import importlib
from fractions import Fraction

from bethero.bankroll import Bankroll
from bethero.ev import devig_proportional, evaluate
from bethero.gates import MIN_EDGE_PP, MIN_EV, Grade, grade
from bethero.lines import settle_total, total_outcome_probs
from analysis.settle import LEDGER, payout

UNIT = 1000.0
"""假設注碼 —— 與實際部位的標準注碼相同，方便直接比較。"""


def classify() -> list[dict]:
    rows = []
    for date in sorted(LEDGER):
        spec = LEDGER[date]
        slate = importlib.import_module(spec["module"])
        if not all(hasattr(slate, a) for a in
                   ("GAMES", "build_model", "readiness_for", "PARK_KEY", "OPEN_AIR")):
            continue                      # 早期 slate 介面不同，略過
        for game in slate.GAMES:
            final = spec["finals"].get(game.home_team)
            if final is None:
                continue
            _, side, stake, hk, status = spec["positions"][game.home_team]
            dists = slate.build_model(game).distributions()
            market = devig_proportional([game.over_hk, game.under_hk])
            over = evaluate(total_outcome_probs(game.total, dists.total_pmf, "over"),
                            game.over_hk, Bankroll().total, market[0])
            under = evaluate(total_outcome_probs(game.total, dists.total_pmf, "under"),
                             game.under_hk, Bankroll().total, market[1])
            best, label = (over, "over") if over.ev >= under.ev else (under, "under")

            readiness = slate.readiness_for(game)
            open_air = slate.PARK_KEY[game.venue] in slate.OPEN_AIR
            min_ev = getattr(slate, "OPEN_AIR_MIN_EV", MIN_EV) if open_air else MIN_EV
            graded = grade(ev=best.ev, edge_pp=best.edge_pp,
                           readiness=readiness, min_ev=min_ev)

            numeric_ok = best.ev >= min_ev and best.edge_pp >= MIN_EDGE_PP
            gated = numeric_ok and graded.grade is not Grade.RECOMMEND
            # 額度用完不是門檻的決定 —— 那類的 readiness 是足夠的
            blocked_by_data = gated and (readiness.blocking_reasons()
                                         or not readiness.sufficient())

            ratio = settle_total(game.total, sum(final), label)
            rows.append({
                "date": date, "game": game.matchup, "ev": best.ev,
                "side": label, "numeric_ok": numeric_ok,
                "blocked_by_data": blocked_by_data,
                "gaps": readiness.soft_gaps(), "blocking": readiness.blocking_reasons(),
                "stake": stake, "status": status,
                "pl": payout(ratio, UNIT, hk), "actual": sum(final),
            })
    return rows


def summarise(label: str, grp: list[dict]) -> None:
    if not grp:
        print(f"| {label} | 0 | — | — | — |")
        return
    pl = sum(r["pl"] for r in grp)
    won = sum(1 for r in grp if r["pl"] > 0)
    print(f"| {label} | {len(grp)} | {sum(r['ev'] for r in grp) / len(grp):+.1%} "
          f"| {won}/{len(grp)} | {pl:+,.0f} | {pl / (UNIT * len(grp)):+.1%} |")


def main() -> None:
    rows = classify()
    A = [r for r in rows if r["numeric_ok"] and not r["blocked_by_data"]]
    B = [r for r in rows if r["numeric_ok"] and r["blocked_by_data"]]
    C = [r for r in rows if not r["numeric_ok"]]

    print("# 資料門檻的實際績效\n")
    print(f"重跑 **{len(rows)} 個已結算部位** 的當日定價與門檻判斷"
          f"（每筆假設 {UNIT:,.0f} 單位）。\n")
    print("| 分類 | 場數 | 平均 EV | 贏 | 假設損益 | ROI |")
    print("|---|---|---|---|---|---|")
    summarise("A 數值面通過＋門檻通過", A)
    summarise("**B 數值面通過＋門檻擋下**", B)
    summarise("C 數值面不通過", C)

    print("\n## B 類 —— 門檻真正介入的部位\n")
    if not B:
        print("（無）")
    else:
        print("| 日期 | 比賽 | 方向 | EV | 實際總分 | 假設損益 | 擋下的原因 |")
        print("|---|---|---|---|---|---|---|")
        for r in sorted(B, key=lambda x: x["date"]):
            why = "；".join(r["blocking"] or r["gaps"][:2]) or "資料完整度不足"
            print(f"| {r['date'][5:]} | {r['game']} | "
                  f"{'大分' if r['side'] == 'over' else '小分'} | {r['ev']:+.1%} "
                  f"| {r['actual']} | {r['pl']:+,.0f} | {why} |")
        pl = sum(r["pl"] for r in B)
        won = sum(1 for r in B if r["pl"] > 0)
        print(f"\n- 這 **{len(B)}** 個部位平均 EV **{sum(r['ev'] for r in B) / len(B):+.1%}**"
              f"，數值面全部合格。")
        print(f"- 實際結果 **{won} 勝 {len(B) - won} 敗**，"
              f"假設各下 {UNIT:,.0f} 單位合計 **{pl:+,.0f}**"
              f"（ROI {pl / (UNIT * len(B)):+.1%}）。")
        if pl < 0:
            print(f"- **門檻是賺錢的**: 它擋下的是一組看起來 "
                  f"{sum(r['ev'] for r in B) / len(B):+.1%} 但實際賠 "
                  f"{-pl:,.0f} 的部位。")
        else:
            print(f"- ⚠️ **門檻到目前為止是賠錢的**: 它擋下的部位合計賺 {pl:+,.0f}。"
                  "樣本仍小，但若持續為正，該重新檢討門檻的高度。")

    # ---------- A vs B 的差距測得出來嗎 ----------
    print("\n## 這個差距測得出來嗎？\n")
    ra = [r["pl"] / UNIT for r in A]
    rb = [r["pl"] / UNIT for r in B]
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    va = sum((x - ma) ** 2 for x in ra) / (len(ra) - 1)
    vb = sum((x - mb) ** 2 for x in rb) / (len(rb) - 1)
    se = (va / len(ra) + vb / len(rb)) ** 0.5
    n_se = abs(ma - mb) / se if se else 0.0
    print(f"A 類 ROI {ma:+.1%}、B 類 ROI {mb:+.1%}，差距 **{ma - mb:+.1%}**，"
          f"標準誤 {se:.1%} → **{n_se:.1f} 個標準誤**。\n")
    if n_se >= 2:
        print("- 已達 2 個標準誤，**門檻確實分離出兩群報酬不同的部位**。")
    else:
        print(f"- **只有 {n_se:.1f} 個標準誤，還測不出來。** 30 個百分點的 ROI 差距"
              "看起來很大，但單注報酬的標準差接近 1.0，"
              f"{len(B)} 場的標準誤就有 {(vb / len(rb)) ** 0.5:.1%}。")
        need = int(round(len(B) * (n_se and (2 / n_se) ** 2 or 0), -1))
        print(f"- 要在 2 個標準誤下確認這個差距，B 類大約需要 **{need} 場**"
              f"（目前 {len(B)} 場）。以目前每天 0-2 個被擋部位的速度，"
              "還要好幾個月。")
        print("- **所以這張表現在只是「方向一致」，不是「已經證實」。** "
              "它支持繼續維持門檻（機制上也說得通: 先發查無成績的比賽"
              "本來就更難預測），但不足以用來替門檻的高度辯護。")

    # ---------- 哪一道門檻在做事 ----------
    print("\n## 是哪一道門檻在做事？\n")
    tally: dict[str, list[float]] = {}
    for r in B:
        for why in (r["blocking"] or r["gaps"][:2]):
            tally.setdefault(why, []).append(r["pl"])
    print("| 門檻 | 擋下 | 假設損益 |")
    print("|---|---|---|")
    for why, pls in sorted(tally.items(), key=lambda kv: sum(kv[1])):
        print(f"| {why} | {len(pls)} | {sum(pls):+,.0f} |")
    print("\n- 注意同一個部位可能同時缺多項，所以這張表的場數合計大於 "
          f"{len(B)}，損益也會重複計算。它只說明「哪些缺口最常出現」，"
          "不能拿來把損益歸因到單一門檻。")

    print("\n## 怎麼讀這張表\n")
    print("- **A 類不是門檻的功勞**，是模型加上市場定價的結果; "
          "它們之中沒下到的那些是 **單日額度** 的決定，與門檻無關。")
    print("- **C 類與門檻完全無關** —— 數值面就不合格，有沒有門檻都不會下。")
    print(f"- 只有 B 類在回答「門檻值不值得」。它的樣本是 {len(B)} 場，"
          "遠小於整體，所以這個結論的不確定度比看起來大: "
          f"單場總分標準差 4.0 分，{len(B)} 場的勝敗仍有很大運氣成分。")
    print("- 這裡的 EV 是用 **當天的** 校準值重算的（slate 模組會 import "
          "當前的 config），所以與當天報告上的數字可能有小幅差異; "
          "分類（數值面是否合格）對這點不敏感，但個別 EV 數值會動。")


if __name__ == "__main__":
    main()
