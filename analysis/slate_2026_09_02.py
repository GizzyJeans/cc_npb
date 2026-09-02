"""2026-09-02 NPB 五場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_09_02.py``

**這是露天 EV 門檻降回 +4% 後的第一份報告。**
`bethero.gates.OPEN_AIR_MIN_EV` 已於 2026-09-02 由 0.07 改為 0.04，
理由是 scorecard 追蹤 88 場後露天的模型誤差 (-0.08, n=43) 反而比巨蛋
(+0.25, n=45) 還小 —— 門檻的前提不成立。見該常數的 docstring 與
analysis/backtest_open_air_threshold.py。

⚠️ 又是兩個非主場球場
--------------------
連續第二天出現，一樣是讀官方公示的球場欄位才發現:

* **DeNA @ 巨人 在 京セラD大阪**（連兩天），不是東京巨蛋。
  係數 0.881 vs 1.010 —— 差 13%。
* **歐力士 @ 樂天 在 盛岡**（昨天是秋田），不是樂天生命公園。
  盛岡本季 **只有 1 場**，係數 0.9884 幾乎完全收縮到 1.0，
  不是可用的估計 —— `park_factor_known` 記為 False。

樂天連兩天在不同的地方球場辦主場賽，兩天的球場係數都不可用。

先發樣本與角色
--------------
* **岩嵜翔 (歐力士)**: 17 場 **15.1 局**、失分率 7.04、季內每場 0.90 局。
  8/10 之後四次登板 **全是後援**（第 3-5 任、各投 1 局、11-17 球）。
  今天是本季首度先發，用法幾乎確定是開局投手，取 2.00 局。
  15.1 局遠低於 25 局門檻 —— 該場 **同時** 缺球場係數與先發成績，
  是今天資料最差的一場，與昨天的秋田那場同型。
* **鈴木健矢 (廣島)**: 季中由後援轉先發（8/26 已處理）。季內 IP/G 1.83
  仍是混合值，近期先發 5 局 76 球，取 5.50。
* **達孝太 (火腿)**: 同為轉先發（8/26 已處理）。季內 IP/G 4.29，
  近期先發 7 局 102 球，取 6.67。
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

DATE = "2026-09-02"
DATA_AS_OF = "2026-09-02 17:20 JST (UTC 08:20)"

GAMES = [
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="廣島鯉魚", home_team="中日龍",
        away_starter="鈴木健矢 (右)", home_starter="涌井秀章 (右)",
        venue="バンテリンドーム (巨蛋)",
        handicap_raw="1+10", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6-50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-70", f5_total_raw="3-75",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="福岡軟銀鷹", home_team="日本火腿",
        away_starter="上沢直之 (右)", home_starter="達孝太 (右)",
        venue="エスコンＦ (巨蛋)",
        handicap_raw="1+10", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="8+25", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-30", f5_total_raw="4-50",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="歐力士猛牛", home_team="東北樂天金鷲",
        away_starter="岩嵜翔 (右)", home_starter="荘司康誠 (右)",
        # ⚠️ 中性場地，本季僅 1 場，球場係數不可用。
        venue="盛岡 (露天・中性場地)",
        handicap_raw="1+40", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7平", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-50", f5_total_raw="4+75",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="阪神虎", home_team="養樂多燕子",
        away_starter="西勇輝 (右)", home_starter="山野太一 (左)",
        venue="神宮 (露天)",
        handicap_raw="1+35", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7-75", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-40", f5_total_raw="4+25",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="橫濱DeNA灣星", home_team="讀賣巨人",
        away_starter="東克樹 (左)", home_starter="西舘勇陽 (右)",
        # ⚠️ 巨人的主場比賽連兩天辦在京セラD大阪，不是東京巨蛋。
        venue="京セラD大阪 (巨蛋・中性場地)",
        handicap_raw="1+50", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6-50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-50", f5_total_raw="3-50",
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
    "バンテリンドーム (巨蛋)": "バンテリンドーム",
    "エスコンＦ (巨蛋)": "エスコンＦ",
    "盛岡 (露天・中性場地)": "盛岡",
    "神宮 (露天)": "神宮",
    "京セラD大阪 (巨蛋・中性場地)": "京セラD大阪",
}

OPEN_AIR = {"盛岡", "神宮"}

NEUTRAL_PARK_FACTOR = 1.0
"""配適資料裡沒有 (或場次太少不足以估計) 的球場採用的中性值。"""


def park_factor(game: BoardGame) -> float:
    """球場係數；資料不足的球場退回中性值並由門檻揭露。"""
    return cal.PARK_FACTORS_2026.get(PARK_KEY[game.venue], NEUTRAL_PARK_FACTOR)


DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限，比 Bankroll 的 5,000 更緊。"""

OPEN_AIR_MIN_EV = GATE_OPEN_AIR_MIN_EV
"""露天球場的 EV 門檻，改由 `bethero.gates` 統一定義。

**2026-09-02 起等於一般門檻 0.04** —— 原本的 +7% 已撤除。
撤除理由與回溯檢驗見 `bethero.gates.OPEN_AIR_MIN_EV` 的 docstring
與 analysis/backtest_open_air_threshold.py。本檔不再各寫一次，
避免同一條政策散在十幾個檔案裡各自漂移。"""

STARTED: set[str] = set()
"""本報告產出時已開賽的場次 (以主隊記)。今日五場全部 18:00 開賽，無。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "盛岡": "露天，中性場地。未取得逐時預報",
    "神宮": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。"""

# (顯示名, 收縮後失分率係數, **今日預期局數**, 說明, 季內 IP/G)
STARTERS = {
    "広島": ("鈴木健矢", 0.806, 5.50,
             "28 場 51.1 局 防禦率 2.10；季中由後援轉先發，"
             "季內 IP/G 1.83 是混合值，近期先發 5 局 76 球", 1.83),
    "中日": ("涌井秀章", 0.899, 5.74,
             "9 場 51.2 局 防禦率 2.79、**僅 4 四球**", 5.74),
    "ソフトバンク": ("上沢直之", 0.957, 6.02,
                  "17 場 102.1 局 防禦率 2.64（失分率 3.34）", 6.02),
    "日本ハム": ("達孝太", 0.895, 6.67,
                "23 場 98.2 局 防禦率 2.92；同為季中轉先發，"
                "近期先發 7 局 102 球", 4.29),
    "オリックス": ("岩嵜翔", 1.251, 2.00,
                "17 場 **15.1 局**、失分率 7.04、季內每場 0.90 局；"
                "8/10 後四次登板全是後援（第 3-5 任、各 1 局）——"
                "今天是本季首度先發，用法幾乎確定是開局投手", 0.90),
    "楽天": ("荘司康誠", 1.127, 6.15,
             "20 場 123 局 防禦率 4.17、失分率 4.32、34 四球 —— 本日最差", 6.15),
    "阪神": ("西勇輝", 0.966, 5.00,
             "7 場 35 局 防禦率 2.57（失分率 2.83）；樣本偏薄已重收縮", 5.00),
    "ヤクルト": ("山野太一", 0.742, 6.42,
                "20 場 128.1 局 防禦率 2.10、每場 6.4 局 —— 本日最佳", 6.42),
    "DeNA": ("東克樹", 0.838, 6.50,
             "20 場 130 局 防禦率 2.35、每場 6.5 局、僅 18 四球", 6.50),
    "巨人": ("西舘勇陽", 0.904, 5.00,
             "8 場 38.2 局 防禦率 2.79、失分全為自責，但 16 四球偏多", 4.83),
}

STARTER_IP = {
    "広島": 51.3, "中日": 51.7, "ソフトバンク": 102.3, "日本ハム": 98.7,
    "オリックス": 15.3, "楽天": 123.0, "阪神": 35.0, "ヤクルト": 128.3,
    "DeNA": 130.0, "巨人": 38.7,
}

ROLE_CHANGED = {"広島", "日本ハム", "オリックス"}
"""季中由後援轉先發 (鈴木健矢、達孝太) 或首度先發 (岩嵜翔)。
他們的失分率都是在較短的登板中累積的，通常優於長局數先發，
壓力測試把這三隊改用季內守備係數以量化方向。"""

BULLPEN_NOTE = {
    "広島": "9/1 用 4 人 —— 正常",
    "中日": "9/1 用 5 人（被打 5 分）—— 略吃緊",
    "ソフトバンク": "9/1 用 4 人（僅得 1 分）—— 正常",
    "日本ハム": "9/1 用 3 人（2-1 險勝）—— 充分",
    "オリックス": "9/1 用 5 人（被打 5 分）—— 略吃緊",
    "楽天": "9/1 用 3 人（5-1 勝）—— 充分",
    "阪神": "9/1 用 4 人（6-2 勝）—— 正常",
    "ヤクルト": "9/1 用 5 人（被打 6 分）—— 略吃緊",
    "DeNA": "9/1 用 4 人 —— 正常",
    "巨人": "9/1 用 4 人（4-3 險勝）—— 正常",
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
            f"校準已更新到 9/1 收盤（{cal.SAMPLE_GAMES} 場）。"
            f"聯盟每隊每場得分 {cal.LEAGUE_RPG:.4f}、主場係數 {cal.HOME_EDGE:.4f}。",
            "**十場先發全數與 npb.jp 9/2 官方預告先發公示一致。**"
            "只有五場 —— 西武與羅德今日輪空。",
            "⚠️ **連續第二天出現非主場球場**，一樣是讀官方公示的球場欄位才發現："
            "DeNA @ 巨人 在 **京セラD大阪**（係數 0.881）而非東京巨蛋（1.010），"
            "差 13%；歐力士 @ 樂天 在 **盛岡**（昨天是秋田）而非樂天生命公園。"
            "樂天連兩天在不同的地方球場辦主場賽，兩天的球場係數都不可用。",
            "⚠️ **盛岡本季只有 1 場**，係數 0.9884 幾乎完全收縮到 1.0，"
            "不是可用的估計 —— `park_factor_known` 記為 False。"
            "該場同時有先發樣本不足（岩嵜翔 15.1 局），兩個缺口，"
            "EV +28.2% 全日最高但不可下注。",
            "**岩嵜翔（歐力士）今天是本季首度先發**：17 場 15.1 局、失分率 7.04、"
            "季內每場 0.90 局，8/10 後四次登板全是後援（第 3-5 任、各投 1 局、"
            "11-17 球）。用法幾乎確定是開局投手，今日局數取 2.00。",
            "**這是露天 EV 門檻降回 +4% 後的第一份報告。**"
            "門檻已於 2026-09-02 由 0.07 改為 0.04，並移進 `bethero.gates` "
            "統一定義，不再散在每日檔案裡。撤除理由是門檻的前提不成立：",
            "  scorecard 追蹤 88 場後，露天的模型誤差 −0.08（n=43）反而比巨蛋 "
            "+0.25（n=45）**還小**，差距 0.4 個標準誤。"
            "不是因為它讓我們少賺 —— 回溯檢驗顯示這個改動在歷史上會 **少賺 2,000**。"
            "用 2 注的輸贏決定規則，和當初用零證據設立它是同一個錯誤。",
            "**而今天就示範了回溯檢驗的另一個發現：真正的約束是單日額度。**"
            "阪神 @ 養樂多 的 +4.2% 在舊門檻下會被擋掉，新門檻下數值面通過了 —— "
            "但當天已有三個 EV 更高的部位把 3,000 用完，它還是下不了。"
            "門檻只在「合格部位少於三個」的日子才會實際咬到。",
            "露天場的 `weather_known` 仍維持 False 並印在「已放棄的門檻」欄。"
            "放棄的是門檻，不是揭露。",
            "讓分與上半場盤全數不定價。理由是結構性的：模型的 Var(分差) 被"
            "共享環境因子壓窄約 2.3 倍，且數學上與 dispersion_k 無關。"
            "見 analysis/diagnose_margin.py。",
        ],
        sources=[
            "https://npb.jp/announcement/starter/（2026-09-02 預告先發公示，含球場欄位）",
            "https://npb.jp/games/2026/schedule_09_detail.html（9 月賽程）",
            "https://npb.jp/bis/2026/stats/idp1_<team>.html（個人投手成績）",
            "https://npb.jp/scores/2026/<date>/<slug>/box.html"
            "（牛棚用球數、逐場先發順位 —— 用來判定角色轉換）",
            "賠率：使用者提供之看板截圖（2026-09-02）",
        ],
    )


if __name__ == "__main__":
    print(build_report().render())
