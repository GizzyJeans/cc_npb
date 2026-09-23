"""2026-09-23 **第二張盤** —— 17:00 / 18:00 JST 的三場。

執行: ``python3 analysis/slate_2026_09_23b.py``

⚠️ 今天的額度已經用完 —— 本盤只定價存檔
----------------------------------------
上午盤（`slate_2026_09_23.py`）三場全部推薦，各 1,000，剛好用滿 3,000:

    阪神 @ 養樂多  小分 7-70   +11.1%   1,000
    巨人 @ 廣島    小分 6.5    +8.7%    1,000
    西武 @ 軟銀    大分 7+20   +6.5%    1,000

單日上限是 **每天** 3,000，不是每張盤（2026-09-20 起的作法），所以本盤的
`DAILY_BUDGET` 是 **0**。數值面與門檻都通過的場次會以「額度用完」降為觀察
—— 那是額度的決定、不是門檻的決定，`validate_gates` 會把它們歸在 A 類。
照樣定價，是因為有定價、沒下注的場次是乾淨的對照組。

**結果額度沒有派上用場**: 兩場正 EV 都先被資料門檻（先發樣本不足）
擋下，會進 B 類而不是 A 類; 第三場 EV 為負。

**上午那三場不重新定價**，理由同 9/20b: 當時的推薦是依當時可覆核的報價
做出的，事後重算會改寫那個決定的紀錄。

看板在 16:41 JST 收到，距歐力士 @ 羅德開賽只有 19 分鐘。

查證結果
--------
* 三場的對戰、球場、主客與開賽時間，全部與 npb.jp 相符。
* **六位先發的姓名與投球側 6/6 相符**。看板「盧切西」= npb.jp「ルケーシー」
  （羅德的外籍左投），「莊司」= 荘司（莊/荘 已在對照表）。
* **三個先發觸發檢查，逐一處理:**

  - **山﨑福也（火腿）—— 查證後排除角色轉換嫌疑。** 季內 IP/G 只有 3.48，
    但逐場看 box.html: 3/28-4/17 七場全是後援（第2-5任、每場 ≤1 局），
    **6/6 起九場全是第1任**、4.2-7 局、平均 **5.48 局**。3.48 是兩種用法的
    混合值。預期局數採 5.48; 係數沿用季內成績（後援只佔 6.1 局），
    與 9/19 高野脩汰的作法一致。
  - **仲地礼亜（中日）—— 樣本不足，且是本季一軍首次先發。** 一軍 4 場
    全是後援（4/11-5/10，第2-5任），合計 7.0 局失 8 分，5/10 之後沒上過一軍。
    二軍（ウエスタン）17 場 78.1 局、失分率 3.10、每場 4.61 局 —— 在二軍是
    先發用法。預期局數採二軍的 4.61; 係數只能用一軍 7 局收縮（1.182），
    所以 `starter_stats_known` 記為缺口並做壓力測試。
    不列入 `ROLE_CHANGED`: 他不是開局投手，是從二軍輪值叫上來先發。
  - **ルケーシー（羅德）—— 樣本不足。** 本季 3 場 15.0 局（每場 5.0 局，
    9/13 已確認是第1任），未達 25 局門檻。
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

DATE = "2026-09-23"
DATA_AS_OF = "2026-09-23 16:47 JST (UTC 07:47)"

T17 = "17:00 JST（看板 16:00 台北）"
T18 = "18:00 JST（看板 17:00 台北）"

GAMES = [
    BoardGame(
        date=DATE, start_time=T17,
        away_team="歐力士猛牛", home_team="千葉羅德",
        away_starter="九里亜蓮 (右)", home_starter="盧切西 (左)",
        venue="ZOZOマリンスタジアム (露天)",
        handicap_raw="1+80", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7-50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-50", f5_total_raw="4+25",
    ),
    BoardGame(
        date=DATE, start_time=T18,
        away_team="東北樂天鷹", home_team="日本火腿",
        away_starter="莊司康誠 (右)", home_starter="山﨑福也 (左)",
        venue="エスコンＦ (開閉式屋頂)",
        handicap_raw="1+30", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="8+50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-10", f5_total_raw="4-25",
    ),
    BoardGame(
        date=DATE, start_time=T18,
        away_team="中日龍", home_team="橫濱DeNA灣星",
        away_starter="仲地礼亜 (右)", home_starter="深沢鳳介 (右)",
        venue="横浜スタジアム (露天)",
        handicap_raw="1-40", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="8+50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1+95", f5_total_raw="4-50",
    ),
]

JP = {
    "歐力士猛牛": "オリックス", "千葉羅德": "ロッテ",
    "東北樂天鷹": "楽天", "日本火腿": "日本ハム",
    "中日龍": "中日", "橫濱DeNA灣星": "DeNA",
}
PARK_KEY = {
    "ZOZOマリンスタジアム (露天)": "ZOZOマリン",
    "エスコンＦ (開閉式屋頂)": "エスコンＦ",
    "横浜スタジアム (露天)": "横浜",
}

OPEN_AIR = {"ZOZOマリン", "横浜"}
"""エスコンＦ 為開閉式屋頂，視為室內（與 9/20 相同）。"""

NEUTRAL_PARK_FACTOR = 1.0
"""配適資料裡沒有的球場採用的中性值。本盤三場都在主要球場，未用到。"""


def park_factor(game: BoardGame) -> float:
    return cal.PARK_FACTORS_2026.get(PARK_KEY[game.venue], NEUTRAL_PARK_FACTOR)


DAILY_BUDGET = 0.0
"""⚠️ 這是 **剩下的** 額度: 0。

使用者指定的單日曝險上限是 3,000，上午盤（`slate_2026_09_23.py`）三場
各 1,000 已經用滿。同日第二張盤共用額度的作法沿用 2026-08-22 與 09-20。"""

OPEN_AIR_MIN_EV = GATE_OPEN_AIR_MIN_EV
"""露天球場的 EV 門檻，由 `bethero.gates` 統一定義（2026-09-02 起 = 0.04）。"""

STARTED: set[str] = set()
"""本報告產出時 (16:47 JST / 07:47 UTC) 三場皆未開賽。
歐力士 @ 羅德 17:00 JST 只剩約 13 分鐘; 另兩場 18:00 JST。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "ZOZOマリン": "露天，臨海、風的影響在十二座球場中最大。未取得逐時預報",
    "横浜": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。
本盤兩人未達: 仲地礼亜 7.0 局、ルケーシー 15.0 局。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。本盤未用到 —— 仲地有二軍先發紀錄。"""

# (顯示名, 收縮後失分率係數, 今日預期局數, 說明, 季內 IP/G)
STARTERS = {
    "オリックス": ("九里亜蓮", 1.121, 6.03,
                "25 場 150.2 局 失分率 3.88、每場 6.0 局", 6.03),
    "ロッテ": ("ルケーシー", 1.026, 5.00,
              "**本季僅 3 場 15.0 局**（失分率 4.20、每場 5.0 局）—— "
              "未達 25 局門檻，收縮後幾乎回到聯盟平均", 5.00),
    "楽天": ("荘司康誠", 1.051, 6.35,
             "23 場 146.0 局 失分率 3.88、每場 6.3 局", 6.35),
    "日本ハム": ("山﨑福也", 0.868, 5.48,
                "16 場 55.2 局 失分率 2.75。季內 IP/G 3.48 是 **7 場後援"
                "（3/28-4/17）+ 9 場先發（6/6 起）的混合值**；逐場查證 9 場"
                "全是第1任、平均 5.48 局，採 5.48", 3.48),
    "中日": ("仲地礼亜", 1.182, 4.61,
             "**一軍本季 4 場全是後援、僅 7.0 局失 8 分**（最後登板 5/10）"
             "—— 今天是本季一軍首次先發。二軍 17 場 78.1 局、失分率 3.10、"
             "每場 4.61 局，預期局數採二軍值", 1.75),
    "DeNA": ("深沢鳳介", 0.998, 5.52,
             "9 場 49.2 局 失分率 3.81、每場 5.5 局", 5.52),
}

STARTER_IP = {
    "オリックス": 150.7, "ロッテ": 15.0, "楽天": 146.0,
    "日本ハム": 55.7, "中日": 7.0, "DeNA": 49.7,
}

ROLE_CHANGED: set[str] = set()
"""本盤無角色轉換案例。

* 山﨑福也的 IP/G 3.48 觸發了嫌疑，但逐場查證排除: 6/6 起九場全是第1任。
  **IP/G 偏低只是嫌疑，不是判決。**
* 仲地礼亜一軍全是後援，但他今天不是開局投手，是從二軍輪值叫上來先發
  —— 走「樣本不足」的路徑（壓力測試換球隊季內守備係數），
  不走「開局投手」的路徑。"""

BULLPEN_NOTE = {
    "オリックス": "9/21 牛棚 5 人 86 球（山口 僅 3 局）；9/22 用 5 人（東松 5 局 "
                "86 球失 3，牛棚 4 人 51 球；6-4 勝）—— 正常；但牛棚係數 1.274 "
                "為全聯盟次差",
    "ロッテ": "9/21 雨天中止（休息）；9/22 用 6 人（ジャクソン 5 局 77 球失 2，"
              "牛棚 **5 人 94 球**失 4；4-6 敗）—— 略吃緊",
    "楽天": "9/21 雨天中止（休息）；9/22 用 4 人（伊藤樹 5 局 109 球失 4，"
            "牛棚 3 人 44 球；5-6 敗）—— 充分；但牛棚係數 1.320 為全聯盟最差",
    "日本ハム": "9/21 牛棚 3 人 50 球；9/22 用 4 人（北山 6 局 92 球失 5，"
                "牛棚 3 人 47 球；6-5 勝）—— 正常",
    "中日": "9/21 牛棚 2 人 32 球（髙橋宏 7 局無失分）；9/22 用 5 人（マラー 僅 3 局 "
            "87 球失 7，牛棚 4 人 84 球、5 局；3-7 敗）—— 略吃緊",
    "DeNA": "9/21 牛棚 6 人 85 球；9/22 用 5 人（東 5 局 96 球失 3，牛棚 4 人 53 球；"
            "7-3 勝）—— 正常；牛棚係數 0.894 為全聯盟第三佳",
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
            lineup_note="16:47 JST 尚未公布，依使用者指示略過",
            bullpen_note=f"{game.home_team}：{BULLPEN_NOTE[home]}；"
                         f"{game.away_team}：{BULLPEN_NOTE[away]}",
            park_weather_note=(
                f"球場係數 {park_factor(game):.3f}（2026 實測）。"
                + WEATHER.get(PARK_KEY[game.venue], "開閉式屋頂，天氣不影響")
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
                "今日 3,000 單位額度已由上午盤用完（本盤可用 0）—— "
                f"本場 EV {a.evaluation.ev:+.1%}，數值面與資料門檻都通過，"
                "只因額度未下"
            ]

    notes = [
        f"校準涵蓋到 {cal.sample_through()} 收盤（{cal.SAMPLE_GAMES} 場）。"
        f"聯盟每隊每場 {cal.LEAGUE_RPG:.4f} 分、主場乘數 {cal.HOME_EDGE:.4f}。",
        "⚠️ **今天的 3,000 額度已被上午盤用完**（阪神 @ 養樂多 小分 7-70、"
        "巨人 @ 廣島 小分 6.5、西武 @ 軟銀 大分 7+20 各 1,000）。"
        "本盤 **只定價存檔、不下注**。單日上限是每天、不是每張盤。",
        "實際上額度根本輪不到當理由: 兩場正 EV（歐力士 @ 羅德 大分、"
        "中日 @ DeNA 小分）都 **先被資料門檻擋下** —— 先發樣本不足，"
        "軟性缺口超過 2 項。這兩場會進 `validate_gates` 的 **B 類**，"
        "正是檢驗資料門檻有沒有用的那一類。",
        "看板在 16:41 JST 收到: 歐力士 @ 羅德 17:00 JST（16:00 台北），"
        "距開賽只有 19 分鐘；另兩場 18:00 JST（17:00 台北）。",
        "六位先發的 **姓名與投球側 6/6 相符**（「盧切西」= ルケーシー、"
        "「莊司」= 荘司）。",
        "**山﨑福也（火腿）查證後排除角色轉換嫌疑**：季內 IP/G 3.48 是"
        "「3/28-4/17 七場後援 + 6/6 起九場先發」的混合值；九場先發全是第1任、"
        "平均 5.48 局，預期局數採 5.48。",
        "**仲地礼亜（中日）是本季一軍首次先發**：一軍 4 場全是後援（7.0 局、"
        "最後登板 5/10），二軍 17 場 78.1 局、每場 4.61 局。係數只有 7 局可用，"
        "記為資料缺口並做壓力測試。**ルケーシー（羅德）** 也只有 15.0 局。",
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
