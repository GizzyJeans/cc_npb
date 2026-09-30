"""2026-09-30 NPB 看板兩場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_09_30.py``

兩場都是 18:00 JST（17:00 台北）。看板在 17:50 JST 收到，距開賽約 10 分鐘。
看板把兩場標成「滾球」，但 npb.jp 顯示兩場都還是【試合開始前】 —— 盤口是賽前盤。
養樂多 @ 阪神 是 9/29 雨天中止那場的補賽（24 回戦）。

⚠️ 先讀這段
-----------
2026-09-30 結算時「已下注 vs 未下注」偏誤差距到了 2 個標準誤，
`analysis/validate_market_shrinkage.py` 顯示 **模型與盤口的分歧幾乎全是模型的誤差**
（β ≈ 1.2，定價當時的值 2.9 個標準誤）。依那個結果，本檔算出的 EV **不可信**。
使用者尚未決定要不要暫停下注或改模型，所以本檔照原流程定價、門檻也未改。

查證結果
--------
* 兩場的對戰、球場、主客與先發，全部與 npb.jp 相符（樂天 @ 羅德 的比賽頁
  已公布先發打線與バッテリー: ルケーシー、荘司）。
* 四位先發的姓名與投球側 4/4 相符。
* ルケーシー（羅德）本季 4 場 22.0 局，仍未達 25 局門檻 —— 羅德 @ 樂天 最多只能觀察。
* 羅德 @ 樂天 的大小盤兩邊賠率不對稱（大 0.880、小 0.980），以比例去水處理。
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

DATE = "2026-09-30"
DATA_AS_OF = "2026-09-30 17:53 JST (UTC 08:53)"

T = "18:00 JST（看板 17:00 台北）"

GAMES = [
    BoardGame(
        date=DATE, start_time=T,
        away_team="養樂多燕子", home_team="阪神虎",
        away_starter="奥川恭伸 (右)", home_starter="高橋遥人 (左)",
        venue="甲子園 (露天)",
        handicap_raw="2+50", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="5-75", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1+40", f5_total_raw="3+25",
    ),
    BoardGame(
        date=DATE, start_time=T,
        away_team="千葉羅德", home_team="東北樂天鷹",
        away_starter="盧切西 (左)", home_starter="莊司康誠 (右)",
        venue="楽天モバイル (露天)",
        handicap_raw="1+30", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6-50", over_hk=0.880, under_hk=0.980,
    ),
]

JP = {
    "養樂多燕子": "ヤクルト", "阪神虎": "阪神",
    "千葉羅德": "ロッテ", "東北樂天鷹": "楽天",
}
PARK_KEY = {
    "甲子園 (露天)": "甲子園",
    "楽天モバイル (露天)": "楽天モバイル",
}

OPEN_AIR = {"甲子園", "楽天モバイル"}
"""兩座都是露天。"""

NEUTRAL_PARK_FACTOR = 1.0
"""配適資料裡沒有的球場採用的中性值。今日未用到。"""


def park_factor(game: BoardGame) -> float:
    return cal.PARK_FACTORS_2026.get(PARK_KEY[game.venue], NEUTRAL_PARK_FACTOR)


DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限。今日只有這一張盤。"""

OPEN_AIR_MIN_EV = GATE_OPEN_AIR_MIN_EV
"""露天球場的 EV 門檻，由 `bethero.gates` 統一定義（2026-09-02 起 = 0.04）。"""

STARTED: set[str] = set()
"""本報告產出時 (17:53 JST / 08:53 UTC) 兩場皆未開賽（npb.jp【試合開始前】）。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "甲子園": "露天。未取得逐時風向／氣溫預報（前一天 9/29 此處雨天中止）",
    "楽天モバイル": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。今日 ルケーシー 22.0 局未達。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。今日未用到。"""

# (顯示名, 收縮後失分率係數, 今日預期局數, 說明, 季內 IP/G)
STARTERS = {
    "ヤクルト": ("奥川恭伸", 0.816, 6.82,
                "22 場 150.0 局 失分率 3.06、每場 6.8 局", 6.82),
    "阪神": ("髙橋遥人", 0.768, 6.86,
             "22 場 151.0 局 失分率 **2.21** —— 本日最佳、每場 6.9 局", 6.86),
    "ロッテ": ("ルケーシー", 0.943, 5.50,
              "**本季僅 4 場 22.0 局**（失分率 2.86、每場 5.5 局）—— 未達 25 局門檻", 5.50),
    "楽天": ("荘司康誠", 1.021, 6.29,
             "24 場 151.0 局 失分率 3.75、每場 6.3 局", 6.29),
}

STARTER_IP = {"ヤクルト": 150.0, "阪神": 151.0, "ロッテ": 22.0, "楽天": 151.0}

ROLE_CHANGED: set[str] = set()
"""今日無角色轉換案例 —— 四人的季內 IP/G 都在 5.50-6.86 之間。"""

BULLPEN_NOTE = {
    "ヤクルト": "9/27 牛棚 6 人 121 球（0-11 敗）；9/28 休兵、9/29 雨天中止 —— 已休兩天",
    "阪神": "9/26 之後 9/27、9/28 休兵、9/29 雨天中止 —— 已休三天，充分",
    "ロッテ": "9/29 吉川 5 局 72 球，牛棚 4 人 60 球（6-3 勝）—— 正常",
    "楽天": "9/29 伊藤樹 6 局 106 球，牛棚 1 人 51 球（3-6 敗）—— 正常；但牛棚係數為全聯盟最差",
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
            lineup_note="樂天 @ 羅德 已公布先發打線（npb.jp），未納入模型；阪神場未查",
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
        "⚠️ **這些 EV 不可信**：9/30 結算時「已下注 vs 未下注」偏誤差距到了 2 個標準誤，"
        "`analysis/market-shrinkage.md` 顯示模型與盤口的分歧幾乎全是模型的誤差"
        "（β ≈ 1.2，2.9 個標準誤）。建議暫停實際下注，使用者尚未決定 —— 本檔照原流程定價。",
        "兩場都是 18:00 JST（17:00 台北），看板在 17:50 JST 收到，距開賽約 10 分鐘。"
        "看板標成「滾球」，但 npb.jp 顯示兩場都還是【試合開始前】，盤口是賽前盤。",
        "養樂多 @ 阪神 是 9/29 雨天中止那場的補賽。",
        "四位先發姓名與投球側 4/4 相符。ルケーシー 本季 22.0 局，仍未達 25 局門檻。",
        "羅德 @ 樂天 大小盤賠率不對稱（大 0.880、小 0.980），以比例去水處理。",
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
