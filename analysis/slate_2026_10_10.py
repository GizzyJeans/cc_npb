"""2026-10-10 クライマックスシリーズ 第一階段 第 1 戰 —— 季後賽定價。

執行: ``python3 analysis/slate_2026_10_10.py``

⚠️ 這是 **季後賽**，使用者明確要求定價（「季後賽」）。先讀這段
-------------------------------------------------------------
1. **模型沒有對季後賽校準過。** 係數全來自例行賽 858 場。季後賽是王牌先發、
   牛棚全力投入、短期決戰 —— 模型表達不了。
2. **四隊牛棚都休了 3-8 天**，季後賽又會把最好的後援投手集中使用。例行賽的牛棚
   係數是整季平均（含敗戰處理投手），**很可能高估季後賽的失分** —— 也就是
   大分的 EV 可能被高估。
3. **模型與盤口的分歧本來就不可信**（`analysis/market-shrinkage.md`，
   例行賽定價當時的值 β ≈ 1.26、3.1 個標準誤）。季後賽在模型的校準範圍之外，
   只會更不可信。
4. 門檻與模型照舊、未改（使用者尚未決定）。結算記在 `settle.POSTSEASON`，
   **不混進** 例行賽的 scorecard 與驗證腳本。

查證結果
--------
* 兩場的對戰、球場、主客、開賽時間（14:00 JST = 13:00 台北）與 npb.jp 相符。
* 看板未列先發，採 npb.jp 予告先発: 井上温大 vs 東克樹、平良海馬 vs 有原航平。
  四人都是整季先發（103-161 局），沒有任何資料門檻被觸發。
* 這家看板的版面不同（讓分數字掛在讓分方那一列）: 西武 讓 1-25、DeNA 讓 1+70。
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

DATE = "2026-10-10"
DATA_AS_OF = "2026-10-10 10:52 JST (UTC 01:52)"

T = "14:00 JST（看板 13:00 台北）"

POSTSEASON = True
"""季後賽 —— 結算記在 analysis.settle.POSTSEASON，與例行賽 LEDGER 分開。"""

GAMES = [
    BoardGame(
        date=DATE, start_time=T,
        away_team="日本火腿", home_team="西武獅",
        away_starter="有原航平 (右)", home_starter="平良海馬 (右)",
        venue="ベルーナドーム (巨蛋)",
        handicap_raw="1-25", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6+50", over_hk=0.930, under_hk=0.930,
    ),
    BoardGame(
        date=DATE, start_time=T,
        away_team="橫濱DeNA灣星", home_team="讀賣巨人",
        away_starter="東克樹 (左)", home_starter="井上温大 (左)",
        venue="東京ドーム (巨蛋)",
        handicap_raw="1+70", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="5+25", over_hk=0.930, under_hk=0.930,
    ),
]

JP = {
    "日本火腿": "日本ハム", "西武獅": "西武",
    "橫濱DeNA灣星": "DeNA", "讀賣巨人": "巨人",
}
PARK_KEY = {
    "ベルーナドーム (巨蛋)": "ベルーナドーム",
    "東京ドーム (巨蛋)": "東京ドーム",
}

OPEN_AIR: set[str] = set()
"""兩座都是巨蛋。"""

NEUTRAL_PARK_FACTOR = 1.0
"""配適資料裡沒有的球場採用的中性值。今日未用到。"""


def park_factor(game: BoardGame) -> float:
    return cal.PARK_FACTORS_2026.get(PARK_KEY[game.venue], NEUTRAL_PARK_FACTOR)


DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限。"""

OPEN_AIR_MIN_EV = GATE_OPEN_AIR_MIN_EV
"""露天球場的 EV 門檻，由 `bethero.gates` 統一定義（2026-09-02 起 = 0.04）。今日未用到。"""

STARTED: set[str] = set()
"""本報告產出時 (10:52 JST / 01:52 UTC) 兩場皆未開賽，距 14:00 JST 約 3 小時。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER: dict[str, str] = {}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。今日四人全部通過。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。今日未用到。"""

# (顯示名, 收縮後失分率係數, 今日預期局數, 說明, 季內 IP/G)
STARTERS = {
    "西武": ("平良海馬", 0.601, 6.35,
             "23 場 146.0 局 失分率 **1.54** —— 本日最佳、每場 6.3 局", 6.35),
    "日本ハム": ("有原航平", 1.246, 6.08,
                "17 場 103.1 局 失分率 **5.14** —— 本日最差、每場 6.1 局", 6.08),
    "巨人": ("井上温大", 0.754, 6.39,
             "23 場 147.0 局 失分率 2.39、每場 6.4 局", 6.39),
    "DeNA": ("東克樹", 0.820, 6.45,
             "25 場 161.1 局 失分率 2.79、每場 6.5 局", 6.45),
}

STARTER_IP = {"西武": 146.0, "日本ハム": 103.3, "巨人": 147.0, "DeNA": 161.3}

ROLE_CHANGED: set[str] = set()
"""今日無角色轉換案例 —— 四人都是整季先發。"""

BULLPEN_NOTE = {
    "西武": "例行賽最後一場 10/6，已休 3 天 —— 全員可用",
    "日本ハム": "例行賽最後一場 10/1，已休 8 天 —— 全員可用",
    "巨人": "例行賽最後一場 10/3，已休 6 天 —— 全員可用；牛棚係數為全聯盟最佳",
    "DeNA": "例行賽最後一場 10/4，已休 5 天 —— 全員可用",
}

ENV = NPBEnvironment(
    league_rpg=cal.LEAGUE_RPG,
    dispersion_k=cal.DISPERSION_K,
    home_edge=cal.HOME_EDGE,
    extras_resolve_rate=cal.EXTRAS_RESOLVE_RATE,
    source=f"npb.jp 2026 例行賽逐場比分 {cal.SAMPLE_GAMES} 場",
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
        risks.append(
            "⚠️ **季後賽**：牛棚休了 3-8 天、最好的後援投手會被集中使用，例行賽的"
            "牛棚係數是整季平均 —— 模型很可能 **高估** 失分，大分的 EV 可能被高估"
        )
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
            lineup_note="10:52 JST 尚未公布，依使用者指示略過",
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
        f"校準: 例行賽全季 {cal.SAMPLE_GAMES} 場（{cal.SAMPLE_RANGE}）。"
        f"聯盟每隊每場 {cal.LEAGUE_RPG:.4f} 分、主場乘數 {cal.HOME_EDGE:.4f}。",
        "⚠️ **季後賽**：使用者明確要求定價。模型沒有對季後賽校準過 —— 王牌先發、"
        "牛棚全力投入、短期決戰都表達不了。",
        "⚠️ **這些 EV 不可信**：例行賽的市場收縮檢定顯示模型與盤口的分歧幾乎全是"
        "模型的誤差（β ≈ 1.26，3.1 個標準誤）；季後賽在校準範圍之外，只會更不可信。"
        "建議不要實際下注。門檻與模型照舊、未改。",
        "四隊牛棚都休了 3-8 天，季後賽會集中使用最好的後援投手 —— "
        "模型的牛棚係數是例行賽整季平均，很可能高估失分。",
        "四位先發都是整季先發（103-161 局），沒有資料門檻被觸發。看板未列先發，"
        "採 npb.jp 予告先発。",
        "結算記在 `analysis.settle.POSTSEASON`，不混進例行賽的 scorecard 與驗證腳本。",
        "全場讓分仍不定價，理由見各場風險欄。",
    ]
    # 校準過期時自動置頂警告 —— 見 config.calibration_2026.freshness_note
    stale = cal.freshness_note(DATE)
    if stale and cal.SAMPLE_GAMES == 858:
        stale = None   # 例行賽已全部打完、10/9 無賽事: 校準是完整的，不是過期
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
