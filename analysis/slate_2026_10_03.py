"""2026-10-03 NPB 看板四場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_10_03.py``

四場都是 18:00 JST（17:00 台北）。看板在 17:16 JST 收到，距開賽約 45 分鐘。
看板標「滾球」是莊家的走地標記，不代表已開賽（同 9/30）。
另有 廣島 vs 阪神 14:00 JST 一場不在看板上。

⚠️ 先讀這段
-----------
`analysis/validate_market_shrinkage.py`: 模型與盤口的分歧幾乎全是模型的誤差
（定價當時的值 β ≈ 1.27、3.0 個標準誤）。依那個結果，本檔算出的 EV **不可信**。
使用者尚未決定要不要暫停下注或改模型，所以照原流程定價、門檻也未改。

查證結果
--------
* 四場的對戰、球場、主客與先發，全部與 npb.jp 賽程頁的「先發」欄相符。
* 八位先發的姓名與投球側 8/8 相符。
* **三位先發樣本不足**，所以只有 **中日 @ 養樂多** 有機會推薦:

  - 辛島航（樂天）**本季一軍 0 場**（樂天投手成績頁沒有他）。二軍 10 場 27.1 局、
    每場 2.73 局 —— 短局數用法，列入 `ROLE_CHANGED`，係數只能用先驗（1/球場曝險）。
  - 唐川侑己（羅德）一軍 1 場先發 5.0 局，預期局數採 5.00。二軍 17 場、每場 4.61 局。
  - 島田舜也（DeNA）一軍 4 場 19.2 局、每場 4.92 局。

巨人牛棚兩天 208 球（10/1 甲子園延長 12 局 2-2 和局用 7 人 128 球，10/2 再 6 人 80 球）。
一如既往只揭露、不調整。
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

DATE = "2026-10-03"
DATA_AS_OF = "2026-10-03 17:17 JST (UTC 08:17)"

T = "18:00 JST（看板 17:00 台北）"

GAMES = [
    BoardGame(
        date=DATE, start_time=T,
        away_team="福岡軟銀鷹", home_team="千葉羅德",
        away_starter="松本晴 (左)", home_starter="唐川侑己 (右)",
        venue="ZOZOマリンスタジアム (露天)",
        handicap_raw="2-55", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="8-75", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1-35", f5_total_raw="4-75",
    ),
    BoardGame(
        date=DATE, start_time=T,
        away_team="歐力士猛牛", home_team="東北樂天鷹",
        away_starter="九里亜蓮 (右)", home_starter="辛島航 (左)",
        venue="楽天モバイル (露天)",
        handicap_raw="1+60", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6-75", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-10", f5_total_raw="3.5",
    ),
    BoardGame(
        date=DATE, start_time=T,
        away_team="中日龍", home_team="養樂多燕子",
        away_starter="髙橋宏斗 (右)", home_starter="高梨裕稔 (右)",
        venue="神宮 (露天)",
        handicap_raw="1+35", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6.5", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-45", f5_total_raw="4+75",
        # 純小數 = 字面上的半球盤，永不和局。使用者 2026-08-13 已目視確認。
        attested_fields=frozenset({"total"}),
    ),
    BoardGame(
        date=DATE, start_time=T,
        away_team="橫濱DeNA灣星", home_team="讀賣巨人",
        away_starter="島田舜也 (右)", home_starter="井上温大 (左)",
        venue="東京ドーム (巨蛋)",
        handicap_raw="1+25", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6+25", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-70", f5_total_raw="3-25",
    ),
]

JP = {
    "福岡軟銀鷹": "ソフトバンク", "千葉羅德": "ロッテ",
    "歐力士猛牛": "オリックス", "東北樂天鷹": "楽天",
    "中日龍": "中日", "養樂多燕子": "ヤクルト",
    "橫濱DeNA灣星": "DeNA", "讀賣巨人": "巨人",
}
PARK_KEY = {
    "ZOZOマリンスタジアム (露天)": "ZOZOマリン",
    "楽天モバイル (露天)": "楽天モバイル",
    "神宮 (露天)": "神宮",
    "東京ドーム (巨蛋)": "東京ドーム",
}

OPEN_AIR = {"ZOZOマリン", "楽天モバイル", "神宮"}
"""東京ドーム 是巨蛋。"""

NEUTRAL_PARK_FACTOR = 1.0
"""配適資料裡沒有的球場採用的中性值。今日四場都在主要球場，未用到。"""


def park_factor(game: BoardGame) -> float:
    return cal.PARK_FACTORS_2026.get(PARK_KEY[game.venue], NEUTRAL_PARK_FACTOR)


DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限。今日只有這一張盤（廣島 vs 阪神 不在看板上）。"""

OPEN_AIR_MIN_EV = GATE_OPEN_AIR_MIN_EV
"""露天球場的 EV 門檻，由 `bethero.gates` 統一定義（2026-09-02 起 = 0.04）。"""

STARTED: set[str] = set()
"""本報告產出時 (17:17 JST / 08:17 UTC) 四場皆未開賽，距 18:00 JST 約 43 分鐘。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "ZOZOマリン": "露天，臨海、風的影響在十二座球場中最大。未取得逐時預報",
    "楽天モバイル": "露天。未取得逐時風向／氣溫預報",
    "神宮": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。
今日三人未達: 辛島航 0、唐川侑己 5.0、島田舜也 19.2 局。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。今日未用到（辛島採二軍值）。"""

# (顯示名, 收縮後失分率係數, 今日預期局數, 說明, 季內 IP/G)
STARTERS = {
    "ソフトバンク": ("松本晴", 0.854, 5.59,
                  "21 場 117.1 局 失分率 2.84、每場 5.6 局", 5.59),
    "ロッテ": ("唐川侑己", 1.075, 5.00,
              "**一軍本季僅 1 場 5.0 局**（失 4）；二軍 17 場 78.1 局、每場 4.61 局、"
              "失分率 3.56", 5.00),
    "オリックス": ("九里亜蓮", 1.088, 6.06,
                "26 場 157.2 局 失分率 3.71、每場 6.1 局", 6.06),
    "楽天": ("辛島航", 0.994, 2.73,
             "**本季一軍 0 場**；二軍 10 場 27.1 局、每場 2.73 局、失分率 3.62 —— "
             "係數只能用先驗，預期局數採二軍值", 0.0),
    "中日": ("髙橋宏斗", 0.895, 6.48,
             "18 場 116.2 局 失分率 3.09、每場 6.5 局", 6.48),
    "ヤクルト": ("高梨裕稔", 0.869, 5.69,
                "14 場 79.2 局 失分率 3.28、每場 5.7 局", 5.69),
    "DeNA": ("島田舜也", 1.072, 4.92,
             "**一軍 4 場 19.2 局**（失分率 5.03、每場 4.9 局）；二軍 13 場 44.1 局、"
             "失分率 2.03", 4.92),
    "巨人": ("井上温大", 0.775, 6.41,
             "22 場 141.0 局 失分率 **2.49** —— 本日最佳、每場 6.4 局", 6.41),
}

STARTER_IP = {
    "ソフトバンク": 117.3, "ロッテ": 5.0, "オリックス": 157.7, "楽天": 0.0,
    "中日": 116.7, "ヤクルト": 79.7, "DeNA": 19.7, "巨人": 141.0,
}

ROLE_CHANGED = {"楽天"}
"""辛島航 —— 本季一軍 0 場，二軍每場 2.73 局。今天名義上先發，實際上很可能
是短局數; 預期局數採二軍 2.73（blended_defence 的 0.35 下限會生效），
壓力測試換球隊季內守備係數（與 9/29 中村優斗的處理一致）。"""

BULLPEN_NOTE = {
    "ソフトバンク": "10/1 上沢 先發、牛棚 2 人 25 球；10/2 前田悠 先發、牛棚 2 人 26 球"
                  " —— 充分；牛棚係數為全聯盟次佳",
    "ロッテ": "10/1 ロング 先發、牛棚 2 人 69 球；10/2 田中 先發、牛棚 3 人 45 球 —— 正常",
    "オリックス": "9/29 之後 9/30、10/1、10/2 休兵 —— 已休三天，充分；但牛棚係數為全聯盟次差",
    "楽天": "10/1 瀧中 先發、牛棚 3 人 74 球（2-8 敗）；10/2 休兵 —— 正常；"
            "牛棚係數為全聯盟最差",
    "中日": "10/1 大野 先發、牛棚 2 人 39 球（1-5 敗）；10/2 預備日休兵 —— 充分",
    "ヤクルト": "10/1 休兵；10/2 山野 先發、牛棚 2 人 35 球（5-1 勝）—— 充分",
    "DeNA": "9/28 之後休兵四天 —— 充分；牛棚係數為全聯盟第三佳",
    "巨人": "10/1 甲子園延長 12 局 2-2 和局，牛棚 **7 人 128 球**；10/2 山﨑 先發、"
            "牛棚 **6 人 80 球**（1-5 敗）—— **兩天 208 球，吃緊**；牛棚係數為全聯盟最佳",
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
            lineup_note="17:17 JST 尚未公布，依使用者指示略過",
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
        "⚠️ **這些 EV 不可信**：`analysis/market-shrinkage.md` 顯示模型與盤口的分歧"
        "幾乎全是模型的誤差（β ≈ 1.27，3.0 個標準誤）。建議暫停實際下注，"
        "使用者尚未決定 —— 本檔照原流程定價。",
        "四場都是 18:00 JST（17:00 台北），看板在 17:16 JST 收到。"
        "看板的「滾球」是走地標記，四場都還沒開賽。",
        "八位先發姓名與投球側 8/8 相符。",
        "⚠️ **三位先發樣本不足**（辛島航 一軍 0 場、唐川侑己 5.0 局、島田舜也 19.2 局），"
        "所以只有 **中日 @ 養樂多** 有機會推薦。",
        "辛島航二軍每場 2.73 局，列入角色轉換（短局數開局）處理。",
        "巨人牛棚兩天 208 球（10/1 延長 12 局和局 + 10/2）。**只揭露、不調整。**",
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
