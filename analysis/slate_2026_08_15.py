"""2026-08-15 NPB 全六場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_08_15.py``

使用者先提供了 14:00 JST 三場的詳細頁 (含上半場盤)，稍後再提供
完整六場的列表看板。本檔以 **完整看板** 為準。

盤口在兩次截圖之間有移動 (見 `LINE_MOVES`) —— 這是目前唯一能拿到的
市場動向資訊。

這一版新增的東西
----------------
* `GameModel.partial_distributions()` —— 前 N 局的分布。上半場兩隊攻擊
  次數相同，不需要九局下的特殊處理，也沒有延長局。
* 以 307 場逐局比分測得 `F5_SHARE = 0.5710`。

結論仍然是只定價 **全場大小**。三個被排除的市場各有實測理由:

* 全場讓分: P(分差=±1) 高估 6-7pp，今日盤口 base 落在 1。
* 上半大小: P(上半總分>3) 高估 6.71pp，而三場的上半盤正好切在 3.5/4。
* 上半讓分: P(上半分差=0) 高估 5.04pp，而兩場的上半讓分結算在 0 分。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bethero.bankroll import Bankroll
from bethero.board import BoardGame
from bethero.ev import devig_proportional, evaluate
from bethero.gates import DataReadiness, grade
from bethero.lines import total_outcome_probs
from bethero.model import GameModel, NPBEnvironment, TeamInput
from bethero.report import DailyReport, GameAnalysis
from config import calibration_2026 as cal

DATE = "2026-08-15"
DATA_AS_OF = "2026-08-15 15:40 JST (UTC 06:40)"
START_JST = "14:00 JST（看板 13:00 為台北時間）"

GAMES = [
    BoardGame(
        date=DATE, start_time="14:00 JST（看板 13:00 台北）",
        away_team="讀賣巨人", home_team="中日龍",
        away_starter="竹丸和幸 (左)", home_starter="穆勒 (左)",
        venue="バンテリンドーム ナゴヤ (巨蛋)",
        handicap_raw="1+80", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7+50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-35", f5_total_raw="3.5",
    ),
    BoardGame(
        date=DATE, start_time="14:00 JST（看板 13:00 台北）",
        away_team="東北樂天金鷲", home_team="福岡軟銀鷹",
        away_starter="早川隆久 (左)", home_starter="上茶谷大河 (右)",
        venue="みずほPayPayドーム (巨蛋)",
        handicap_raw="1-75", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7.5", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0.5", f5_total_raw="4+50",
        attested_fields=frozenset({"total"}),
    ),
    BoardGame(
        date=DATE, start_time="14:00 JST（看板 13:00 台北）",
        away_team="日本火腿", home_team="歐力士猛牛",
        away_starter="加藤貴之 (左)", home_starter="寺西成騎 (右)",
        venue="京セラドーム大阪 (巨蛋)",
        handicap_raw="1-30", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7+25", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-90", f5_total_raw="3.5",
    ),
    BoardGame(
        date=DATE, start_time="17:00 JST（看板 16:00 台北）",
        away_team="千葉羅德", home_team="西武獅",
        away_starter="傑克森 (右)", home_starter="隅田知一郎 (左)",
        venue="ベルーナドーム (巨蛋)",
        handicap_raw="1+40", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6.5", over_hk=0.930, under_hk=0.930,
        attested_fields=frozenset({"total"}),
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="阪神虎", home_team="廣島鯉魚",
        away_starter="大竹耕太郎 (左)", home_starter="斉藤優汰 (右)",
        venue="マツダスタジアム (露天)",
        handicap_raw="1-30", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7平", over_hk=0.930, under_hk=0.930,
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="橫濱DeNA灣星", home_team="養樂多燕子",
        away_starter="篠木健太郎 (右)", home_starter="增居翔太 (左)",
        venue="明治神宮野球場 (露天)",
        handicap_raw="1+20", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="8+25", over_hk=0.930, under_hk=0.930,
    ),
]

JP = {
    "中日龍": "中日", "讀賣巨人": "巨人",
    "歐力士猛牛": "オリックス", "日本火腿": "日本ハム",
    "福岡軟銀鷹": "ソフトバンク", "東北樂天金鷲": "楽天",
    "西武獅": "西武", "千葉羅德": "ロッテ",
    "廣島鯉魚": "広島", "阪神虎": "阪神",
    "養樂多燕子": "ヤクルト", "橫濱DeNA灣星": "DeNA",
}
PARK_KEY = {
    "バンテリンドーム ナゴヤ (巨蛋)": "バンテリンドーム",
    "京セラドーム大阪 (巨蛋)": "京セラD大阪",
    "みずほPayPayドーム (巨蛋)": "みずほPayPay",
    "ベルーナドーム (巨蛋)": "ベルーナドーム",
    "マツダスタジアム (露天)": "マツダスタジアム",
    "明治神宮野球場 (露天)": "神宮",
}

OPEN_AIR = {"マツダスタジアム", "神宮"}

# 同一平台兩個時點的盤口差異 (12:00 前後的詳細頁 -> 13:10 的列表看板)。
# 這不是開盤價，但是目前唯一能取得的市場動向。
LINE_MOVES = {
    "中日龍": "讓分 1+70 → 1+80（中日讓得更多）；大小 7+50 未動",
    "福岡軟銀鷹": "未動（讓分 1-75、大小 7.5）",
    "歐力士猛牛": "讓分 1-25 → 1-30；大小 7+50 → 7+25"
                  "（等效由 6.75 升到 6.875，市場往大分方向修）",
    # 15:35 台北看板的第三個時點 —— 後三場只有讓分動，大小盤全數未動。
    "西武獅": "讓分 1+20 → 1+40（等效 0.90 → 0.80，西武讓得更少）；大小 6.5 未動",
    "廣島鯉魚": "讓分 1-20 → 1-30（等效 1.10 → 1.15，阪神讓得更多）；大小 7平 未動",
    "養樂多燕子": "讓分與大小皆未動（1+20／8+25）",
}

WEATHER = {
    "マツダスタジアム": "露天。**來源衝突**：廣島市 8/15 日級降水機率 60%、"
                       "全國有局部雷陣雨預警，但棒球專用的雨天中止預報被引述為"
                       "「中止機率 1%、降水機率 2%」。兩者差距過大且無法直接查證"
                       "（該站被出口政策擋下），依規範不採信任何一方",
    "神宮": "露天。同屬 8/15 局部雷陣雨預警範圍；神宮 8/13 已因雨中止過一次。"
            "逐時預報來源同樣無法直接查證",
}

# 今日先發 (npb.jp idp1_<team>.html, 2026-08-15 擷取)。
# is_opener: 季內單場平均局數 < 3 局 —— 實際用法是後援，今天等於開局投手。
STARTERS = {
    "中日": ("マラー", 0.9386, 6.33, "13 場 82.1 局 防禦率 2.73", False),
    "巨人": ("竹丸和幸", 1.0510, 5.88, "17 場 100 局 防禦率 3.33、107 三振", False),
    "オリックス": ("寺西成騎", 1.2359, 1.88, "26 場 49 局 防禦率 4.22", True),
    "日本ハム": ("加藤貴之", 0.9269, 5.67, "17 場 96.1 局 防禦率 2.71、僅 9 四球", False),
    "ソフトバンク": ("上茶谷大河", 0.8063, 2.00, "30 場 60 局 防禦率 1.95", True),
    "楽天": ("早川隆久", 0.8606, 6.67, "15 場 100 局 防禦率 2.79、103 三振", False),
    "西武": ("隅田知一郎", 0.9183, 7.06, "17 場 120 局 防禦率 2.55、每場 7.1 局", False),
    "ロッテ": ("ジャクソン", 0.9393, 6.18, "19 場 117.1 局 防禦率 3.22、42 四球", False),
    "広島": ("斉藤優汰", 1.0680, 4.73, "5 場 23.2 局 防禦率 4.18（樣本僅 23.2 局）", False),
    "阪神": ("大竹耕太郎", 1.0609, 5.90, "13 場 76.2 局 防禦率 2.82", False),
    "ヤクルト": ("増居翔太", 0.7903, 4.25, "4 場 17 局 防禦率 0.53（樣本僅 17 局，收縮後拉回甚多）", False),
    "DeNA": ("篠木健太郎", 1.1004, 5.70, "11 場 62.2 局 防禦率 4.45", False),
}

BULLPEN_NOTE = {
    "中日": "8/13 用 4 人、8/14 用 3 人（髙橋宏 112 球）；無連兩日登板",
    "巨人": "8/13 用 5 人、8/14 用 4 人（ハワード 81 球）；中川連兩日登板",
    "オリックス": "8/13 用 6 人、8/14 用 4 人（髙島 89 球）；入山、山﨑連兩日登板",
    "日本ハム": "8/13 用 5 人、8/14 用 3 人（達 102 球）；堀連兩日登板",
    "ソフトバンク": "8/13 用 4 人、8/14 用 3 人（大津 112 球）；無連兩日登板",
    "楽天": "8/13 用 5 人、8/14 用 5 人（藤井 84 球）；無連兩日登板",
    "西武": "8/13 用 5 人、8/14 用 **7 人**，佐藤隼、黒木、豆田三人連兩日登板 —— 牛棚負荷全聯盟最重",
    "ロッテ": "8/13 用 4 人、8/14 用 3 人（小島 93 球）；無連兩日登板",
    "広島": "8/13 因雨中止、8/14 只用 2 人（森下 113 球幾乎完投）—— 牛棚極為充足",
    "阪神": "8/13 用 4 人、8/14 用 4 人（才木僅 54 球即退場、門別 30 球）",
    "ヤクルト": "8/13 因雨中止、8/14 用 4 人（奥川 110 球）",
    "DeNA": "8/13 用 4 人、8/14 用 4 人（平良 93 球）",
}

ENV = NPBEnvironment(
    league_rpg=cal.LEAGUE_RPG,
    dispersion_k=cal.DISPERSION_K,
    home_edge=cal.HOME_EDGE,
    extras_resolve_rate=cal.EXTRAS_RESOLVE_RATE,
    source="npb.jp 2026 逐場比分 629 場",
    as_of=cal.AS_OF,
)


def build_model(game: BoardGame) -> GameModel:
    def side(team: str) -> TeamInput:
        _, factor, ip_gs, _, _ = STARTERS[team]
        return TeamInput(
            name=team,
            off_factor=cal.TEAM_OFFENCE[team],
            def_factor=cal.blended_defence(factor, ip_gs, cal.BULLPEN_FACTOR[team]),
            starter_ip=ip_gs,
        )

    return GameModel(home=side(JP[game.home_team]), away=side(JP[game.away_team]),
                     env=ENV, park_factor=cal.PARK_FACTORS_2026[PARK_KEY[game.venue]])


def has_opener(game: BoardGame) -> bool:
    return STARTERS[JP[game.home_team]][4] or STARTERS[JP[game.away_team]][4]


def stress_season_defence(game: BoardGame) -> GameModel:
    """壓力測試: 開局投手的球隊改用季內守備係數。

    模型把開局投手當成「先發」，用他後援等級的失分率去算，結果反而讓
    該隊今天看起來 **比平常強**（軟銀 0.825 vs 季內 0.938）。但實測
    開局投手的比賽是多得分的。這個反向誤差必須量化，不能只註記。
    """
    def side(team: str) -> TeamInput:
        _, factor, ip_gs, _, is_opener = STARTERS[team]
        dfn = (cal.TEAM_DEFENCE_SEASON[team] if is_opener
               else cal.blended_defence(factor, ip_gs, cal.BULLPEN_FACTOR[team]))
        return TeamInput(team, cal.TEAM_OFFENCE[team], dfn, ip_gs)

    return GameModel(home=side(JP[game.home_team]), away=side(JP[game.away_team]),
                     env=ENV, park_factor=cal.PARK_FACTORS_2026[PARK_KEY[game.venue]])


def readiness_for(game: BoardGame) -> DataReadiness:
    return DataReadiness(
        # 只問要下的那個盤: 本日只定價全場大小。上半盤的裸小數寫法仍會
        # 在報告的「盤口待確認」揭露，但它擋不到另一個獨立的盤口。
        line_type_confirmed=not game.audit_for("total"),
        starters_confirmed=True,
        lineups_confirmed=False,
        waived=frozenset({"lineups_confirmed"}),
        prices_verified=True,
        bullpen_usage_known=True,
        team_rates_known=True,
        park_factor_known=True,
        weather_known=PARK_KEY[game.venue] not in OPEN_AIR,
        injuries_known=False,
        market_prices_known=False,
    )


def build_report() -> DailyReport:
    analyses = []
    for game in GAMES:
        home, away = JP[game.home_team], JP[game.away_team]
        model = build_model(game)
        dists = model.distributions()
        f5 = model.partial_distributions(cal.F5_SHARE)
        readiness = readiness_for(game)

        market = devig_proportional([game.over_hk, game.under_hk])
        over = evaluate(total_outcome_probs(game.total, dists.total_pmf, "over"),
                        game.over_hk, Bankroll().total, market[0])
        under = evaluate(total_outcome_probs(game.total, dists.total_pmf, "under"),
                         game.under_hk, Bankroll().total, market[1])
        best, label = (over, "大分") if over.ev >= under.ev else (under, "小分")
        graded = grade(ev=best.ev, edge_pp=best.edge_pp, readiness=readiness)

        sp_h, sp_a = STARTERS[home], STARTERS[away]
        opener_bits = [f"{n} 為開局投手（季內每場僅 {ip:.1f} 局）"
                       for n, _, ip, _, is_op in (sp_h, sp_a) if is_op]

        risks = [
            "全場讓分：模型 P(分差=±1) 高估 6-7pp，今日盤口 base 落在 1，不定價",
            "上半場盤：模型 P(上半總分>3) 高估 6.71pp、P(上半分差=0) 高估 5.04pp，"
            "而看板的上半盤正切在這些點上，不定價",
        ]
        if opener_bits:
            s_d = stress_season_defence(game).distributions()
            s_ev = evaluate(
                total_outcome_probs(game.total, s_d.total_pmf,
                                    "over" if label == "大分" else "under"),
                game.over_hk, Bankroll().total, market[0]).ev
            risks.append(
                "；".join(opener_bits)
                + "。實測開局投手的比賽上半場多 1.22 分（5.02 vs 3.80）、"
                  "全場多 0.54 分。更麻煩的是模型把開局投手當先發、用他"
                  "後援等級的失分率去算，反而讓該隊看起來比平常強 —— "
                  f"誤差方向與這個實測效果相反。壓力測試：開局隊改用季內"
                  f"守備係數後預期總分 {s_d.expected_total():.2f}"
                  f"（原 {dists.expected_total():.2f}）、{label} EV "
                  f"{s_ev:+.1%}（原 {best.ev:+.1%}）"
            )

        analyses.append(GameAnalysis(
            game=game,
            readiness=readiness,
            selection=f"{label} {game.total_raw}",
            line_label=f"讓分 {game.handicap_raw}／大小 {game.total_raw}",
            evaluation=best,
            graded=graded,
            dists=dists,
            pitching_note=(
                f"{game.away_starter} {sp_a[3]}／{game.home_starter} {sp_h[3]}。"
                f"當日守備係數 主 {model.home.def_factor:.3f}、客 {model.away.def_factor:.3f}"
                + ("　⚠️ " + "、".join(opener_bits) if opener_bits else "")
            ),
            lineup_note="12:40 JST 尚未公布，依使用者指示略過",
            bullpen_note=f"{game.home_team}：{BULLPEN_NOTE[home]}；"
                         f"{game.away_team}：{BULLPEN_NOTE[away]}",
            park_weather_note=(
                f"球場係數 {cal.PARK_FACTORS_2026[PARK_KEY[game.venue]]:.3f}（2026 實測）。"
                + WEATHER.get(PARK_KEY[game.venue], "巨蛋，天氣不影響")
            ),
            market_note=(
                "賠率已由看板截圖確認。"
                + (f"上半盤 {game.f5_handicap_raw}／{game.f5_total_raw} 已記錄但不定價；"
                   if game.f5_total_raw else "")
                + "盤口移動：" + LINE_MOVES.get(game.home_team, "無第二個時點可比對")
            ),
            rationale=(
                f"模型預期總分 {dists.expected_total():.2f}"
                f"（{home} {dists.lam_home:.2f} - {away} {dists.lam_away:.2f}）、"
                f"上半 {f5.expected_total():.2f}；"
                f"{label} 模型機率 {best.model_prob:.1%}、EV {best.ev:+.1%}"
            ),
            risks=risks,
            cancel_conditions=["正式打線公布後若主力輪休須重算", "先發臨時更換即作廢"]
            + (["露天球場，達延賽標準即取消"]
               if PARK_KEY[game.venue] in OPEN_AIR else []),
        ))

    return DailyReport(
        date=DATE,
        bankroll=Bankroll(),
        analyses=analyses,
        data_as_of=DATA_AS_OF,
        global_notes=[
            "本報告只涵蓋使用者提供看板的三場 14:00 JST 賽事；"
            "另外三場（神宮 18:00、マツダ 18:00、ベルーナ 17:00）未提供盤口，未分析。",
            "校準已更新到 8/14 收盤（629 場）。三場皆為巨蛋，天氣不影響。",
            "六名先發已對照 npb.jp 預告先發公示全名核對一致。",
            "**新增上半場模型**：以 307 場逐局比分測得前 5 局佔全場得分 "
            "57.10%（高於 5/9=55.6%，因為主隊九局下常常不必打）。",
            "**但上半場盤仍不定價**：模型 P(上半總分>3) 為 53.61% vs 實測 "
            "46.91%（高估 6.71pp），P(上半分差=0) 為 21.65% vs 實測 16.61%"
            "（高估 5.04pp）。三場的上半大小切在 3.5／3.5／4+50，兩場的上半讓分"
            "結算在 0 分 —— 全部踩在偏誤最大的點上。",
            "**兩場有開局投手**：軟銀 上茶谷大河（30 場 60 局）與 歐力士 寺西成騎"
            "（26 場 49 局）季內都是後援用法，快取的逐場資料顯示兩人歷次登板都是"
            "第 2-8 任投手、投 6-26 球。實測「計畫性開局投手」的比賽上半場多 "
            "1.22 分而全場只多 0.54 分。",
            "注意不要用「先發實際投不到 3 局」估開局投手效果 —— 那是被打爆的結果"
            "而非原因，會算出 10.11 分的假效果（選擇偏誤）。",
            "本次為第三個盤口時點（台北 15:35）。後三場 **大小盤全數未動**，"
            "只有西武與廣島兩場的讓分移動，因此大小分的定價結論與前一版相同。",
            "14:00 JST 三場（中日、軟銀、歐力士）在本報告產出時已開打，"
            "其定價僅供事後對帳，不再是可下注的建議。",
            "露天兩場的天氣來源互相衝突（日級 60% vs 球場級 1-2%）且都無法直接"
            "查證，依 AGENT.md「來源衝突只能標示為觀察」處理 —— "
            "養樂多那場的 +10.3% EV 因此仍不轉為推薦。",
        ],
        sources=[
            "https://npb.jp/announcement/starter/（2026-08-15 預告先發公示）",
            "https://npb.jp/games/2026/schedule_08_detail.html（賽程與 8/14 比分）",
            "https://npb.jp/bis/2026/stats/idp1_<team>.html（個人投手成績）",
            "https://npb.jp/scores/2026/<date>/<slug>/box.html（逐局比分 307 場、"
            "牛棚用球數、先發實際局數）",
            "賠率：使用者提供之看板截圖（2026-08-15）",
        ],
    )


if __name__ == "__main__":
    print(build_report().render())
