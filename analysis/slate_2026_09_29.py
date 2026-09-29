"""2026-09-29 NPB 看板四場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_09_29.py``

四場都是 18:00 JST（17:00 台北）。看板在 17:33 JST 收到，距開賽只有 27 分鐘。

查證結果
--------
* 四場的對戰、球場、主客與先發，全部與 npb.jp 賽程頁的「先發」欄相符。
* **八位先發的姓名與投球側 8/8 相符**（npb.jp 的 `*` 左投記號與看板一致）。
* **四位先發未達 25 局門檻**，所以四場裡只有 **廣島 @ 巨人** 有機會推薦:

  - 中村優斗（養樂多）一軍 2 場 3.0 局；二軍 16 場 38 局、每場 2.38 局。
    兩級都是短局數用法 —— 列入 `ROLE_CHANGED`，預期局數採二軍 2.38。
  - 東松快征（歐力士）一軍 6 場 9.0 局，唯一一次先發是 9/22 的 5 局 86 球，
    預期局數採 5.00。二軍 20 場、每場 3.07 局。
  - 吉川悠斗（羅德）一軍 2 場 9.0 局失 10 分。
  - 伊藤樹（樂天）5 場 24.0 局 —— 只差 1 局。門檻就是門檻，不因為差一點而放寬。

⚠️ 西武牛棚兩天 242 球
---------------------
9/28 先發隅田知一郎只投 0.1 局就退場，牛棚 5 人吃了 162 球、8.2 局;
前一天 9/27 冨士 2.2 局退場，牛棚 6 人 80 球。一如既往 **只揭露、不調整** ——
牛棚疲勞假說在 113 場全樣本上是 0.3 個標準誤、方向相反。
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

DATE = "2026-09-29"
DATA_AS_OF = "2026-09-29 17:36 JST (UTC 08:36)"

T = "18:00 JST（看板 17:00 台北）"

GAMES = [
    BoardGame(
        date=DATE, start_time=T,
        away_team="養樂多燕子", home_team="阪神虎",
        away_starter="中村優斗 (右)", home_starter="大竹耕太郎 (左)",
        venue="甲子園 (露天)",
        handicap_raw="1-50", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6-25", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1+50", f5_total_raw="3-50",
    ),
    BoardGame(
        date=DATE, start_time=T,
        away_team="歐力士猛牛", home_team="西武獅",
        away_starter="東松快征 (左)", home_starter="平良海馬 (右)",
        venue="ベルーナドーム (巨蛋)",
        handicap_raw="1-65", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6.5", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1+50", f5_total_raw="3-75",
        # 純小數 = 字面上的半球盤，永不和局。使用者 2026-08-13 已目視確認。
        attested_fields=frozenset({"total"}),
    ),
    BoardGame(
        date=DATE, start_time=T,
        away_team="千葉羅德", home_team="東北樂天鷹",
        away_starter="吉川悠斗 (左)", home_starter="伊藤樹 (右)",
        venue="楽天モバイル (露天)",
        handicap_raw="1+20", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7-50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-70", f5_total_raw="4+50",
    ),
    BoardGame(
        date=DATE, start_time=T,
        away_team="廣島鯉魚", home_team="讀賣巨人",
        away_starter="玉村昇悟 (左)", home_starter="戸郷翔征 (右)",
        venue="東京ドーム (巨蛋)",
        handicap_raw="1+35", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6+50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-40", f5_total_raw="3-25",
    ),
]

JP = {
    "養樂多燕子": "ヤクルト", "阪神虎": "阪神",
    "歐力士猛牛": "オリックス", "西武獅": "西武",
    "千葉羅德": "ロッテ", "東北樂天鷹": "楽天",
    "廣島鯉魚": "広島", "讀賣巨人": "巨人",
}
PARK_KEY = {
    "甲子園 (露天)": "甲子園",
    "ベルーナドーム (巨蛋)": "ベルーナドーム",
    "楽天モバイル (露天)": "楽天モバイル",
    "東京ドーム (巨蛋)": "東京ドーム",
}

OPEN_AIR = {"甲子園", "楽天モバイル"}
"""ベルーナドーム、東京ドーム 視為巨蛋。"""

NEUTRAL_PARK_FACTOR = 1.0
"""配適資料裡沒有的球場採用的中性值。今日四場都在主要球場，未用到。"""


def park_factor(game: BoardGame) -> float:
    return cal.PARK_FACTORS_2026.get(PARK_KEY[game.venue], NEUTRAL_PARK_FACTOR)


DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限。今日只有這一張盤，全額可用。"""

OPEN_AIR_MIN_EV = GATE_OPEN_AIR_MIN_EV
"""露天球場的 EV 門檻，由 `bethero.gates` 統一定義（2026-09-02 起 = 0.04）。"""

STARTED: set[str] = set()
"""本報告產出時 (17:36 JST / 08:36 UTC) 四場皆未開賽，距 18:00 JST 約 24 分鐘。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "甲子園": "露天。未取得逐時風向／氣溫預報",
    "楽天モバイル": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。
今日四人未達: 中村優斗 3.0、東松快征 9.0、吉川悠斗 9.0、伊藤樹 24.0 局。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。今日未用到。"""

# (顯示名, 收縮後失分率係數, 今日預期局數, 說明, 季內 IP/G)
STARTERS = {
    "ヤクルト": ("中村優斗", 0.910, 2.38,
                "**一軍僅 2 場 3.0 局**（每場 1.5 局）；二軍 16 場 38 局、每場 2.38 局、"
                "失分率 5.45 —— 兩級都是短局數用法，預期局數採二軍值", 1.50),
    "阪神": ("大竹耕太郎", 1.024, 5.63,
             "17 場 95.2 局 失分率 3.39、每場 5.6 局", 5.63),
    "オリックス": ("東松快征", 1.198, 5.00,
                "**一軍 6 場僅 9.0 局**（失分率 7.00）；唯一一次先發是 9/22 的 5 局 86 球，"
                "預期局數採 5.00。二軍 20 場 61.1 局、每場 3.07 局", 1.50),
    "西武": ("平良海馬", 0.606, 6.32,
             "22 場 139.0 局 失分率 **1.55** —— 本日最佳、每場 6.3 局", 6.32),
    "ロッテ": ("吉川悠斗", 1.228, 4.50,
              "**一軍 2 場 9.0 局失 10 分**（每場 4.5 局）；二軍 13 場 50.2 局、失分率 3.02",
              4.50),
    "楽天": ("伊藤樹", 0.975, 4.80,
             "5 場 24.0 局 失分率 3.38、每場 4.8 局 —— **差 1 局未達 25 局門檻**；"
             "二軍 14 場 75 局、每場 5.36 局", 4.80),
    "巨人": ("戸郷翔征", 0.997, 5.49,
             "13 場 71.1 局 失分率 3.66、每場 5.5 局", 5.49),
    "広島": ("玉村昇悟", 0.903, 5.24,
             "14 場 73.1 局 失分率 2.95、每場 5.2 局", 5.24),
}

STARTER_IP = {
    "ヤクルト": 3.0, "阪神": 95.7, "オリックス": 9.0, "西武": 139.0,
    "ロッテ": 9.0, "楽天": 24.0, "巨人": 71.3, "広島": 73.3,
}

ROLE_CHANGED = {"ヤクルト"}
"""中村優斗 —— 一軍每場 1.5 局、二軍每場 2.38 局，兩級都是短局數用法。
今天名義上先發，實際上可能是短局數的開局; 預期局數採二軍 2.38
（blended_defence 的 0.35 下限會生效），壓力測試換球隊季內守備係數。

東松快征不列入: 9/22 已先發 5 局 86 球，是正在轉先發的投手，不是開局投手
（與 9/23 仲地礼亜的處理一致）。"""

BULLPEN_NOTE = {
    "ヤクルト": "9/27 牛棚 **6 人 121 球**（高橋 僅 2.2 局失 7 即退場；0-11 敗）；"
                "9/28 休兵 —— 已休一天",
    "阪神": "9/27、9/28 連休兩天 —— 充分",
    "オリックス": "9/27 牛棚 5 人 106 球（髙島 僅 2.2 局失 6 即退場；5-12 敗）；"
                "9/28 休兵 —— 已休一天；牛棚係數為全聯盟次差",
    "西武": "9/27 牛棚 6 人 80 球（冨士 僅 2.2 局）；9/28 隅田 **僅 0.1 局**即退場，"
            "牛棚 **5 人 162 球**、8.2 局（2-4 敗）—— **兩天 242 球，吃緊**",
    "ロッテ": "9/27 牛棚 3 人 39 球；9/28 ジャクソン 6.2 局 118 球，牛棚 3 人 59 球"
              "（3-8 敗）—— 正常",
    "楽天": "9/27 早川 7 局，牛棚 1 人 14 球；9/28 岸 5 局，牛棚 5 人 62 球 —— 正常；"
            "但牛棚係數為全聯盟最差",
    "巨人": "9/27 小笠原 5 局，牛棚 4 人 51 球（11-0 勝）；9/28 休兵 —— 充分；"
            "牛棚係數為全聯盟最佳",
    "広島": "9/27 栗林 7 局，牛棚 2 人 24 球；9/28 工藤 5 局，牛棚 4 人 70 球 —— 正常",
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
            out.append(f"{name}（季內 IP/G {season_ipg:.2f}，後援用法 → "
                       f"今日採用 {ip_gs:.2f} 局，權重大半交給牛棚）")
    return out


def stress_season_defence(game: BoardGame) -> GameModel:
    """把樣本不足與後援用法的先發，換成該隊季內守備係數。"""
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
        # 方向與價格一起取 —— 見 9/11 修正的 bug。
        side_key = "over" if label == "大分" else "under"
        side_hk = game.over_hk if label == "大分" else game.under_hk
        side_mkt = market[0] if label == "大分" else market[1]

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
        if changed:
            risks.append(
                "⚠️ **開局投手效應，模型無法表達**：`cal.OPENER_F5_EFFECT` 顯示"
                "計畫性開局投手的場次全場平均 7.43 分、正規先發對決 6.89 分"
                "（**差 +0.54 分**）。模型用固定比例切 lambda，表達不了"
                "「把失分往前搬」，本場預期總分可能偏低約半分 —— "
                "也就是這裡的小分 EV 可能被高估。"
                "（該組數字出自有 bug 的舊解析，方向應成立但數值待重算，故只揭露不套用。）"
            )
        if thin or changed:
            s_d = stress_season_defence(game).distributions()
            s_ev = evaluate(total_outcome_probs(game.total, s_d.total_pmf, side_key),
                            side_hk, Bankroll().total, side_mkt).ev
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
                head.append("後援用法而非先發：" + "、".join(changed))
            risks.append(
                "；".join(head)
                + "。逐隊方向：" + "；".join(bits)
                + f"。壓力測試：改用季內守備係數後預期總分 "
                  f"{s_d.expected_total():.2f}（原 {dists.expected_total():.2f}，"
                  f"{delta:+.2f}）、{label} EV {s_ev:+.1%}（原 {best.ev:+.1%}）"
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
            lineup_note="17:36 JST 尚未公布，依使用者指示略過",
            bullpen_note=f"{game.home_team}：{BULLPEN_NOTE[home]}；"
                         f"{game.away_team}：{BULLPEN_NOTE[away]}",
            park_weather_note=(
                f"球場係數 {park_factor(game):.3f}（2026 實測）。"
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

    notes = [
        f"校準涵蓋到 {cal.sample_through()} 收盤（{cal.SAMPLE_GAMES} 場）。"
        f"聯盟每隊每場 {cal.LEAGUE_RPG:.4f} 分、主場乘數 {cal.HOME_EDGE:.4f}。",
        "四場都是 18:00 JST（17:00 台北）。看板在 17:33 JST 收到，距開賽只有 **27 分鐘**。",
        "八位先發的 **姓名與投球側 8/8 相符**。",
        "⚠️ **四位先發未達 25 局門檻**（中村優斗 3.0、東松快征 9.0、吉川悠斗 9.0、"
        "伊藤樹 24.0 局），所以只有 **廣島 @ 巨人** 有機會推薦。伊藤樹只差 1 局 ——"
        "門檻就是門檻，不因為差一點而放寬。",
        "中村優斗一軍每場 1.5 局、二軍每場 2.38 局，列入角色轉換（短局數開局）處理。"
        "東松快征 9/22 已先發 5 局，採 5.00 局、不列入。",
        "⚠️ 西武牛棚兩天 242 球（9/28 隅田只投 0.1 局就退場，牛棚 162 球）。"
        "**只揭露、不調整** —— 牛棚疲勞假說在 113 場全樣本上是 0.3 個標準誤、方向相反。",
        "全場讓分與上半場盤仍不定價，理由見各場風險欄。",
    ]
    # 校準過期時自動置頂警告 —— 見 config.calibration_2026.freshness_note
    stale = cal.freshness_note(DATE)
    if stale:
        notes.insert(0, stale)

    return DailyReport(
        date=DATE,
        bankroll=Bankroll(),
        analyses=analyses,
        data_as_of=DATA_AS_OF,
        global_notes=notes,
    )


if __name__ == "__main__":
    print(build_report().render())
