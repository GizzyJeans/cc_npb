"""2026-09-08 NPB 全六場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_09_08.py``

看板回到列表格式（客隊在上、主隊在下標 [主]），與 9/6 的單場詳細頁
主客順序相反 —— 仍逐場對照官方賽程確認，六場的主客與球場全部一致。

⚠️ 先發核對的來源與 8/27、8/29、9/4 相同
--------------------------------------
npb.jp 的 9/8 官方預告先發已取不到（該頁只保留隔日場次，
產出時 17:15 JST 已翻到 9/9）。改用賽程頁的 `pit` 欄位（官方，只給主隊）:
六場主隊先發與看板 **全部一致** —— 戸郷／東／才木／田中／ジェリー／モイネロ。
六名客隊先發也都確認在正確球隊且樣本充分。
主隊官方確認、客隊看板來源加名單佐證，這個弱化必須揭露。

先發樣本
--------
* **モイネロ (軟銀) 首度越過門檻**: 4 場 29 局、失分率 0.93。
  9/1 時他只有 21 局、被 `starter_stats_known` 擋下；今天 29 局已達標，
  該場恢復可定價。收縮仍把 0.93 拉到係數 0.760 —— 這個方向的偏誤
  （低估頂級投手）依然存在，只是不再構成硬缺口。
* **山﨑福也 (火腿)**: 15 場 51 局、季內 IP/G 3.40 仍是後援與先發的混合值，
  沿用 9/1 的處理，取近期先發的 5.50 局並列入 `ROLE_CHANGED`。
* 其餘十人季內每場局數全部 >= 5.19，無開局投手。
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

DATE = "2026-09-08"
DATA_AS_OF = "2026-09-08 17:22 JST (UTC 08:22)"

GAMES = [
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="東北樂天金鷲", home_team="千葉羅德",
        away_starter="前田健太 (右)", home_starter="田中晴也 (右)",
        venue="ZOZOマリンスタジアム (露天)",
        handicap_raw="1+95", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="8-50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-20", f5_total_raw="4.5",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="日本火腿", home_team="福岡軟銀鷹",
        away_starter="山﨑福也 (左)", home_starter="Ｌ．モイネロ (左)",
        venue="みずほPayPay (巨蛋)",
        handicap_raw="1-45", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6.5", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1+70", f5_total_raw="3-50",
        # 使用者於 2026-08-13 確認: 裸小數就是字面上的半球盤，不會走盤。
        attested_fields=frozenset({"total"}),
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="廣島鯉魚", home_team="阪神虎",
        away_starter="床田寛樹 (左)", home_starter="才木浩人 (右)",
        venue="甲子園 (露天)",
        handicap_raw="1-50", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="5-75", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-80", f5_total_raw="3+50",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="西武獅", home_team="歐力士猛牛",
        away_starter="平良海馬 (右)", home_starter="ジェリー (右)",
        venue="京セラD大阪 (巨蛋)",
        handicap_raw="1平", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6平", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-60", f5_total_raw="3-25",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="養樂多燕子", home_team="橫濱DeNA灣星",
        away_starter="奥川恭伸 (右)", home_starter="東克樹 (左)",
        venue="横浜 (露天)",
        handicap_raw="1-80", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7-25", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1+30", f5_total_raw="4+50",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="中日龍", home_team="讀賣巨人",
        away_starter="柳裕也 (右)", home_starter="戸郷翔征 (右)",
        venue="東京ドーム (巨蛋)",
        handicap_raw="1+10", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6平", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-30", f5_total_raw="3-25",
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
    "京セラD大阪 (巨蛋)": "京セラD大阪",
    "横浜 (露天)": "横浜",
    "東京ドーム (巨蛋)": "東京ドーム",
}

OPEN_AIR = {"ZOZOマリン", "甲子園", "横浜"}

NEUTRAL_PARK_FACTOR = 1.0
"""配適資料裡沒有的球場採用的中性值。今日未用到。"""


def park_factor(game: BoardGame) -> float:
    """球場係數；資料不足的球場退回中性值並由門檻揭露。"""
    return cal.PARK_FACTORS_2026.get(PARK_KEY[game.venue], NEUTRAL_PARK_FACTOR)


DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限，比 Bankroll 的 5,000 更緊。"""

OPEN_AIR_MIN_EV = GATE_OPEN_AIR_MIN_EV
"""露天球場的 EV 門檻，由 `bethero.gates` 統一定義（2026-09-02 起 = 0.04）。"""

STARTED: set[str] = set()
"""本報告產出時 (17:22 JST) 六場皆未開賽，18:00 開打。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "ZOZOマリン": "露天，臨海、風的影響在十二座球場中最大。未取得逐時預報",
    "甲子園": "露天。未取得逐時風向／氣溫預報",
    "横浜": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。今日十二人全部通過
（最低 モイネロ 29 局 —— 9/1 時他只有 21 局、曾被此門檻擋下）。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。"""

# (顯示名, 收縮後失分率係數, 今日預期局數, 說明, 季內 IP/G)
STARTERS = {
    "楽天": ("前田健太", 0.894, 5.44,
             "12 場 65.1 局 防禦率 2.48（失分率 2.89）", 5.44),
    "ロッテ": ("田中晴也", 1.184, 5.33,
              "13 場 69.1 局 防禦率 4.54、失分率 4.93、27 四球 —— 本日最差", 5.33),
    "日本ハム": ("山﨑福也", 0.821, 5.50,
                "15 場 51 局 防禦率 2.29、失分全為自責；季內 IP/G 3.40 是"
                "後援與先發的混合值，近期先發投 5-6 局", 3.40),
    "ソフトバンク": ("Ｌ．モイネロ", 0.760, 7.25,
                  "4 場 29 局 防禦率 0.62、失分率 0.93、每場 7.3 局 —— "
                  "本日最佳；9/1 時只有 21 局曾被門檻擋下，今天已達標", 7.25),
    "広島": ("床田寛樹", 0.975, 6.12,
             "19 場 116.1 局 防禦率 2.86（失分率 3.48）、31 四球", 6.12),
    "阪神": ("才木浩人", 0.898, 6.19,
             "21 場 130 局 防禦率 2.63、每場 6.2 局", 6.19),
    "西武": ("平良海馬", 0.643, 6.20,
             "20 場 124 局 防禦率 1.45、失分率 1.67 —— 本日次佳，"
             "但 42 四球全聯盟最多", 6.20),
    "オリックス": ("ジェリー", 1.065, 5.19,
                "19 場 98.2 局 防禦率 3.28（失分率 3.65）", 5.19),
    "ヤクルト": ("奥川恭伸", 0.843, 6.79,
                "19 場 129 局 防禦率 2.93、每場 6.8 局", 6.79),
    "DeNA": ("東克樹", 0.821, 6.52,
             "21 場 137 局 防禦率 2.30、每場 6.5 局、僅 18 四球", 6.52),
    "中日": ("柳裕也", 0.797, 6.23,
             "22 場 137 局 防禦率 2.50、失分率 2.56", 6.23),
    "巨人": ("戸郷翔征", 0.845, 5.73,
             "10 場 57.1 局 防禦率 2.35（失分率 2.51）", 5.73),
}

STARTER_IP = {
    "楽天": 65.3, "ロッテ": 69.3, "日本ハム": 51.0, "ソフトバンク": 29.0,
    "広島": 116.3, "阪神": 130.0, "西武": 124.0, "オリックス": 98.7,
    "ヤクルト": 129.0, "DeNA": 137.0, "中日": 137.0, "巨人": 57.3,
}

ROLE_CHANGED = {"日本ハム"}
"""山﨑福也 —— 季內 IP/G 3.40 是後援與先發的混合值。
他的失分率也是在較短的登板中累積的，壓力測試改用球隊季內守備係數。"""

BULLPEN_NOTE = {
    "楽天": "9/6 用 5 人（3-6 敗）—— 略吃緊",
    "ロッテ": "9/6 用 3 人（3-0 完封勝）—— 充分",
    "日本ハム": "9/6 用 4 人（6-3 勝）—— 正常",
    "ソフトバンク": "9/6 用 5 人（2-5 敗）—— 略吃緊",
    "広島": "9/6 用 4 人（被完封 0-4）—— 正常",
    "阪神": "9/6 用 4 人（1-4 敗）—— 正常",
    "西武": "9/6 用 4 人（5-2 勝）—— 正常",
    "オリックス": "9/6 用 4 人（被完封 0-3）—— 正常",
    "ヤクルト": "9/6 因雨中止 —— 牛棚全休",
    "DeNA": "9/6 用 4 人（4-1 勝）—— 正常",
    "中日": "9/6 因雨中止 —— 牛棚全休",
    "巨人": "9/6 用 3 人（4-0 完封勝）—— 充分",
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
            f"校準已更新到 9/6 收盤（{cal.SAMPLE_GAMES} 場）。"
            f"聯盟每隊每場得分 {cal.LEAGUE_RPG:.4f}、主場係數 {cal.HOME_EDGE:.4f}。"
            "9/7 無比賽；9/6 的中日 @ 養樂多因雨中止。",
            "看板回到列表格式（客隊在上、主隊在下標 [主]），與 9/6 的單場詳細頁"
            "主客順序相反。仍逐場對照官方賽程確認，六場主客與球場全部一致。",
            "⚠️ **9/8 的官方預告先發已取不到**（該頁只保留隔日場次，"
            "產出時 17:15 JST 已翻到 9/9），與 8/27、8/29、9/4 同一個問題。"
            "改用賽程頁的 `pit` 欄位（官方，只給主隊）—— 六場主隊先發與看板"
            "**全部一致**；六名客隊先發也都確認在正確球隊且樣本充分。"
            "主隊官方確認、客隊看板來源加名單佐證，這個弱化必須揭露。",
            "**モイネロ（軟銀）首度越過先發樣本門檻**：4 場 29 局、失分率 0.93。"
            "9/1 時他只有 21 局、被 `starter_stats_known` 擋下（那場事後也證明"
            "該擋 —— 軟銀只得 1 分、總分 3，模型的大分會輸）。今天 29 局已達標，"
            "該場恢復可定價。收縮仍把 0.93 拉到係數 0.760，"
            "**低估頂級投手的方向偏誤依然存在**，只是不再構成硬缺口。",
            "⚠️ **首選 +35.1% 是至今下注過最大的 EV**（前高是 9/4 的 +29.3%）："
            "養樂多 @ DeNA，模型 5.88 vs 市場等效約 7.125，差 1.25 分。"
            "**但這次的性質與先前的大分歧不同**：8/27 的石川雅規（+31.7%）與 "
            "8/29 的大川慈英（+14.2%）都是「模型缺資料而市場有」，兩次市場都對；"
            "今天兩名先發是全場資料最完整的其中兩位（奥川恭伸 129 局、"
            "東克樹 137 局），分歧來自模型與市場對同一組已知輸入的判斷不同。"
            "這不保證模型是對的，但它不是同一種錯誤。",
            "**追蹤中的訊號**：9/6 收盤時「已下注 − 未下注」的偏誤差距為 "
            "**1.6 個標準誤**（8/28 起：1.7 → 0.9 → 0.9 → 1.2 → 1.5 → 1.6，"
            "自低點單向上升四次）。行動門檻仍是 2 個標準誤 —— "
            "屆時應停止依現行方式下注並回頭改模型。",
            "**「模型過度發散」的假說已排除**：9/8 用校準斜率正式檢定，"
            "模型 b = 0.825（標準誤 0.382，僅 0.46 個標準誤）、"
            "市場盤口 b = 1.451（0.88 個標準誤），**兩者都測不出來**。"
            "根因是預測值標準差只有 0.92 而實際總分標準差 3.67，"
            "要分辨需要約 2,000 場。因此不再用它解釋押大分／押小分的差異。"
            "見 analysis/validate_calibration_slope.py。",
            "**得分水位仍不調整**：106 場的整體偏誤 +0.00 分，"
            "未下注對照組（57 場）的「實際 − 盤口」−0.13 分。",
            "讓分與上半場盤全數不定價。理由是結構性的：模型的 Var(分差) 被"
            "共享環境因子壓窄約 2.3 倍，且數學上與 dispersion_k 無關。"
            "見 analysis/diagnose_margin.py。",
        ],
        sources=[
            "https://npb.jp/games/2026/schedule_09_detail.html"
            "（賽程、9/6 比分、**主隊先發 pit 欄位**、主客隊別與球場欄位）",
            "https://npb.jp/bis/2026/stats/idp1_<team>.html（個人投手成績）",
            "https://npb.jp/scores/2026/<date>/<slug>/box.html（牛棚用球數）",
            "⚠️ https://npb.jp/announcement/starter/ 今日 **無法取得**"
            "（該頁只保留隔日場次，已翻到 9/9）",
            "賠率：使用者提供之看板截圖（2026-09-08）",
        ],
    )


if __name__ == "__main__":
    print(build_report().render())
