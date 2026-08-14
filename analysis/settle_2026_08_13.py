"""2026-08-13 實際結果對帳。

執行: ``python3 analysis/settle_2026_08_13.py``

結算刻意重用 `bethero.lines` —— 也就是當初定價用的同一份結算規則，
避免「定價一套、對帳另一套」。比分取自 npb.jp 賽程頁 2026-08-14 擷取。
"""

from __future__ import annotations

import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bethero.lines import parse_board_line, settle_handicap, settle_total
from analysis.slate_2026_08_13 import GAMES, build_model
from config.calibration_2026 import OBSERVED

cal_mean = OBSERVED["平均總分"]

RESULTS_AS_OF = "2026-08-14 15:43 JST（npb.jp 賽程頁）"

# npb.jp 2026-08-13 最終比分 (主隊, 客隊)；None = 中止
FINALS: dict[str, tuple[int, int] | None] = {
    "中日龍": (1, 5),          # 中日 1 - 5 DeNA
    "福岡軟銀鷹": (3, 4),        # ソフトバンク 3 - 4 ロッテ
    "日本火腿": (8, 2),         # 日本ハム 8 - 2 西武
    "東北樂天金鷲": (2, 8),       # 楽天 2 - 8 オリックス
    "養樂多燕子": None,          # ヤクルト - 広島 中止（雨）
    "讀賣巨人": (2, 3),         # 巨人 2 - 3 阪神
}

# 當時報告的下注單: 比賽 -> (選項, 方向, 注碼, 賠率, 狀態)
POSITIONS = {
    "中日龍": ("小分 7+25", "under", 1000.0, 0.930, "推薦"),
    "讀賣巨人": ("大分 6.5", "over", 1000.0, 0.930, "推薦"),
    "東北樂天金鷲": ("大分 7平", "over", 0.0, 0.930, "觀察"),
    "養樂多燕子": ("小分 7-25", "under", 0.0, 0.930, "觀察"),
    "日本火腿": ("小分 8+75", "under", 0.0, 0.930, "不下注"),
    "福岡軟銀鷹": ("大分 8平", "over", 0.0, 0.930, "不下注"),
}


def payout(ratio: Fraction, stake: float, hk: float) -> float:
    """把結算比例換成損益。正比例按賠率收，負比例賠本金。"""
    r = float(ratio)
    return stake * (r * hk if r > 0 else r)


def main() -> None:
    print(f"# 2026-08-13 實際結果對帳　（結果擷取：{RESULTS_AS_OF}）\n")

    print("## 模型預期總分 vs 實際\n")
    print("| 比賽 | 模型預期 | 實際 | 誤差 |")
    print("|---|---|---|---|")
    errs, played = [], 0
    for game in GAMES:
        final = FINALS[game.home_team]
        dists = build_model(game).distributions()
        pred = dists.expected_total()
        if final is None:
            print(f"| {game.matchup} | {pred:.2f} | 中止 | — |")
            continue
        actual = sum(final)
        errs.append(abs(pred - actual))
        played += 1
        print(f"| {game.matchup} | {pred:.2f} | {actual} | {pred - actual:+.2f} |")
    flat = [abs(cal_mean - sum(FINALS[g.home_team]))
            for g in GAMES if FINALS[g.home_team] is not None]
    print(f"\n已開打 {played} 場，模型平均絕對誤差 **{sum(errs) / len(errs):.2f} 分**，"
          f"「一律猜聯盟平均 {cal_mean:.2f} 分」的基準線為 {sum(flat) / len(flat):.2f} 分。"
          f"單場總分的季內標準差是 4.05，五場的樣本完全無法區分兩者 —— "
          f"這一欄不構成任何模型有效或無效的證據。\n")

    print("## 下注單結算\n")
    print("| 比賽 | 選項 | 狀態 | 注碼 | 實際總分 | 結算 | 損益 |")
    print("|---|---|---|---|---|---|---|")
    net = 0.0
    for game in GAMES:
        sel, side, stake, hk, status = POSITIONS[game.home_team]
        final = FINALS[game.home_team]
        if final is None:
            print(f"| {game.matchup} | {sel} | {status} | {stake:,.0f} | 中止 "
                  f"| 賽事取消、本金退回 | 0 |")
            continue
        total = sum(final)
        ratio = settle_total(game.total, total, side)
        pl = payout(ratio, stake, hk)
        net += pl
        verdict = {1: "全贏", -1: "全輸"}.get(
            float(ratio), f"{float(ratio):+g} 比例結算")
        print(f"| {game.matchup} | {sel} | {status} | {stake:,.0f} | {total} "
              f"| {verdict} | {pl:+,.0f} |")
    print(f"\n**實際下注損益：{net:+,.0f} 單位**"
          f"（本金 100,000，{net / 100000:+.2%}）\n")

    print("## 讓分盤（當日刻意不定價）實際落點\n")
    print("| 比賽 | 盤口 | 讓分方 | 讓分方淨勝分 | 結算 |")
    print("|---|---|---|---|---|")
    for game in GAMES:
        final = FINALS[game.home_team]
        line = parse_board_line(game.handicap_raw)
        fav = game.home_team if game.handicap_side == "home" else game.away_team
        if final is None:
            print(f"| {game.matchup} | {game.handicap_raw} | {fav} | 中止 | — |")
            continue
        hs, as_ = final
        margin = (hs - as_) if game.handicap_side == "home" else (as_ - hs)
        ratio = settle_handicap(line, margin)
        note = ""
        if margin == line.base:
            note = "　← **正好落在關鍵分**"
        print(f"| {game.matchup} | {game.handicap_raw} | {fav} | {margin:+d} "
              f"| {float(ratio):+g}{note} |")

    print("\n## 門檻表現\n")
    hits = 0
    for game in GAMES:
        sel, side, stake, hk, status = POSITIONS[game.home_team]
        final = FINALS[game.home_team]
        if final is None:
            continue
        ratio = settle_total(game.total, sum(final), side)
        if float(ratio) > 0:
            hits += 1
    print(f"- 模型偏好的方向在已開打的 {played} 場中命中 **{hits} 場**。"
          f"n={played}，這個比例沒有統計意義，不要拿它調模型。")
    print("- 兩筆「不下注」都擋掉了輸盤：軟銀大分 8平（實際 7，輸）、"
          "日本火腿小分 8+75（實際 10，輸）。兩者都是卡在 EV 未達 +4%。")
    print("- 天氣門檻擋下的養樂多小分，該場確實因雨中止 —— "
          "延賽會退回本金，所以門檻沒有省下金錢，但理由是對的。")
    print("- 同樣被天氣擋下的樂天大分 7平（實際 10）會贏 +930。"
          "門檻這次的代價是漏掉一注贏盤，這是不對稱風控的必然成本。")
    print("- 讓分盤不定價的決定：阪神 1+95 這場 **正好落在淨勝 1 分**，"
          "也就是模型 P(分差=+1) 高估 5.96pp 的那一點。已開打 5 場有 1 場"
          "落在關鍵整數上，與實測 29.1% 的一分差比例一致。")


if __name__ == "__main__":
    main()
