"""2026-08-27 NPB 五場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_08_27.py``

只有五場: 火腿與西武的系列賽已於 8/26 結束，今日輪空。

⚠️ 本日的先發核對方式與平常不同
--------------------------------
npb.jp 的 `予告先発` 頁 **只保留隔日場次**，本報告產出時 (17:35 JST，
距開賽 25 分鐘) 該頁已翻到 8/28，今天的官方公示取不到了。改用兩個替代來源:

1. **賽程頁每一列的 `pit` 欄位** —— 這是官方資料，但只給 **主隊** 先發。
   五場的主隊先發全部與看板一致:
   石川 / 金丸 / 栗林 / 毛利 / ジェリー。
   看板寫的「赫耶勒」對應官方的 **ジェリー**（歐力士）—— 這是同一個先發
   欄位的兩種音譯，但字面差很多，記錄下來。

2. **各隊本季投手成績表** —— 五名客隊先發全部確認在正確球隊的名單內
   (上茶谷大河、下村海翔、片山皓心、前田健太、マタ)。

也就是說: 主隊先發是官方確認，**客隊先發只有看板來源 + 名單存在性佐證**。
`starters_confirmed` 仍記為 True，理由是看板的主隊先發與官方五場全中，
這是對看板可靠度相當強的即時佐證; 但這個弱化必須寫在這裡，不能只寫在心裡。

先發樣本與角色
--------------
* **石川雅規 (養樂多)**: 本季 **零登板**，成績表裡查無此人的任何一列。
  這是目前為止最極端的樣本不足 —— 係數只能用聯盟平均。
* **マタ (巨人)**: 5 場 24.1 局，低於 25 局門檻。
  巨人 @ 養樂多 因此 **兩名先發都不合格**。
* **片山皓心 (DeNA)**: 4 場 19 局，同樣不合格。
* **上茶谷大河 (軟銀)**: 季內 IP/G 只有 2.16，但查逐場 box 後確認
  **7/16 起連五場都是第 1 任投手、投 6-7 局**，是季中由後援轉先發，
  與 8/26 的鈴木健矢／ロング／達孝太 同一類。改用近期先發的 6.60 局。
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

DATE = "2026-08-27"
DATA_AS_OF = "2026-08-27 17:35 JST (UTC 08:35)"

GAMES = [
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="福岡軟銀鷹", home_team="千葉羅德",
        away_starter="上茶谷大河 (右)", home_starter="毛利海大 (左)",
        venue="ZOZOマリンスタジアム (露天)",
        handicap_raw="2+90", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="8平", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1+60", f5_total_raw="4-50",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="阪神虎", home_team="中日龍",
        away_starter="下村海翔 (右)", home_starter="金丸夢斗 (左)",
        venue="バンテリンドーム (巨蛋)",
        handicap_raw="1+90", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7+50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0", f5_total_raw="4+50",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="橫濱DeNA灣星", home_team="廣島鯉魚",
        away_starter="片山皓心 (左)", home_starter="栗林良吏 (右)",
        venue="マツダスタジアム (露天)",
        # 看板上讓分標在主隊列 —— 廣島讓分。
        handicap_raw="1+60", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6+25", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-60", f5_total_raw="3-25",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="東北樂天金鷲", home_team="歐力士猛牛",
        away_starter="前田健太 (右)", home_starter="ジェリー (右)",
        venue="京セラD大阪 (巨蛋)",
        handicap_raw="1+80", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7-50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-40", f5_total_raw="4+75",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="讀賣巨人", home_team="養樂多燕子",
        away_starter="マタ (右)", home_starter="石川雅規 (左)",
        venue="神宮 (露天)",
        handicap_raw="1+15", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="8.5", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-65", f5_total_raw="5+50",
        # 使用者於 2026-08-13 確認: 裸小數就是字面上的半球盤，不會走盤。
        attested_fields=frozenset({"total"}),
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
    "バンテリンドーム (巨蛋)": "バンテリンドーム",
    "マツダスタジアム (露天)": "マツダスタジアム",
    "京セラD大阪 (巨蛋)": "京セラD大阪",
    "神宮 (露天)": "神宮",
}

OPEN_AIR = {"ZOZOマリン", "マツダスタジアム", "神宮"}

DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限，比 Bankroll 的 5,000 更緊。"""

OPEN_AIR_MIN_EV = 0.07
"""露天球場的 EV 門檻 (一般為 +4%)，2026-08-16 使用者決定。
scorecard.py 持續追蹤其依據: 8/26 收盤時露天 +0.35 分 (n=28) vs
巨蛋 +0.13 分 (n=31)，差距 0.2 個標準誤 —— 尚無證據要調整。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "ZOZOマリン": "露天，臨海、風的影響在十二座球場中最大。未取得逐時預報",
    "マツダスタジアム": "露天。未取得逐時風向／氣溫預報",
    "神宮": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」(收縮局數 60，25 局只剩約 29% 權重)。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。"""

# (顯示名, 收縮後失分率係數, **今日預期局數**, 說明, 季內 IP/G)
STARTERS = {
    "ソフトバンク": ("上茶谷大河", 0.891, 6.60,
                  "31 場 67 局 防禦率 2.55，但季內 IP/G 只有 2.16 —— "
                  "7/16 起連五場都是第 1 任、投 6-7 局，已轉為正規先發", 2.16),
    "ロッテ": ("毛利海大", 1.164, 4.50,
              "14 場 65.1 局 防禦率 4.82、失分率 4.96；六次先發 2-6 局起伏大", 4.67),
    "阪神": ("下村海翔", 1.076, 5.44,
             "6 場 32.2 局 防禦率 3.03（失分率 3.86）；樣本偏薄，已重收縮", 5.44),
    "中日": ("金丸夢斗", 0.873, 6.42,
             "20 場 128.1 局 防禦率 2.59、115 三振 —— 本日最佳先發", 6.42),
    "DeNA": ("片山皓心", 1.048, 5.50,
             "4 場 19 局 防禦率 4.26 —— 樣本不足；三次先發都投 5-6 局", 4.75),
    "広島": ("栗林良吏", 0.797, 6.46,
             "13 場 84 局 防禦率 2.04、失分率 2.36 —— 本日十人中最佳", 6.46),
    "楽天": ("前田健太", 0.888, 5.39,
             "11 場 59.1 局 防禦率 2.73（失分率 2.88）", 5.39),
    "オリックス": ("ジェリー", 0.940, 5.33,
                "18 場 96 局 防禦率 2.63（失分率 3.00）、24 四球", 5.33),
    "巨人": ("マタ", 0.965, 4.87,
             "5 場 24.1 局 防禦率 3.33 —— 低於 25 局門檻，且 15 四球偏多", 4.87),
    "ヤクルト": ("石川雅規", 1.000, DEFAULT_IP_PER_START,
                "**本季零登板**，投手成績表查無任何一列 —— "
                "係數只能用聯盟平均，等於沒有輸入", 0.0),
}

STARTER_IP = {
    "ソフトバンク": 67.0, "ロッテ": 65.3, "阪神": 32.7, "中日": 128.3,
    "DeNA": 19.0, "広島": 84.0, "楽天": 59.3, "オリックス": 96.0,
    "巨人": 24.3, "ヤクルト": 0.0,
}

ROLE_CHANGED = {"ソフトバンク"}
"""季中由後援轉先發者 (上茶谷大河)。失分率是後援時期累積的，
通常優於先發，模型會高估他。壓力測試改用球隊季內守備係數。"""

BULLPEN_NOTE = {
    "ソフトバンク": "8/26 用 5 人（上沢 90 球）—— 正常",
    "ロッテ": "8/26 打滿十局延長、用 5 人 —— 略吃緊",
    "阪神": "8/26 用 4 人（下村未登板）—— 正常",
    "中日": "8/26 只用 3 人 —— 充分",
    "DeNA": "8/26 用 4 人 —— 正常",
    "広島": "8/26 用 5 人 —— 正常",
    "楽天": "8/26 用 5 人 —— 正常",
    "オリックス": "8/26 用 4 人 —— 正常",
    "巨人": "8/26 用 5 人 —— 正常",
    "ヤクルト": "8/26 用 5 人 —— 正常",
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
            f"校準已更新到 8/26 收盤（{cal.SAMPLE_GAMES} 場）。"
            f"聯盟每隊每場得分 {cal.LEAGUE_RPG:.4f}、主場係數 {cal.HOME_EDGE:.4f}。",
            "**只有五場**：火腿與西武的系列賽已於 8/26 結束，今日輪空。",
            "⚠️ **今天的官方預告先發取不到**：npb.jp 該頁只保留隔日場次，"
            "本報告產出時（17:35 JST）已翻到 8/28。改用賽程頁的 `pit` 欄位"
            "（官方，但只給主隊）+ 各隊本季投手成績表核對客隊先發是否在隊。"
            "五場的主隊先發與看板全中，客隊五人也都查得到在正確球隊 —— "
            "但客隊先發終究只有看板單一來源，這個弱化必須揭露。",
            "看板的「赫耶勒」對應官方賽程頁的 **ジェリー**（歐力士）。"
            "兩種音譯字面差很多，但指向同一個先發欄位。",
            "**巨人 @ 養樂多 的 +31.7% 是假的優勢，已擋在推薦之外。**"
            "養樂多先發石川雅規 **本季零登板**、巨人先發マタ 只有 24.1 局，"
            "兩人都不合格。模型對石川完全沒有輸入、只能給聯盟平均，"
            "而市場把盤口開到 8.5 —— 市場顯然知道一些模型不知道的事"
            "（石川是本季首度登板）。這種情況下押小分，等於在跟"
            "唯一握有資訊的一方對賭。這是 `starter_stats_known` 這道"
            "不可放棄的門檻最典型的用途。",
            "**上茶谷大河（軟銀）是季中由後援轉先發**：季內 IP/G 只有 2.16，"
            "但 7/16 起連五場都是第 1 任投手、投 6-7 局。已改用 6.60 局，"
            "與 8/26 的鈴木健矢／ロング／達孝太 同一類處理，並跑壓力測試。",
            "露天三場（ZOZOマリン、マツダ、神宮）維持 +7% EV 門檻。"
            "scorecard 追蹤的依據：露天 +0.35 分（n=28）vs 巨蛋 +0.13 分"
            "（n=31），差距 0.2 個標準誤，尚無證據要調整。",
            "讓分與上半場盤全數不定價。讓分的理由已從「觀察到偏誤」升級為"
            "「知道原因」：模型的 Var(分差) 被共享環境因子結構性壓窄約 2.3 倍，"
            "且數學上與 dispersion_k 無關。見 analysis/diagnose_margin.py。",
        ],
        sources=[
            "https://npb.jp/games/2026/schedule_08_detail.html"
            "（賽程、8/26 比分、**主隊先發 pit 欄位**）",
            "https://npb.jp/bis/2026/stats/idp1_<team>.html（個人投手成績）",
            "https://npb.jp/bis/teams/rst_<team>.html（支配下名簿，用來確認石川雅規在隊）",
            "https://npb.jp/scores/2026/<date>/<slug>/box.html"
            "（牛棚用球數、逐場先發順位 —— 用來判定角色轉換）",
            "⚠️ https://npb.jp/announcement/starter/ 今日 **無法取得**"
            "（該頁只保留隔日場次，已翻到 8/28）",
            "賠率：使用者提供之看板截圖（2026-08-27）",
        ],
    )


if __name__ == "__main__":
    print(build_report().render())
