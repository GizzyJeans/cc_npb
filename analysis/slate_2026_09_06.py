"""2026-09-06 NPB —— 只有兩場提供盤口。

執行: ``python3 analysis/slate_2026_09_06.py``

⚠️ 看板格式與主客順序
--------------------
今天使用者提供的是 **單場詳細頁** 截圖，不是平常的列表看板。
兩者的主客順序 **相反**:

* 列表看板: 上方是客隊、下方標 [主]。
* 單場詳細頁: **主隊在前、客隊在後**（無 [主] 標記）。

若照列表看板的慣例讀，今天兩場的主客會 **全部顛倒** ——
主場優勢乘數與九局下不打的邏輯都會反向，是會實質改變定價的錯誤。

已逐場對照 npb.jp 官方賽程確認:

    DeNA 竹田祐  @ 阪神 大竹耕太郎     甲子園        18:00
    巨人 小笠原慎之介 @ 広島 森翔平      マツダスタジアム   18:00

官方 9/6 預告先發公示完整可取得，四名先發全數與看板一致。

其餘四場（中日@養樂多 17:00、火腿@樂天 16:00、羅德@歐力士 13:00、
西武@軟銀 13:00）未提供盤口，且多數已開賽，不納入。

先發樣本
--------
**竹田祐 (DeNA) 5 場 22.1 局、失分率 8.46** —— 低於 25 局門檻，
`starter_stats_known` 記為 False，該場不可推薦。

姓名比對
--------
廣島先發 **森翔平** 又一次出現（8/13 同姓誤配的當事人，廣島另有
森下暢仁、森浦大輔）。本檔用官方全名做 **精確** 比對（`==`），
比對失敗直接報錯而非退回子字串，避免重演。
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

DATE = "2026-09-06"
DATA_AS_OF = "2026-09-06 17:15 JST (UTC 08:15)"

GAMES = [
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="橫濱DeNA灣星", home_team="阪神虎",
        away_starter="竹田祐 (右)", home_starter="大竹耕太郎 (左)",
        venue="甲子園 (露天)",
        # 看板上讓分標在阪神列 —— 阪神是主隊且為讓分方。
        handicap_raw="1+10", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6.5", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-80", f5_total_raw="3-75",
        # 使用者於 2026-08-13 確認: 裸小數就是字面上的半球盤，不會走盤。
        attested_fields=frozenset({"total"}),
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="讀賣巨人", home_team="廣島鯉魚",
        away_starter="小笠原慎之介 (左)", home_starter="森翔平 (左)",
        venue="マツダスタジアム (露天)",
        # 看板上讓分標在巨人列 —— 巨人是客隊且為讓分方。
        handicap_raw="0-20", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6+75", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-20", f5_total_raw="3-50",
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
    "甲子園 (露天)": "甲子園",
    "マツダスタジアム (露天)": "マツダスタジアム",
}

OPEN_AIR = {"甲子園", "マツダスタジアム"}

NEUTRAL_PARK_FACTOR = 1.0
"""配適資料裡沒有的球場採用的中性值。今日未用到。"""


def park_factor(game: BoardGame) -> float:
    """球場係數；資料不足的球場退回中性值並由門檻揭露。"""
    return cal.PARK_FACTORS_2026.get(PARK_KEY[game.venue], NEUTRAL_PARK_FACTOR)


DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限。今天只有兩場有盤口，用不到上限。"""

OPEN_AIR_MIN_EV = GATE_OPEN_AIR_MIN_EV
"""露天球場的 EV 門檻，由 `bethero.gates` 統一定義（2026-09-02 起 = 0.04）。"""

STARTED: set[str] = set()
"""本報告產出時 (17:15 JST) 兩場皆未開賽，18:00 開打。"""

LINE_MOVES = {}
"""本日只取得單一時點的盤口，無移動可比對。"""

WEATHER = {
    "甲子園": "露天。未取得逐時風向／氣溫預報",
    "マツダスタジアム": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。今日 竹田祐 22.1 局未達標。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。"""

# (顯示名, 收縮後失分率係數, 今日預期局數, 說明, 季內 IP/G)
STARTERS = {
    "DeNA": ("竹田祐", 1.336, 4.47,
             "5 場 22.1 局 防禦率 6.04、**失分率 8.46** —— "
             "低於 25 局門檻，係數已重收縮但仍是本日最差", 4.47),
    "阪神": ("大竹耕太郎", 1.016, 5.78,
             "15 場 86.2 局 防禦率 2.80（失分率 3.43）、僅 14 四球", 5.78),
    "巨人": ("小笠原慎之介", 0.843, 6.14,
             "7 場 43 局 防禦率 2.30、失分全為自責、僅 7 四球 —— 本日最佳", 6.14),
    "広島": ("森翔平", 0.922, 5.74,
             "13 場 74.2 局 防禦率 3.01（失分率 3.13）、22 四球", 5.74),
}

STARTER_IP = {"DeNA": 22.3, "阪神": 86.7, "巨人": 43.0, "広島": 74.7}

ROLE_CHANGED: set[str] = set()
"""今日無季中角色轉換者。"""

BULLPEN_NOTE = {
    "DeNA": "9/5 用 4 人（3-2 險勝）—— 正常",
    "阪神": "9/5 用 4 人（2-3 敗）—— 正常",
    "巨人": "9/5 打滿延長 11 局、用 6 人（10-5 勝）—— **最吃緊**",
    "広島": "9/5 打滿延長 11 局、用 6 人（5-10 敗）—— **最吃緊**",
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
            f"校準已更新到 9/5 收盤（{cal.SAMPLE_GAMES} 場）。"
            f"聯盟每隊每場得分 {cal.LEAGUE_RPG:.4f}、主場係數 {cal.HOME_EDGE:.4f}。",
            "**今天只有兩場提供盤口，而且兩場都不下注。**"
            "其餘四場（中日@養樂多 17:00、火腿@樂天 16:00、羅德@歐力士 13:00、"
            "西武@軟銀 13:00）未提供盤口且多數已開賽，不納入。",
            "⚠️ **看板格式改了，主客順序與平常相反。**"
            "今天提供的是 **單場詳細頁**（主隊在前、客隊在後、無 [主] 標記），"
            "不是平常的列表看板（客隊在上、主隊在下標 [主]）。"
            "若照列表看板的慣例讀，兩場的主客會 **全部顛倒** —— "
            "主場優勢乘數與九局下不打的邏輯都會反向，是會實質改變定價的錯誤。"
            "已逐場對照 npb.jp 官方賽程確認：DeNA @ 阪神（甲子園）、"
            "巨人 @ 廣島（マツダ），四名先發也與官方公示全數一致。",
            "**DeNA @ 阪神 的 +5.8% 被先發樣本門檻擋下**："
            "DeNA 先發竹田祐 5 場 22.1 局、失分率 8.46，低於 25 局門檻，"
            "`starter_stats_known` 記為 False。收縮已把他的 8.46 拉到係數 1.336，"
            "但 22 局就是不足以定價 —— 這道門檻不可放棄。",
            "**巨人 @ 廣島 的 +2.4% 未達 +4% 門檻**，"
            "即使露天溢價已於 9/2 撤除也一樣不夠。",
            "廣島先發 **森翔平** 又一次出現（8/13 同姓誤配的當事人，"
            "廣島另有森下暢仁、森浦大輔）。本檔用官方全名做 **精確** 比對，"
            "比對失敗直接報錯而非退回子字串。",
            "**追蹤中的訊號**：9/5 收盤時「已下注 − 未下注」的偏誤差距來到 "
            "**1.5 個標準誤**（8/28 起是 1.7 → 0.9 → 0.9 → 1.2 → 1.5，"
            "最近四次單向上升）；押大分 37 場「實際−模型」−1.04。"
            "兩者都未達 2 個標準誤故維持不動作，但若「已下注 vs 未下注」"
            "觸及 2 個標準誤，應停止依現行方式下注並回頭改模型。",
            "**得分水位仍不調整**：未下注對照組（55 場）的「實際 − 盤口」"
            "為 −0.08 分，104 場的整體偏誤 +0.07 分（0.2 個標準誤）。",
            "讓分與上半場盤全數不定價。理由是結構性的：模型的 Var(分差) 被"
            "共享環境因子壓窄約 2.3 倍，且數學上與 dispersion_k 無關。"
            "見 analysis/diagnose_margin.py。",
        ],
        sources=[
            "https://npb.jp/announcement/starter/（2026-09-06 預告先發公示）",
            "https://npb.jp/games/2026/schedule_09_detail.html"
            "（賽程、9/5 比分、**主客隊別與球場欄位** —— 用來校正看板的顯示順序）",
            "https://npb.jp/bis/2026/stats/idp1_<team>.html（個人投手成績）",
            "賠率：使用者提供之單場詳細頁截圖（2026-09-06，兩場）",
        ],
    )


if __name__ == "__main__":
    print(build_report().render())
