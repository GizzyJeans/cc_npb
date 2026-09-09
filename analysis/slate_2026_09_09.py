"""2026-09-09 NPB 全六場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_09_09.py``

資料狀況
--------
* **官方預告先發完整可取得**，六場十二人全數與看板一致
  （馬塔 = Ｂ．マタ）。今天沒有「公示頁已翻到隔日」的問題。
* **十二人全部越過 25 局門檻**。マタ（巨人）31 局是最低的 ——
  8/29 時他只有 24.1 局、剛好被擋下，今天剛過。
* 唯一需要角色修正的是 **達孝太（火腿）**: 24 場 106.2 局、
  季內 IP/G 4.44 仍是後援與先發的混合值，沿用 8/26 起的處理取 6.67 局。

⚠️ 一個中性場地
--------------
**西武 @ 歐力士 在「ほっと神戸」**，不是京セラD大阪。
該球場本季只有 **3 場**，配適出的係數 0.9934 幾乎完全被收縮到 1.0，
不是可用的估計 —— 它不在 `PARK_FACTORS_2026` 的主要球場表內，
`park_factor()` 會退回中性值 1.0 且 `park_factor_known` 記為 False。
這是本月第三次遇到樂天／歐力士在地方球場辦主場賽（秋田 0 場、
盛岡 1 場、ほっと神戸 3 場），三次的球場係數都不可用。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bethero.bankroll import Bankroll
from bethero.board import BoardGame
from bethero.ev import devig_proportional, evaluate
from bethero.gates import DataReadiness, Grade, grade
from bethero.gates import OPEN_AIR_MIN_EV as GATE_OPEN_AIR_MIN_EV
from bethero.lines import total_outcome_probs
from bethero.model import GameModel, NPBEnvironment, TeamInput
from bethero.report import DailyReport, GameAnalysis
from config import calibration_2026 as cal

DATE = "2026-09-09"
DATA_AS_OF = "2026-09-09 15:45 JST (UTC 06:45)"

GAMES = [
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="東北樂天金鷲", home_team="千葉羅德",
        away_starter="荘司康誠 (右)", home_starter="毛利海大 (左)",
        venue="ZOZOマリンスタジアム (露天)",
        handicap_raw="1+75", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="8+50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-30", f5_total_raw="4-50",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="日本火腿", home_team="福岡軟銀鷹",
        away_starter="達孝太 (右)", home_starter="上沢直之 (右)",
        venue="みずほPayPay (巨蛋)",
        handicap_raw="1平", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7-25", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-50", f5_total_raw="4+50",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="廣島鯉魚", home_team="阪神虎",
        away_starter="床田寛樹 (左)", home_starter="髙橋遥人 (左)",
        venue="甲子園 (露天)",
        handicap_raw="1-75", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="5-25", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1+80", f5_total_raw="3+75",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="西武獅", home_team="歐力士猛牛",
        away_starter="菅井信也 (左)", home_starter="九里亜蓮 (右)",
        # ⚠️ 中性場地，本季僅 3 場，球場係數不可用。
        venue="ほっと神戸 (露天・中性場地)",
        handicap_raw="1+85", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7平", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-20", f5_total_raw="4+50",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="養樂多燕子", home_team="橫濱DeNA灣星",
        away_starter="山野太一 (左)", home_starter="石田裕太郎 (右)",
        venue="横浜 (露天)",
        handicap_raw="1+50", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7平", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-50", f5_total_raw="4+25",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="中日龍", home_team="讀賣巨人",
        away_starter="大野雄大 (左)", home_starter="Ｂ．マタ (右)",
        venue="東京ドーム (巨蛋)",
        handicap_raw="1+75", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6平", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-10", f5_total_raw="3-75",
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
    "みずほPayPay (巨蛋)": "みずほPayPay",
    "甲子園 (露天)": "甲子園",
    "ほっと神戸 (露天・中性場地)": "ほっと神戸",
    "横浜 (露天)": "横浜",
    "東京ドーム (巨蛋)": "東京ドーム",
}

OPEN_AIR = {"ZOZOマリン", "甲子園", "ほっと神戸", "横浜"}

NEUTRAL_PARK_FACTOR = 1.0
"""配適資料裡沒有 (或場次太少不足以估計) 的球場採用的中性值。
今日的ほっと神戸本季僅 3 場，適用。"""


def park_factor(game: BoardGame) -> float:
    """球場係數；資料不足的球場退回中性值並由門檻揭露。"""
    return cal.PARK_FACTORS_2026.get(PARK_KEY[game.venue], NEUTRAL_PARK_FACTOR)


DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限，比 Bankroll 的 5,000 更緊。"""

OPEN_AIR_MIN_EV = GATE_OPEN_AIR_MIN_EV
"""露天球場的 EV 門檻，由 `bethero.gates` 統一定義（2026-09-02 起 = 0.04）。"""

STARTED: set[str] = set()
"""本報告產出時 (15:45 JST) 六場皆未開賽，18:00 開打。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "ZOZOマリン": "露天，臨海、風的影響在十二座球場中最大。未取得逐時預報",
    "甲子園": "露天。未取得逐時風向／氣溫預報",
    "ほっと神戸": "露天，中性場地。未取得逐時預報",
    "横浜": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。
今日十二人全部通過，最低是 マタ 31 局（8/29 時 24.1 局曾被此門檻擋下）。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。今日未用到。"""

# (顯示名, 收縮後失分率係數, 今日預期局數, 說明, 季內 IP/G)
STARTERS = {
    "楽天": ("荘司康誠", 1.082, 6.24,
             "21 場 131 局 防禦率 3.92、失分率 4.05、34 四球", 6.24),
    "ロッテ": ("毛利海大", 1.216, 4.69,
              "15 場 70.1 局 防禦率 4.99、失分率 5.12 —— 本日最差", 4.69),
    "日本ハム": ("達孝太", 0.876, 6.67,
                "24 場 106.2 局 防禦率 2.78；季內 IP/G 4.44 是後援與先發的"
                "混合值，近期先發投 6-7 局", 4.44),
    "ソフトバンク": ("上沢直之", 0.926, 6.13,
                  "18 場 110.1 局 防禦率 2.53（失分率 3.18）", 6.13),
    "広島": ("床田寛樹", 0.975, 6.12,
             "19 場 116.1 局 防禦率 2.86（失分率 3.48）、31 四球；"
             "9/8 對阪神因雨中止，今日再度先發", 6.12),
    "阪神": ("髙橋遥人", 0.765, 6.98,
             "19 場 132.2 局 防禦率 1.90、每場 7.0 局、僅 16 四球 —— 本日最佳", 6.98),
    "西武": ("菅井信也", 0.946, 5.48,
             "7 場 38.1 局 防禦率 3.05、失分全為自責；樣本偏薄已重收縮", 5.48),
    "オリックス": ("九里亜蓮", 1.097, 6.12,
                "23 場 140.2 局 防禦率 3.20、失分率 3.77、**57 四球最多**", 6.12),
    "ヤクルト": ("山野太一", 0.731, 6.44,
                "21 場 135.1 局 防禦率 2.13、每場 6.4 局 —— 本日次佳", 6.44),
    "DeNA": ("石田裕太郎", 0.936, 6.04,
             "17 場 102.2 局 防禦率 3.16（失分率 3.33）", 6.04),
    "中日": ("大野雄大", 0.724, 6.61,
             "19 場 125.2 局 防禦率 2.08、失分率 2.15、每場 6.6 局", 6.61),
    "巨人": ("Ｂ．マタ", 0.928, 5.17,
             "6 場 31 局 防禦率 2.90，但 20 四球偏多；"
             "8/29 時只有 24.1 局曾被門檻擋下，今天剛過", 5.17),
}

STARTER_IP = {
    "楽天": 131.0, "ロッテ": 70.3, "日本ハム": 106.7, "ソフトバンク": 110.3,
    "広島": 116.3, "阪神": 132.7, "西武": 38.3, "オリックス": 140.7,
    "ヤクルト": 135.3, "DeNA": 102.7, "中日": 125.7, "巨人": 31.0,
}

ROLE_CHANGED = {"日本ハム"}
"""達孝太 —— 季內 IP/G 4.44 是後援與先發的混合值。
他的失分率也是在較短的登板中累積的，壓力測試改用球隊季內守備係數。"""

BULLPEN_NOTE = {
    "楽天": "9/8 用 4 人（2-3 敗）—— 正常",
    "ロッテ": "9/8 用 4 人（3-2 險勝）—— 正常",
    "日本ハム": "9/8 用 **6 人**（1-14 慘敗，牛棚吃掉大量局數）—— 最吃緊；"
                "球隊牛棚係數也因此由 1.094 升到 **1.151**",
    "ソフトバンク": "9/8 用 3 人（14-1 大勝）—— 充分",
    "広島": "9/8 因雨中止 —— 牛棚全休",
    "阪神": "9/8 因雨中止 —— 牛棚全休",
    "西武": "9/8 用 3 人（2-0 完封勝）—— 充分",
    "オリックス": "9/8 用 4 人（被完封 0-2）—— 正常",
    "ヤクルト": "9/8 打滿延長 10 局、用 5 人（3-1 勝）—— 略吃緊",
    "DeNA": "9/8 打滿延長 10 局、用 5 人（1-3 敗）—— 略吃緊",
    "中日": "9/8 用 3 人（3-0 完封勝）—— 充分",
    "巨人": "9/8 用 4 人（被完封 0-3）—— 正常",
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
            f"校準已更新到 9/8 收盤（{cal.SAMPLE_GAMES} 場）。"
            f"聯盟每隊每場得分 {cal.LEAGUE_RPG:.4f}、主場係數 {cal.HOME_EDGE:.4f}。"
            "9/8 的廣島 @ 阪神因雨中止，兩隊今日再戰。",
            "**官方預告先發完整可取得**，六場十二人全數與看板一致（馬塔 = Ｂ．マタ）。"
            "今天沒有「公示頁已翻到隔日」的問題。",
            "**十二人全部越過 25 局門檻**，最低是 マタ（巨人）31 局 —— "
            "8/29 時他只有 24.1 局、剛好被此門檻擋下，今天剛過。"
            "唯一需要角色修正的是達孝太（火腿）：季內 IP/G 4.44 仍是"
            "後援與先發的混合值，沿用 8/26 起的處理取 6.67 局。",
            "⚠️ **西武 @ 歐力士 在「ほっと神戸」**，不是京セラD大阪。"
            "該球場本季只有 **3 場**，係數 0.9934 幾乎完全被收縮到 1.0，"
            "不是可用的估計 —— 退回中性值並將 `park_factor_known` 記為 False。"
            "這是本月第三次遇到樂天／歐力士在地方球場辦主場賽"
            "（秋田 0 場、盛岡 1 場、ほっと神戸 3 場），三次的球場係數都不可用。",
            "⚠️ **首選連兩天是同一組對戰**：養樂多 @ DeNA，昨天 +35.1%（已贏，"
            "實際總分 4）、今天 +32.4%。模型 5.86 vs 市場 7.0，差 1.14 分。"
            "先發換人了（昨天 奥川／東，今天 山野／石田裕），但兩隊打線"
            "依然是全聯盟最弱（養樂多 0.780）與中段（DeNA 1.025），"
            "模型與市場的分歧點是一樣的。昨天贏了不代表今天對 —— "
            "這是同一個分歧的第二次下注，不是兩個獨立的發現。",
            "⚠️ **「已下注 vs 未下注」的訊號來到 1.8 個標準誤**"
            "（8/28 起：1.7 → 0.9 → 0.9 → 1.2 → 1.5 → 1.6 → 1.8，自低點五連升）。"
            "9/8 三注全中卻讓訊號變強 —— 該指標量的不是輸贏，"
            "是我選的場次與略過的場次之間模型誤差有無系統性差異。"
            "更直接的一組：已下注場次「實際−盤口」+0.52、未下注 −0.25。",
            "  **到 2 個標準誤時的具體做法**（先寫下來，避免屆時臨時決定）："
            "不調 `league_rpg`（未下注對照組近零，測了兩週都一致）；"
            "不收縮預測值（該假說 9/8 已用校準斜率排除，需約 2,000 場才測得出）。"
            "要做的是把已下注場次按「模型−盤口」的絕對值分層，"
            "檢查誤差是否集中在分歧最大的那一層；若是，"
            "最直接的補救是對分歧幅度設上限。",
            "**得分水位仍不調整**：111 場的整體偏誤 −0.02 分（0.1 個標準誤），"
            "未下注對照組（59 場）的「實際 − 盤口」−0.25 分。",
            "讓分與上半場盤全數不定價。理由是結構性的：模型的 Var(分差) 被"
            "共享環境因子壓窄約 2.3 倍，且數學上與 dispersion_k 無關。"
            "見 analysis/diagnose_margin.py。",
        ],
        sources=[
            "https://npb.jp/announcement/starter/（2026-09-09 預告先發公示，含球場欄位）",
            "https://npb.jp/games/2026/schedule_09_detail.html（賽程與 9/8 比分）",
            "https://npb.jp/bis/2026/stats/idp1_<team>.html（個人投手成績）",
            "https://npb.jp/scores/2026/<date>/<slug>/box.html（牛棚用球數）",
            "賠率：使用者提供之看板截圖（2026-09-09）",
        ],
    )


if __name__ == "__main__":
    print(build_report().render())
