"""2026-09-10 NPB 全六場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_09_10.py``

資料狀況
--------
* **官方預告先發完整可取得**，六場十二人全數與看板一致。
* 十二人的 **投球側也逐一對上**: npb.jp 的個人投手成績用前置 ``*``
  標記左投，十二人的左右手與看板標註 **12/12 相符**。這是一個
  獨立於名字的交叉驗證 —— 名字對了但左右手抄錯，模型不會發現。
* 十二人全部越過 25 局門檻。最低是 **佐藤爽（西武）38.0 局**。

⚠️ 一位季中由後援轉先發
----------------------
**高野脩汰（羅德）** 季內 28 場 43.0 局、IP/G 僅 **1.54** —— 那是
27 場後援加 1 場先發的混合值，不能當先發局數用。逐場查證:

    2026-08-25  第2任  3.0 局  39 球   ← 後援
    2026-09-01  第1任  7.0 局  98 球   ← 生涯首度先發，勝投

今日採用 **5.50 局**（`DEFAULT_IP_PER_START`，聯盟典型先發局數）。
9/1 那天他還沒有任何先發紀錄，當時取保守的 4.00 局; 現在有一場
7 局 98 球的實績，但一場不足以主張他是七局投手，取聯盟典型值。
他的失分率同樣是後援時期累積的，`ROLE_CHANGED` 會觸發壓力測試。

✅ 一位查證後排除的嫌疑
---------------------
**髙島泰都（歐力士）** 季內 20 場 86.2 局、IP/G **4.33**，數字上
看起來也像後援與先發的混合值。逐場查證後 **不是**:

    2026-08-29  第1任  5.0 局  78 球
    2026-09-04  第1任  5.0 局  89 球   ← 勝投

兩場都是先發、都投滿 5 局。他就是一位「投不深的先發」，
4.33 局是真實的先發局數，不做角色修正。
**IP/G 偏低只是嫌疑，不是判決 —— 要看逐場的登板順位才算數。**

⚠️ 又一次中性場地
----------------
**西武 @ 歐力士 在「ほっと神戸」**，連續第二天。該球場本季累計
只有 **4 場**，配適出的 0.9957 幾乎完全被收縮到 1.0，不是可用的
估計 —— 它不在 `PARK_FACTORS_2026` 的主要球場表內，`park_factor()`
會退回中性值 1.0 且 `park_factor_known` 記為 False。
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

DATE = "2026-09-10"
DATA_AS_OF = "2026-09-10 15:00 JST (UTC 06:00)"

GAMES = [
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="東北樂天金鷲", home_team="千葉羅德",
        away_starter="岸孝之 (右)", home_starter="高野脩汰 (左)",
        venue="ZOZOマリンスタジアム (露天)",
        handicap_raw="0", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7.5", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-10", f5_total_raw="4-25",
        # 純小數 = 字面上的半球盤，永不和局。使用者 2026-08-13 已目視確認。
        attested_fields=frozenset({"total"}),
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="日本火腿", home_team="福岡軟銀鷹",
        away_starter="加藤貴之 (左)", home_starter="松本晴 (左)",
        venue="みずほPayPay (巨蛋)",
        handicap_raw="1+10", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7+25", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-50", f5_total_raw="4+75",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="廣島鯉魚", home_team="阪神虎",
        away_starter="栗林良吏 (右)", home_starter="才木浩人 (右)",
        venue="甲子園 (露天)",
        handicap_raw="1+10", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="5+50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-50", f5_total_raw="3+50",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="西武獅", home_team="歐力士猛牛",
        away_starter="佐藤爽 (左)", home_starter="髙島泰都 (右)",
        # ⚠️ 中性場地，本季僅 4 場，球場係數不可用。
        venue="ほっと神戸 (露天・中性場地)",
        handicap_raw="1+70", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7-50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-20", f5_total_raw="4+50",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="養樂多燕子", home_team="橫濱DeNA灣星",
        away_starter="吉村貢司郎 (右)", home_starter="深沢鳳介 (右)",
        venue="横浜 (露天)",
        handicap_raw="1-50", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="8+50", over_hk=0.930, under_hk=0.930,
        # 上半大小同樣是純小數，但上半盤不定價，僅記錄。
        f5_handicap_raw="1+40", f5_total_raw="4.5",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="中日龍", home_team="讀賣巨人",
        away_starter="金丸夢斗 (左)", home_starter="井上温大 (左)",
        venue="東京ドーム (巨蛋)",
        handicap_raw="1+25", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6+25", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-40", f5_total_raw="3-75",
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
    "ZOZOマリンスタジアム (露天)": "ZOZOマリン",
    "みずほPayPay (巨蛋)": "みずほPayPay",
    "甲子園 (露天)": "甲子園",
    "ほっと神戸 (露天・中性場地)": "ほっと神戸",
    "横浜 (露天)": "横浜",
    "東京ドーム (巨蛋)": "東京ドーム",
}

OPEN_AIR = {"ZOZOマリン", "甲子園", "ほっと神戸", "横浜"}

NEUTRAL_PARK_FACTOR = 1.0
"""配適資料裡沒有 (或場次太少不足以估計) 的球場採用的中性值。
今日的ほっと神戸本季累計 4 場，適用。"""


def park_factor(game: BoardGame) -> float:
    """球場係數；資料不足的球場退回中性值並由門檻揭露。"""
    return cal.PARK_FACTORS_2026.get(PARK_KEY[game.venue], NEUTRAL_PARK_FACTOR)


DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限，比 Bankroll 的 5,000 更緊。"""

OPEN_AIR_MIN_EV = GATE_OPEN_AIR_MIN_EV
"""露天球場的 EV 門檻，由 `bethero.gates` 統一定義（2026-09-02 起 = 0.04）。"""

STARTED: set[str] = set()
"""本報告產出時 (15:00 JST) 六場皆未開賽，18:00 開打。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "ZOZOマリン": "露天，臨海、風的影響在十二座球場中最大。未取得逐時預報",
    "甲子園": "露天。未取得逐時風向／氣溫預報",
    "ほっと神戸": "露天，中性場地。未取得逐時預報",
    "横浜": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。
今日十二人全部通過，最低是 佐藤爽 38.0 局。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。今日用於高野脩汰。"""

# (顯示名, 收縮後失分率係數, 今日預期局數, 說明, 季內 IP/G)
STARTERS = {
    "楽天": ("岸孝之", 0.897, 6.00,
             "9 場 54.0 局 防禦率 2.67、失分率 2.83、每場 6.0 局", 6.00),
    "ロッテ": ("高野脩汰", 0.981, DEFAULT_IP_PER_START,
              "28 場 43.0 局 防禦率 3.14；季內 IP/G 1.54 是 27 場後援加 "
              "1 場先發的混合值，9/1 首度先發投 7 局 98 球", 1.54),
    "日本ハム": ("加藤貴之", 0.947, 5.67,
                "18 場 102.0 局 防禦率 2.74（失分率 3.35）", 5.67),
    "ソフトバンク": ("松本晴", 0.914, 5.63,
                  "18 場 101.1 局 防禦率 3.02（失分率 3.11）", 5.63),
    "広島": ("栗林良吏", 0.852, 6.51,
             "15 場 97.2 局 防禦率 2.49、失分率 2.76、每場 6.5 局 —— 本日次佳；"
             "季中由後援轉先發但 IP/G 早已是先發水準", 6.51),
    "阪神": ("才木浩人", 0.900, 6.19,
             "21 場 130.0 局 防禦率 2.63（失分率 2.84）、每場 6.2 局", 6.19),
    "西武": ("佐藤爽", 1.026, 5.43,
             "7 場 38.0 局 防禦率 3.79；**本日最薄樣本**，已重收縮至近聯盟平均", 5.43),
    "オリックス": ("髙島泰都", 1.190, 4.33,
                "20 場 86.2 局 防禦率 4.05、失分率 4.36 —— **本日最差**；"
                "每場僅 4.3 局，但 8/29 與 9/4 皆為第1任先發、都投滿 5 局，"
                "確認是真實的先發局數而非後援混合值", 4.33),
    "ヤクルト": ("吉村貢司郎", 1.118, 5.85,
                "18 場 105.1 局 防禦率 4.61（失分率 4.78）", 5.85),
    "DeNA": ("深沢鳳介", 1.072, 5.33,
             "8 場 42.2 局 防禦率 3.38、失分率 4.43；樣本偏薄", 5.33),
    "中日": ("金丸夢斗", 0.864, 6.42,
             "22 場 141.1 局 防禦率 2.67、失分率 2.93、每場 6.4 局 —— 局數最多", 6.42),
    "巨人": ("井上温大", 0.791, 6.26,
             "19 場 119.0 局 防禦率 2.19、失分率 2.50、每場 6.3 局 —— **本日最佳**", 6.26),
}

STARTER_IP = {
    "楽天": 54.0, "ロッテ": 43.0, "日本ハム": 102.0, "ソフトバンク": 101.3,
    "広島": 97.7, "阪神": 130.0, "西武": 38.0, "オリックス": 86.7,
    "ヤクルト": 105.3, "DeNA": 42.7, "中日": 141.3, "巨人": 119.0,
}

ROLE_CHANGED = {"ロッテ"}
"""高野脩汰 —— 季內 IP/G 1.54 是 27 場後援加 1 場先發的混合值。
他的失分率也是在後援登板中累積的（後援本來就比先發好看），
壓力測試改用球隊季內守備係數。

栗林良吏（廣島）同樣是季中由後援轉先發，但他的季內 IP/G 已達 6.51、
97.2 局全部是先發水準的樣本，混合值的問題不存在，故不列入。"""

BULLPEN_NOTE = {
    "楽天": "9/9 用 3 人（荘司 6 局 111 球，牛棚 2 人 51 球；4-10 敗）—— 正常",
    "ロッテ": "9/9 用 **6 人**（毛利 4 局即退場，牛棚 5 人 67 球；10-4 勝）"
              "—— 人次多但球數輕",
    "日本ハム": "9/9 用 5 人（達孝太 3.2 局 80 球即退場，牛棚 4 人 82 球；4-5 敗）"
                "—— 連兩日吃緊，牛棚係數 1.144 已是全聯盟第 3 差",
    "ソフトバンク": "9/9 用 4 人（上沢 6 局，牛棚 3 人 53 球；5-4 勝）—— 正常",
    "広島": "9/9 用 **2 人**（床田 8 局 106 球、森浦 1 局 18 球；3-1 勝）"
            "—— 本日最充分",
    "阪神": "9/9 用 4 人（髙橋遥人 6.1 局 111 球，牛棚 3 人 53 球；1-3 敗）—— 正常",
    "西武": "9/9 用 4 人（菅井 3.2 局 75 球，牛棚 3 人 80 球；8-0 完封勝）—— 正常",
    "オリックス": "9/9 用 5 人（九里 4 局失 6，牛棚 4 人 75 球；0-8 敗）—— 略吃緊",
    "ヤクルト": "9/9 用 **2 人**（山野 5.1 局 103 球、石原 16 球；2-9 敗）—— 充分",
    "DeNA": "9/9 用 3 人（石田裕太郎 5 局 95 球，牛棚 2 人僅 20 球；9-2 勝）—— 充分",
    "中日": "9/9 用 4 人（大野 5 局 91 球，牛棚 3 人 72 球；1-5 敗）—— 正常",
    "巨人": "9/9 用 **7 人**（マタ 3 局 46 球即退場，牛棚 6 人 101 球；5-1 勝）"
            "—— **本日最吃緊**",
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
            lineup_note="15:00 JST 尚未公布，依使用者指示略過",
            bullpen_note=f"{game.home_team}：{BULLPEN_NOTE[home]}；"
                         f"{game.away_team}：{BULLPEN_NOTE[away]}",
            park_weather_note=(
                f"球場係數 {park_factor(game):.3f}"
                + ("（2026 實測）。" if PARK_KEY[game.venue] in cal.PARK_FACTORS_2026
                   else "（⚠️ 本季僅 4 場，採中性值 1.0）。")
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
            f"校準已更新到 9/9 收盤（{cal.SAMPLE_GAMES} 場）。"
            f"聯盟每隊每場 {cal.LEAGUE_RPG:.4f} 分、主場乘數 {cal.HOME_EDGE:.4f}。",
            "**最近窗口的得分水位已翻負。** 45 天窗口的每隊 RPG 由 8/15 的 3.7688 "
            "掉到 3.6186、30 天由 3.7137 掉到 3.6655，且最近 14 天比 4-6 月 "
            "**低 0.206 分**（-0.39 個標準誤）。7-9 月 vs 4-6 月的差距也由 8/28 的 "
            "1.29 個標準誤退回 **1.04 個標準誤**。當初沒有採用近窗口 RPG 是對的 —— "
            "見 config/calibration_2026.py 的 LEAGUE_RPG_RECENT 說明。",
            "十二位先發的 **左右手已用 npb.jp 的左投標記獨立核對，12/12 相符**。",
            "高野脩汰（羅德）季中由後援轉先發，季內 IP/G 1.54 是混合值，"
            f"今日採用 {DEFAULT_IP_PER_START:.2f} 局並觸發壓力測試。",
            "髙島泰都（歐力士）IP/G 4.33 一度被懷疑是混合值，逐場查證後排除："
            "8/29 與 9/4 皆為第1任先發且都投滿 5 局。",
            "ほっと神戸為中性場地、本季累計僅 4 場，球場係數不可用，"
            "採中性值 1.0 並記為缺口。",
            "⚠️ **火腿 @ 軟銀 的分歧 +1.57 分是本季已下注部位裡最大的一級**"
            "（歷史 55 場的分歧範圍是 0.01-1.83）。9/10 的分層檢驗顯示"
            "模型誤差 **不** 集中在高分歧場次（0.4 個標準誤），而且最高分歧層的 "
            "ROI 反而最好（+36.1%），所以不因分歧大而打折 —— "
            "但這是今天最該盯的一場，見 analysis/validate_disagreement_strata.py。",
            "全場讓分與上半場盤仍不定價，理由見各場風險欄。",
        ],
    )


if __name__ == "__main__":
    print(build_report().render())
