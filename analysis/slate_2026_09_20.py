"""2026-09-20 NPB 看板三場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_09_20.py``

看板上的三場都是 14:00 JST（13:00 台北），本報告產出時距開賽約 90 分鐘
—— 比 9/19 那天的 13 分鐘從容得多。

⚠️ npb.jp 今天其實有六場，看板只列三場
--------------------------------------
另外三場（中日 @ 廣島、阪神 @ DeNA、羅德 @ 西武）都是 18:00 JST，
看板尚未列出。本檔只處理看板上的三場 —— **沒有盤口就沒有定價**，
不對沒有報價的比賽產生「建議」。若稍後拿到那三場的盤口再另行處理。

查證結果
--------
* 三場的對戰、球場、主客與先發，全部與 npb.jp 賽程頁的「先發」欄相符。
* **六位先發的姓名與投球側 6/6 相符**。看板「瀧中瞭太」與 npb.jp 寫法
  一致（瀧/滝 的等價已加進對照表備用，今天沒用到）。
* 六人全部越過 25 局門檻、也全部是先發用法（IP/G 4.32-6.67），
  **今天沒有任何門檻被觸發**。

髙島泰都（歐力士）的 IP/G 仍是 4.32，與 9/10 查證時的 4.33 幾乎相同。
當時逐場查證確認他是「投不深的先發」而非後援混合值（8/29、9/4 皆為
第1任且都投滿 5 局），該判斷至今沒有需要修正的地方。
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
DATA_AS_OF = "2026-09-20 12:30 JST (UTC 03:30)"

T = "14:00 JST（看板 13:00 台北）"

GAMES = [
    BoardGame(
        date=DATE, start_time=T,
        away_team="歐力士猛牛", home_team="日本火腿",
        away_starter="髙島泰都 (右)", home_starter="有原航平 (右)",
        venue="エスコンＦ (開閉式屋頂)",
        handicap_raw="2+35", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="8平", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1+10", f5_total_raw="4-75",
    ),
    BoardGame(
        date=DATE, start_time=T,
        away_team="福岡軟銀鷹", home_team="東北樂天金鷲",
        away_starter="大津亮介 (右)", home_starter="瀧中瞭太 (右)",
        venue="楽天モバイル (露天)",
        handicap_raw="2+55", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="8+50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1+50", f5_total_raw="4-25",
    ),
    BoardGame(
        date=DATE, start_time=T,
        away_team="養樂多燕子", home_team="讀賣巨人",
        away_starter="高橋奎二 (左)", home_starter="小笠原慎之介 (左)",
        venue="東京ドーム (巨蛋)",
        handicap_raw="1平", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6+50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-60", f5_total_raw="3-25",
    ),
]

JP = {
    "歐力士猛牛": "オリックス", "日本火腿": "日本ハム",
    "福岡軟銀鷹": "ソフトバンク", "東北樂天金鷲": "楽天",
    "養樂多燕子": "ヤクルト", "讀賣巨人": "巨人",
}
PARK_KEY = {
    "エスコンＦ (開閉式屋頂)": "エスコンＦ",
    "楽天モバイル (露天)": "楽天モバイル",
    "東京ドーム (巨蛋)": "東京ドーム",
}

OPEN_AIR = {"楽天モバイル"}
"""エスコンＦ 為開閉式屋頂、東京ドーム 為巨蛋，兩者視為室內。"""

NEUTRAL_PARK_FACTOR = 1.0
"""配適資料裡沒有的球場採用的中性值。今日六場都在主要球場，未用到。"""


def park_factor(game: BoardGame) -> float:
    return cal.PARK_FACTORS_2026.get(PARK_KEY[game.venue], NEUTRAL_PARK_FACTOR)


DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限，比 Bankroll 的 5,000 更緊。"""

OPEN_AIR_MIN_EV = GATE_OPEN_AIR_MIN_EV
"""露天球場的 EV 門檻，由 `bethero.gates` 統一定義（2026-09-02 起 = 0.04）。"""

STARTED: set[str] = set()
"""本報告產出時 (12:30 JST / 03:30 UTC) 三場皆未開賽，距 14:00 JST 約 90 分鐘。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "楽天モバイル": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。
今日六人全部通過，最低是小笠原慎之介 56.0 局 —— 安全邊際很大。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。今日未用到。"""

# (顯示名, 收縮後失分率係數, 今日預期局數, 說明, 季內 IP/G)
STARTERS = {
    "オリックス": ("髙島泰都", 1.270, 4.32,
                "21 場 90.2 局 失分率 **4.76** —— 本日最差；每場僅 4.3 局，"
                "但 9/10 已逐場查證確認是「投不深的先發」而非後援混合值", 4.32),
    "日本ハム": ("有原航平", 1.159, 6.22,
                "15 場 93.1 局 失分率 4.63、每場 6.2 局", 6.22),
    "ソフトバンク": ("大津亮介", 0.840, 6.67,
                  "20 場 133.1 局 失分率 2.77、每場 6.7 局 —— **本日最佳**", 6.67),
    "楽天": ("瀧中瞭太", 1.033, 5.67,
             "18 場 102.0 局 失分率 3.79、每場 5.7 局", 5.67),
    "ヤクルト": ("高橋奎二", 1.002, 5.56,
                "15 場 83.1 局 失分率 4.10、每場 5.6 局", 5.56),
    "巨人": ("小笠原慎之介", 0.858, 6.22,
             "9 場 56.0 局 失分率 2.57、每場 6.2 局 —— 本日次佳", 6.22),
}

STARTER_IP = {
    "オリックス": 90.7, "日本ハム": 93.3, "ソフトバンク": 133.3,
    "楽天": 102.0, "ヤクルト": 83.3, "巨人": 56.0,
}

ROLE_CHANGED: set[str] = set()
"""今日無角色轉換案例 —— 六人的季內 IP/G 都在 4.32-6.67 之間，全是先發型態。

髙島泰都的 4.32 最低，但 9/10 已逐場查證（8/29、9/4 皆為第1任、都投滿
5 局）確認是真實的先發局數，不是後援混合值。"""

BULLPEN_NOTE = {
    "オリックス": "9/19 用 3 人（エスピノーザ 7 局 96 球失 4，牛棚 2 人僅 28 球；"
                "7-4 勝）—— 充分",
    "日本ハム": "9/19 用 4 人（伊藤大海 6 局 **120 球** 失 6，牛棚 3 人 56 球；"
                "4-7 敗）—— 正常",
    "ソフトバンク": "9/19 用 4 人（前田悠伍 4.2 局 103 球失 5 即退場，牛棚 3 人 71 球；"
                  "2-5 敗）—— 略吃緊",
    "楽天": "9/19 用 3 人（早川隆久 7 局 100 球失 2，牛棚 2 人僅 26 球；5-2 勝）"
            "—— 充分；但牛棚係數 1.336 仍是全聯盟最差",
    "ヤクルト": "9/19 用 5 人（高梨裕稔 5 局 93 球失 1，牛棚 4 人 58 球；3-5 敗）"
                "—— 略吃緊",
    "巨人": "9/19 用 2 人（田中将大 7 局 102 球失 1，牛棚僅 1 人 24 球；14-1 大勝）"
            "—— 充分；牛棚係數 0.815 為全聯盟最佳",
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
            lineup_note="12:30 JST 尚未公布，依使用者指示略過",
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
        "看板三場都是 14:00 JST（13:00 台北），產出時距開賽約 **90 分鐘** —— "
        "比 9/19 那天的 13 分鐘從容得多。",
        "⚠️ **npb.jp 今天有六場，看板只列三場。** 另外三場（中日 @ 廣島、"
        "阪神 @ DeNA、羅德 @ 西武）都是 18:00 JST，看板尚未列出。"
        "本檔只處理看板上的三場 —— **沒有盤口就沒有定價**。",
        "六位先發的 **姓名與投球側 6/6 相符**，六人也全部越過 25 局門檻"
        "（最低小笠原慎之介 56.0 局）、全部是先發用法（IP/G 4.32-6.67）。"
        "**今天沒有任何門檻被觸發。**",
        "髙島泰都（歐力士）IP/G 4.32 是六人最低，但 9/10 已逐場查證"
        "（8/29、9/4 皆為第1任且都投滿 5 局）確認是真實的先發局數、"
        "不是後援混合值。該判斷至今無需修正。",
        "⚠️ **歐力士 @ 火腿 的分歧 +1.93 分會是本季已下注部位的最大值**"
        "（目前紀錄是 9/4 的 1.73）。模型 9.93 vs 盤口 8.00 —— 兩位先發的"
        "失分率都在 4.6 以上、エスコンＦ 的球場係數 1.048 偏高、"
        "兩隊打線又都在聯盟前四。不因分歧大而打折（9/10 的分層檢驗顯示"
        "最高分歧層 ROI 仍是三層最佳、+21.7%），但這是今天最該盯的一場。",
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
