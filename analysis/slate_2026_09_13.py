"""2026-09-13 NPB 看板四場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_09_13.py``

⚠️ 一場在報告產出時已經開賽
--------------------------
**日本火腿 @ 西武 17:00 JST（16:00 台北）在本報告產出時已開賽約 25 分鐘。**
`STARTED` 收錄該場，`prices_verified` 記為 False —— 那是 **硬性** 門檻，
所以它不可能成為推薦，不論 EV 多漂亮。仍然定價並留下紀錄，
是為了讓它進入 scorecard 的未下注對照組。

這是 8/30 之後第二次遇到「看板上有一場已經開打」。週日的開賽時間
比平日早一小時（17:00 JST 而非 18:00），很容易吃掉緩衝。

⚠️ 校準值比平常舊一天
--------------------
容器在兩次工作之間被回收，scratchpad 裡完整的 IPF 重配適腳本
（parse_season / fit / pf_fix / today_inputs）一併遺失。距第一球只剩
不到 40 分鐘，重寫整條管線來不及，因此:

* **球隊進攻／守備、球場、牛棚係數沿用 config 裡 9/11 收盤的版本（757 場）**，
  沒有含 9/12 的 6 場。樣本少 0.8%，係數變動在小數點第三位，
  對 EV 的影響遠小於單場變異 —— 但這是事實，必須寫出來。
* **先發個人成績是今天最新的**（9/13 抓取），各隊球場曝險也重新算過
  （見 scratchpad/quick.py），所以先發係數本身沒有過期。

教訓: 這條管線只活在 scratchpad 裡，容器一回收就沒了。
應該把它收進版控，不要每次都靠重寫。

查證結果
--------
* 四場的對戰、球場、主客與先發，全部與 npb.jp 賽程頁的「先發」欄相符。
  今天該欄兩隊都有。
* **八位先發的投球側 8/8 與看板相符**（npb.jp 以前置 ``*`` 標記左投）。
* 八人全部越過 25 局門檻。最低是 **竹田祐（DeNA）27.2 局**，
  只高出門檻 2.2 局，而且失分率 7.16 是今日最差 —— 樣本薄且成績差，
  模型的收縮會把他大幅拉回聯盟平均，實際可能比模型顯示的更糟。
* **才木浩人（阪神）本季成績與 9/10 完全相同**（21 場 130.0 局）——
  他 9/10 也被預告先發，但該場雨天中止、未登板。與栗林良吏 9/10 的
  情況相同，兩人都不是短休。

另外，npb.jp 今天其實有五場，看板只列四場 —— 少的那場
（軟銀 @ 羅德 13:30 JST）在看板產出前就開打了。本檔只處理看板上的四場。
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

DATE = "2026-09-13"
DATA_AS_OF = "2026-09-13 17:25 JST (UTC 08:25)　⚠️ 球隊/球場/牛棚係數為 9/11 收盤版"

GAMES = [
    BoardGame(
        date=DATE, start_time="17:00 JST（看板 16:00 台北）⚠️ 已開賽",
        away_team="日本火腿", home_team="西武獅",
        away_starter="有原航平 (右)", home_starter="武内夏暉 (左)",
        venue="ベルーナドーム (巨蛋)",
        handicap_raw="1+40", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6.5", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-40", f5_total_raw="3-75",
        # 純小數 = 字面上的半球盤，永不和局。使用者 2026-08-13 已目視確認。
        attested_fields=frozenset({"total"}),
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="中日龍", home_team="阪神虎",
        away_starter="髙橋宏斗 (右)", home_starter="才木浩人 (右)",
        venue="甲子園 (露天)",
        handicap_raw="1-15", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="5-75", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-60", f5_total_raw="3平",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="廣島鯉魚", home_team="養樂多燕子",
        away_starter="森翔平 (左)", home_starter="高橋奎二 (左)",
        venue="神宮 (露天)",
        handicap_raw="1+90", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7+25", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-10", f5_total_raw="4+75",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="讀賣巨人", home_team="橫濱DeNA灣星",
        away_starter="小笠原慎之介 (左)", home_starter="竹田祐 (右)",
        venue="横浜 (露天)",
        handicap_raw="1+95", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7-75", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-10", f5_total_raw="4-50",
    ),
]

JP = {
    "日本火腿": "日本ハム", "西武獅": "西武",
    "中日龍": "中日", "阪神虎": "阪神",
    "廣島鯉魚": "広島", "養樂多燕子": "ヤクルト",
    "讀賣巨人": "巨人", "橫濱DeNA灣星": "DeNA",
}
PARK_KEY = {
    "ベルーナドーム (巨蛋)": "ベルーナドーム",
    "甲子園 (露天)": "甲子園",
    "神宮 (露天)": "神宮",
    "横浜 (露天)": "横浜",
}

OPEN_AIR = {"甲子園", "神宮", "横浜"}

NEUTRAL_PARK_FACTOR = 1.0
"""配適資料裡沒有的球場採用的中性值。今日四場都在主要球場，未用到。"""


def park_factor(game: BoardGame) -> float:
    return cal.PARK_FACTORS_2026.get(PARK_KEY[game.venue], NEUTRAL_PARK_FACTOR)


DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限，比 Bankroll 的 5,000 更緊。"""

OPEN_AIR_MIN_EV = GATE_OPEN_AIR_MIN_EV
"""露天球場的 EV 門檻，由 `bethero.gates` 統一定義（2026-09-02 起 = 0.04）。"""

STARTED = {"西武"}
"""⚠️ 火腿 @ 西武 17:00 JST 已於本報告產出前約 25 分鐘開賽。
`prices_verified` 為硬性門檻，該場不可能成為推薦。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "甲子園": "露天。未取得逐時風向／氣溫預報",
    "神宮": "露天，**全聯盟得分最高的球場**（PF 1.197）。未取得逐時預報",
    "横浜": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。
今日八人全部通過，最低是竹田祐 27.2 局 —— 只高出 2.2 局。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。今日未用到。"""

# (顯示名, 收縮後失分率係數, 今日預期局數, 說明, 季內 IP/G)
STARTERS = {
    "日本ハム": ("有原航平", 1.190, 6.24,
                "14 場 87.1 局 防禦率 4.84 —— 本日最差之一", 6.24),
    "西武": ("武内夏暉", 0.892, 6.48,
             "20 場 129.2 局 失分率 2.98、每場 6.5 局", 6.48),
    "中日": ("髙橋宏斗", 0.990, 6.29,
             "16 場 100.2 局 失分率 3.58、每場 6.3 局", 6.29),
    "阪神": ("才木浩人", 0.899, 6.19,
             "21 場 130.0 局 失分率 2.84、每場 6.2 局；"
             "9/10 亦被預告先發但該場雨天中止、未登板，成績與當時相同", 6.19),
    "広島": ("森翔平", 0.953, 5.79,
             "14 場 81.0 局 失分率 3.33、每場 5.8 局", 5.79),
    "ヤクルト": ("高橋奎二", 1.041, 5.52,
                "14 場 77.1 局 失分率 4.42；神宮的球場係數已另計，"
                "這裡是球場中性後的值", 5.52),
    "巨人": ("小笠原慎之介", 0.775, 6.50,
             "8 場 52.0 局 失分率 **1.90**、每場 6.5 局 —— **本日最佳**", 6.50),
    "DeNA": ("竹田祐", 1.282, 4.61,
             "6 場 27.2 局 失分率 **7.16** —— **本日最差**，且樣本只高出 "
             "25 局門檻 2.2 局，收縮後仍是全場最高的守備係數", 4.61),
}

STARTER_IP = {
    "日本ハム": 87.3, "西武": 129.7, "中日": 100.7, "阪神": 130.0,
    "広島": 81.0, "ヤクルト": 77.3, "巨人": 52.0, "DeNA": 27.7,
}

ROLE_CHANGED: set[str] = set()
"""今日無角色轉換案例 —— 八人的季內 IP/G 都在 4.6-6.5 之間，全是先發型態。"""

BULLPEN_NOTE = {
    "日本ハム": "9/12 與西武打滿 **12 局和局**（3-3），先發伊藤大海投 8 局 112 球、"
                "牛棚 4 人 58 球 —— 先發吃下大部分，牛棚尚可",
    "西武": "9/12 與火腿打滿 **12 局和局**（3-3），先發隅田知一郎投 8 局 110 球、"
            "牛棚 4 人 53 球 —— 同上，但今天只休一晚就再戰同一對手",
    "中日": "9/12 用 **6 人**（涌井秀章 3.2 局 81 球即退場，牛棚 5 人吃 101 球；"
            "5-6 敗）—— **本日最吃緊**",
    "阪神": "9/12 用 4 人（村上頌樹 5 局 104 球，牛棚 3 人僅 30 球；0-1 敗）—— 充分",
    "広島": "9/12 用 4 人（栗林良吏 5 局 78 球失 4，牛棚 3 人 51 球；2-7 敗）—— 正常",
    "ヤクルト": "9/12 用 5 人（高梨裕稔 5 局 95 球，牛棚 4 人 67 球；6-5 勝）—— 略吃緊",
    "巨人": "9/12 用 3 人（竹丸和幸 7 局 109 球失 0，牛棚 2 人僅 30 球；1-0 勝）"
            "—— 本日最充分",
    "DeNA": "9/12 用 3 人（尾形崇斗 7.2 局 109 球，牛棚 2 人僅 15 球；7-2 勝）"
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
            lineup_note="17:25 JST 尚未公布，依使用者指示略過",
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
            "⚠️ **火腿 @ 西武（17:00 JST）在本報告產出時已開賽約 25 分鐘。** "
            "`prices_verified` 是硬性門檻，該場不可能成為推薦；仍定價以留下"
            "未下注對照組的紀錄。週日開賽比平日早一小時，緩衝很容易被吃掉。",
            "⚠️ **球隊／球場／牛棚係數是 9/11 收盤版（757 場），未含 9/12 的 6 場。** "
            "容器在兩次工作之間被回收，scratchpad 裡的重配適管線一併遺失，"
            "距第一球不到 40 分鐘、不足以重寫。樣本少 0.8%，係數差在小數第三位，"
            "但這是事實。**先發個人成績與各隊球場曝險是今天重新抓取與計算的。**",
            "八位先發的 **投球側 8/8 與看板相符**，對戰／球場／主客亦與 npb.jp "
            "賽程頁的「先發」欄完全一致。",
            "八人全部越過 25 局門檻。最低是 **竹田祐（DeNA）27.2 局**，"
            "只高出 2.2 局，且失分率 7.16 為今日最差 —— "
            "樣本薄加上成績差，收縮後的係數可能仍然過於樂觀。",
            "才木浩人（阪神）本季成績與 9/10 完全相同 —— 他 9/10 也被預告先發，"
            "但該場雨天中止、未登板。與栗林良吏昨日的情況相同，兩人都不是短休。",
            "npb.jp 今日實際有五場，看板只列四場；少的那場（軟銀 @ 羅德 "
            "13:30 JST）在看板產出前已開打。",
            "全場讓分與上半場盤仍不定價，理由見各場風險欄。",
        ],
    )


if __name__ == "__main__":
    print(build_report().render())
