"""2026-09-18 NPB 全三場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_09_18.py``

三場都 18:00 JST 開賽，時間充裕。校準涵蓋到 9/17 收盤（784 場），
由 `cal.freshness_note()` 在定價前確認為最新。

⚠️ 大小盤讓水第二次出現
----------------------
**中日 @ 巨人** 的大小盤是 大 **0.900** / 小 **0.960**，讓球也不對稱
（客 0.980 / 主 0.920）。另外兩場仍是齊一的 0.950 / 0.930。

首見是 2026-09-11，當時順帶抓出一個 bug: 壓力測試區塊固定傳
``game.over_hk`` 不論方向，兩邊同價時無害、不同價時會算錯 3 個百分點。
那個修正（`side_hk`）已沿用至今，本檔直接受惠。

去水後市場機率 大 50.78% / 小 49.22% —— 市場在盤口之外額外偏向大分。
小分 0.960 比 0.930 多賠 3.2%，EV 已依各邊實際價格計算。

查證結果
--------
* 三場的對戰、球場、主客與先發，全部與 npb.jp 賽程頁的「先發」欄相符
  （9/18 清晨的例行結算已先核對過一次，此處再確認）。
* **六位先發的姓名與投球側 6/6 相符**，今天沒有異體字或音譯問題。
* 六人全部越過 25 局門檻、也全部是先發用法（IP/G 5.06-6.41）。
  **今天沒有任何門檻被觸發**，是 9/16 以來第二次。
  最薄的是片山皓心（DeNA）30.1 局 —— 9/13 時他以整整 0 局的差距
  通過門檻（25.0 局），現在安全邊際擴大到 5 局。

⚠️ 中日與巨人已休兵兩天
----------------------
9/16 與 9/17 全聯盟的賽程都不含這兩隊，他們上次出賽是 **9/15**。
兩隊的牛棚都是完全休息的狀態 —— 但模型的牛棚係數是整季平均，
同樣不會反映這件事。方向與 9/15 那次（巨人／DeNA 被榨乾）相反。

⚠️ 但這個方向 **不套用任何修正**。2026-09-16 用 8/12-9/15 全部 171 場
box.html（330 個球隊場次）檢定過「前一天牛棚負擔預測模型誤差」，
主要指標 **0.3 個標準誤且方向相反**（見 analysis/validate_bullpen_fatigue.py）。
那次假說還是事前登記的，仍然沒通過。所以這裡只揭露、不調整。
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

DATE = "2026-09-18"
DATA_AS_OF = "2026-09-18 16:35 JST (UTC 07:35)"

T = "18:00 JST（看板 17:00 台北）"

GAMES = [
    BoardGame(
        date=DATE, start_time=T,
        away_team="廣島鯉魚", home_team="阪神虎",
        away_starter="森下暢仁 (右)", home_starter="大竹耕太郎 (左)",
        venue="甲子園 (露天)",
        handicap_raw="1-20", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6-50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-90", f5_total_raw="3-75",
    ),
    BoardGame(
        date=DATE, start_time=T,
        away_team="養樂多燕子", home_team="橫濱DeNA灣星",
        away_starter="山野太一 (左)", home_starter="片山皓心 (左)",
        venue="横浜 (露天)",
        handicap_raw="1+30", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7平", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-40", f5_total_raw="4+50",
    ),
    BoardGame(
        date=DATE, start_time=T,
        away_team="中日龍", home_team="讀賣巨人",
        away_starter="金丸夢斗 (左)", home_starter="井上温大 (左)",
        venue="東京ドーム (巨蛋)",
        # ⚠️ 讓球與大小盤兩邊都不同價，本季第二次 (首見 9/11)。
        handicap_raw="1平", handicap_side="home",
        handicap_home_hk=0.920, handicap_away_hk=0.980,
        total_raw="6+25", over_hk=0.900, under_hk=0.960,
        f5_handicap_raw="0-60", f5_total_raw="3-50",
    ),
]

JP = {
    "廣島鯉魚": "広島", "阪神虎": "阪神",
    "養樂多燕子": "ヤクルト", "橫濱DeNA灣星": "DeNA",
    "中日龍": "中日", "讀賣巨人": "巨人",
}
PARK_KEY = {
    "甲子園 (露天)": "甲子園",
    "横浜 (露天)": "横浜",
    "東京ドーム (巨蛋)": "東京ドーム",
}

OPEN_AIR = {"甲子園", "横浜"}
"""東京ドーム 是巨蛋。"""

NEUTRAL_PARK_FACTOR = 1.0
"""配適資料裡沒有的球場採用的中性值。今日六場都在主要球場，未用到。"""


def park_factor(game: BoardGame) -> float:
    return cal.PARK_FACTORS_2026.get(PARK_KEY[game.venue], NEUTRAL_PARK_FACTOR)


DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限，比 Bankroll 的 5,000 更緊。"""

OPEN_AIR_MIN_EV = GATE_OPEN_AIR_MIN_EV
"""露天球場的 EV 門檻，由 `bethero.gates` 統一定義（2026-09-02 起 = 0.04）。"""

STARTED: set[str] = set()
"""本報告產出時 (16:35 JST) 三場皆未開賽，18:00 開打。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "甲子園": "露天。未取得逐時風向／氣溫預報",
    "横浜": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。
今日六人全部通過，最低是片山皓心 30.3 局。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。今日未用到。"""

# (顯示名, 收縮後失分率係數, 今日預期局數, 說明, 季內 IP/G)
STARTERS = {
    "広島": ("森下暢仁", 1.064, 5.98,
             "20 場 119.2 局 失分率 3.99、每場 6.0 局", 5.98),
    "阪神": ("大竹耕太郎", 1.068, 5.54,
             "16 場 88.2 局 失分率 3.65、每場 5.5 局", 5.54),
    "ヤクルト": ("山野太一", 0.786, 6.39,
                "22 場 140.2 局 失分率 2.82、每場 6.4 局 —— 本日最佳之一", 6.39),
    "DeNA": ("片山皓心", 0.969, 5.06,
             "6 場 30.1 局 失分率 3.56；**本日最薄樣本**，但已比 9/13 的 "
             "25.0 局多出 5 局安全邊際", 5.06),
    "中日": ("金丸夢斗", 0.874, 6.41,
             "23 場 147.1 局 失分率 2.99、每場 6.4 局 —— 局數最多", 6.41),
    "巨人": ("井上温大", 0.807, 6.27,
             "20 場 125.1 局 失分率 2.59、每場 6.3 局 —— **本日最佳**", 6.27),
}

STARTER_IP = {
    "広島": 119.7, "阪神": 88.7, "ヤクルト": 140.7,
    "DeNA": 30.3, "中日": 147.3, "巨人": 125.3,
}

ROLE_CHANGED: set[str] = set()
"""今日無角色轉換案例 —— 四人的季內 IP/G 都在 4.65-6.23 之間，全是先發型態。"""

BULLPEN_NOTE = {
    "広島": "9/17 用 4 人（床田寛樹 4 局 82 球失 7 即退場，牛棚 3 人 49 球；"
            "2-7 敗）—— 略吃緊",
    "阪神": "9/17 用 4 人（髙橋遥人 6 局 90 球失 2，牛棚 3 人 46 球；7-2 勝）—— 正常",
    "ヤクルト": "9/17 用 4 人（奥川恭伸 7 局 100 球失 2，牛棚 3 人僅 23 球；"
                "1-2 敗）—— 充分",
    "DeNA": "9/17 用 4 人（石田裕太郎 6 局 105 球失 0，牛棚 3 人 50 球；2-1 勝）"
            "—— 正常",
    "中日": "**9/16、9/17 連兩天休兵**，上次出賽是 9/15 —— 牛棚完全休息",
    "巨人": "**9/16、9/17 連兩天休兵**，上次出賽是 9/15 —— 牛棚完全休息；"
            "牛棚係數 0.821 本就是全聯盟最佳",
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
            lineup_note="16:35 JST 尚未公布，依使用者指示略過",
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
        "⚠️ **中日 @ 巨人 的大小盤兩邊不同價**（大 0.900／小 0.960），"
        "讓球也不對稱（客 0.980／主 0.920）。本季第二次（首見 9/11）。"
        "去水後市場機率 大 50.8%／小 49.2% —— 市場在盤口之外額外偏向大分；"
        "小分多賠 3.2%。EV 已依各邊實際價格計算（9/11 修正的 `side_hk`）。",
        "六位先發的 **姓名與投球側 6/6 相符**，今天沒有異體字或音譯問題。",
        "**今天沒有任何門檻被觸發** —— 六人全越過 25 局、也全是先發用法"
        "（IP/G 5.06-6.41）。最薄的片山皓心 30.1 局，比 9/13 剛好卡在門檻上"
        "（25.0 局）時多了 5 局安全邊際。",
        "⚠️ **中日與巨人已連休兩天**（9/16、9/17 皆無賽程），牛棚完全休息。"
        "模型的牛棚係數是整季平均，不反映這件事 —— **但不套用任何修正**："
        "9/16 用 171 場 box.html（330 個球隊場次）檢定過「前一天牛棚負擔"
        "預測模型誤差」，主要指標 0.3 個標準誤且方向相反，"
        "而那還是事前登記的假說。只揭露，不調整。",
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
