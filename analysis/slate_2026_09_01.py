"""2026-09-01 NPB 全六場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_09_01.py``

⚠️ 兩場不在主場球場
-------------------
官方公示揭露兩件照「主隊 = 主場」假設就會算錯的事:

* **DeNA @ 巨人 在 京セラD大阪**，不是東京巨蛋。
  球場係數 0.876 vs 1.011 —— 差 13%，直接影響總分預期。
* **歐力士 @ 樂天 在 秋田**，不是樂天生命公園。
  秋田本季 **零場次**，配適資料裡根本沒有這座球場，
  只能用中性值 1.0，`park_factor_known` 記為 False。

這兩件事都是讀官方公示的球場欄位才發現的，不是從隊名推出來的。

先發樣本與角色
--------------
* **高野脩汰 (羅德)**: 季內 27 場全部是後援 (快取的 11 次登板 **第 1 任 0 次**)，
  今天是本季首度先發。最長一次 4 局 67 球。季內 IP/G 1.33 完全不能用，
  改採 4.00 局，並列入 `ROLE_CHANGED` 跑壓力測試。
* **山﨑福也 (火腿)**: 季內 IP/G 3.14，但快取 8 次登板中 **7 次是第 1 任**、
  投 5-6 局。季均被少數短局數登板拉低，改採 5.50 局。
* **モイネロ (軟銀)**: 3 場 21 局、失分率 0.43（8/25 九局完封）。
  三場全是先發，但 **21 局低於 25 局門檻** ——
  `starter_stats_known` 記為 False，該場不可推薦。
* **伊藤樹 (樂天)**: 2 場 7 局，同樣不合格。
  該場 **同時** 缺球場係數（秋田）與先發成績，是今天資料最差的一場。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bethero.bankroll import Bankroll
from bethero.board import BoardGame
from bethero.ev import devig_proportional, evaluate
from bethero.gates import DataReadiness, Grade, grade
from bethero.lines import total_outcome_probs
from bethero.model import GameModel, NPBEnvironment, TeamInput
from bethero.report import DailyReport, GameAnalysis
from config import calibration_2026 as cal

DATE = "2026-09-01"
DATA_AS_OF = "2026-09-01 15:00 JST (UTC 06:00)"

GAMES = [
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="西武獅", home_team="千葉羅德",
        away_starter="平良海馬 (右)", home_starter="高野脩汰 (左)",
        venue="ZOZOマリンスタジアム (露天)",
        handicap_raw="1-10", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7+50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-90", f5_total_raw="3.5",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="廣島鯉魚", home_team="中日龍",
        away_starter="床田寛樹 (左)", home_starter="大野雄大 (左)",
        venue="バンテリンドーム (巨蛋)",
        handicap_raw="1+20", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6-50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-40", f5_total_raw="3-50",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="福岡軟銀鷹", home_team="日本火腿",
        away_starter="Ｌ．モイネロ (左)", home_starter="山﨑福也 (左)",
        venue="エスコンＦ (巨蛋)",
        handicap_raw="1-65", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7-50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1+50", f5_total_raw="4+50",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="歐力士猛牛", home_team="東北樂天金鷲",
        away_starter="九里亜蓮 (右)", home_starter="伊藤樹 (右)",
        # ⚠️ 中性場地 —— 不是樂天生命公園，且本季零場次、無球場係數。
        venue="秋田 (露天・中性場地)",
        handicap_raw="0-75", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7+25", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-10", f5_total_raw="4+50",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="阪神虎", home_team="養樂多燕子",
        away_starter="髙橋遥人 (左)", home_starter="吉村貢司郎 (右)",
        venue="神宮 (露天)",
        handicap_raw="2+5", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7-25", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1-20", f5_total_raw="4+25",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="橫濱DeNA灣星", home_team="讀賣巨人",
        away_starter="石田裕太郎 (右)", home_starter="戸郷翔征 (右)",
        # ⚠️ 巨人的主場比賽辦在京セラD大阪，不是東京巨蛋 (係數 0.876 vs 1.011)。
        venue="京セラD大阪 (巨蛋・中性場地)",
        handicap_raw="1+65", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6平", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-20", f5_total_raw="3-25",
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
    "ZOZOマリンスタジアム (露天)": "ZOZOマリン",
    "バンテリンドーム (巨蛋)": "バンテリンドーム",
    "エスコンＦ (巨蛋)": "エスコンＦ",
    "秋田 (露天・中性場地)": "秋田",
    "神宮 (露天)": "神宮",
    "京セラD大阪 (巨蛋・中性場地)": "京セラD大阪",
}

OPEN_AIR = {"ZOZOマリン", "秋田", "神宮"}

NEUTRAL_PARK_FACTOR = 1.0
"""配適資料裡沒有的球場採用的中性值。今日的秋田本季零場次。"""


def park_factor(game: BoardGame) -> float:
    """球場係數；配適資料裡沒有的球場退回中性值並由門檻揭露。"""
    return cal.PARK_FACTORS_2026.get(PARK_KEY[game.venue], NEUTRAL_PARK_FACTOR)


DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限，比 Bankroll 的 5,000 更緊。"""

OPEN_AIR_MIN_EV = 0.07
"""露天球場的 EV 門檻 (一般為 +4%)，2026-08-16 使用者決定。
其依據 (露天 vs 巨蛋的誤差差距) 已連續多天在 0 附近，這個門檻已經
站不太住，應在資料乾淨且無其他變動的日子處理掉 —— 今天有兩場中性
場地與四項資料缺口，不是動門檻的時候。"""

STARTED: set[str] = set()
"""本報告產出時已開賽的場次 (以主隊記)。今日六場全部 18:00 開賽，無。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "ZOZOマリン": "露天，臨海、風的影響在十二座球場中最大。未取得逐時預報",
    "秋田": "露天，中性場地。未取得逐時預報",
    "神宮": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。"""

# (顯示名, 收縮後失分率係數, **今日預期局數**, 說明, 季內 IP/G)
STARTERS = {
    "西武": ("平良海馬", 0.655, 6.16,
             "19 場 117 局 防禦率 1.46、失分率 1.69 —— 本日最佳，但 42 四球最多", 6.16),
    "ロッテ": ("高野脩汰", 1.045, 4.00,
              "27 場 36 局 防禦率 3.75，**全部是後援登板**；今天是本季首度先發，"
              "最長一次 4 局 67 球", 1.33),
    "広島": ("床田寛樹", 1.005, 6.02,
             "18 場 108.1 局 防禦率 2.99（失分率 3.66）", 6.02),
    "中日": ("大野雄大", 0.728, 6.61,
             "18 場 119 局 防禦率 2.04、每場 6.6 局 —— 本日次佳", 6.61),
    "ソフトバンク": ("Ｌ．モイネロ", 0.777, 7.00,
                  "3 場 21 局 防禦率 0.43（8/25 九局完封）—— 三場全是先發，"
                  "但 21 局低於門檻，模型只能重收縮", 7.00),
    "日本ハム": ("山﨑福也", 0.845, 5.50,
                "14 場 44 局 防禦率 2.45；季內 IP/G 3.14 被少數短局數登板拉低，"
                "近期先發都投 5-6 局", 3.14),
    "オリックス": ("九里亜蓮", 1.071, 6.17,
                "22 場 135.2 局 防禦率 3.12（失分率 3.71）、**52 四球最多**", 6.17),
    "楽天": ("伊藤樹", 1.077, 5.00,
             "2 場 7 局 防禦率 6.43 —— 樣本不足；8/25 首度先發投 5 局失 1 分", 3.50),
    "阪神": ("髙橋遥人", 0.762, 7.02,
             "18 場 126.1 局 防禦率 1.85、每場 7.0 局、僅 13 四球", 7.02),
    "ヤクルト": ("吉村貢司郎", 1.085, 5.78,
                "17 場 98.1 局 防禦率 4.39、失分率 4.58 —— 本日最差", 5.78),
    "DeNA": ("石田裕太郎", 0.919, 6.04,
             "16 場 96.2 局 防禦率 3.07（失分率 3.26）", 6.04),
    "巨人": ("戸郷翔征", 0.814, 5.81,
             "9 場 52.1 局 防禦率 2.24、失分全為自責", 5.81),
}

STARTER_IP = {
    "西武": 117.0, "ロッテ": 36.0, "広島": 108.3, "中日": 119.0,
    "ソフトバンク": 21.0, "日本ハム": 44.0, "オリックス": 135.7, "楽天": 7.0,
    "阪神": 126.3, "ヤクルト": 98.3, "DeNA": 96.7, "巨人": 52.3,
}

ROLE_CHANGED = {"ロッテ", "日本ハム"}
"""高野脩汰 (27 場全後援、今天首度先發) 與 山﨑福也 (季均被短局數登板拉低)。
兩人的失分率都是在較短的登板中累積的，通常優於長局數先發，
壓力測試把這兩隊改用季內守備係數以量化方向。"""

BULLPEN_NOTE = {
    "西武": "8/30 用 4 人 —— 正常（8/31 全聯盟休兵）",
    "ロッテ": "8/30 用 5 人 —— 正常（8/31 休兵，已恢復）",
    "広島": "8/30 用 4 人 —— 正常（8/31 休兵）",
    "中日": "8/30 用 4 人 —— 正常（8/31 休兵）",
    "ソフトバンク": "8/30 用 4 人 —— 正常（8/31 休兵）",
    "日本ハム": "8/30 用 5 人 —— 正常（8/31 休兵，已恢復）",
    "オリックス": "8/30 用 5 人 —— 正常（8/31 休兵，已恢復）",
    "楽天": "8/30 用 4 人 —— 正常（8/31 休兵）",
    "阪神": "8/30 用 3 人 —— 充分（8/31 休兵）",
    "ヤクルト": "8/30 用 4 人 —— 正常（8/31 休兵）",
    "DeNA": "8/30 用 4 人 —— 正常（8/31 休兵）",
    "巨人": "8/30 用 4 人 —— 正常（8/31 休兵）",
}

ENV = NPBEnvironment(
    league_rpg=cal.LEAGUE_RPG,
    dispersion_k=cal.DISPERSION_K,
    home_edge=cal.HOME_EDGE,
    extras_resolve_rate=cal.EXTRAS_RESOLVE_RATE,
    source=f"npb.jp 2026 逐場比分 {cal.SAMPLE_GAMES} 場",
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
                     env=ENV, park_factor=park_factor(game))


def thin_starters(game: BoardGame) -> list[str]:
    return [f"{STARTERS[t][0]}（本季僅 {STARTER_IP[t]:.1f} 局）"
            for t in (JP[game.away_team], JP[game.home_team])
            if STARTER_IP[t] < MIN_STARTER_IP]


def role_changed(game: BoardGame) -> list[str]:
    out = []
    for t in (JP[game.away_team], JP[game.home_team]):
        if t in ROLE_CHANGED:
            name, _, ip_gs, _, season_ipg = STARTERS[t]
            out.append(f"{name}（季內 IP/G {season_ipg:.2f} → 今日採用 {ip_gs:.2f} 局）")
    return out


def stress_season_defence(game: BoardGame) -> GameModel:
    """把樣本不足與角色轉換的先發，換成該隊季內守備係數。

    兩種情況的偏誤方向相同 —— 都會讓該隊今天看起來比實際好:
    樣本不足者的係數幾乎全是聯盟平均; 轉先發者的失分率是後援時期
    累積的，而後援本來就比先發好看。
    """
    def side(team: str) -> TeamInput:
        _, factor, ip_gs, _, _ = STARTERS[team]
        suspect = STARTER_IP[team] < MIN_STARTER_IP or team in ROLE_CHANGED
        dfn = (cal.TEAM_DEFENCE_SEASON[team] if suspect
               else cal.blended_defence(factor, ip_gs, cal.BULLPEN_FACTOR[team]))
        return TeamInput(team, cal.TEAM_OFFENCE[team], dfn, ip_gs)

    return GameModel(home=side(JP[game.home_team]), away=side(JP[game.away_team]),
                     env=ENV, park_factor=park_factor(game))


def readiness_for(game: BoardGame) -> DataReadiness:
    open_air = PARK_KEY[game.venue] in OPEN_AIR
    return DataReadiness(
        line_type_confirmed=not game.audit_for("total"),
        starters_confirmed=True,
        lineups_confirmed=False,
        waived=(frozenset({"lineups_confirmed", "weather_known"}) if open_air
                else frozenset({"lineups_confirmed"})),
        # 已開賽的場次，賽前盤口已不可得 —— 硬性門檻，不可能成為推薦。
        prices_verified=JP[game.home_team] not in STARTED,
        bullpen_usage_known=True,
        starter_stats_known=not thin_starters(game),
        team_rates_known=True,
        park_factor_known=PARK_KEY[game.venue] in cal.PARK_FACTORS_2026,
        weather_known=not open_air,
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
        thin, changed = thin_starters(game), role_changed(game)

        risks = [
            "全場讓分：模型 Var(分差) 結構性偏窄約 2.3 倍（實測 16.24、模型 6.9），"
            "且與 dispersion_k 無關 —— 見 analysis/diagnose_margin.py，不定價",
            "上半場盤：修正逐局比分解析後最大偏離約 3.3pp，"
            "對 3pp 門檻沒有安全邊際，不定價",
        ]
        if thin or changed:
            s_d = stress_season_defence(game).distributions()
            s_ev = evaluate(
                total_outcome_probs(game.total, s_d.total_pmf,
                                    "over" if label == "大分" else "under"),
                game.over_hk, Bankroll().total,
                market[0] if label == "大分" else market[1]).ev
            bits = []
            for t, is_home in ((home, True), (away, False)):
                if STARTER_IP[t] >= MIN_STARTER_IP and t not in ROLE_CHANGED:
                    continue
                today = (model.home if is_home else model.away).def_factor
                season = cal.TEAM_DEFENCE_SEASON[t]
                bits.append(
                    f"{STARTERS[t][0]}：當日守備係數 {today:.3f} vs 該隊季內 "
                    f"{season:.3f}，模型{'高估' if today > season else '低估'}{t}的失分"
                )
            delta = s_d.expected_total() - dists.expected_total()
            head = []
            if thin:
                head.append("先發樣本不足：" + "、".join(thin))
            if changed:
                head.append("季中由後援轉先發（失分率是後援時期累積的，"
                            "通常優於先發）：" + "、".join(changed))
            risks.append(
                "；".join(head)
                + "。逐隊方向：" + "；".join(bits)
                + f"。壓力測試：改用季內守備係數後預期總分 "
                  f"{s_d.expected_total():.2f}（原 {dists.expected_total():.2f}，"
                  f"{delta:+.2f}）、{label} EV {s_ev:+.1%}（原 {best.ev:+.1%}）"
                  f"；也就是目前的輸入相對偏向"
                  f"{'小分' if delta > 0 else '大分'}，這個 {label} 的 EV 若有偏差"
                  f"比較可能是被{'低估' if s_ev > best.ev else '高估'}了"
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
                f"當日守備係數 主 {model.home.def_factor:.3f}、"
                f"客 {model.away.def_factor:.3f}"
                + ("　⚠️ " + "；".join(thin + changed) if (thin or changed) else "")
            ),
            lineup_note="15:30 JST 尚未公布，依使用者指示略過",
            bullpen_note=f"{game.home_team}：{BULLPEN_NOTE[home]}；"
                         f"{game.away_team}：{BULLPEN_NOTE[away]}",
            park_weather_note=(
                f"球場係數 {park_factor(game):.3f}"
                + ("（2026 實測）。" if PARK_KEY[game.venue] in cal.PARK_FACTORS_2026
                   else "（⚠️ 本季零場次，採中性值 1.0）。")
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
            + (["露天球場，達延賽標準即取消"] if open_air else []),
        ))

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
            f"校準已更新到 8/30 收盤（{cal.SAMPLE_GAMES} 場）。"
            f"聯盟每隊每場得分 {cal.LEAGUE_RPG:.4f}、主場係數 {cal.HOME_EDGE:.4f}。"
            "8/31 為全聯盟休兵日。",
            "**十二名先發全數與 npb.jp 9/1 官方預告先發公示一致。**",
            "⚠️ **兩場不在主場球場，這是讀官方公示的球場欄位才發現的：**"
            "DeNA @ 巨人 辦在 **京セラD大阪**（係數 0.876）而不是東京巨蛋"
            "（1.011）—— 差 13%；歐力士 @ 樂天 辦在 **秋田**"
            "而不是樂天生命公園。照「主隊 = 主場」推會兩場都算錯。",
            "⚠️ **秋田本季零場次**，配適資料裡沒有這座球場，只能用中性值 1.0，"
            "`park_factor_known` 記為 False。該場同時還有先發樣本不足"
            "（樂天 伊藤樹 2 場 7 局），是今天資料最差的一場。",
            "**高野脩汰（羅德）今天是本季首度先發**：27 場全部後援，"
            "快取的 11 次登板 **第 1 任 0 次**，最長一次 4 局 67 球。"
            "季內 IP/G 1.33 完全不能當先發局數用，改採 4.00 局並跑壓力測試。"
            "他的失分率也是後援時期累積的，通常優於長局數先發。",
            "**モイネロ（軟銀）三場全是先發**（含 8/25 九局完封）、失分率 0.43，"
            "但 **21 局低於 25 局門檻** —— `starter_stats_known` 記為 False。"
            "這道門檻不可放棄，該場不可推薦。這次擋掉的是一個"
            "「模型嚴重低估其實力」的方向，與 8/27、8/29 那兩次相反，"
            "但門檻的邏輯一樣：樣本不足就是樣本不足。",
            "**得分水位仍不調整。** 8/30 收盤時整體偏誤 +0.23 分"
            "（0.6 個標準誤，82 場）；「已下注 vs 未下注」的差距 0.9 個標準誤，"
            "未下注對照組的「實際 − 盤口」+0.30。8/28 那個一度看似要成立的"
            "選擇偏誤訊號（1.7 個標準誤）已連兩天穩在 0.9 —— 它退掉了。",
            "露天三場（ZOZOマリン、秋田、神宮）維持 +7% EV 門檻。"
            "該門檻的依據已連續多天為零，但今天有兩場中性場地與四項資料缺口，"
            "不是動門檻的時候。",
            "讓分與上半場盤全數不定價。讓分的理由是結構性的："
            "模型的 Var(分差) 被共享環境因子壓窄約 2.3 倍，"
            "且數學上與 dispersion_k 無關。見 analysis/diagnose_margin.py。",
        ],
        sources=[
            "https://npb.jp/announcement/starter/（2026-09-01 預告先發公示，含球場欄位）",
            "https://npb.jp/games/2026/schedule_09_detail.html（9 月賽程）",
            "https://npb.jp/games/2026/schedule_08_detail.html（8 月賽程與比分）",
            "https://npb.jp/bis/2026/stats/idp1_<team>.html（個人投手成績）",
            "https://npb.jp/scores/2026/<date>/<slug>/box.html"
            "（牛棚用球數、逐場先發順位 —— 用來判定角色轉換）",
            "賠率：使用者提供之看板截圖（2026-09-01）",
        ],
    )


if __name__ == "__main__":
    print(build_report().render())
