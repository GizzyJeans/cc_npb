"""2026-09-12 NPB 全六場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_09_12.py``

⚠️ 五場 14:00 JST 開賽，時間很緊
-------------------------------
今天是週六，六場裡 **五場 14:00 JST（13:00 台北）**，只有西武主場那場
18:00 JST。本報告產出時距第一球約 28 分鐘。這與平日 18:00 開賽的節奏
完全不同 —— 週六的看板要早四小時處理。

⚠️ 一位先發查無本季一軍成績
--------------------------
**ラトリッジ（軟銀）** 完全不在 npb.jp 的軟銀個人投手成績頁上 ——
不是局數太少，是 **本季一軍零登板**。這是 8/18 吉川悠斗的同一種情況。
`starter_stats_known` 記為 False，加上原本就缺的傷病與多家報價，
軟性缺口 3 項 > 2，該場不可能成為推薦。

他的係數只能取聯盟平均（收縮後 1.000，因為樣本為零時完全退回先驗），
預期局數取 `DEFAULT_IP_PER_START` 5.50 局。這兩個數字都不是估計值，
是「沒有資訊」的佔位符 —— 報告裡不應該把它們當成對他的判斷。

⚠️ 一位季中換隊的先發，成績分散在兩隊的頁面
------------------------------------------
**尾形崇斗** 今天是 DeNA 的先發，但他本季在 **兩隊都有成績**:

    ソフトバンク  10 場 12.0 局  失 4  防禦率 3.00   IP/G 1.20  ← 後援
    DeNA        13 場 68.0 局  失 25 防禦率 3.18   IP/G 5.23  ← 先發

本檔 **只採用 DeNA 那段**。理由與高野脩汰、石川柊太的處理一致:
把後援時期的局數併進來會壓低 IP/G（80 局 / 23 場 = 3.48），
讓模型以為他今天只投 3.5 局、而把過多權重給牛棚。
換隊本身也讓兩段樣本不同質（不同聯盟、不同守備、不同用法）。

**這件事只有逐隊查證才看得到。** 只抓 DeNA 的頁面會得到正確答案，
但那是運氣 —— 若先抓到軟銀的頁面就會拿到一組後援數字安在先發頭上。
今天是因為「尾形崇斗同時出現在兩隊名單」才發現的。

⚠️ 栗林良吏連兩場預告先發
------------------------
他 9/10 也被預告先發，但 **那場（廣島 @ 阪神）雨天中止**，他並未登板，
所以本季成績與 9/10 完全相同（15 場 97.2 局）、也沒有短休問題。
若沒查中止紀錄，會誤以為他中兩天就再上。

其他
----
* 看板第 6 場的 **讓球** 欄是純小數 `0.5`。`attested_fields` 只涵蓋
  `total`，所以 `audit()` 會標記它、但 `audit_for("total")` 不會 ——
  讓球盤本來就不定價，不該讓它污染大小盤的門檻。這是 8/25 加上
  `audit_for()` 的原因。
* 六場都在主要球場，無球場係數缺口。
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

DATE = "2026-09-12"
DATA_AS_OF = "2026-09-12 13:25 JST (UTC 04:25)"

EARLY = "14:00 JST（看板 13:00 台北）"
LATE = "18:00 JST（看板 17:00 台北）"

GAMES = [
    BoardGame(
        date=DATE, start_time=EARLY,
        away_team="養樂多燕子", home_team="中日龍",
        away_starter="高梨裕稔 (右)", home_starter="涌井秀章 (右)",
        venue="バンテリンドーム (巨蛋)",
        handicap_raw="1+50", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6-75", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-50", f5_total_raw="3-50",
    ),
    BoardGame(
        date=DATE, start_time=EARLY,
        away_team="千葉羅德", home_team="福岡軟銀鷹",
        away_starter="小島和哉 (左)", home_starter="ラトリッジ (右)",
        venue="みずほPayPay (巨蛋)",
        handicap_raw="1-75", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="8平", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1+60", f5_total_raw="4-75",
    ),
    BoardGame(
        date=DATE, start_time=EARLY,
        away_team="橫濱DeNA灣星", home_team="廣島鯉魚",
        away_starter="尾形崇斗 (右)", home_starter="栗林良吏 (右)",
        venue="マツダスタジアム (露天)",
        handicap_raw="0", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6平", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0", f5_total_raw="3-50",
    ),
    BoardGame(
        date=DATE, start_time=EARLY,
        away_team="東北樂天金鷲", home_team="歐力士猛牛",
        away_starter="早川隆久 (左)", home_starter="Ａ．エスピノーザ (右)",
        venue="京セラD大阪 (巨蛋)",
        handicap_raw="1+90", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6-50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-20", f5_total_raw="3-75",
    ),
    BoardGame(
        date=DATE, start_time=EARLY,
        away_team="阪神虎", home_team="讀賣巨人",
        away_starter="村上頌樹 (右)", home_starter="竹丸和幸 (左)",
        venue="東京ドーム (巨蛋)",
        handicap_raw="1-20", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6+50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-70", f5_total_raw="3-50",
    ),
    BoardGame(
        date=DATE, start_time=LATE,
        away_team="日本火腿", home_team="西武獅",
        away_starter="伊藤大海 (右)", home_starter="隅田知一郎 (左)",
        venue="ベルーナドーム (巨蛋)",
        # ⚠️ 讓球是純小數 0.5; 讓球不定價，且 audit_for("total") 不受影響。
        handicap_raw="0.5", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6-50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-20", f5_total_raw="3-50",
    ),
]

JP = {
    "養樂多燕子": "ヤクルト", "中日龍": "中日",
    "千葉羅德": "ロッテ", "福岡軟銀鷹": "ソフトバンク",
    "橫濱DeNA灣星": "DeNA", "廣島鯉魚": "広島",
    "東北樂天金鷲": "楽天", "歐力士猛牛": "オリックス",
    "阪神虎": "阪神", "讀賣巨人": "巨人",
    "日本火腿": "日本ハム", "西武獅": "西武",
}
PARK_KEY = {
    "バンテリンドーム (巨蛋)": "バンテリンドーム",
    "みずほPayPay (巨蛋)": "みずほPayPay",
    "マツダスタジアム (露天)": "マツダスタジアム",
    "京セラD大阪 (巨蛋)": "京セラD大阪",
    "東京ドーム (巨蛋)": "東京ドーム",
    "ベルーナドーム (巨蛋)": "ベルーナドーム",
}

OPEN_AIR = {"マツダスタジアム"}

NEUTRAL_PARK_FACTOR = 1.0
"""配適資料裡沒有的球場採用的中性值。今日六場都在主要球場，未用到。"""


def park_factor(game: BoardGame) -> float:
    return cal.PARK_FACTORS_2026.get(PARK_KEY[game.venue], NEUTRAL_PARK_FACTOR)


DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限，比 Bankroll 的 5,000 更緊。"""

OPEN_AIR_MIN_EV = GATE_OPEN_AIR_MIN_EV
"""露天球場的 EV 門檻，由 `bethero.gates` 統一定義（2026-09-02 起 = 0.04）。"""

STARTED: set[str] = set()
"""本報告產出時 (13:25 JST) 六場皆未開賽 —— 但五場只剩約 35 分鐘。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "マツダスタジアム": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。
今日 **ラトリッジ（軟銀）本季一軍零登板**，是最極端的一種。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。今日用於ラトリッジ。"""

# (顯示名, 收縮後失分率係數, 今日預期局數, 說明, 季內 IP/G)
STARTERS = {
    "ヤクルト": ("高梨裕稔", 0.837, 5.85,
                "11 場 64.1 局 防禦率 2.66（失分率 2.94）、每場 5.9 局", 5.85),
    "中日": ("涌井秀章", 0.937, 5.67,
             "10 場 56.2 局 防禦率 3.18（失分率同 3.18）", 5.67),
    "ロッテ": ("小島和哉", 1.105, 5.67,
              "17 場 96.1 局 防禦率 3.64、失分率 4.30", 5.67),
    "ソフトバンク": ("ラトリッジ", 1.000, DEFAULT_IP_PER_START,
                  "**本季一軍零登板** —— 係數與局數都是聯盟平均佔位符，"
                  "不是對他的估計", 0.0),
    "DeNA": ("尾形崇斗", 0.935, 5.23,
             "DeNA 時期 13 場 68.0 局 防禦率 3.18（失分率 3.31）、每場 5.2 局；"
             "季初在軟銀另有 10 場 12.0 局的後援成績，**未併入**", 5.23),
    "広島": ("栗林良吏", 0.852, 6.51,
             "15 場 97.2 局 防禦率 2.49、失分率 2.76、每場 6.5 局；"
             "9/10 亦被預告先發但該場雨天中止、未登板", 6.51),
    "楽天": ("早川隆久", 0.860, 6.74,
             "19 場 128.0 局 防禦率 2.74、失分率 2.88、每場 6.7 局", 6.74),
    "オリックス": ("Ａ．エスピノーザ", 0.880, 6.45,
                "20 場 129.0 局 防禦率 2.65、失分率 2.72、每場 6.5 局", 6.45),
    "阪神": ("村上頌樹", 0.746, 6.88,
             "23 場 158.1 局 防禦率 **1.93**、失分率 2.16、每場 6.9 局 "
             "—— **本日最佳**，局數也是全聯盟最多之一", 6.88),
    "巨人": ("竹丸和幸", 1.116, 5.74,
             "19 場 109.0 局 防禦率 3.72、失分率 4.29 —— 本日最差", 5.74),
    "日本ハム": ("伊藤大海", 0.949, 6.55,
                "23 場 150.2 局 防禦率 3.11（失分率 3.40）、每場 6.6 局", 6.55),
    "西武": ("隅田知一郎", 0.825, 7.19,
             "21 場 151.0 局 防禦率 2.21、失分率 2.68、**每場 7.2 局最深**", 7.19),
}

STARTER_IP = {
    "ヤクルト": 64.3, "中日": 56.7, "ロッテ": 96.3, "ソフトバンク": 0.0,
    "DeNA": 68.0, "広島": 97.7, "楽天": 128.0, "オリックス": 129.0,
    "阪神": 158.3, "巨人": 109.0, "日本ハム": 150.7, "西武": 151.0,
}

ROLE_CHANGED: set[str] = set()
"""今日無角色轉換案例。

尾形崇斗雖是季中換隊，但本檔採用的 DeNA 時期樣本 **本身就全部是先發**
（13 場 68 局、IP/G 5.23），沒有混合值問題，因此不列入。
處理方式是「只取換隊後的樣本」，不是「用壓力測試補償」。"""

BULLPEN_NOTE = {
    "ヤクルト": "9/10 用 4 人（吉村貢司郎 3 局 68 球即退場，牛棚 3 人吃 5 局；1-8 敗）"
                "—— 前天吃緊，昨天休兵",
    "中日": "9/10 用 4 人（金丸夢斗 6 局 87 球，牛棚 3 人；3-5 敗）；昨天休兵 —— 充分",
    "ロッテ": "9/11 用 4 人（石川柊太 3.1 局失 8 即退場，牛棚 3 人收尾；1-11 慘敗）"
              "—— 吃緊",
    "ソフトバンク": "9/11 用 3 人（前田悠伍 7 局 105 球失 1，牛棚 2 人；11-1 大勝）"
                  "—— 充分",
    "DeNA": "9/11 用 5 人（片山皓心 5.1 局 116 球，牛棚 4 人；6-1 勝）—— 正常",
    "広島": "9/11 用 5 人（森下暢仁 7 局 107 球失 0，牛棚 4 人吃 2 局；1-6 敗）"
            "—— 正常；9/10 因雨中止已多休一天",
    "楽天": "9/10 用 2 人（岸孝之 7 局 118 球失 6，牛棚 1 人；1-6 敗）；"
            "昨天休兵 —— 充分",
    "オリックス": "9/11 用 5 人（山口廉王 4.2 局 97 球失 4，牛棚 4 人吃 4.1 局；5-4 險勝）"
                "—— 吃緊，牛棚係數 1.259 仍是全聯盟最差",
    "阪神": "9/10 對廣島因雨中止 —— **已連休兩日**，本日最充分",
    "巨人": "9/10 用 4 人（井上温大 6.1 局 109 球，牛棚 3 人；5-3 勝）；"
            "昨天休兵 —— 充分",
    "日本ハム": "9/10 用 2 人（加藤貴之 7 局 99 球，牛棚僅 1 人；2-3 敗）；"
                "昨天休兵 —— 充分",
    "西武": "9/11 用 5 人（渡邉勇太朗 3.2 局 80 球即退場，牛棚 4 人吃 4.1 局；4-5 敗）"
            "—— 吃緊",
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
    out = []
    for t in (JP[game.away_team], JP[game.home_team]):
        if STARTER_IP[t] < MIN_STARTER_IP:
            ip = STARTER_IP[t]
            out.append(f"{STARTERS[t][0]}（"
                       + ("**本季一軍零登板**" if ip == 0
                          else f"本季僅 {ip:.1f} 局") + "）")
    return out


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
            lineup_note="13:25 JST 尚未公布，依使用者指示略過",
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
            f"校準已更新到 9/11 收盤（{cal.SAMPLE_GAMES} 場）。"
            f"聯盟每隊每場 {cal.LEAGUE_RPG:.4f} 分、主場乘數 {cal.HOME_EDGE:.4f}。",
            "⚠️ **週六賽程：五場 14:00 JST（13:00 台北）開賽**，"
            "本報告產出時距第一球僅約 35 分鐘。只有西武主場那場是 18:00 JST。",
            "**ラトリッジ（軟銀）本季一軍零登板**，完全不在 npb.jp 的成績頁上。"
            "他的係數 1.000 與局數 5.50 都是「沒有資訊」的佔位符，不是估計值。"
            "該場軟性缺口 3 項 > 2，不可能成為推薦。",
            "**尾形崇斗（DeNA）季中由軟銀換隊**，成績分散在兩隊頁面："
            "軟銀 10 場 12.0 局（後援）、DeNA 13 場 68.0 局（先發）。"
            "本檔只採用 DeNA 那段 —— 併入後援局數會把 IP/G 壓到 3.48，"
            "讓模型錯把權重給牛棚。只抓對頁面會得到正確答案，但那是運氣。",
            "栗林良吏（廣島）9/10 也曾被預告先發，但 **該場雨天中止、他未登板**，"
            "所以本季成績與 9/10 相同、也沒有短休問題。",
            "六場都在主要球場，無球場係數缺口。",
            "全場讓分與上半場盤仍不定價，理由見各場風險欄。",
        ],
    )


if __name__ == "__main__":
    print(build_report().render())
