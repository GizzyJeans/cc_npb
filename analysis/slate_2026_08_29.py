"""2026-08-29 NPB 全六場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_08_29.py``

本日的資料狀況是這輪最差的
--------------------------
1. **npb.jp 的 8/29 官方預告先發已取不到** —— 該頁只保留隔日場次，
   產出時 (13:45 JST) 已翻到 8/30。與 8/27 同一個問題。
   改用賽程頁的 `pit` 欄位，那是官方資料但 **只給主隊先發**。

2. **看板本身有四場沒有列先發**。賽程頁補上了其中三個主隊
   (阪神 大竹、廣島 玉村、歐力士 髙島)，但 **三個客隊先發至今未公布**:
   巨人、養樂多、軟銀。

   `starters_confirmed` 是 **硬性** 門檻。這三場一律不可下注，
   模型仍會定價，但那只是紀錄，不是建議。

3. **日本火腿先發大川慈英本季只投 0.2 局、防禦率 27.00**。
   模型對他等於沒有輸入，而看板把這場開到 **9+75 —— 全日最高**。

   這與 8/27 養樂多 石川雅規 (本季零登板、盤口 8.5) 是同一個模式，
   而那次的結果是: 石川投 0.1 局失 6 分、總分 11，模型算出的
   小分 +31.7% 若下注會輸。**市場對「無資料先發」的定價，
   一次都不要跟它作對。**

4. 第一場 (羅德 @ 火腿) 14:00 JST 開打，本報告產出時已接近或已經開賽 ——
   該場的定價僅供事後對帳。

先發角色
--------
今日九名已知先發中，只有 歐力士 髙島泰都 的每場局數偏低 (4.26)，
但仍在 3 局以上，不屬開局投手。無季中角色轉換案例。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bethero.bankroll import Bankroll
from bethero.board import BoardGame
from bethero.ev import devig_proportional, evaluate
from bethero.gates import DataReadiness, Grade, grade
from bethero.lines import total_outcome_probs
from bethero.model import GameModel, NPBEnvironment, TeamInput
from bethero.report import DailyReport, GameAnalysis
from config import calibration_2026 as cal

DATE = "2026-08-29"
DATA_AS_OF = "2026-08-29 13:45 JST (UTC 04:45)"

UNANNOUNCED = {"巨人", "ヤクルト", "ソフトバンク"}
"""客隊先發至今未公布的三隊。`starters_confirmed` 因此為 False (硬性門檻)。"""

GAMES = [
    BoardGame(
        date=DATE, start_time="14:00 JST（看板 13:00 台北）",
        away_team="千葉羅德", home_team="日本火腿",
        away_starter="傑克森／ジャクソン (右)", home_starter="大川慈英 (右)",
        venue="エスコンＦ (巨蛋)",
        handicap_raw="1+90", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="9+75", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0", f5_total_raw="5+50",
    ),
    BoardGame(
        date=DATE, start_time="17:00 JST（看板 16:00 台北）",
        away_team="東北樂天金鷲", home_team="西武獅",
        away_starter="早川隆久 (左)", home_starter="隅田知一郎 (左)",
        venue="ベルーナドーム (巨蛋)",
        handicap_raw="1平", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6.5", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-80", f5_total_raw="4+75",
        # 使用者於 2026-08-13 確認: 裸小數就是字面上的半球盤，不會走盤。
        attested_fields=frozenset({"total"}),
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="讀賣巨人", home_team="阪神虎",
        away_starter="**未公布**", home_starter="大竹耕太郎 (左)",
        venue="甲子園 (露天)",
        handicap_raw="1+10", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6-25", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-60", f5_total_raw="3-50",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="養樂多燕子", home_team="廣島鯉魚",
        away_starter="**未公布**", home_starter="玉村昇悟 (左)",
        venue="マツダスタジアム (露天)",
        handicap_raw="1+90", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6-50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-20", f5_total_raw="3-75",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="福岡軟銀鷹", home_team="歐力士猛牛",
        away_starter="**未公布**", home_starter="髙島泰都 (右)",
        venue="京セラD大阪 (巨蛋)",
        handicap_raw="2+90", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7-50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1+40", f5_total_raw="4+50",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="中日龍", home_team="橫濱DeNA灣星",
        away_starter="穆勒／マラー (左)", home_starter="平良拳太郎 (右)",
        venue="横浜 (露天)",
        handicap_raw="1+40", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="8+75", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-60", f5_total_raw="4-50",
    ),
]

JP = {
    "中日龍": "中日", "讀賣巨人": "巨人",
    "歐力士猛牛": "オリックス", "日本火腿": "日本ハム",
    "福岡軟銀鷹": "ソフトバンク", "東北樂天金鷲": "楽天",
    "西武獅": "西武", "千葉羅德": "ロッテ",
    "廣島鯉魚": "広島", "阪神虎": "阪神",
    "養樂多燕子": "ヤクルト", "橫濱DeNA灣星": "DeNA",
}
PARK_KEY = {
    "エスコンＦ (巨蛋)": "エスコンＦ",
    "ベルーナドーム (巨蛋)": "ベルーナドーム",
    "甲子園 (露天)": "甲子園",
    "マツダスタジアム (露天)": "マツダスタジアム",
    "京セラD大阪 (巨蛋)": "京セラD大阪",
    "横浜 (露天)": "横浜",
}

OPEN_AIR = {"甲子園", "マツダスタジアム", "横浜"}

DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限，比 Bankroll 的 5,000 更緊。"""

OPEN_AIR_MIN_EV = 0.07
"""露天球場的 EV 門檻。scorecard 追蹤其依據: 8/28 收盤時
露天 +0.35 分 (n=34) vs 巨蛋 +0.31 分 (n=36)，差距約 0.0 個標準誤。
門檻的依據持續為零，但今天三場露天全部因先發未公布而不可下注，
所以調不調都沒有影響 —— 留待資料乾淨的日子再處理。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "甲子園": "露天。未取得逐時風向／氣溫預報",
    "マツダスタジアム": "露天。未取得逐時風向／氣溫預報",
    "横浜": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄 (或先發根本未公布) 時採用的聯盟典型先發局數。"""

# (顯示名, 收縮後失分率係數, 今日預期局數, 說明, 季內 IP/G)
STARTERS = {
    "ロッテ": ("ジャクソン", 0.922, 6.19,
              "21 場 130 局 防禦率 3.12（失分率 3.32）、每場 6.2 局", 6.19),
    "日本ハム": ("大川慈英", 1.174, DEFAULT_IP_PER_START,
                "**2 場 0.2 局、防禦率 27.00** —— 等同無輸入，"
                "係數幾乎全部來自聯盟平均", 0.33),
    "楽天": ("早川隆久", 0.844, 6.71,
             "17 場 114 局 防禦率 2.61、每場 6.7 局", 6.71),
    "西武": ("隅田知一郎", 0.862, 7.11,
             "19 場 135 局 防禦率 2.33、每場 7.1 局、僅 19 四球 —— 本日最佳", 7.11),
    "阪神": ("大竹耕太郎", 1.062, 5.76,
             "14 場 80.2 局 防禦率 3.01（失分率 3.68）", 5.76),
    "広島": ("玉村昇悟", 0.919, 5.40,
             "10 場 54 局 防禦率 2.67（失分率 3.00）", 5.40),
    "オリックス": ("髙島泰都", 1.225, 4.26,
                "18 場 76.2 局 防禦率 4.34、失分率 4.70 —— 本日最差，"
                "每場 4.3 局偏短", 4.26),
    "中日": ("マラー", 0.871, 6.42,
             "15 場 96.1 局 防禦率 2.52、每場 6.4 局", 6.42),
    "DeNA": ("平良拳太郎", 1.006, 5.00,
             "17 場 85 局 防禦率 3.60（失分率 3.81）", 5.00),
    # --- 以下三隊先發未公布，一律用聯盟平均佔位 ---
    "巨人": ("**未公布**", 1.000, DEFAULT_IP_PER_START,
             "先發至今未公布 —— 用聯盟平均佔位，此場不可下注", 0.0),
    "ヤクルト": ("**未公布**", 1.000, DEFAULT_IP_PER_START,
                "先發至今未公布 —— 用聯盟平均佔位，此場不可下注", 0.0),
    "ソフトバンク": ("**未公布**", 1.000, DEFAULT_IP_PER_START,
                  "先發至今未公布 —— 用聯盟平均佔位，此場不可下注", 0.0),
}

STARTER_IP = {
    "ロッテ": 130.0, "日本ハム": 0.7, "楽天": 114.0, "西武": 135.0,
    "阪神": 80.7, "広島": 54.0, "オリックス": 76.7, "中日": 96.3, "DeNA": 85.0,
    "巨人": 0.0, "ヤクルト": 0.0, "ソフトバンク": 0.0,
}

ROLE_CHANGED: set[str] = set()
"""今日無季中角色轉換者。"""

BULLPEN_NOTE = {
    "ロッテ": "8/28 用 5 人 —— 正常",
    "日本ハム": "8/28 用 4 人 —— 正常",
    "楽天": "8/28 用 5 人（失 8 分）—— 略吃緊",
    "西武": "8/28 用 4 人 —— 正常",
    "阪神": "8/28 只用 3 人 —— 充分",
    "広島": "8/28 用 4 人 —— 正常",
    "オリックス": "8/28 用 4 人（被完封）—— 正常",
    "中日": "8/28 用 4 人 —— 正常",
    "DeNA": "8/28 用 4 人 —— 正常",
    "巨人": "8/28 用 4 人 —— 正常",
    "ヤクルト": "8/28 用 4 人 —— 正常",
    "ソフトバンク": "8/28 用 4 人（完封歐力士）—— 正常",
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
                     env=ENV, park_factor=cal.PARK_FACTORS_2026[PARK_KEY[game.venue]])


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
    """把樣本不足與角色轉換的先發，換成該隊季內守備係數。

    兩種情況的偏誤方向相同 —— 都會讓該隊今天看起來比實際好:
    樣本不足者的係數幾乎全是聯盟平均; 轉先發者的失分率是後援時期
    累積的，而後援本來就比先發好看。
    """
    def side(team: str) -> TeamInput:
        _, factor, ip_gs, _, _ = STARTERS[team]
        suspect = STARTER_IP[team] < MIN_STARTER_IP or team in ROLE_CHANGED
        dfn = (cal.TEAM_DEFENCE_SEASON[team] if suspect
               else cal.blended_defence(factor, ip_gs, cal.BULLPEN_FACTOR[team]))
        return TeamInput(team, cal.TEAM_OFFENCE[team], dfn, ip_gs)

    return GameModel(home=side(JP[game.home_team]), away=side(JP[game.away_team]),
                     env=ENV, park_factor=cal.PARK_FACTORS_2026[PARK_KEY[game.venue]])


def readiness_for(game: BoardGame) -> DataReadiness:
    open_air = PARK_KEY[game.venue] in OPEN_AIR
    return DataReadiness(
        line_type_confirmed=not game.audit_for("total"),
        starters_confirmed=not (JP[game.away_team] in UNANNOUNCED
                                or JP[game.home_team] in UNANNOUNCED),
        lineups_confirmed=False,
        waived=(frozenset({"lineups_confirmed", "weather_known"}) if open_air
                else frozenset({"lineups_confirmed"})),
        prices_verified=True,
        bullpen_usage_known=True,
        starter_stats_known=not thin_starters(game),
        team_rates_known=True,
        park_factor_known=True,
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
        if thin or changed:
            s_d = stress_season_defence(game).distributions()
            s_ev = evaluate(
                total_outcome_probs(game.total, s_d.total_pmf,
                                    "over" if label == "大分" else "under"),
                game.over_hk, Bankroll().total,
                market[0] if label == "大分" else market[1]).ev
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
                head.append("季中由後援轉先發（失分率是後援時期累積的，"
                            "通常優於先發）：" + "、".join(changed))
            risks.append(
                "；".join(head)
                + "。逐隊方向：" + "；".join(bits)
                + f"。壓力測試：改用季內守備係數後預期總分 "
                  f"{s_d.expected_total():.2f}（原 {dists.expected_total():.2f}，"
                  f"{delta:+.2f}）、{label} EV {s_ev:+.1%}（原 {best.ev:+.1%}）"
                  f"；也就是目前的輸入相對偏向"
                  f"{'小分' if delta > 0 else '大分'}，這個 {label} 的 EV 若有偏差"
                  f"比較可能是被{'低估' if s_ev > best.ev else '高估'}了"
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
            lineup_note="15:30 JST 尚未公布，依使用者指示略過",
            bullpen_note=f"{game.home_team}：{BULLPEN_NOTE[home]}；"
                         f"{game.away_team}：{BULLPEN_NOTE[away]}",
            park_weather_note=(
                f"球場係數 {cal.PARK_FACTORS_2026[PARK_KEY[game.venue]]:.3f}（2026 實測）。"
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
            f"校準已更新到 8/28 收盤（{cal.SAMPLE_GAMES} 場）。"
            f"聯盟每隊每場得分 {cal.LEAGUE_RPG:.4f}、主場係數 {cal.HOME_EDGE:.4f}。",
            "⚠️ **本輪資料狀況最差的一天，三場硬性不可下注。**"
            "npb.jp 的 8/29 官方預告先發已取不到（該頁只保留隔日場次，"
            "產出時 13:45 JST 已翻到 8/30），而 **看板本身有四場沒列先發**。"
            "賽程頁的 `pit` 欄位補上三個主隊（阪神 大竹、廣島 玉村、"
            "歐力士 髙島），但 **巨人、養樂多、軟銀的客隊先發至今未公布**。"
            "`starters_confirmed` 是硬性門檻，這三場一律不可下注。",
            "⚠️ **日本火腿先發大川慈英本季只投 0.2 局、防禦率 27.00**，"
            "模型對他等於沒有輸入 —— 而看板把這場開到 **9+75，全日最高**。"
            "這與 8/27 養樂多石川雅規（本季零登板、盤口 8.5）完全同一個模式，"
            "而那次石川投 0.1 局失 6 分、總分 11，模型的小分 +31.7% 若下注會輸。"
            "**市場對「無資料先發」的定價，一次都不要跟它作對。**",
            "第一場（羅德 @ 火腿）14:00 JST 開打，本報告產出時已接近或已經開賽，"
            "其定價僅供事後對帳，不是可下注的建議。",
            "**得分水位仍不調整，而且調查方向已經轉向。**"
            "8/28 收盤新增的「水位偏誤 vs 選擇偏誤」切分顯示："
            "未下注場次（n=38）的「實際 − 盤口」只有 +0.04 分，等於零 —— "
            "聯盟得分水位沒有問題；但已下注場次（n=32）是 +1.01 分，"
            "差距 1.7 個標準誤。調 `league_rpg` 救不了，"
            "該查的是模型在哪些情境下與市場分歧且方向錯誤。",
            "露天三場（甲子園、マツダ、横浜）今天全部因先發未公布而不可下注，"
            "所以 +7% 門檻調不調都沒有影響。該門檻的依據（露天 vs 巨蛋誤差差距）"
            "已連續兩天為零，留待資料乾淨的日子再處理。",
            "讓分與上半場盤全數不定價。讓分的理由是結構性的："
            "模型的 Var(分差) 被共享環境因子壓窄約 2.3 倍，"
            "且數學上與 dispersion_k 無關。見 analysis/diagnose_margin.py。",
        ],
        sources=[
            "https://npb.jp/games/2026/schedule_08_detail.html"
            "（賽程、8/28 比分、**主隊先發 pit 欄位**）",
            "https://npb.jp/bis/2026/stats/idp1_<team>.html（個人投手成績）",
            "https://npb.jp/scores/2026/<date>/<slug>/box.html（牛棚用球數）",
            "⚠️ https://npb.jp/announcement/starter/ 今日 **無法取得**"
            "（該頁只保留隔日場次，已翻到 8/30）",
            "賠率：使用者提供之看板截圖（2026-08-29）",
        ],
    )


if __name__ == "__main__":
    print(build_report().render())
