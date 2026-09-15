"""2026-09-15 NPB 全六場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_09_15.py``

六場都 18:00 JST 開賽，時間充裕。校準已涵蓋到 9/14 收盤（771 場），
由 ``cal.freshness_note()`` 在報告最上面自動確認 —— 這是 9/15 新加的防護，
不再靠「記得跑重配適」。

⚠️ 三位先發本季局數不足 25 局
----------------------------
    ルーカス（阪神）    4 場 19.2 局
    森脇亮介（西武）   20 場 18.0 局   ← 而且是後援用法
    伊藤樹（樂天）      3 場 13.0 局

`starter_stats_known` 記為 False。**西武 @ 樂天 那場兩位先發都不足**，
是本輪第一次遇到。三場都不可能成為推薦。

⚠️ 兩位是後援用法，不是先發
--------------------------
**森脇亮介（西武）** 20 場 18.0 局、**IP/G 僅 0.90**。逐場查證: 9/12 是
第5任投 1 局 10 球。他是不折不扣的後援投手，今天應該是 **計畫性開局投手**。

**鈴木健矢（廣島）** 30 場 58.1 局、**IP/G 1.94**、防禦率 2.16。
局數越過 25 局門檻（所以 `starter_stats_known` 為 True），但 1.94 局的
用法不是先發。他在廣島近四場（9/11-9/14）都沒登板。

兩人都列入 `ROLE_CHANGED`，預期局數採其季內 IP/G ——
`blended_defence` 的權重下限 0.35 會把大部分權重交給牛棚，
那正是開局投手該有的結構。

⚠️ 模型無法表達「開局投手」這件事
--------------------------------
`cal.OPENER_F5_EFFECT` 記錄過: 計畫性開局投手的場次全場平均 7.43 分，
正規先發對決 6.89 分，**差 +0.54 分**。模型用固定比例把 lambda 切給
先發與牛棚，完全無法表達「把失分往前搬」這件事。

所以西武 @ 樂天（森脇開局）與廣島 @ 養樂多（鈴木開局）的預期總分
**可能偏低約半分**。前者已被門檻擋下; 後者沒有，已在該場風險欄標明。
（那組數字出自有 bug 的舊解析，方向應成立但數值待重算，故僅揭露不套用。）

⚠️ 巨人與 DeNA 的牛棚昨晚被榨乾
------------------------------
9/14 兩隊打滿 12 局:

    巨人   用 **10 人**，牛棚 9 人 144 球
    DeNA  用 **9 人**，牛棚 8 人 105 球

模型的牛棚係數是整季平均，**完全不知道昨晚發生了什麼**。今天這場
（巨人 @ DeNA）的實際失分很可能高於模型預期。對照組: 中日昨天
マラー 完投 9 局、牛棚 0 人，今天是全聯盟最充分的一隊。

查證結果
--------
* 六場的對戰、球場、主客與先發，全部與 npb.jp 賽程頁的「先發」欄相符。
* **十二位先發的姓名與投球側 12/12 相符**。三個外籍名字已對上:
  看板「盧卡斯」= ルーカス（阪神）、「莫伊聶羅」= モイネロ（軟銀）、
  「赫耶勒」= **ジェリー**（歐力士）。最後一個音譯差很多，是逐一比對
  歐力士的四位外籍投手（エスピノーザ／ジェリー／ペルドモ／マチャド）
  後確定的 —— 只有 ジェリー 的用法與局數對得上先發。
* **鈴木健矢已不在日本火腿名單上**，本季成績全在廣島頁面（30 場 58.1 局）。
  與 9/12 的尾形崇斗一樣是季中換隊，但他的成績沒有分散在兩隊。

其他
----
* 看板第 5 場的 **讓球** 是純小數 `0.5`、第 1 場的 **上半大小** 是 `3.5`。
  兩者都不定價，`audit_for("total")` 不受影響。
* エスコンＦ 是開閉式屋頂，本檔視為巨蛋（`weather_known` 為 True）。
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

DATE = "2026-09-15"
DATA_AS_OF = "2026-09-15 14:30 JST (UTC 05:30)"

T = "18:00 JST（看板 17:00 台北）"

GAMES = [
    BoardGame(
        date=DATE, start_time=T,
        away_team="中日龍", home_team="阪神虎",
        away_starter="柳裕也 (右)", home_starter="盧卡斯 (左)",
        venue="甲子園 (露天)",
        handicap_raw="1+20", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6-75", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-50", f5_total_raw="3.5",
    ),
    BoardGame(
        date=DATE, start_time=T,
        away_team="千葉羅德", home_team="日本火腿",
        away_starter="田中晴也 (右)", home_starter="北山亘基 (右)",
        venue="エスコンＦ (開閉式屋頂)",
        handicap_raw="2+40", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7.5", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1+5", f5_total_raw="4-50",
        # 純小數 = 字面上的半球盤，永不和局。使用者 2026-08-13 已目視確認。
        attested_fields=frozenset({"total"}),
    ),
    BoardGame(
        date=DATE, start_time=T,
        away_team="福岡軟銀鷹", home_team="歐力士猛牛",
        away_starter="莫伊聶羅 (左)", home_starter="赫耶勒 (右)",
        venue="京セラD大阪 (巨蛋)",
        handicap_raw="2-10", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7+50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1平", f5_total_raw="4+75",
    ),
    BoardGame(
        date=DATE, start_time=T,
        away_team="西武獅", home_team="東北樂天金鷲",
        away_starter="森脇亮介 (右)", home_starter="伊藤樹 (右)",
        venue="楽天モバイル (露天)",
        handicap_raw="0", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7平", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0", f5_total_raw="4+75",
    ),
    BoardGame(
        date=DATE, start_time=T,
        away_team="廣島鯉魚", home_team="養樂多燕子",
        away_starter="鈴木健矢 (右)", home_starter="吉村貢司郎 (右)",
        venue="神宮 (露天)",
        # ⚠️ 讓球是純小數 0.5；讓球不定價，且 audit_for("total") 不受影響。
        handicap_raw="0.5", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7-50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-10", f5_total_raw="4-25",
    ),
    BoardGame(
        date=DATE, start_time=T,
        away_team="讀賣巨人", home_team="橫濱DeNA灣星",
        away_starter="戶鄉翔征 (右)", home_starter="東克樹 (左)",
        venue="横浜 (露天)",
        handicap_raw="1+10", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6.5", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-75", f5_total_raw="4+75",
        attested_fields=frozenset({"total"}),
    ),
]

JP = {
    "中日龍": "中日", "阪神虎": "阪神",
    "千葉羅德": "ロッテ", "日本火腿": "日本ハム",
    "福岡軟銀鷹": "ソフトバンク", "歐力士猛牛": "オリックス",
    "西武獅": "西武", "東北樂天金鷲": "楽天",
    "廣島鯉魚": "広島", "養樂多燕子": "ヤクルト",
    "讀賣巨人": "巨人", "橫濱DeNA灣星": "DeNA",
}
PARK_KEY = {
    "甲子園 (露天)": "甲子園",
    "エスコンＦ (開閉式屋頂)": "エスコンＦ",
    "京セラD大阪 (巨蛋)": "京セラD大阪",
    "楽天モバイル (露天)": "楽天モバイル",
    "神宮 (露天)": "神宮",
    "横浜 (露天)": "横浜",
}

OPEN_AIR = {"甲子園", "楽天モバイル", "神宮", "横浜"}
"""エスコンＦ 是開閉式屋頂，視為巨蛋。"""

NEUTRAL_PARK_FACTOR = 1.0
"""配適資料裡沒有的球場採用的中性值。今日六場都在主要球場，未用到。"""


def park_factor(game: BoardGame) -> float:
    return cal.PARK_FACTORS_2026.get(PARK_KEY[game.venue], NEUTRAL_PARK_FACTOR)


DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限，比 Bankroll 的 5,000 更緊。"""

OPEN_AIR_MIN_EV = GATE_OPEN_AIR_MIN_EV
"""露天球場的 EV 門檻，由 `bethero.gates` 統一定義（2026-09-02 起 = 0.04）。"""

STARTED: set[str] = set()
"""本報告產出時 (14:30 JST) 六場皆未開賽，18:00 開打。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "甲子園": "露天。未取得逐時風向／氣溫預報",
    "楽天モバイル": "露天。未取得逐時風向／氣溫預報",
    "神宮": "露天，**全聯盟得分最高的球場**（PF 1.180）。未取得逐時預報",
    "横浜": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。
今日 **三人未過**: ルーカス 19.2 局、森脇亮介 18.0 局、伊藤樹 13.0 局。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。今日未用到 ——
局數不足的三人都仍有自己的 IP/G 可用。"""

# (顯示名, 收縮後失分率係數, 今日預期局數, 說明, 季內 IP/G)
STARTERS = {
    "中日": ("柳裕也", 0.767, 6.26,
             "23 場 144.0 局 失分率 2.44、每場 6.3 局 —— 本日最佳之一", 6.26),
    "阪神": ("ルーカス", 1.127, 4.92,
             "本季僅 4 場 19.2 局、失分率 4.58 —— **查無可用先發樣本**", 4.92),
    "ロッテ": ("田中晴也", 1.145, 5.45,
              "14 場 76.1 局 失分率 4.60 —— 本日最差", 5.45),
    "日本ハム": ("北山亘基", 0.851, 6.29,
                "21 場 132.0 局 失分率 2.86、每場 6.3 局", 6.29),
    "ソフトバンク": ("モイネロ", 0.734, 7.07,
                  "5 場 35.1 局 防禦率 **0.76**、失分率 1.02、每場 7.1 局 "
                  "—— **本日最佳**；登板數少但局數已越過門檻", 7.07),
    "オリックス": ("ジェリー", 1.048, 5.33,
                "20 場 106.2 局 失分率 3.54、每場 5.3 局", 5.33),
    "西武": ("森脇亮介", 0.940, 0.90,
             "20 場 **18.0 局**、**IP/G 0.90** —— 純後援投手（9/12 為第5任投 1 局），"
             "今日應為計畫性開局投手；查無可用先發樣本", 0.90),
    "楽天": ("伊藤樹", 0.992, 4.33,
             "本季僅 3 場 13.0 局 —— **查無可用先發樣本**", 4.33),
    "広島": ("鈴木健矢", 0.793, 1.94,
             "30 場 58.1 局 防禦率 2.16，局數越過門檻，但 **IP/G 僅 1.94** "
             "是後援用法；近四場（9/11-9/14）未登板。季中由日本火腿轉隊", 1.94),
    "ヤクルト": ("吉村貢司郎", 1.188, 5.70,
                "19 場 108.1 局 失分率 **5.15** —— 本日最差", 5.70),
    "巨人": ("戶鄉翔征", 0.861, 5.85,
             "11 場 64.1 局 失分率 2.66、每場 5.9 局", 5.85),
    "DeNA": ("東克樹", 0.793, 6.55,
             "22 場 144.0 局 失分率 2.62、每場 6.6 局", 6.55),
}

STARTER_IP = {
    "中日": 144.0, "阪神": 19.7, "ロッテ": 76.3, "日本ハム": 132.0,
    "ソフトバンク": 35.3, "オリックス": 106.7, "西武": 18.0, "楽天": 13.0,
    "広島": 58.3, "ヤクルト": 108.3, "巨人": 64.3, "DeNA": 144.0,
}

ROLE_CHANGED = {"西武", "広島"}
"""兩位是後援用法而非先發:

* 森脇亮介（西武）IP/G 0.90 —— 純後援，今日應為計畫性開局投手。
* 鈴木健矢（廣島）IP/G 1.94 —— 局數過門檻但用法是後援。

兩人的失分率都是在短局數登板中累積的（後援本來就比先發好看），
壓力測試改用球隊季內守備係數。"""

BULLPEN_NOTE = {
    "中日": "9/14 **マラー 完投 9 局 106 球失 0、牛棚 0 人** —— 本日最充分",
    "阪神": "9/14 用 5 人（伊藤将司 5 局 73 球失 4，牛棚 4 人 66 球；0-6 敗）—— 正常",
    "ロッテ": "9/13 用 4 人（ルケーシー 4 局 100 球失 5，牛棚 3 人 56 球；4-7 敗）；"
              "昨天休兵 —— 充分",
    "日本ハム": "9/13 用 4 人（有原航平 6 局 90 球失 1，牛棚 3 人 42 球；7-1 勝）；"
                "昨天休兵 —— 充分",
    "ソフトバンク": "9/13 用 **6 人**（上茶谷大河 4 局 80 球失 4 即退場，牛棚 5 人 53 球；"
                  "7-4 勝）；昨天休兵 —— 已回復",
    "オリックス": "9/13 休兵、昨天亦休兵 —— 充分；但牛棚係數 1.262 仍是全聯盟最差",
    "西武": "9/13 用 4 人（武内夏暉 5.1 局 96 球失 7，牛棚 3 人 60 球；1-7 敗）；"
            "昨天休兵。**今日若由森脇開局，牛棚要吃下約 8 局**",
    "楽天": "9/13、9/14 皆休兵 —— 充分；但牛棚係數 1.351 是全聯盟最差之一",
    "広島": "9/14 用 5 人（玉村昇悟 5.1 局 99 球失 0，牛棚 4 人 43 球；3-0 勝）"
            "—— 正常。**今日若由鈴木開局，牛棚負擔會明顯加重**",
    "ヤクルト": "9/14 用 6 人（増居翔太 4 局 76 球失 2 即退場，牛棚 5 人 77 球；"
                "0-3 敗）—— 略吃緊",
    "巨人": "9/14 打滿 12 局、用 **10 人**（西舘勇陽 3 局 54 球即退場，"
            "牛棚 9 人 144 球）—— **本日最吃緊，模型完全不知道這件事**",
    "DeNA": "9/14 打滿 12 局、用 **9 人**（平良拳太郎 5 局 80 球，牛棚 8 人 105 球）"
            "—— **本日次吃緊，模型完全不知道這件事**",
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
        for t, label_t in ((home, game.home_team), (away, game.away_team)):
            if t in ("巨人", "DeNA"):
                risks.append(
                    f"⚠️ **{label_t} 的牛棚昨晚（9/14）打滿 12 局被大量消耗**"
                    f"（{'用 10 人、牛棚 9 人 144 球' if t == '巨人' else '用 9 人、牛棚 8 人 105 球'}）。"
                    "模型的牛棚係數是整季平均，**完全不知道這件事** —— "
                    "今天的實際失分很可能高於模型預期，方向偏大分。"
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
            lineup_note="14:30 JST 尚未公布，依使用者指示略過",
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
        "**三位先發本季局數不足 25 局**：ルーカス（阪神）19.2 局、"
        "森脇亮介（西武）18.0 局、伊藤樹（樂天）13.0 局。"
        "**西武 @ 樂天 兩位先發都不足**，是本輪第一次。三場皆不可能成為推薦。",
        "**兩位是後援用法而非先發**：森脇亮介 IP/G **0.90**（9/12 為第5任投 1 局，"
        "今日應為計畫性開局投手）、鈴木健矢（廣島）IP/G **1.94**（局數過門檻但"
        "用法是後援，近四場未登板）。兩人的預期局數採其 IP/G，"
        "權重下限 0.35 會把大半交給牛棚。",
        "⚠️ **開局投手的場次模型會偏低約半分**（7.43 vs 6.89），"
        "已在該兩場的風險欄標明，但不套用數值修正 —— 那組數字出自有 bug 的舊解析。",
        "⚠️ **巨人與 DeNA 的牛棚昨晚打滿 12 局被榨乾**（巨人用 10 人／牛棚 144 球，"
        "DeNA 用 9 人／牛棚 105 球）。模型的牛棚係數是整季平均，完全不知道這件事。"
        "對照組：中日昨天マラー完投、牛棚 0 人。",
        "十二位先發的 **姓名與投球側 12/12 相符**。三個外籍名字已對上："
        "「盧卡斯」= ルーカス、「莫伊聶羅」= モイネロ、"
        "**「赫耶勒」= ジェリー**（音譯差很大，是逐一比對歐力士四位外籍投手後確定的）。",
        "鈴木健矢已不在日本火腿名單上，本季成績全在廣島頁面 —— 季中換隊，"
        "但與 9/12 的尾形崇斗不同，他的成績沒有分散在兩隊。",
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
