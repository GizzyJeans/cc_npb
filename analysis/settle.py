"""通用對帳: 把某一天的下注單與 npb.jp 實際比分結算。

執行: ``python3 -m analysis.settle 2026-08-14``

結算重用 `bethero.lines` —— 定價與對帳共用同一份結算規則，
避免兩邊各寫一套而悄悄分岐。
"""

from __future__ import annotations

import importlib
import sys
from fractions import Fraction

from bethero.lines import settle_handicap, settle_total

# date -> (slate module, {看板主隊: (主隊得分, 客隊得分) 或 None 表示中止},
#          {看板主隊: (選項, over/under, 注碼, 賠率, 狀態)})
LEDGER: dict[str, dict] = {
    "2026-08-13": {
        "module": "analysis.slate_2026_08_13",
        "as_of": "2026-08-14 15:43 JST",
        "finals": {
            "中日龍": (1, 5), "福岡軟銀鷹": (3, 4), "日本火腿": (8, 2),
            "東北樂天金鷲": (2, 8), "養樂多燕子": None, "讀賣巨人": (2, 3),
        },
        "positions": {
            "中日龍": ("小分 7+25", "under", 1000.0, 0.930, "推薦"),
            "讀賣巨人": ("大分 6.5", "over", 1000.0, 0.930, "推薦"),
            "東北樂天金鷲": ("大分 7平", "over", 0.0, 0.930, "觀察"),
            "養樂多燕子": ("小分 7-25", "under", 0.0, 0.930, "觀察"),
            "日本火腿": ("小分 8+75", "under", 0.0, 0.930, "不下注"),
            "福岡軟銀鷹": ("大分 8平", "over", 0.0, 0.930, "不下注"),
        },
    },
    "2026-08-14": {
        "module": "analysis.slate_2026_08_14",
        "as_of": "2026-08-15 12:30 JST",
        "finals": {
            "中日龍": (0, 1), "福岡軟銀鷹": (2, 5), "廣島鯉魚": (6, 1),
            "歐力士猛牛": (6, 2), "西武獅": (7, 0), "養樂多燕子": (7, 2),
        },
        "positions": {
            "西武獅": ("小分 7+50", "under", 1000.0, 0.930, "推薦"),
            "福岡軟銀鷹": ("小分 8+50", "under", 1000.0, 0.930, "推薦"),
            "養樂多燕子": ("小分 8+75", "under", 0.0, 0.930, "觀察"),
            "廣島鯉魚": ("大分 6.5", "over", 0.0, 0.930, "不下注"),
            "中日龍": ("小分 6-50", "under", 0.0, 0.930, "不下注"),
            "歐力士猛牛": ("大分 6.5", "over", 0.0, 0.930, "不下注"),
        },
    },
    "2026-08-15": {
        "module": "analysis.slate_2026_08_15",
        "as_of": "2026-08-15 22:55 JST（npb.jp 各場 box.html）",
        "finals": {
            "中日龍": (11, 2), "福岡軟銀鷹": (4, 6), "歐力士猛牛": (4, 12),
            "西武獅": (1, 5), "廣島鯉魚": (5, 2), "養樂多燕子": (4, 3),
        },
        "positions": {
            "中日龍": ("小分 7+50", "under", 1000.0, 0.930, "推薦"),
            "福岡軟銀鷹": ("小分 7.5", "under", 1000.0, 0.930, "推薦"),
            "西武獅": ("小分 6.5", "under", 1000.0, 0.930, "推薦"),
            "養樂多燕子": ("小分 8+25", "under", 0.0, 0.930, "觀察"),
            "廣島鯉魚": ("小分 7平", "under", 0.0, 0.930, "不下注"),
            "歐力士猛牛": ("小分 7+25", "under", 0.0, 0.930, "不下注"),
        },
    },
    "2026-08-16": {
        "module": "analysis.slate_2026_08_16",
        "as_of": "2026-08-17 13:00 JST（npb.jp 賽程頁）",
        "finals": {
            "西武獅": (7, 1), "廣島鯉魚": (1, 8), "養樂多燕子": (2, 1),
        },
        "positions": {
            "養樂多燕子": ("小分 8-75", "under", 1000.0, 0.930, "推薦"),
            "廣島鯉魚": ("小分 7-25", "under", 0.0, 0.930, "不下注"),
            "西武獅": ("小分 7+75", "under", 0.0, 0.930, "不下注"),
        },
    },
    "2026-08-18": {
        "module": "analysis.slate_2026_08_18",
        "as_of": "2026-08-19 13:00 JST（npb.jp 賽程頁）",
        "finals": {
            "橫濱DeNA灣星": (4, 3), "東北樂天金鷲": (6, 2), "西武獅": (7, 4),
            "廣島鯉魚": (11, 4), "阪神虎": (3, 2),
        },
        "positions": {
            "廣島鯉魚": ("小分 7+50", "under", 1000.0, 0.930, "推薦"),
            "橫濱DeNA灣星": ("小分 7.5", "under", 1000.0, 0.930, "推薦"),
            "阪神虎": ("小分 6+25", "under", 1000.0, 0.930, "推薦"),
            "西武獅": ("大分 6-50", "over", 0.0, 0.930, "觀察（超出單日上限）"),
            "東北樂天金鷲": ("小分 7.5", "under", 0.0, 0.930, "不下注"),
        },
    },
}


def payout(ratio: Fraction, stake: float, hk: float) -> float:
    r = float(ratio)
    return stake * (r * hk if r > 0 else r)


def run(date: str) -> None:
    spec = LEDGER[date]
    slate = importlib.import_module(spec["module"])
    finals, positions = spec["finals"], spec["positions"]

    print(f"# {date} 實際結果對帳　（結果擷取：{spec['as_of']}）\n")

    print("## 模型預期總分 vs 實際\n")
    print("| 比賽 | 模型預期 | 實際 | 誤差 |")
    print("|---|---|---|---|")
    errs, flats = [], []
    lg_total = 2 * __import__("config.calibration_2026", fromlist=["x"]).LEAGUE_RPG
    for game in slate.GAMES:
        pred = slate.build_model(game).distributions().expected_total()
        final = finals[game.home_team]
        if final is None:
            print(f"| {game.matchup} | {pred:.2f} | 中止 | — |")
            continue
        actual = sum(final)
        errs.append(abs(pred - actual))
        flats.append(abs(lg_total - actual))
        print(f"| {game.matchup} | {pred:.2f} | {actual} | {pred - actual:+.2f} |")
    print(f"\n已開打 {len(errs)} 場，模型平均絕對誤差 **{sum(errs) / len(errs):.2f} 分**，"
          f"「一律猜聯盟平均 {lg_total:.2f}」的基準線 {sum(flats) / len(flats):.2f} 分。"
          f"單場總分季內標準差 4.03 —— 這種樣本數不構成任何結論。\n")

    print("## 下注單結算\n")
    print("| 比賽 | 選項 | 狀態 | 注碼 | 實際總分 | 結算 | 損益 |")
    print("|---|---|---|---|---|---|---|")
    net = staked = 0.0
    for game in slate.GAMES:
        sel, side, stake, hk, status = positions[game.home_team]
        final = finals[game.home_team]
        if final is None:
            print(f"| {game.matchup} | {sel} | {status} | {stake:,.0f} | 中止 "
                  f"| 賽事取消、本金退回 | 0 |")
            continue
        total = sum(final)
        ratio = settle_total(game.total, total, side)
        pl = payout(ratio, stake, hk)
        net += pl
        staked += stake
        verdict = {1.0: "全贏", -1.0: "全輸", 0.0: "走盤"}.get(
            float(ratio), f"{float(ratio):+g} 比例結算")
        print(f"| {game.matchup} | {sel} | {status} | {stake:,.0f} | {total} "
              f"| {verdict} | {pl:+,.0f} |")
    print(f"\n**實際下注 {staked:,.0f} 單位，損益 {net:+,.0f}**"
          f"（本金 100,000，{net / 100000:+.2%}）\n")

    print("## 未下注選項的事後結果（僅供追蹤，不是漏失的獲利）\n")
    print("| 比賽 | 選項 | 狀態 | 假設 1,000 單位 |")
    print("|---|---|---|---|")
    for game in slate.GAMES:
        sel, side, stake, hk, status = positions[game.home_team]
        if stake > 0:
            continue
        final = finals[game.home_team]
        if final is None:
            print(f"| {game.matchup} | {sel} | {status} | 中止、退回 |")
            continue
        pl = payout(settle_total(game.total, sum(final), side), 1000.0, hk)
        print(f"| {game.matchup} | {sel} | {status} | {pl:+,.0f} |")

    print("\n## 讓分盤（刻意不定價）實際落點\n")
    print("| 比賽 | 盤口 | 讓分方 | 淨勝分 | 結算 |")
    print("|---|---|---|---|---|")
    for game in slate.GAMES:
        final = finals[game.home_team]
        fav = game.home_team if game.handicap_side == "home" else game.away_team
        if final is None:
            print(f"| {game.matchup} | {game.handicap_raw} | {fav} | 中止 | — |")
            continue
        hs, as_ = final
        margin = (hs - as_) if game.handicap_side == "home" else (as_ - hs)
        line = game.handicap
        ratio = settle_handicap(line, margin)
        note = "　← **落在關鍵分**" if margin == line.base else ""
        print(f"| {game.matchup} | {game.handicap_raw} | {fav} | {margin:+d} "
              f"| {float(ratio):+g}{note} |")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "2026-08-14")
