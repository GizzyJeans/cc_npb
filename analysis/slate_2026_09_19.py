"""2026-09-19 NPB 全六場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_09_19.py``

⚠️ 週六賽程: 三場 14:00 JST、三場 18:00 JST
-------------------------------------------
本報告產出時距 **14:00 JST 那三場** 只剩幾分鐘。`STARTED` 依實際完成
時間填寫 —— 已開賽的場次 `prices_verified` 為 False，是 **硬性** 門檻，
不可能成為推薦。18:00 JST 的三場還有四小時，不受影響。

這是本輪第三次遇到「看板上有場次即將或已經開打」（8/30、9/13、今天），
三次都在週末或提前開賽的日子。gates-performance 的 X 類記的就是這個，
唯一該讀出來的是 **週末的盤口要早點拿到**，不是放寬門檻。

⚠️ 高野脩汰（羅德）—— 依 9/10 預先寫下的值處理
---------------------------------------------
他的季內 IP/G 仍只有 **1.72**（29 場 50.0 局），因為 27 場後援還壓在
分母裡。但逐場看，他生涯的 **兩次先發都正好投 7.0 局**:

    2026-09-01  第1任  7.0 局  98 球   （生涯首度先發，勝投）
    2026-09-10  第1任  7.0 局  101 球  失 1

9/10 的報告結尾寫著「他已連兩次先發都投 7 局，**下次可用 7.00**」。
今天就是下次，所以採用 7.00 局 —— 這是 **事前寫下的決定**，
不是看到今天的盤口才挑的數字。

他仍列入 `ROLE_CHANGED`: 3.24 的失分率大部分是後援時期累積的，
壓力測試照跑。另外他自 9/10 之後 **九天未登板**（50.0 局未變）。

查證結果
--------
* 六場的對戰、球場、主客與先發，全部與 npb.jp 賽程頁的「先發」欄相符。
* **十二位先發的姓名與投球側 12/12 相符**，今天沒有異體字或音譯問題。
* 除高野脩汰外，其餘十一人都是先發用法（IP/G 4.95-7.23）、
  且全部越過 25 局門檻。最薄的是中西聖輝（中日）34.2 局。
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

DATE = "2026-09-19"
DATA_AS_OF = "2026-09-19 13:47 JST (UTC 04:47)"

EARLY = "14:00 JST（看板 13:00 台北）"
LATE = "18:00 JST（看板 17:00 台北）"

GAMES = [
    BoardGame(
        date=DATE, start_time=EARLY,
        away_team="歐力士猛牛", home_team="日本火腿",
        away_starter="埃斯皮諾薩 (右)", home_starter="伊藤大海 (右)",
        venue="エスコンＦ (開閉式屋頂)",
        handicap_raw="1+30", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7+50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-30", f5_total_raw="4+50",
    ),
    BoardGame(
        date=DATE, start_time=EARLY,
        away_team="福岡軟銀鷹", home_team="東北樂天金鷲",
        away_starter="前田悠伍 (左)", home_starter="早川隆久 (左)",
        venue="楽天モバイル (露天)",
        handicap_raw="1-60", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="8+75", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-80", f5_total_raw="4+50",
    ),
    BoardGame(
        date=DATE, start_time=EARLY,
        away_team="中日龍", home_team="讀賣巨人",
        away_starter="中西聖輝 (右)", home_starter="田中将大 (右)",
        venue="東京ドーム (巨蛋)",
        handicap_raw="1-20", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7-50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0.5", f5_total_raw="4-25",
    ),
    BoardGame(
        date=DATE, start_time=LATE,
        away_team="西武獅", home_team="千葉羅德",
        away_starter="隅田知一郎 (左)", home_starter="高野脩汰 (左)",
        venue="ZOZOマリンスタジアム (露天)",
        handicap_raw="1+5", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7+75", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-50", f5_total_raw="3.5",
    ),
    BoardGame(
        date=DATE, start_time=LATE,
        away_team="廣島鯉魚", home_team="阪神虎",
        away_starter="栗林良吏 (右)", home_starter="村上頌樹 (右)",
        venue="甲子園 (露天)",
        handicap_raw="1+40", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="5+50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-40", f5_total_raw="2.5",
    ),
    BoardGame(
        date=DATE, start_time=LATE,
        away_team="養樂多燕子", home_team="橫濱DeNA灣星",
        away_starter="高梨裕稔 (右)", home_starter="尾形崇斗 (右)",
        venue="横浜 (露天)",
        handicap_raw="1+30", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7+25", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-50", f5_total_raw="4+50",
    ),
]

JP = {
    "歐力士猛牛": "オリックス", "日本火腿": "日本ハム",
    "福岡軟銀鷹": "ソフトバンク", "東北樂天金鷲": "楽天",
    "中日龍": "中日", "讀賣巨人": "巨人",
    "西武獅": "西武", "千葉羅德": "ロッテ",
    "廣島鯉魚": "広島", "阪神虎": "阪神",
    "養樂多燕子": "ヤクルト", "橫濱DeNA灣星": "DeNA",
}
PARK_KEY = {
    "エスコンＦ (開閉式屋頂)": "エスコンＦ",
    "楽天モバイル (露天)": "楽天モバイル",
    "東京ドーム (巨蛋)": "東京ドーム",
    "ZOZOマリンスタジアム (露天)": "ZOZOマリン",
    "甲子園 (露天)": "甲子園",
    "横浜 (露天)": "横浜",
}

OPEN_AIR = {"楽天モバイル", "ZOZOマリン", "甲子園", "横浜"}
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
"""本報告產出時 (13:47 JST / 04:47 UTC) **六場皆未開賽**。

14:00 JST 的三場只剩約 13 分鐘 —— 要下就得立刻下，否則賽後
`prices_verified` 轉 False，該場就只能列為觀察。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "楽天モバイル": "露天。未取得逐時風向／氣溫預報",
    "ZOZOマリン": "露天，臨海、風的影響在十二座球場中最大。未取得逐時預報",
    "甲子園": "露天。未取得逐時風向／氣溫預報",
    "横浜": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。
今日十二人全部通過，最低是中西聖輝 34.7 局。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。今日未用到。"""

# (顯示名, 收縮後失分率係數, 今日預期局數, 說明, 季內 IP/G)
STARTERS = {
    "オリックス": ("Ａ．エスピノーザ", 0.891, 6.40,
                "21 場 134.1 局 失分率 2.75、每場 6.4 局", 6.40),
    "日本ハム": ("伊藤大海", 0.951, 6.61,
                "24 場 158.2 局 失分率 3.40、每場 6.6 局", 6.61),
    "ソフトバンク": ("前田悠伍", 0.708, 5.84,
                  "17 場 99.1 局 防禦率 1.90、失分率 1.90 —— **本日最佳**", 5.84),
    "楽天": ("早川隆久", 0.881, 6.65,
             "20 場 133.0 局 失分率 2.98、每場 6.7 局", 6.65),
    "中日": ("中西聖輝", 1.204, 4.95,
             "7 場 34.2 局 失分率 **5.71** —— 本日最差，樣本也最薄"
             "（剛越過 25 局門檻 9.2 局）", 4.95),
    "巨人": ("田中将大", 1.134, 5.11,
             "12 場 61.1 局 失分率 4.55、每場 5.1 局", 5.11),
    "西武": ("隅田知一郎", 0.818, 7.23,
             "22 場 159.0 局 失分率 2.66、**每場 7.2 局最深**", 7.23),
    "ロッテ": ("高野脩汰", 0.951, 7.00,
              "29 場 50.0 局、季內 IP/G 僅 1.72（27 場後援壓在分母裡）；"
              "但生涯兩次先發 9/1 與 9/10 **都正好投 7.0 局**，"
              "依 9/10 報告預先寫下的值採用 7.00 局。自 9/10 後九天未登板", 1.72),
    "広島": ("栗林良吏", 0.886, 6.42,
             "16 場 102.2 局 失分率 2.98、每場 6.4 局", 6.42),
    "阪神": ("村上頌樹", 0.750, 6.81,
             "24 場 163.1 局 防禦率 **2.15**、每場 6.8 局 —— 本日次佳", 6.81),
    "ヤクルト": ("高梨裕稔", 0.877, 5.78,
                "12 場 69.1 局 失分率 3.25、每場 5.8 局", 5.78),
    "DeNA": ("尾形崇斗", 0.916, 5.40,
             "DeNA 時期 14 場 75.2 局 失分率 3.21；季初在軟銀另有後援成績，"
             "**未併入**（見 9/12 的處理）", 5.40),
}

STARTER_IP = {
    "オリックス": 134.3, "日本ハム": 158.7, "ソフトバンク": 99.3, "楽天": 133.0,
    "中日": 34.7, "巨人": 61.3, "西武": 159.0, "ロッテ": 50.0,
    "広島": 102.7, "阪神": 163.3, "ヤクルト": 69.3, "DeNA": 75.7,
}

ROLE_CHANGED = {"ロッテ"}
"""高野脩汰 —— 季內 IP/G 1.72 仍是 27 場後援加 2 場先發的混合值。
他的 3.24 失分率大部分是後援時期累積的（後援本來就比先發好看），
壓力測試改用球隊季內守備係數。

預期局數不用 IP/G 而用 **7.00**: 生涯兩次先發（9/1、9/10）都正好 7.0 局，
且 9/10 的報告已 **預先寫下** 下次採用 7.00。這不是看今天盤口才挑的數字。"""

BULLPEN_NOTE = {
    "オリックス": "9/17 用 4 人（曽谷 敗投；1-7 敗）；**9/18 休兵** —— 已回復",
    "日本ハム": "9/17 用 4 人（達孝太 勝投；4-2 勝）；**9/18 休兵** —— 已回復",
    "ソフトバンク": "9/17 用 4 人（松本晴 勝投；7-1 大勝）；**9/18 休兵** —— 充分",
    "楽天": "9/17 用 4 人（古謝樹 勝投；5-1 勝）；**9/18 休兵** —— 充分",
    "中日": "9/18 **用 1 人** —— 金丸夢斗 投 8.1 局 113 球，牛棚 0 人（0-2 敗）"
            "—— 本日最充分",
    "巨人": "9/18 用 2 人（井上温大 8 局 110 球失 0，牛棚僅 1 人 14 球；2-0 勝）"
            "—— 充分；牛棚係數 0.823 為全聯盟最佳",
    "西武": "9/17 用 4 人（菅井信也 敗投；2-4 敗）；**9/18 休兵** —— 已回復",
    "ロッテ": "9/17 用 4 人（森 敗投；1-5 敗）；**9/18 休兵** —— 已回復",
    "広島": "9/18 用 2 人（森下暢仁 7 局 106 球失 2，牛棚僅 1 人 8 球；1-2 敗）"
            "—— 充分",
    "阪神": "9/18 用 4 人（大竹耕太郎 7 局 72 球失 0，牛棚 3 人 32 球；2-1 勝）"
            "—— 正常",
    "ヤクルト": "9/18 用 3 人（山野太一 7.2 局 121 球失 1，牛棚 2 人僅 18 球；"
                "3-1 勝）—— 充分",
    "DeNA": "9/18 用 4 人（片山皓心 7 局 114 球失 0，牛棚 3 人 41 球；1-3 敗）"
            "—— 正常",
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
            lineup_note="13:47 JST 尚未公布，依使用者指示略過",
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
        "⚠️ **週六賽程：14:00 JST 的三場（歐力士@火腿、軟銀@樂天、中日@巨人）"
        "距開賽僅約 13 分鐘**，要下就得立刻下。18:00 JST 的三場還有四小時。",
        "這是本輪第三次遇到看板上有場次即將／已經開打（8/30、9/13、今天），"
        "三次都在週末或提前開賽的日子。唯一該讀出來的是 **週末的盤口要早點拿到**。",
        "十二位先發的 **姓名與投球側 12/12 相符**，今天沒有異體字或音譯問題。"
        "十二人也全部越過 25 局門檻，最薄的是中西聖輝（中日）34.2 局。",
        "⚠️ **高野脩汰（羅德）預期局數採 7.00 —— 這是 9/10 預先寫下的值。** "
        "他的季內 IP/G 仍只有 1.72（27 場後援壓在分母裡），但生涯兩次先發"
        "（9/1、9/10）都正好投 7.0 局，9/10 的報告已寫明「下次可用 7.00」。"
        "他仍列入 ROLE_CHANGED，因為失分率是後援時期累積的。",
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
