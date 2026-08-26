"""2026-08-26 NPB 全六場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_08_26.py``

本日最重要的一件事: 三名先發是「季中由後援轉先發」
--------------------------------------------------
模型用 `IP/G`（季內總局數 ÷ 總登板場次）當作「這位先發今天預期投幾局」，
再用它決定先發與牛棚的混合權重。這對整季固定輪值的投手沒問題，
但今天有三個人的 `IP/G` 是 **兩種角色混出來的**，完全代表不了現況:

    投手              季內 IP/G   近期先發實際局數        差距
    鈴木健矢 (広島)      1.72      8/09 6局、8/19 5局      +3.8
    ロング  (ロッテ)     2.53      8 次先發平均 4.75 局     +2.2
    達孝太  (日本ハム)    4.08      7/31 6、8/07 7、8/14 7   +2.6

三人季內都有大量「投 1 局」的後援場次把分母灌大。直接用 `IP/G` 會把
先發權重壓到下限 0.35，等於當成「計畫性開局投手」——
**但他們今天都不是開局投手，是正規輪值的先發。**

怎麼查出來的: 讀快取的逐場 box，看他們是第幾任投手。
ロング 8 次登板全是第 1 任、投 3-7 局；鈴木健矢 7 月前都是第 4-7 任
投 1 局，8/09 起才變成第 1 任投 5-6 局；達孝太 7/31 起同樣轉為第 1 任。

⚠️ 一個附帶的偏誤，方向要記住: 他們的季內失分率是 **後援時期累積的**，
而後援的失分率通常優於先發（短打數、全力投）。所以模型今天會 **高估**
這三人的水準。鈴木健矢最明顯: 季內失分率 2.14 全部來自後援，
模型算出廣島今日守備係數 0.936，而廣島季內是 1.030。
`role_changed()` 標出這些人，壓力測試會把他們換成球隊季內守備係數。

另外 歐力士 齋藤響介 本季只投過 **0.3 局**（外加一次 0 局的後援），
等於首度先發，`starter_stats_known` 記為 False。
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

DATE = "2026-08-26"
DATA_AS_OF = "2026-08-26 15:30 JST (UTC 06:30)"

GAMES = [
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="橫濱DeNA灣星", home_team="廣島鯉魚",
        away_starter="東克樹 (左)", home_starter="鈴木健矢 (右)",
        venue="マツダスタジアム (露天)",
        handicap_raw="1-50", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6-50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1+70", f5_total_raw="3.5",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="讀賣巨人", home_team="養樂多燕子",
        away_starter="井上温大 (左)", home_starter="山野太一 (左)",
        venue="神宮 (露天)",
        handicap_raw="1+50", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7+75", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-50", f5_total_raw="4+75",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="日本火腿", home_team="西武獅",
        away_starter="達孝太 (右)", home_starter="渡邉勇太朗 (右)",
        venue="ベルーナドーム (巨蛋)",
        handicap_raw="1+40", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6.5", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-50", f5_total_raw="3.5",
        # 使用者於 2026-08-13 確認: 裸小數就是字面上的半球盤，不會走盤。
        attested_fields=frozenset({"total"}),
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="福岡軟銀鷹", home_team="千葉羅德",
        away_starter="上沢直之 (右)", home_starter="Ｓ．ロング (左)",
        venue="ZOZOマリンスタジアム (露天)",
        handicap_raw="2+70", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="8+50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1+60", f5_total_raw="4-25",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="阪神虎", home_team="中日龍",
        away_starter="伊藤将司 (左)", home_starter="涌井秀章 (右)",
        venue="バンテリンドーム (巨蛋)",
        handicap_raw="1+50", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7平", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-20", f5_total_raw="4+75",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="東北樂天金鷲", home_team="歐力士猛牛",
        away_starter="荘司康誠 (右)", home_starter="齋藤響介 (右)",
        venue="京セラD大阪 (巨蛋)",
        # 看板上這場的讓分標在主隊列 (與其他五場相反)，且盤口為 0。
        handicap_raw="0", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7-75", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0", f5_total_raw="4-25",
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
    "マツダスタジアム (露天)": "マツダスタジアム",
    "神宮 (露天)": "神宮",
    "ベルーナドーム (巨蛋)": "ベルーナドーム",
    "ZOZOマリンスタジアム (露天)": "ZOZOマリン",
    "バンテリンドーム (巨蛋)": "バンテリンドーム",
    "京セラD大阪 (巨蛋)": "京セラD大阪",
}

OPEN_AIR = {"マツダスタジアム", "神宮", "ZOZOマリン"}

DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限，比 Bankroll 的 5,000 更緊。"""

OPEN_AIR_MIN_EV = 0.07
"""露天球場的 EV 門檻 (一般為 +4%)，2026-08-16 使用者決定。

2026-08-25 起 scorecard.py 會持續追蹤這個門檻的依據:
露天 +0.32 分 (n=25) vs 巨蛋 -0.03 分 (n=28)，差距 0.4 個標準誤 ——
尚無證據顯示露天誤差較大，門檻維持不動。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "マツダスタジアム": "露天。未取得逐時風向／氣溫預報",
    "神宮": "露天。未取得逐時風向／氣溫預報",
    "ZOZOマリン": "露天，臨海、風的影響在十二座球場中最大。未取得逐時預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」(收縮局數 60，25 局只剩約 29% 權重)。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。"""

# (顯示名, 收縮後失分率係數, **今日預期局數**, 說明, 季內 IP/G)
# 第 3 欄刻意 **不是** 季內 IP/G —— 見模組說明的角色轉換問題。
STARTERS = {
    "DeNA": ("東克樹", 0.847, 6.53,
             "19 場 124 局 防禦率 2.47、每場 6.5 局 —— 本日最穩定的先發", 6.53),
    "広島": ("鈴木健矢", 0.821, 5.50,
             "27 場 46.1 局 防禦率 2.14，但 **7 月前全是後援**；"
             "轉先發後 8/09 六局失 1 分（75 球）、8/19 五局失 1 分（76 球）"
             "—— 先發 11 局失 2 分，後援等級的失分率暫時撐住了", 1.72),
    "巨人": ("井上温大", 0.785, 6.28,
             "18 場 113 局 防禦率 2.15、111 三振", 6.28),
    "ヤクルト": ("山野太一", 0.757, 6.39,
                "19 場 121.1 局 防禦率 2.15 —— 本日十二人中最佳", 6.39),
    "日本ハム": ("達孝太", 0.935, 6.67,
                "22 場 89.2 局 防禦率 3.11；7 月中前多為後援，"
                "7/31 起轉先發且連三場投 6-7 局", 4.08),
    "西武": ("渡邉勇太朗", 0.927, 6.52,
             "18 場 117.1 局 防禦率 3.14、每場 6.5 局，但 35 四球偏多", 6.52),
    "ソフトバンク": ("上沢直之", 0.949, 6.02,
                  "16 場 96.1 局 防禦率 2.62（失分率 3.27）", 6.02),
    "ロッテ": ("Ｓ．ロング", 1.192, 4.00,
              "24 場 60.2 局 防禦率 4.75、失分率 5.19；季中由後援轉先發，"
              "8 次先發平均 4.75 局，但 **最近兩場都只投 3 局**", 2.53),
    "阪神": ("伊藤将司", 0.936, 5.10,
             "7 場 35.2 局 防禦率 2.52；樣本偏薄，已重收縮", 5.10),
    "中日": ("涌井秀章", 0.957, 5.71,
             "8 場 45.2 局 防禦率 3.15、僅 3 四球", 5.71),
    "楽天": ("荘司康誠", 1.094, 6.16,
             "19 場 117 局 防禦率 4.08、被全壘打 19 支 —— 本日最差", 6.16),
    "オリックス": ("齋藤響介", 1.351, DEFAULT_IP_PER_START,
                "1 場 0.1 局、防禦率 189.00 —— 等同首度先發，"
                "係數幾乎全部來自聯盟平均", 0.33),
}

STARTER_IP = {
    "DeNA": 124.0, "広島": 46.3, "巨人": 113.0, "ヤクルト": 121.3,
    "日本ハム": 89.7, "西武": 117.3, "ソフトバンク": 96.3, "ロッテ": 60.7,
    "阪神": 35.7, "中日": 45.7, "楽天": 117.0, "オリックス": 0.3,
}

ROLE_CHANGED = {"広島", "ロッテ", "日本ハム"}
"""季中由後援轉先發者。他們的季內失分率是後援時期累積的，通常優於
先發時期，因此模型會 **高估** 他們今天的水準（低估失分）。
壓力測試把這些球隊改用季內守備係數，量化這個偏誤。"""

# 8/24 全聯盟休兵、8/25 全隊出賽，今日為連續第二天比賽。
BULLPEN_NOTE = {
    "DeNA": "8/25 用 5 人（深沢 94 球）—— 正常",
    "広島": "8/25 用 5 人（床田 83 球）—— 正常",
    "巨人": "8/25 用 **7 人**（則本 67 球、赤星 40 球）—— 本日最吃緊",
    "ヤクルト": "8/25 用 5 人（吉村 121 球完投未果）—— 正常",
    "日本ハム": "8/25 只用 3 人（伊藤 104 球）—— 充分",
    "西武": "8/25 只用 3 人（平良 105 球）—— 充分",
    "ソフトバンク": "8/25 **只用 1 人**（モイネロ 115 球完封）—— 牛棚全休，最充分",
    "ロッテ": "8/25 用 4 人（吉川 97 球）—— 正常",
    "阪神": "8/25 用 4 人（西勇 77 球）—— 正常",
    "中日": "8/25 只用 3 人（大野 111 球）—— 充分",
    "楽天": "8/25 用 5 人（伊藤樹 85 球）—— 正常",
    "オリックス": "8/25 用 5 人（九里 102 球）—— 正常",
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
        starters_confirmed=True,
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
            f"校準已更新到 8/25 收盤（{cal.SAMPLE_GAMES} 場）。"
            f"聯盟每隊每場得分 {cal.LEAGUE_RPG:.4f}、主場係數 {cal.HOME_EDGE:.4f}。"
            "神宮 +0.016、マツダ +0.014 是昨天那兩場 14 分與 15 分推上去的。",
            "十二名先發已對照 npb.jp 預告先發公示全名核對一致。"
            "羅德的「隆恩」= Ｓ．ロング；西武的 渡邊/渡邉 又是一組異體字，"
            "全名比對一律先做 NFKC 正規化。",
            "**本日最重要的修正：三名先發是季中由後援轉先發**"
            "（廣島 鈴木健矢、羅德 ロング、火腿 達孝太）。他們的季內 IP/G "
            "分別只有 1.72 / 2.53 / 4.08，直接拿來用會把先發權重壓到下限 0.35、"
            "當成開局投手處理。查逐場 box 確認三人近期都是第 1 任投手且投 3-7 局，"
            "已改用近期先發的實際局數 5.50 / 4.00 / 6.67。",
            "同一件事的附帶偏誤：他們的失分率是 **後援時期** 累積的，"
            "而後援通常比先發好看，所以模型會高估這三人。"
            "鈴木健矢最明顯（季內失分率 2.14 全來自後援）。"
            "三場都有壓力測試量化這個方向。",
            "**DeNA @ 廣島 這注的優勢幾乎全押在鈴木健矢身上**：壓力測試把他換成"
            "廣島季內守備係數後，小分 EV 由 +13.8% 掉到 +0.9%，等於整個邊際消失。"
            "支持模型輸入的直接證據是他轉先發後的兩場：8/09 六局失 1 分、"
            "8/19 五局失 1 分（共 11 局失 2 分），後援等級的失分率確實撐住了 —— "
            "但 11 局就是 11 局，這注的風險集中度是今天三注裡最高的。"
            "對照組：ロング 8/19 三局失 3 分被打 8 支，與他 5.19 的失分率一致，"
            "所以軟銀那注的大分即使在壓力測試下仍有 +9.1%，撐得住。",
            "歐力士 齋藤響介本季只投過 0.1 局，等同首度先發，"
            "`starter_stats_known` 記為 False —— 該門檻不可放棄。",
            "8/24 全聯盟休兵、8/25 全隊出賽，今天是連續第二天比賽。"
            "軟銀昨天モイネロ 115 球完封、**只用 1 名投手**，牛棚最充分；"
            "巨人用了 7 人，最吃緊。",
            "露天三場（マツダ、神宮、ZOZOマリン）維持 +7% EV 門檻。"
            "8/25 起 scorecard 持續追蹤其依據：露天 +0.32 分（n=25）vs "
            "巨蛋 -0.03 分（n=28），差距 0.4 個標準誤，尚無證據要調整。",
            "讓分盤仍不定價，但理由已從「觀察到偏誤」升級為「知道原因」："
            "模型的 Var(分差) 被共享環境因子結構性壓窄約 2.3 倍，"
            "且數學上與 dispersion_k 無關。見 analysis/diagnose_margin.py。",
        ],
        sources=[
            "https://npb.jp/announcement/starter/（2026-08-26 預告先發公示）",
            "https://npb.jp/games/2026/schedule_08_detail.html（賽程與 8/25 比分）",
            "https://npb.jp/bis/2026/stats/idp1_<team>.html（個人投手成績）",
            "https://npb.jp/scores/2026/<date>/<slug>/box.html"
            "（牛棚用球數、逐場先發順位 —— 用來判定角色轉換）",
            "賠率：使用者提供之看板截圖（2026-08-26）",
        ],
    )


if __name__ == "__main__":
    print(build_report().render())
