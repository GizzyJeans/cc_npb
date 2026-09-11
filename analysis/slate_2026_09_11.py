"""2026-09-11 NPB 全三場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_09_11.py``

⚠️ 看板第一次出現「大小盤讓水」
------------------------------
到 9/10 為止，這個看板的大小盤兩邊 **一律** 都是 0.930，價格全部靠
``N±XX`` 的百分比浮動。今天前兩場不是:

    羅德 @ 軟銀    7.5  大 **0.900** / 小 **0.960**
    西武 @ 歐力士  7平  大 **0.900** / 小 **0.960**
    DeNA @ 廣島   7+75 大 0.930 / 小 0.930   ← 仍是舊格式

大 0.900 代表大分賠得少、小 0.960 代表小分賠得多 —— 市場在盤口之外
**額外偏向大分**。去水後市場機率是 大 50.78% / 小 49.22%（水 3.65%）。

這件事有兩個後果，都已處理:

1. **小分的 EV 變好**: 0.960 比 0.930 多賠 3.2%，同樣的模型機率下
   小分的 EV 會高出約 3 個百分點。
2. **程式碼有一個到今天才會咬人的 bug**: 先前每日 slate 的壓力測試
   區塊固定傳 ``game.over_hk``，不論方向。兩邊都是 0.930 時無害，
   今天會用 0.900 去算小分的壓力測試 EV。本檔已改為依方向取價
   （見 `build_report` 裡的 `side_hk`），實測影響:

       羅德 @ 軟銀    壓力測試小分 EV  正確 +6.7%（舊寫法 +3.5%，差 3.3pp）
       西武 @ 歐力士  壓力測試小分 EV  正確 +5.2%（舊寫法 +2.4%，差 2.8pp）

   壓力測試不直接決定下注，但它是判斷「EV 偏差比較可能往哪邊」的依據，
   差 3 個百分點足以翻轉那個判斷。先前 24 天的數字不受影響（兩邊同價）。

去水方法沿用 `devig_proportional`。今天特地對照了 `devig_power`
（模組文件說它更適合兩邊不對稱的盤）: 0.900/0.960 下兩者只差
**0.04 個百分點**，不足以改變任何結論，因此不在今天換方法 ——
換掉會讓今天與先前 24 天的數字失去可比性。

⚠️ 三場裡有兩場的先發查無可用成績
--------------------------------
    山口廉王（歐力士）  本季 **1 場 4.0 局**   ← 幾乎等於沒有樣本
    石川柊太（羅德）    本季 **5 場 12.0 局**、IP/G 2.40

兩人都遠低於 25 局門檻，`starter_stats_known` 記為 False。加上原本就
缺的傷病與多家報價，軟性缺口達 3 項 > 2，兩場都不可能成為推薦。

這個門檻今年已擋對兩次: 8/27 石川雅規（本季 0 局）實際投 0.1 局失 6 分、
全場 11 分; 8/29 大川慈英（0.2 局）全場 16 分。兩次的 EV 都很漂亮。

石川柊太另有角色問題: 5 場 12 局、8/28 是 **第2任** 投 3 局 54 球，
明顯是限制球數的復歸調整期，今日採 4.00 局並列入 `ROLE_CHANGED`。

⚠️ 片山皓心（DeNA）剛好卡在門檻上
--------------------------------
本季 5 場 **25.0 局**，而門檻是「低於 25 局」—— 他以整整 0 局的差距
通過。逐場查證確認是真先發（8/27 對廣島 第1任 6 局 104 球）。

查證時遇到同名陷阱: 本機 box 裡有 7 筆「片山」，其中 **6 筆是歐力士的
另一位片山**（多為 1 局的後援），只有 8/27 那筆才是 DeNA 的片山皓心。
只比對姓氏會把一位後援投手的成績安到先發頭上。

其他
----
* 予告先發頁已翻到 9/12（本月第五次），改由賽程頁的「先發」欄取得 ——
  今天該欄 **兩隊都有**，比先前只有主隊的情況好。
* 看板寫「渡**邊**勇太朗」，npb.jp 寫「渡**邉**勇太朗」。這兩個是不同的
  漢字（不是相容字元，NFKC 不會合併），需另外做異體字等價。
  西武投手群只有一位渡邉，指涉無歧義。
* 歐力士回到 **京セラD大阪**（PF 0.8645），不再是前兩天的ほっと神戸。
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

DATE = "2026-09-11"
DATA_AS_OF = "2026-09-11 15:30 JST (UTC 06:30)"

GAMES = [
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="千葉羅德", home_team="福岡軟銀鷹",
        away_starter="石川柊太 (右)", home_starter="前田悠伍 (左)",
        venue="みずほPayPay (巨蛋)",
        handicap_raw="2+5", handicap_side="home",
        handicap_home_hk=0.920, handicap_away_hk=0.980,
        # ⚠️ 大小盤兩邊不同價，這是本看板首見。
        total_raw="7.5", over_hk=0.900, under_hk=0.960,
        f5_handicap_raw="1平", f5_total_raw="4-50",
        # 純小數 = 字面上的半球盤，永不和局。使用者 2026-08-13 已目視確認。
        attested_fields=frozenset({"total"}),
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="西武獅", home_team="歐力士猛牛",
        away_starter="渡邊勇太朗 (右)", home_starter="山口廉王 (右)",
        venue="京セラD大阪 (巨蛋)",
        handicap_raw="1+10", handicap_side="away",
        handicap_home_hk=0.980, handicap_away_hk=0.920,
        total_raw="7平", over_hk=0.900, under_hk=0.960,
        f5_handicap_raw="0-50", f5_total_raw="4+50",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="橫濱DeNA灣星", home_team="廣島鯉魚",
        away_starter="片山皓心 (左)", home_starter="森下暢仁 (右)",
        venue="マツダスタジアム (露天)",
        handicap_raw="1+40", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7+75", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-20", f5_total_raw="4+75",
    ),
]

JP = {
    "歐力士猛牛": "オリックス", "福岡軟銀鷹": "ソフトバンク",
    "西武獅": "西武", "千葉羅德": "ロッテ",
    "廣島鯉魚": "広島", "橫濱DeNA灣星": "DeNA",
}
PARK_KEY = {
    "みずほPayPay (巨蛋)": "みずほPayPay",
    "京セラD大阪 (巨蛋)": "京セラD大阪",
    "マツダスタジアム (露天)": "マツダスタジアム",
}

OPEN_AIR = {"マツダスタジアム"}

NEUTRAL_PARK_FACTOR = 1.0
"""配適資料裡沒有 (或場次太少不足以估計) 的球場採用的中性值。今日未用到 ——
三場都在主要球場，是 8/25 以來第一次三場全部有可用的球場係數。"""


def park_factor(game: BoardGame) -> float:
    """球場係數；資料不足的球場退回中性值並由門檻揭露。"""
    return cal.PARK_FACTORS_2026.get(PARK_KEY[game.venue], NEUTRAL_PARK_FACTOR)


DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限，比 Bankroll 的 5,000 更緊。"""

OPEN_AIR_MIN_EV = GATE_OPEN_AIR_MIN_EV
"""露天球場的 EV 門檻，由 `bethero.gates` 統一定義（2026-09-02 起 = 0.04）。"""

STARTED: set[str] = set()
"""本報告產出時 (15:30 JST) 三場皆未開賽，18:00 開打。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "マツダスタジアム": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。

今日 **兩人未過**（山口廉王 4.0 局、石川柊太 12.0 局），
而片山皓心以 25.0 局 **剛好等於門檻**（條件是「低於」才擋）。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。今日未直接採用 ——
石川柊太的登板紀錄顯示他還在限制球數，取更保守的 4.00 局。"""

# (顯示名, 收縮後失分率係數, 今日預期局數, 說明, 季內 IP/G)
STARTERS = {
    "ロッテ": ("石川柊太", 1.062, 4.00,
              "本季僅 5 場 12.0 局、防禦率 3.75，**查無可用先發樣本**；"
              "8/28 是第2任投 3 局 54 球，仍在限制球數的復歸期", 2.40),
    "ソフトバンク": ("前田悠伍", 0.723, 5.77,
                  "16 場 92.1 局 防禦率 **1.95**、失分率 1.95、每場 5.8 局 "
                  "—— 本日最佳，且是本季定價過最好的先發係數之一", 5.77),
    "西武": ("渡邊勇太朗", 1.016, 6.49,
             "19 場 123.1 局 防禦率 3.58（失分率 3.65）、每場 6.5 局 "
             "—— 本日局數最深", 6.49),
    "オリックス": ("山口廉王", 1.115, 4.00,
                "本季僅 **1 場 4.0 局**、防禦率 6.75，**查無可用先發樣本**；"
                "係數幾乎全部來自聯盟平均先驗", 4.00),
    "DeNA": ("片山皓心", 1.007, 5.00,
             "5 場 25.0 局 防禦率 3.60（失分率 3.96）、每場 5.0 局；"
             "樣本薄但已達門檻，8/27 對廣島曾投 6 局 104 球", 5.00),
    "広島": ("森下暢仁", 1.110, 5.93,
             "19 場 112.2 局 防禦率 3.83、失分率 4.23 —— 本日最差", 5.93),
}

STARTER_IP = {
    "ロッテ": 12.0, "ソフトバンク": 92.3, "西武": 123.3,
    "オリックス": 4.0, "DeNA": 25.0, "広島": 112.7,
}

ROLE_CHANGED = {"ロッテ"}
"""石川柊太 —— 5 場 12 局、IP/G 2.40 是短局數登板累積的。
他的失分率不是在先發負荷下產生的，壓力測試改用球隊季內守備係數。

山口廉王不列入: 他不是「角色轉換」，是 **樣本幾乎不存在**（1 場 4 局），
已由 `starter_stats_known` 擋住，壓力測試也會因樣本不足條款一併觸發。"""

BULLPEN_NOTE = {
    "ロッテ": "9/10 用 3 人（高野脩汰 7 局 101 球失 1，牛棚 2 人；6-1 勝）—— 充分",
    "ソフトバンク": "9/10 用 5 人（松本晴 5 局 97 球，牛棚 4 人各 1 局；3-2 險勝）"
                  "—— 略吃緊，四名後援全部出場",
    "西武": "9/10 用 5 人（佐藤爽 5 局 86 球失 3，牛棚 4 人各 1 局；8-4 勝）—— 正常",
    "オリックス": "9/10 用 5 人（髙島泰都 4 局 91 球失 6，牛棚 4 人吃 5 局；4-8 敗）"
                "—— 吃緊，且牛棚係數 1.271 為全聯盟最差",
    "DeNA": "9/10 用 3 人（深沢鳳介 7 局 119 球失 0，牛棚 2 人；8-1 勝）—— 充分",
    "広島": "9/10 對阪神因雨中止 —— **牛棚全休**，本日最充分",
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
        # ⚠️ 兩邊價格今天不同，方向與價格必須一起取，不能固定用 over_hk。
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
        if game.over_hk != game.under_hk:
            risks.append(
                f"本場大小盤 **兩邊不同價**（大 {game.over_hk:.3f}／"
                f"小 {game.under_hk:.3f}），是本看板首見。去水後市場機率 "
                f"大 {market[0]:.1%}／小 {market[1]:.1%} —— "
                "市場在盤口之外額外偏向大分，EV 已依實際價格計算"
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
                head.append("季中短局數登板（失分率不是在先發負荷下產生的，"
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
                f"球場係數 {park_factor(game):.3f}（2026 實測）。"
                + WEATHER.get(PARK_KEY[game.venue], "巨蛋，天氣不影響")
            ),
            market_note=(
                f"賠率已由看板截圖確認（大 {game.over_hk:.3f}／"
                f"小 {game.under_hk:.3f}）。"
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
            f"校準已更新到 9/10 收盤（{cal.SAMPLE_GAMES} 場）。"
            f"聯盟每隊每場 {cal.LEAGUE_RPG:.4f} 分、主場乘數 {cal.HOME_EDGE:.4f}。",
            "**看板首次出現大小盤讓水**：前兩場 大 0.900／小 0.960，"
            "第三場仍是 0.930／0.930。EV 已依各邊實際價格計算；"
            "同時修正了先前 slate 壓力測試固定用 `over_hk` 的 bug —— "
            "兩邊同價時無害，今天會算錯。",
            "**三場裡兩場的先發查無可用成績**：山口廉王（歐力士）本季 1 場 4.0 局、"
            "石川柊太（羅德）5 場 12.0 局，兩場的 `starter_stats_known` 皆為 False，"
            "軟性缺口 3 項 > 2，不可能成為推薦。此門檻 8/27 與 8/29 已擋對兩次。",
            "片山皓心（DeNA）本季 25.0 局，以 **整整 0 局的差距** 通過 25 局門檻；"
            "逐場查證確認是真先發。查證時另需排除歐力士同姓的另一位片山 —— "
            "本機 7 筆「片山」中有 6 筆不是他。",
            "看板的「渡邊勇太朗」= npb.jp 的「渡邉勇太朗」（不同漢字，非相容字元，"
            "NFKC 不會合併），西武投手群僅此一位渡邉，指涉無歧義。",
            "三場都在主要球場（みずほPayPay 1.0025、京セラD大阪 0.8645、"
            "マツダ 0.9905），是 8/25 以來第一次沒有球場係數缺口。",
            "近窗口得分水位續降：14 天窗口每場總分 6.746，比整季 7.203 低 0.46 分。"
            "**但這和 8 月看到它偏高時一樣不能拿來改參數** —— "
            "63 場的窗口本來就會這樣晃，見 config/calibration_2026.py。",
            "全場讓分與上半場盤仍不定價，理由見各場風險欄。",
        ],
    )


if __name__ == "__main__":
    print(build_report().render())
