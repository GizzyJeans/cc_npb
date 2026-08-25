"""2026-08-25 NPB 全六場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_08_25.py``

本日的兩件事值得先講
--------------------
1. **8/24 是全聯盟休兵日**，十二支球隊一律休息一天。牛棚疲勞在今天
   幾乎沒有隊間差異，這是少數可以直接說「這個變因今天不重要」的日子。
   （8/22 ZOZO 與橫濱兩場因雨中止，所以火腿／羅德／阪神／DeNA 這四隊
   近三日只打了一場，比其他八隊更輕鬆一點。）

2. **三名先發本季樣本近乎於零**，而且分布得很不巧:
   モイネロ 2 場 12 局、吉川悠斗 1 場 5 局、伊藤樹 1 場 2 局。
   軟銀 @ 羅德 那場 **兩隊先發都在這份名單裡** ——
   模型最大的單一變因等於沒有輸入。`starter_stats_known` 因此記為
   False，該欄位不在 `WAIVABLE_SOFT` 內，這兩場無論 EV 多漂亮都上不了推薦。

   特別點名 モイネロ: 12 局 0.75 防禦率被收縮到係數 0.874，
   但他的真實水準遠優於此。收縮沒有做錯 —— 12 局就是不夠 —— 但要知道
   這個偏誤的方向是 **高估軟銀的失分**，也就是把模型往大分推。

姓名比對
--------
`伊藤大海` 在 npb.jp 的個人成績表裡用的是相容字 U+FA45（海的異體），
預告先發頁用的是一般的 U+6D77，直接字串比對會漏掉。改用 NFKC 正規化後
十二人全數唯一命中。這與本月稍早 `髙橋遥/遙` 是同一類問題。
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

DATE = "2026-08-25"
DATA_AS_OF = "2026-08-25 15:45 JST (UTC 06:45)"

GAMES = [
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="阪神虎", home_team="中日龍",
        away_starter="西勇輝 (右)", home_starter="大野雄大 (左)",
        venue="バンテリンドーム (巨蛋)",
        handicap_raw="1+95", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7平", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-10", f5_total_raw="4+75",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="東北樂天金鷲", home_team="歐力士猛牛",
        away_starter="伊藤樹 (右)", home_starter="九里亜蓮 (右)",
        venue="京セラD大阪 (巨蛋)",
        handicap_raw="1+30", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7-50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-30", f5_total_raw="4-10",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="讀賣巨人", home_team="養樂多燕子",
        away_starter="則本昂大 (右)", home_starter="吉村貢司郎 (右)",
        venue="神宮 (露天)",
        handicap_raw="1+60", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="8-25", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0", f5_total_raw="5+75",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="福岡軟銀鷹", home_team="千葉羅德",
        away_starter="莫伊聶羅 (左)", home_starter="吉川悠斗 (左)",
        venue="ZOZOマリンスタジアム (露天)",
        handicap_raw="2-60", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="8+90", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1-70", f5_total_raw="4-25",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="橫濱DeNA灣星", home_team="廣島鯉魚",
        away_starter="深沢鳳介 (右)", home_starter="床田寛樹 (左)",
        venue="マツダスタジアム (露天)",
        handicap_raw="1+50", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6.5", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-40", f5_total_raw="4+75",
        # 使用者於 2026-08-13 確認: 本看板的裸小數就是字面上的半球盤，
        # 不會走盤，與 N平/N±XX 是兩種不同寫法。
        attested_fields=frozenset({"total"}),
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="日本火腿", home_team="西武獅",
        away_starter="伊藤大海 (右)", home_starter="平良海馬 (右)",
        venue="ベルーナドーム (巨蛋)",
        handicap_raw="0-50", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6+10", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0", f5_total_raw="3-25",
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
    "バンテリンドーム (巨蛋)": "バンテリンドーム",
    "京セラD大阪 (巨蛋)": "京セラD大阪",
    "神宮 (露天)": "神宮",
    "ZOZOマリンスタジアム (露天)": "ZOZOマリン",
    "マツダスタジアム (露天)": "マツダスタジアム",
    "ベルーナドーム (巨蛋)": "ベルーナドーム",
}

OPEN_AIR = {"神宮", "ZOZOマリン", "マツダスタジアム"}

DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限，比 Bankroll 的 5,000 更緊。"""

OPEN_AIR_MIN_EV = 0.07
"""露天球場的 EV 門檻 (一般為 +4%)。

2026-08-16 使用者決定: 露天不再直接封鎖，改成要求更高的 EV。
理由是球場係數本身已內含該球場的常態風況，缺的只是「今日偏離常態多少」
—— 那是增加變異而非造成偏誤，用較高門檻補償比一刀切合理。
放棄 `weather_known` 這件事會照實印在報告的「已放棄的門檻」欄。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "神宮": "露天。未取得逐時風向／氣溫預報",
    "ZOZOマリン": "露天，臨海、風的影響在十二座球場中最大。未取得逐時預報",
    "マツダスタジアム": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。

收縮局數 SHRINK_IP = 60，25 局的樣本只保留約 29% 權重，再低下去
係數幾乎全部來自聯盟平均 —— 那不是估計，是先驗。
今日 モイネロ (12 局)、吉川悠斗 (5 局)、伊藤樹 (2 局) 三人未達標。"""

ROOKIE_DEFAULT_IP_PER_START = 5.50
"""伊藤樹本季唯一一次登板只投 2 局，若直接拿 2.00 當「每場局數」，
`blended_defence` 的先發權重會被壓到下限 0.35，等於把他當成
「計畫性開局投手」—— 但他今天是正式預告先發，不是開局投手。
那個 2.00 是樣本，不是用法。改用聯盟先發的典型局數 5.50。

差別不小: 用 2.00 算出樂天當日守備係數 1.258，用 5.50 是 1.197。
兩者都不可靠 (他的失分率係數 98% 來自聯盟平均)，這場本來就不定價。"""

# 今日先發 (npb.jp idp1_<team>.html, 2026-08-25 擷取，NFKC 正規化後全名比對)。
# (顯示名, 收縮後失分率係數, 每場局數, 說明, is_opener)
STARTERS = {
    "阪神": ("西勇輝", 0.966, 5.00,
             "6 場 30 局 防禦率 2.40（失分率 2.70）；樣本僅 30 局，已重收縮", False),
    "中日": ("大野雄大", 0.750, 6.59,
             "17 場 112 局 防禦率 2.09、每場 6.6 局 —— 本日十二人中最佳", False),
    "楽天": ("伊藤樹", 1.106, ROOKIE_DEFAULT_IP_PER_START,
             "1 場 2 局 防禦率 18.00 —— 本季幾乎無樣本，係數 97% 來自聯盟平均", False),
    "オリックス": ("九里亜蓮", 1.048, 6.21,
                "21 場 130.1 局 防禦率 2.97（失分率 3.59）、47 四球偏多", False),
    "巨人": ("則本昂大", 1.155, 5.67,
             "9 場 51 局 防禦率 4.94 —— 本日十二人中最差", False),
    "ヤクルト": ("吉村貢司郎", 1.025, 5.83,
                "16 場 93.1 局 防禦率 4.05、被全壘打 15 支", False),
    "ソフトバンク": ("モイネロ", 0.874, 6.00,
                  "2 場 12 局 防禦率 0.75 —— 樣本僅 12 局，係數 83% 來自聯盟平均", False),
    "ロッテ": ("吉川悠斗", 1.016, 5.00,
              "1 場 5 局 防禦率 5.40 —— 8/18 首度先發後僅再投這一場", False),
    "DeNA": ("深沢鳳介", 0.988, 5.48,
             "7 場 38.1 局 防禦率 2.58（失分率 3.76，差距來自失誤後的非自責分）", False),
    "広島": ("床田寛樹", 0.953, 6.08,
             "17 場 103.1 局 防禦率 2.70、每場 6.1 局", False),
    "日本ハム": ("伊藤大海", 0.972, 6.56,
                "21 場 137.2 局 防禦率 3.20、每場 6.6 局、134 三振", False),
    "西武": ("平良海馬", 0.683, 6.11,
             "18 場 110 局 防禦率 1.55 —— 全聯盟頂級，但 41 四球偏多", False),
}

STARTER_IP = {
    "阪神": 30.0, "中日": 112.0, "楽天": 2.0, "オリックス": 130.3,
    "巨人": 51.0, "ヤクルト": 93.3, "ソフトバンク": 12.0, "ロッテ": 5.0,
    "DeNA": 38.3, "広島": 103.3, "日本ハム": 137.7, "西武": 110.0,
}

# 8/24 全聯盟休兵。8/22 ZOZO 與橫濱兩場因雨中止，故火腿／羅德／阪神／DeNA
# 近三日只打一場。沒有任何投手處於連投狀態。
BULLPEN_NOTE = {
    "阪神": "8/22 因雨中止、8/23 用 7 人、8/24 全聯盟休兵 —— 已完全恢復",
    "中日": "8/22 用 5 人、8/23 用 4 人（松山、齋藤連兩天）、8/24 休兵 —— 已恢復",
    "楽天": "8/22 用 4 人、8/23 用 7 人（九谷連兩天）、8/24 休兵 —— 已恢復",
    "オリックス": "8/22 用 6 人、8/23 只用 3 人（曽谷投 103 球）、8/24 休兵 —— 充分",
    "巨人": "8/22 用 6 人、8/23 用 4 人（森田連兩天）、8/24 休兵 —— 已恢復",
    "ヤクルト": "8/22 用 4 人、8/23 用 5 人、8/24 休兵 —— 已恢復",
    "ソフトバンク": "8/22 只用 2 人、8/23 用 3 人（松本晴投 94 球）、8/24 休兵 —— 最充分",
    "ロッテ": "8/22 因雨中止、8/23 用 4 人、8/24 休兵 —— 已完全恢復",
    "DeNA": "8/22 因雨中止、8/23 用 5 人、8/24 休兵 —— 已完全恢復",
    "広島": "8/22 用 4 人、8/23 用 5 人、8/24 休兵 —— 已恢復",
    "日本ハム": "8/22 因雨中止、8/23 只用 3 人（有原投 92 球）、8/24 休兵 —— 已完全恢復",
    "西武": "8/22 用 2 人、8/23 用 7 人、8/24 休兵 —— 已恢復",
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
    """本場先發中本季局數不足 MIN_STARTER_IP 的人。"""
    out = []
    for team in (JP[game.away_team], JP[game.home_team]):
        ip = STARTER_IP[team]
        if ip < MIN_STARTER_IP:
            out.append(f"{STARTERS[team][0]}（本季僅 {ip:.0f} 局）")
    return out


def stress_season_defence(game: BoardGame) -> GameModel:
    """壓力測試: 樣本不足的先發改用該隊季內守備係數。

    收縮把 モイネロ 的 0.75 失分率拉到係數 0.874，方向是 **高估軟銀失分**。
    這個誤差不能只註記，要量化 —— 換成季內守備係數看預期總分差多少。
    """
    def side(team: str) -> TeamInput:
        _, factor, ip_gs, _, _ = STARTERS[team]
        dfn = (cal.TEAM_DEFENCE_SEASON[team] if STARTER_IP[team] < MIN_STARTER_IP
               else cal.blended_defence(factor, ip_gs, cal.BULLPEN_FACTOR[team]))
        return TeamInput(team, cal.TEAM_OFFENCE[team], dfn, ip_gs)

    return GameModel(home=side(JP[game.home_team]), away=side(JP[game.away_team]),
                     env=ENV, park_factor=cal.PARK_FACTORS_2026[PARK_KEY[game.venue]])


def readiness_for(game: BoardGame) -> DataReadiness:
    open_air = PARK_KEY[game.venue] in OPEN_AIR
    return DataReadiness(
        # 只問要下的那個盤: 本日只定價全場大小。
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
        # 露天球場沒有逐時風向/氣溫 —— 照實記為 False，但依使用者
        # 2026-08-16 的決定放棄此門檻，改用 OPEN_AIR_MIN_EV 補償。
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
        thin = thin_starters(game)

        risks = [
            "全場讓分：模型 P(分差=0、±1、±2) 各高估 5-6pp，8/19 以 k=14 重測"
            "仍是 5.98pp，屬結構性問題而非調參問題，不定價",
            "上半場盤：修正逐局比分解析後最大偏離約 3.3pp，對 3pp 的門檻"
            "沒有安全邊際，不定價",
        ]
        if thin:
            s_d = stress_season_defence(game).distributions()
            s_ev = evaluate(
                total_outcome_probs(game.total, s_d.total_pmf,
                                    "over" if label == "大分" else "under"),
                game.over_hk, Bankroll().total,
                market[0] if label == "大分" else market[1]).ev
            risks.append(
                "先發樣本不足：" + "、".join(thin)
                + f"。收縮把他們拉向聯盟平均是對的，但誤差方向是"
                  f"**高估好投手的失分**（モイネロ 12 局實際失分率 0.75，"
                  f"係數卻是 0.874），也就是把模型推向大分。"
                  f"壓力測試：這些投手改用該隊季內守備係數後預期總分 "
                  f"{s_d.expected_total():.2f}（原 {dists.expected_total():.2f}）、"
                  f"{label} EV {s_ev:+.1%}（原 {best.ev:+.1%}）"
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
                + ("　⚠️ 先發樣本不足：" + "、".join(thin) if thin else "")
            ),
            lineup_note="15:45 JST 尚未公布，依使用者指示略過",
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

    # --- 單日曝險上限 (使用者指定 3,000，低於 Bankroll 的 5,000) ---
    # 依 EV 由高到低配置，超出的降級為「觀察」並註明原因，不靜靜消失。
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
            f"校準已更新到 8/23 收盤（{cal.SAMPLE_GAMES} 場）。"
            f"聯盟每隊每場得分 {cal.LEAGUE_RPG:.4f}、主場係數 {cal.HOME_EDGE:.4f}；"
            "重新配適後與前一版最大差異 0.0078，無實質變動。",
            "十二名先發已對照 npb.jp 預告先發公示全名核對一致。"
            "看板寫的 則本昂大（巨人）與 伊藤樹（樂天）我原本認為是錯的，"
            "查證後 **看板正確**，是我對 2026 年球員異動的記憶過時。",
            "`伊藤大海` 在個人成績表用相容字 U+FA45，預告先發頁用 U+6D77，"
            "直接比對會漏掉 —— 已改用 NFKC 正規化，十二人全數唯一命中。",
            "**8/24 全聯盟休兵**，十二隊牛棚一律休息一天，今天沒有隊間疲勞差異。"
            "8/22 因雨中止那兩場的四隊（火腿／羅德／阪神／DeNA）近三日只打一場。",
            "**三名先發本季樣本近乎於零**：モイネロ 12 局、吉川悠斗 5 局、"
            "伊藤樹 2 局。軟銀 @ 羅德 那場兩隊先發都在名單裡。"
            "這三場的 `starter_stats_known` 記為 False，該門檻不可放棄。",
            "軟銀 @ 羅德 的 8+90 是本日最高盤口，而模型對這場的輸入最弱 —— "
            "EV 再高也不會轉成推薦。",
            "露天三場（神宮、ZOZOマリン、マツダ）依 8/16 的決定改用 +7% EV 門檻，"
            "並在各場的「已放棄的門檻」欄照實列出 weather_known。",
            "讓分與上半場盤全數不定價，理由見各場的風險欄。"
            "看板的讓分與上半盤仍完整記錄，供事後追蹤偏誤。",
            "**撤回一個舊警告**：8/13 起每天都附的「部位方向集中，遇到全聯盟爆分"
            "的一天會一起中彈」經實測 **不成立**。單向隨機效果 ANOVA（674 場、"
            "122 個比賽日）得 F = 0.884 < 1、ICC 95% 信賴區間 [-0.063, +0.033]，"
            "日效果標準差上界僅 0.743 分。三注小分同時輸的機率：同一天 6.48%、"
            "跨三天 6.70%。今天三注同為小分，但這不構成額外的集中風險。"
            "見 analysis/validate_day_effect.py。",
            "還活著的風險是另一件事：模型若有系統性方向偏誤，會出現在每一注上"
            "且跨日累積，分散下注稀釋不掉。目前「實際 − 模型」平均 -0.11 分"
            "（0.2 個標準誤），尚無證據。",
            "第二場（樂天 @ 歐力士）看板上全場讓分標在客隊列、上半讓分標在主隊列，"
            "這個組合不尋常但內部一致（先發強度偏歐力士、牛棚強度偏樂天）。"
            "讓分不定價，故不影響任何結論。",
        ],
        sources=[
            "https://npb.jp/announcement/starter/（2026-08-25 預告先發公示）",
            "https://npb.jp/games/2026/schedule_08_detail.html（賽程與 8/23 比分）",
            "https://npb.jp/bis/2026/stats/idp1_<team>.html（個人投手成績）",
            "https://npb.jp/scores/2026/<date>/<slug>/box.html（牛棚用球數）",
            "賠率：使用者提供之看板截圖（2026-08-25）",
        ],
    )


if __name__ == "__main__":
    print(build_report().render())
