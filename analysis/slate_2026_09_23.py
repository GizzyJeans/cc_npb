"""2026-09-23 NPB 看板三場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_09_23.py``

看板三場: 兩場 14:00 JST（13:00 台北）、一場 15:00 JST（14:00 台北）。
本報告產出時距最早開賽約 2 小時 35 分鐘。

⚠️ npb.jp 今天有六場，看板只列三場
------------------------------------
另外三場（歐力士 @ 羅德 17:00、中日 @ DeNA 18:00、樂天 @ 火腿 18:00 JST）
看板尚未列出。本檔只處理看板上的三場 —— **沒有盤口就沒有定價**。

查證結果
--------
* 三場的對戰、球場、主客與開賽時間，全部與 npb.jp 賽程頁及各場頁面相符。
* 看板只有 **西武 @ 軟銀** 列了先發（武内夏暉[左]、上沢直之[右]），
  兩人姓名與投球側都與 npb.jp 相符。另外兩場看板未列先發，
  採 npb.jp 賽程頁的予告先発（奥川 / 髙橋、床田 / 竹丸）。
* 阪神的「髙橋」: 阪神投手成績頁只有一位髙橋（**髙橋遥人**，`*` 左投），
  不是中日的髙橋宏斗 —— 沒有同姓混淆。
* 六人全部越過 25 局門檻、全部是先發用法（IP/G 5.80-6.90），
  **今天沒有任何門檻被觸發**。

大小盤 6.5（巨人 @ 廣島）
-------------------------
看板寫的是純小數 ``6.5``，依使用者 2026-08-13 的確認視為 **字面上的半球盤**
（永不和局），以 ``attested_fields`` 標記。上半大小 ``3.5`` 與西武 @ 軟銀
的上半讓球 ``0.5`` 也是純小數，但上半場盤本來就不定價，不影響今天的判斷。

牛棚: 事前寫下，但不調整
------------------------
阪神與養樂多昨天打滿 11 局，兩隊牛棚合計 **317 球**（阪神 9 人 169 球、
養樂多 6 人 148 球）。阪神的 169 球是本資料集（8/12 起）單日最重；
加上 9/21 的 139 球，連續兩天 **308 球** 也是最重（第二名是巨人 9/14-15 的
240 球）。作為對照，9/15 那個「說中」的案例賽前一天是兩隊合計 249 球
（巨人 144、DeNA 105）—— 今天的 317 比它還重。

這裡照實寫下，但 **不動模型、也不據此偏向任何一邊**:
``analysis/validate_bullpen_fatigue.py`` 在 110 場全樣本上是 0.8 個標準誤、
**方向與假說相反**，而且四層單調地反向。兩次軼事說中不是證據。
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

DATE = "2026-09-23"
DATA_AS_OF = "2026-09-23 11:25 JST (UTC 02:25)"

T14 = "14:00 JST（看板 13:00 台北）"
T15 = "15:00 JST（看板 14:00 台北）"

GAMES = [
    BoardGame(
        date=DATE, start_time=T14,
        away_team="西武獅", home_team="福岡軟銀鷹",
        away_starter="武内夏暉 (左)", home_starter="上沢直之 (右)",
        venue="みずほPayPay (巨蛋)",
        handicap_raw="1-30", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7+20", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0.5", f5_total_raw="4+75",
    ),
    BoardGame(
        date=DATE, start_time=T14,
        away_team="阪神虎", home_team="養樂多燕子",
        away_starter="髙橋遥人 (左)", home_starter="奥川恭伸 (右)",
        venue="神宮 (露天)",
        handicap_raw="2-20", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7-70", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1-10", f5_total_raw="4+75",
    ),
    BoardGame(
        date=DATE, start_time=T15,
        away_team="讀賣巨人", home_team="廣島鯉魚",
        away_starter="竹丸和幸 (左)", home_starter="床田寛樹 (左)",
        venue="マツダスタジアム (露天)",
        handicap_raw="1+30", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6.5", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-30", f5_total_raw="3.5",
        # 純小數 = 字面上的半球盤，永不和局。使用者 2026-08-13 已目視確認。
        attested_fields=frozenset({"total"}),
    ),
]

JP = {
    "西武獅": "西武", "福岡軟銀鷹": "ソフトバンク",
    "阪神虎": "阪神", "養樂多燕子": "ヤクルト",
    "讀賣巨人": "巨人", "廣島鯉魚": "広島",
}
PARK_KEY = {
    "みずほPayPay (巨蛋)": "みずほPayPay",
    "神宮 (露天)": "神宮",
    "マツダスタジアム (露天)": "マツダスタジアム",
}

OPEN_AIR = {"神宮", "マツダスタジアム"}
"""みずほPayPay 是巨蛋。"""

NEUTRAL_PARK_FACTOR = 1.0
"""配適資料裡沒有的球場採用的中性值。今日三場都在主要球場，未用到。"""


def park_factor(game: BoardGame) -> float:
    return cal.PARK_FACTORS_2026.get(PARK_KEY[game.venue], NEUTRAL_PARK_FACTOR)


DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限，比 Bankroll 的 5,000 更緊。"""

OPEN_AIR_MIN_EV = GATE_OPEN_AIR_MIN_EV
"""露天球場的 EV 門檻，由 `bethero.gates` 統一定義（2026-09-02 起 = 0.04）。"""

STARTED: set[str] = set()
"""本報告產出時 (11:25 JST / 02:25 UTC) 三場皆未開賽。
最早的兩場 14:00 JST = 05:00 UTC，還有約 2 小時 35 分鐘。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "神宮": "露天。未取得逐時風向／氣溫預報",
    "マツダスタジアム": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。
今日六人全部通過，最低是竹丸和幸 116.0 局 —— 安全邊際很大。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。今日未用到。"""

# (顯示名, 收縮後失分率係數, 今日預期局數, 說明, 季內 IP/G)
STARTERS = {
    "ソフトバンク": ("上沢直之", 0.900, 6.12,
                  "20 場 122.1 局 失分率 3.09、每場 6.1 局", 6.12),
    "西武": ("武内夏暉", 0.952, 6.43,
             "21 場 135.0 局 失分率 3.33、每場 6.4 局", 6.43),
    "ヤクルト": ("奥川恭伸", 0.796, 6.86,
                "21 場 144.0 局 失分率 2.94、每場 6.9 局 —— 養樂多的球場曝險 1.090"
                "（神宮 1.21）讓球場調整後的係數比原始失分率更好", 6.86),
    "阪神": ("髙橋遥人", 0.780, 6.90,
             "21 場 145.0 局 失分率 **2.23**、每場 6.9 局 —— **本日最佳**", 6.90),
    "広島": ("床田寛樹", 1.008, 6.11,
             "21 場 128.1 局 失分率 3.65、每場 6.1 局", 6.11),
    "巨人": ("竹丸和幸", 1.070, 5.80,
             "20 場 116.0 局 失分率 4.03、每場 5.8 局 —— 本日最差", 5.80),
}

STARTER_IP = {
    "ソフトバンク": 122.3, "西武": 135.0, "ヤクルト": 144.0,
    "阪神": 145.0, "広島": 128.3, "巨人": 116.0,
}

ROLE_CHANGED: set[str] = set()
"""今日無角色轉換案例 —— 六人的季內 IP/G 都在 5.80-6.90 之間，全是先發型態。"""

BULLPEN_NOTE = {
    "ソフトバンク": "9/21 雨天中止（休息）；9/22 用 5 人（上茶谷 5 局 83 球失 1，"
                  "牛棚 4 人 51 球；6-5 勝）—— 充分；牛棚係數 0.843 為全聯盟次佳",
    "西武": "9/21 雨天中止（休息）；9/22 用 5 人（佐藤爽 4 局 78 球失 2，"
            "牛棚 4 人 59 球失 4；5-6 敗）—— 正常",
    "阪神": "9/21 牛棚 7 人 139 球；9/22 用 **10 人**（伊藤将 僅 2 局 38 球失 2，"
            "牛棚 **9 人 169 球**、9 局；延長 11 局 9-7 勝）—— "
            "**兩天 308 球，本資料集（8/12 起）最重**",
    "ヤクルト": "9/21 休兵；9/22 用 7 人（松本健 1.1 局 40 球失 6 即退場，"
                "牛棚 **6 人 148 球**、9.2 局；延長 11 局 7-9 敗）—— 吃緊",
    "巨人": "9/21 休兵；9/22 用 8 人（戸郷 5 局 86 球失 1，牛棚 7 人 110 球、"
            "5.2 局；延長 11 局 1-2 敗）—— 略吃緊；牛棚係數 0.802 為全聯盟最佳",
    "広島": "9/21 牛棚 3 人 75 球；9/22 用 6 人（玉村 6 局 86 球失 1，"
            "牛棚 5 人 71 球、5 局；延長 11 局 2-1 再見勝）—— 正常",
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
        if home == "ヤクルト":
            risks.append(
                "兩隊牛棚昨天打滿 11 局、合計 **317 球**（阪神 169、養樂多 148），"
                "阪神兩天 308 球是本資料集最重。**只揭露、不調整** —— "
                "牛棚疲勞假說在 110 場全樣本上是 0.8 個標準誤、方向相反"
                "（analysis/validate_bullpen_fatigue.py）"
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
            lineup_note="11:25 JST 尚未公布，依使用者指示略過",
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
        "看板三場: 兩場 14:00 JST（13:00 台北）、巨人 @ 廣島 15:00 JST（14:00 台北）。"
        "產出時距最早開賽約 **2 小時 35 分鐘**。",
        "⚠️ **npb.jp 今天有六場，看板只列三場。** 另外三場（歐力士 @ 羅德 17:00、"
        "中日 @ DeNA 18:00、樂天 @ 火腿 18:00 JST）看板尚未列出。"
        "本檔只處理看板上的三場 —— **沒有盤口就沒有定價**。",
        "看板只有西武 @ 軟銀列了先發（姓名與投球側 2/2 相符）；另兩場採 npb.jp "
        "予告先発。阪神的「髙橋」查證為 **髙橋遥人**（`*` 左投，阪神頁面只有這一位髙橋）。"
        "六人全部越過 25 局門檻（最低竹丸和幸 116.0 局）、全部是先發用法"
        "（IP/G 5.80-6.90）。**今天沒有任何門檻被觸發。**",
        "巨人 @ 廣島 的大小盤是純小數 **6.5**，視為字面上的半球盤（永不和局），"
        "以 `attested_fields` 標記。",
        "⚠️ **阪神 @ 養樂多 兩隊牛棚昨天合計 317 球**（11 局延長賽）。阪神兩天 308 球"
        "是本資料集最重。**事前寫下、但不調整**：牛棚疲勞假說在 110 場全樣本上是 "
        "0.8 個標準誤、方向相反。兩次軼事說中（9/15、9/20）不是證據。",
        "⚠️ **「公平賠率／最低接受賠率」兩欄今天起改正**（`bethero.ev.evaluate`）。"
        "舊算法 (1−過盤率)/過盤率 把部分結算裡 **退回的那截本金** 也算成輸，"
        "N±XX 盤一律偏高 —— 今天「大分 7+20」舊值 1.025，比看板 0.930 還高，"
        "看起來像不該下；正確的 EV 歸零點是 **0.799**。"
        "**EV、優勢與分級一直是對的**，過去的推薦不受影響；"
        "受影響的只有這兩欄，而且一律偏保守（只會讓人錯過、不會讓人下錯）。",
        "N±XX 盤的「模型機率」是有效過盤率（部分結算按比例計），"
        "不能直接用 (1−p)/p 換算成公平賠率 —— 要看公平賠率欄。",
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
