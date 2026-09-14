"""2026-09-14 NPB 全三場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_09_14.py``

今天三場 **與昨天完全相同的對戰、相同球場**（各系列的第二戰），
三場都 18:00 JST 開賽，時間充裕。

⚠️ 校準值已經是三天前的
----------------------
球隊／球場／牛棚係數仍是 config 裡 **9/11 收盤的版本（757 場）**，
未含 9/12 與 9/13 的 11 場。原因是 9/13 容器回收時 IPF 重配適管線
（parse_season / fit / pf_fix / today_inputs）遺失，而每天拿到看板的
時間都只夠做先發更新。樣本差 1.4%，係數變動仍在小數第三位，
但 **這個缺口是會累積的**，不能每天用「只差一點」帶過。

已把重建管線排在今天定價完成之後 —— 先讓使用者拿到能用的數字，
再修工具。**先發個人成績與各隊球場曝險是今天重新抓取與計算的。**

查證結果
--------
* 三場的對戰、球場、主客與先發，全部與 npb.jp 賽程頁的「先發」欄相符。
* **六位先發的姓名與投球側 6/6 相符**。今天有兩組異體字要處理:
  看板「伊藤**將**司」= npb「伊藤**将**司」、看板「**增**居翔太」=
  npb「**増**居翔太」。兩組都不是 NFKC 相容字元，必須另列等價表。
  另外看板的「穆勒」= npb 的「マラー」（中日的外籍左投）。
* 六人全部越過 25 局門檻，最低是増居翔太 33.0 局。

⚠️ 昨天兩位先發都投了完投九局
----------------------------
昨天阪神 0-1 中日打滿 11 局，**髙橋宏斗投 9 局 142 球、才木浩人投 9 局
113 球，兩人都沒有失分**。那場的牛棚因此幾乎沒動（各 2 人、27／43 球），
所以兩隊今天的牛棚其實是充足的 —— 但兩位先發都不會在今天登板。
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

DATE = "2026-09-14"
DATA_AS_OF = "2026-09-14 17:45 JST (UTC 08:45)　⚠️ 球隊/球場/牛棚係數為 9/11 收盤版"

GAMES = [
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="中日龍", home_team="阪神虎",
        away_starter="穆勒 (左)", home_starter="伊藤將司 (左)",
        venue="甲子園 (露天)",
        handicap_raw="1-25", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6+75", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-60", f5_total_raw="3-50",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="廣島鯉魚", home_team="養樂多燕子",
        away_starter="玉村昇悟 (左)", home_starter="增居翔太 (左)",
        venue="神宮 (露天)",
        handicap_raw="1+80", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7-75", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-20", f5_total_raw="4+25",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="讀賣巨人", home_team="橫濱DeNA灣星",
        away_starter="西舘勇陽 (右)", home_starter="平良拳太郎 (右)",
        venue="横浜 (露天)",
        handicap_raw="1平", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7平", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-50", f5_total_raw="4+25",
    ),
]

JP = {
    "中日龍": "中日", "阪神虎": "阪神",
    "廣島鯉魚": "広島", "養樂多燕子": "ヤクルト",
    "讀賣巨人": "巨人", "橫濱DeNA灣星": "DeNA",
}
PARK_KEY = {
    "甲子園 (露天)": "甲子園",
    "神宮 (露天)": "神宮",
    "横浜 (露天)": "横浜",
}

OPEN_AIR = {"甲子園", "神宮", "横浜"}
"""今日三場全部露天。"""

NEUTRAL_PARK_FACTOR = 1.0
"""配適資料裡沒有的球場採用的中性值。今日四場都在主要球場，未用到。"""


def park_factor(game: BoardGame) -> float:
    return cal.PARK_FACTORS_2026.get(PARK_KEY[game.venue], NEUTRAL_PARK_FACTOR)


DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限，比 Bankroll 的 5,000 更緊。"""

OPEN_AIR_MIN_EV = GATE_OPEN_AIR_MIN_EV
"""露天球場的 EV 門檻，由 `bethero.gates` 統一定義（2026-09-02 起 = 0.04）。"""

STARTED: set[str] = set()
"""本報告產出時 (17:45 JST) 三場皆未開賽，18:00 開打。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "甲子園": "露天。未取得逐時風向／氣溫預報",
    "神宮": "露天，**全聯盟得分最高的球場**（PF 1.197）。未取得逐時預報",
    "横浜": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。
今日六人全部通過，最低是増居翔太 33.0 局。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。今日未用到。"""

# (顯示名, 收縮後失分率係數, 今日預期局數, 說明, 季內 IP/G)
STARTERS = {
    "中日": ("マラー", 0.871, 6.37,
             "17 場 108.1 局 失分率 2.91、每場 6.4 局 —— 本日最佳", 6.37),
    "阪神": ("伊藤将司", 0.992, 5.11,
             "9 場 46.0 局 失分率 3.13、每場 5.1 局", 5.11),
    "広島": ("玉村昇悟", 0.958, 5.17,
             "12 場 62.0 局 失分率 3.34、每場 5.2 局", 5.17),
    "ヤクルト": ("増居翔太", 0.893, 4.71,
                "7 場 33.0 局 失分率 3.27 —— **本日最薄樣本**，"
                "只高出 25 局門檻 8 局，收縮後大幅回歸聯盟平均", 4.71),
    "巨人": ("西舘勇陽", 0.837, 4.67,
             "10 場 46.2 局 失分率 2.31、但每場僅 4.7 局 —— "
             "投得好卻投不深，牛棚權重會偏高", 4.67),
    "DeNA": ("平良拳太郎", 0.975, 5.02,
             "18 場 90.1 局 失分率 3.59、每場 5.0 局", 5.02),
}

STARTER_IP = {
    "中日": 108.3, "阪神": 46.0, "広島": 62.0,
    "ヤクルト": 33.0, "巨人": 46.7, "DeNA": 90.3,
}

ROLE_CHANGED: set[str] = set()
"""今日無角色轉換案例 —— 八人的季內 IP/G 都在 4.6-6.5 之間，全是先發型態。"""

BULLPEN_NOTE = {
    "中日": "9/13 用 3 人 —— **髙橋宏斗投完投 9 局 142 球失 0**，牛棚只用 2 人 27 球；"
            "1-0 勝（11 局）—— 牛棚充分",
    "阪神": "9/13 用 3 人 —— **才木浩人投完投 9 局 113 球失 0**，牛棚只用 2 人 43 球；"
            "0-1 敗（11 局）—— 牛棚充分",
    "広島": "9/13 用 4 人（森翔平 4 局 63 球即退場，牛棚 3 人 75 球；1-3 敗）—— 略吃緊",
    "ヤクルト": "9/13 用 4 人（高橋奎二 6 局 102 球失 0，牛棚 3 人 54 球；3-1 勝）—— 正常",
    "巨人": "9/13 用 5 人（小笠原慎之介 4 局 58 球失 5 即退場，牛棚 4 人 48 球；"
            "0-5 敗）—— **本日最吃緊**",
    "DeNA": "9/13 用 4 人（竹田祐 6.2 局 103 球失 0，牛棚 3 人僅 28 球；5-0 完封勝）"
            "—— 充分",
}

ENV = NPBEnvironment(
    league_rpg=cal.LEAGUE_RPG,
    dispersion_k=cal.DISPERSION_K,
    home_edge=cal.HOME_EDGE,
    extras_resolve_rate=cal.EXTRAS_RESOLVE_RATE,
    source=f"npb.jp 2026 逐場比分 {cal.SAMPLE_GAMES} 場（⚠️ 9/11 收盤，未含 9/12）",
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
    """把樣本不足與角色轉換的先發，換成該隊季內守備係數。"""
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
            "⚠️ 球隊/球場/牛棚係數為 **9/11 收盤版**（757 場，未含 9/12 的 6 場）"
            "—— 容器回收導致重配適管線遺失，時間不足以重寫。先發個人成績是今日最新",
        ]
        if JP[game.home_team] in STARTED:
            risks.append("⚠️ **本場已開賽**，賽前盤口不可覆核 —— "
                         "`prices_verified` 為硬性門檻，不可能成為推薦")
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
                head.append("季中角色轉換：" + "、".join(changed))
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
            lineup_note="17:45 JST 尚未公布，依使用者指示略過",
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

    return DailyReport(
        date=DATE,
        bankroll=Bankroll(),
        analyses=analyses,
        data_as_of=DATA_AS_OF,
        global_notes=[
            "今日三場 **與昨天完全相同的對戰、相同球場**（各系列第二戰），"
            "三場都 18:00 JST 開賽，時間充裕。",
            "⚠️ **球隊／球場／牛棚係數仍是 9/11 收盤版（757 場）**，未含 9/12、9/13 "
            "的 11 場。9/13 容器回收時重配適管線遺失，之後每天拿到看板的時間都只夠"
            "更新先發。樣本差 1.4%、係數仍差在小數第三位，但 **這個缺口會累積**，"
            "已排在今天定價完成後重建。先發成績與球場曝險是今天重抓重算的。",
            "六位先發的 **姓名與投球側 6/6 相符**。今天有兩組異體字：看板"
            "「伊藤**將**司」= npb「伊藤**将**司」、「**增**居翔太」= 「**増**居翔太」，"
            "兩組都不是 NFKC 相容字元，必須另列等價表；看板「穆勒」= npb「マラー」。",
            "六人全部越過 25 局門檻，最低是増居翔太 33.0 局。",
            "⚠️ 昨天阪神 0-1 中日打滿 11 局，**髙橋宏斗投 9 局 142 球、"
            "才木浩人投 9 局 113 球，兩人都無失分**。兩隊牛棚因此幾乎沒動，"
            "今天反而是充足的一方 —— 但那兩位先發今天不會登板。",
            "全場讓分與上半場盤仍不定價，理由見各場風險欄。",
        ],
    )


if __name__ == "__main__":
    print(build_report().render())
