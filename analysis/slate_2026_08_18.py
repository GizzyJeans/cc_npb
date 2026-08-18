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
from bethero.gates import Grade
from bethero.report import DailyReport, GameAnalysis
from config import calibration_2026 as cal

DATE = "2026-08-18"
DATA_AS_OF = "2026-08-18 16:15 JST (UTC 07:15)"
START_JST = "14:00 JST（看板 13:00 為台北時間）"

GAMES = [
    BoardGame(
        date=DATE, start_time="17:45 JST（看板 16:45 台北）",
        away_team="讀賣巨人", home_team="橫濱DeNA灣星",
        away_starter="山﨑伊織 (右)", home_starter="尾形崇斗 (右)",
        venue="横浜スタジアム (露天)",
        handicap_raw="1+80", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7.5", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-25", f5_total_raw="4平",
        attested_fields=frozenset({"total"}),
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="千葉羅德", home_team="東北樂天金鷲",
        away_starter="吉川悠斗 (左)", home_starter="莊司康誠 (右)",
        venue="楽天モバイルパーク宮城 (露天)",
        handicap_raw="1+10", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7.5", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-60", f5_total_raw="4+25",
        attested_fields=frozenset({"total"}),
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="歐力士猛牛", home_team="西武獅",
        away_starter="九里亜蓮 (右)", home_starter="平良海馬 (右)",
        venue="東京ドーム (巨蛋・西武主場移地)",
        handicap_raw="1-10", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6-50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-60", f5_total_raw="3-50",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="中日龍", home_team="廣島鯉魚",
        away_starter="大野雄大 (左)", home_starter="床田寛樹 (左)",
        venue="マツダスタジアム (露天)",
        handicap_raw="1+70", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7+50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-20", f5_total_raw="3.5",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="養樂多燕子", home_team="阪神虎",
        away_starter="吉村貢司郎 (右)", home_starter="村上頌樹 (右)",
        venue="京セラドーム大阪 (巨蛋)",
        handicap_raw="2+75", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6+25", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1+60", f5_total_raw="3-25",
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
    "横浜スタジアム (露天)": "横浜",
    "楽天モバイルパーク宮城 (露天)": "楽天モバイル",
    "東京ドーム (巨蛋・西武主場移地)": "東京ドーム",
    "マツダスタジアム (露天)": "マツダスタジアム",
    "京セラドーム大阪 (巨蛋)": "京セラD大阪",
}

OPEN_AIR = {"横浜", "楽天モバイル", "マツダスタジアム"}

DAILY_BUDGET = 3000.0
"""使用者 2026-08-16 指定的單日曝險上限，比 Bankroll 的 5,000 更緊。"""

OPEN_AIR_MIN_EV = 0.07
"""露天球場的 EV 門檻 (一般為 +4%)。

2026-08-16 使用者決定: 露天不再直接封鎖，改成要求更高的 EV。
理由是球場係數本身已內含該球場的常態風況，缺的只是「今日偏離常態多少」
—— 那是增加變異而非造成偏誤，用較高門檻補償比一刀切合理。
放棄 `weather_known` 這件事會照實印在報告的「已放棄的門檻」欄。"""

# 同一平台兩個時點的盤口差異 (12:00 前後的詳細頁 -> 13:10 的列表看板)。
# 這不是開盤價，但是目前唯一能取得的市場動向。
LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "横浜": "露天。8/18 關東一帶有陣雨可能，未取得逐時降水機率",
    "楽天モバイル": "露天。未取得仙台當日逐時預報",
    "マツダスタジアム": "露天。未取得廣島當日逐時預報",
}

# 今日先發 (npb.jp idp1_<team>.html, 2026-08-15 擷取)。
# is_opener: 季內單場平均局數 < 3 局 —— 實際用法是後援，今天等於開局投手。
STARTERS = {
    "DeNA": ("尾形崇斗", 0.9542, 5.00, "10 場 50 局 防禦率 3.42、27 四球", False),
    "巨人": ("山﨑伊織", 1.1012, 5.83, "4 場 23.1 局 防禦率 5.01（樣本僅 23.1 局）", False),
    "楽天": ("荘司康誠", 1.0902, 6.17, "18 場 111 局 防禦率 4.14、18 被轟", False),
    # 吉川悠斗: 支配下登錄 (背號 91、1/27 公示) 但本季一軍 0 場登板，
    # 個人成績頁查無此人。以聯盟平均 1.00 當先驗，並把
    # starter_stats_known 記為 False —— 那不是造假，但不確定度極大。
    "ロッテ": ("吉川悠斗", 1.0000, 5.00, "本季一軍 0 場登板（推測首度先發），無任何成績可用", False),
    "西武": ("平良海馬", 0.6763, 6.06, "17 場 103 局 防禦率 1.49、失分率 1.75 —— 全聯盟最佳", False),
    "オリックス": ("九里亜蓮", 0.9823, 6.35, "20 場 127 局 防禦率 2.83", False),
    "広島": ("床田寛樹", 0.9478, 6.15, "16 場 98.1 局 防禦率 2.56", False),
    "中日": ("大野雄大", 0.7464, 6.69, "16 場 107 局 防禦率 2.02", False),
    "阪神": ("村上頌樹", 0.7525, 6.92, "20 場 138.1 局 防禦率 1.82、每場 6.9 局", False),
    "ヤクルト": ("吉村貢司郎", 1.0528, 5.76, "15 場 86.1 局 防禦率 4.27、15 被轟", False),
}

BULLPEN_NOTE = {
    "DeNA": "8/15 用 **6 人**、8/16 用 4 人（片山 95 球）；馬場、浜地、ルイーズ三人連兩日登板",
    "巨人": "8/15 用 3 人、8/16 只用 2 人（小笠原 107 球）—— 牛棚最充足",
    "楽天": "8/15 用 4 人、8/16 用 3 人（古謝 91 球）；無連兩日登板",
    "ロッテ": "8/15 用 4 人、8/16 用 4 人（毛利 45 球、高野脩 67 球）；無連兩日登板",
    "西武": "8/15 用 4 人、8/16 用 4 人（武内 97 球）；無連兩日登板",
    "オリックス": "8/15 用 **6 人**、8/16 又用 **6 人**，川瀬、山岡、権田、阿部四人連兩日登板 —— 全聯盟負荷最重",
    "広島": "8/15 用 5 人、8/16 用 5 人（森 101 球）；無連兩日登板",
    "中日": "8/15 用 3 人、8/16 用 5 人（柳 120 球）；三浦連兩日登板",
    "阪神": "8/15 用 4 人、8/16 用 5 人（伊原 84 球）；無連兩日登板",
    "ヤクルト": "8/15 用 4 人、8/16 用 5 人（松本健 83 球）；星、清水連兩日登板",
}

ENV = NPBEnvironment(
    league_rpg=cal.LEAGUE_RPG,
    dispersion_k=cal.DISPERSION_K,
    home_edge=cal.HOME_EDGE,
    extras_resolve_rate=cal.EXTRAS_RESOLVE_RATE,
    source="npb.jp 2026 逐場比分 643 場",
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
        waived=(frozenset({"lineups_confirmed", "weather_known"})
                if PARK_KEY[game.venue] in OPEN_AIR
                else frozenset({"lineups_confirmed"})),
        prices_verified=True,
        bullpen_usage_known=True,
        # 羅德先發吉川悠斗本季 0 場登板，查無成績 —— 照實記為缺口。
        starter_stats_known=STARTERS[JP[game.away_team]][1] != 1.0
        or JP[game.away_team] != "ロッテ",
        team_rates_known=True,
        park_factor_known=True,
        # 露天球場仍然沒有逐時風向/氣溫 —— 照實記為 False，但依使用者
        # 2026-08-16 的決定放棄此門檻，改用 OPEN_AIR_MIN_EV 補償。
        weather_known=False if PARK_KEY[game.venue] in OPEN_AIR else True,
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
        open_air = PARK_KEY[game.venue] in OPEN_AIR
        graded = grade(ev=best.ev, edge_pp=best.edge_pp, readiness=readiness,
                       min_ev=OPEN_AIR_MIN_EV if open_air else 0.04)

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

    # --- 單日曝險上限 (使用者指定 3,000，低於 Bankroll 的 5,000) ---
    # 依 EV 由高到低配置，超出的降級為「觀察」並註明原因，不靜靜消失。
    budget = DAILY_BUDGET
    for a in sorted(analyses,
                    key=lambda x: -(x.evaluation.ev if x.evaluation else -1)):
        if a.grade is not Grade.RECOMMEND:
            continue
        if a.evaluation.stake <= budget + 1e-9:
            budget -= a.evaluation.stake
        else:
            a.graded.grade = Grade.OBSERVE
            a.graded.reasons = [
                f"已達使用者指定的單日曝險上限 {DAILY_BUDGET:,.0f} 單位"
                f"（本場 EV {a.evaluation.ev:+.1%}，數值面通過但排序在後）"
            ]

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
