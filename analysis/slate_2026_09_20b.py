"""2026-09-20 **第二張盤** —— 18:00 JST 的三場。

執行: ``python3 analysis/slate_2026_09_20b.py``

為什麼分成兩個檔
----------------
今天的看板分兩批到手: 先是 14:00 JST 的三場（見 `slate_2026_09_20.py`），
約五小時後才拿到 18:00 JST 的三場。兩批要共用 **同一個單日額度**，
所以這裡的 `DAILY_BUDGET` 是 **剩下的 2,000**，不是全額 3,000。

    上午盤  歐力士 @ 火腿 大分 8平  +26.3%  已投入 1,000
    本盤    可用餘額 **2,000**

沿用 2026-08-22 的作法（`slate_2026_08_22b.py` 當時的餘額是 1,000），
結算時 LEDGER 用 `"2026-09-20b"` 這個鍵，與上午盤分開記錄。

**上午那三場不重新定價。** 它們已於 14:00 JST 開賽（本檔產出時已過
三小時），賽前盤口不可覆核; 更重要的是，當時的推薦是在開賽前 90 分鐘
依當時可覆核的報價做出的，事後重算會改寫那個決定的紀錄。

查證結果
--------
* 三場的對戰、球場、主客與先發，全部與 npb.jp 賽程頁的「先發」欄相符。
* **六位先發的姓名與投球側 6/6 相符**。看板「傑克森」= npb.jp「ジャクソン」
  （羅德的外籍右投）。
* 六人全部越過 25 局門檻、也全部是先發用法（IP/G 4.90-6.53），
  **本盤同樣沒有任何門檻被觸發**。最薄的是竹田祐（DeNA）34.1 局 ——
  9/11 時他只有 27.2 局、只高出門檻 2.2 局，現在擴大到 9 局。

⚠️ 中日的牛棚昨晚被打爆
----------------------
9/19 中日 1-14 慘敗給巨人，先發中西聖輝 3.1 局就退場，
**牛棚四人吃了 112 球** —— 是當日全聯盟最重的。今天他們先發是大野雄大
（失分率 2.34，本盤最佳），若他投得深就不是問題，投不深則牛棚很危險。

一如既往 **只揭露、不調整**: 9/16 用 171 場 box.html 檢定過
「前一天牛棚負擔預測模型誤差」，主要指標 0.3 個標準誤且方向相反。
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

DATE = "2026-09-20"
DATA_AS_OF = "2026-09-20 17:15 JST (UTC 08:15)"

T = "18:00 JST（看板 17:00 台北）"

GAMES = [
    BoardGame(
        date=DATE, start_time=T,
        away_team="西武獅", home_team="千葉羅德",
        away_starter="武内夏暉 (左)", home_starter="傑克森 (右)",
        venue="ZOZOマリンスタジアム (露天)",
        handicap_raw="1+35", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7+50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-20", f5_total_raw="4+75",
    ),
    BoardGame(
        date=DATE, start_time=T,
        away_team="廣島鯉魚", home_team="中日龍",
        away_starter="森翔平 (左)", home_starter="大野雄大 (左)",
        venue="バンテリンドーム (巨蛋)",
        handicap_raw="1-5", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6-75", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-55", f5_total_raw="3-50",
    ),
    BoardGame(
        date=DATE, start_time=T,
        away_team="橫濱DeNA灣星", home_team="阪神虎",
        away_starter="竹田祐 (右)", home_starter="才木浩人 (右)",
        venue="甲子園 (露天)",
        handicap_raw="1-30", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6平", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1+80", f5_total_raw="3-75",
    ),
]

JP = {
    "西武獅": "西武", "千葉羅德": "ロッテ",
    "廣島鯉魚": "広島", "中日龍": "中日",
    "橫濱DeNA灣星": "DeNA", "阪神虎": "阪神",
}
PARK_KEY = {
    "ZOZOマリンスタジアム (露天)": "ZOZOマリン",
    "バンテリンドーム (巨蛋)": "バンテリンドーム",
    "甲子園 (露天)": "甲子園",
}

OPEN_AIR = {"ZOZOマリン", "甲子園"}
"""バンテリンドーム 是巨蛋。"""

NEUTRAL_PARK_FACTOR = 1.0
"""配適資料裡沒有的球場採用的中性值。今日六場都在主要球場，未用到。"""


def park_factor(game: BoardGame) -> float:
    return cal.PARK_FACTORS_2026.get(PARK_KEY[game.venue], NEUTRAL_PARK_FACTOR)


DAILY_BUDGET = 2000.0
"""⚠️ 這是 **剩下的** 額度，不是全額。

使用者指定的單日曝險上限是 3,000，上午盤（`slate_2026_09_20.py`）已投入
1,000 在歐力士 @ 火腿的大分，因此本盤只剩 2,000。
同日第二張盤的作法沿用 2026-08-22（見 `slate_2026_08_22b.py`）。"""

OPEN_AIR_MIN_EV = GATE_OPEN_AIR_MIN_EV
"""露天球場的 EV 門檻，由 `bethero.gates` 統一定義（2026-09-02 起 = 0.04）。"""

STARTED: set[str] = set()
"""本報告產出時 (17:15 JST / 08:15 UTC) 三場皆未開賽，距 18:00 JST 約 45 分鐘。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "ZOZOマリン": "露天，臨海、風的影響在十二座球場中最大。未取得逐時預報",
    "甲子園": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。
本盤六人全部通過，最低是竹田祐 34.3 局。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。今日未用到。"""

# (顯示名, 收縮後失分率係數, 今日預期局數, 說明, 季內 IP/G)
STARTERS = {
    "西武": ("武内夏暉", 0.955, 6.43,
             "21 場 135.0 局 失分率 3.33、每場 6.4 局", 6.43),
    "ロッテ": ("ジャクソン", 1.013, 6.04,
              "23 場 139.0 局 失分率 3.69、每場 6.0 局", 6.04),
    "広島": ("森翔平", 0.960, 5.67,
             "15 場 85.0 局 失分率 3.39、每場 5.7 局", 5.67),
    "中日": ("大野雄大", 0.758, 6.53,
             "20 場 130.2 局 失分率 **2.34**、每場 6.5 局 —— **本盤最佳**", 6.53),
    "DeNA": ("竹田祐", 1.187, 4.90,
             "7 場 34.1 局 失分率 **5.77** —— 本盤最差，樣本也最薄；"
             "9/11 時他只有 27.2 局（只高出門檻 2.2 局），現已擴大到 9 局", 4.90),
    "阪神": ("才木浩人", 0.869, 6.32,
             "22 場 139.0 局 失分率 2.65、每場 6.3 局 —— 本盤次佳", 6.32),
}

STARTER_IP = {
    "西武": 135.0, "ロッテ": 139.0, "広島": 85.0,
    "中日": 130.7, "DeNA": 34.3, "阪神": 139.0,
}

ROLE_CHANGED: set[str] = set()
"""本盤無角色轉換案例 —— 六人的季內 IP/G 都在 4.90-6.53 之間，全是先發型態。"""

BULLPEN_NOTE = {
    "西武": "9/19 用 3 人（隅田知一郎 7 局 102 球失 2，牛棚 2 人僅 24 球；4-2 勝）"
            "—— 充分",
    "ロッテ": "9/19 用 3 人（高野脩汰 7 局 109 球失 4，牛棚 2 人 35 球；2-4 敗）"
              "—— 充分",
    "広島": "9/19 用 3 人（栗林良吏 7.2 局 113 球失 1，牛棚 2 人僅 18 球；5-1 勝）"
            "—— 充分",
    "中日": "9/19 **牛棚被打爆** —— 中西聖輝 3.1 局 85 球即退場，"
            "牛棚 4 人吃 **112 球**（1-14 慘敗），是當日全聯盟最重的",
    "DeNA": "9/19 用 5 人（尾形崇斗 5 局 85 球失 3，牛棚 4 人 62 球；5-3 勝）"
            "—— 略吃緊",
    "阪神": "9/19 用 5 人（村上頌樹 5 局 90 球失 2，牛棚 4 人 59 球；1-5 敗）"
            "—— 略吃緊",
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
            lineup_note="17:15 JST 尚未公布，依使用者指示略過",
            bullpen_note=f"{game.home_team}：{BULLPEN_NOTE[home]}；"
                         f"{game.away_team}：{BULLPEN_NOTE[away]}",
            park_weather_note=(
                f"球場係數 {park_factor(game):.3f}（2026 實測）。"
                + WEATHER.get(PARK_KEY[game.venue],
                              "開閉式屋頂／巨蛋，天氣不影響"
                              if PARK_KEY[game.venue] == "エスコンＦ"
                              else "巨蛋，天氣不影響")
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
        "⚠️ **這是今天的第二張盤，額度是剩下的 2,000 不是 3,000。** "
        "上午盤已投入 1,000 在歐力士 @ 火腿的大分 8平（EV +26.3%）。"
        "同日第二盤的作法沿用 2026-08-22。",
        "**上午那三場不重新定價** —— 它們已於 14:00 JST 開賽（本盤產出時"
        "已過三小時）；更重要的是，當時的推薦是在開賽前 90 分鐘依當時"
        "可覆核的報價做出的，事後重算會改寫那個決定的紀錄。",
        "六位先發的 **姓名與投球側 6/6 相符**（看板「傑克森」= "
        "npb.jp「ジャクソン」）。六人全部越過 25 局門檻、全部是先發用法"
        "（IP/G 4.90-6.53），**本盤同樣沒有任何門檻被觸發**。"
        "最薄的竹田祐 34.1 局 —— 9/11 時他只有 27.2 局。",
        "⚠️ **中日的牛棚昨晚被打爆**：9/19 以 1-14 慘敗，先發中西聖輝 3.1 局"
        "即退場、牛棚四人吃了 **112 球**，是當日全聯盟最重。今天先發是"
        "大野雄大（失分率 2.34，本盤最佳），他投得深就不是問題。"
        "一如既往 **只揭露、不調整** —— 9/16 的檢定顯示該效應 0.3 個標準誤"
        "且方向相反。",
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
