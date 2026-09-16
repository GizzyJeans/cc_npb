"""2026-09-16 NPB 全兩場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_09_16.py``

今天全聯盟只有兩場，都 18:00 JST 開賽。

⚠️ 今天的新鮮度防護抓到一次真實失誤
----------------------------------
`cal.freshness_note()` 在定價前回報 **校準已過期 1 天**。追下去才發現
今早的自動結算根本沒有寫檔 —— 那一輪的指令是:

    python3 scripts/refresh_calibration.py --as-of "..." | head -4 && ...

``head`` 讀滿 4 行就關掉管線，python 收到 SIGPIPE 在 **寫檔之前** 就死了，
而 ``head`` 自己回 0，所以 ``&&`` 一路往下跑、回報還寫著「校準已更新到
9/15 收盤 (777 場)」。**那句話是錯的**，當時 config 仍停在 771 場／9/14。

這和同一週 pytest 被 ``| tail`` 吞掉結束狀態是同一個坑。已修兩處:

* `scripts/refresh_calibration.py` 改成 **先寫檔、最後才印**，
  並在輸出端吞掉 BrokenPipeError —— 就算輸出被截斷，該做的事也做完了。
* 已實測: 接 ``| head -2`` 仍然正確寫檔。

影響範圍: 9/15 的結算損益 **不受影響**（只看賽果、盤口、注碼），
但該份報告裡的「模型預期總分」是用 9/14 的係數算的。已用正確校準重跑。

**這正是 9/15 加上那道防護的理由 —— 它第一次上工就抓到了東西。**

查證結果
--------
* 兩場的對戰、球場、主客與先發，全部與 npb.jp 賽程頁的「先發」欄相符。
* **四位先發的姓名與投球側 4/4 相符**。看板寫「**莊**司康誠」、
  npb.jp 寫「**荘**司康誠」—— 又一組非 NFKC 相容的異體字，已加入等價表
  （目前累積: 莊/荘、將/将、增/増、邊/邉、髙/高、﨑/崎、澤/沢）。
* 四人全部越過 25 局門檻、也全部是先發用法（IP/G 4.65-6.23），
  今天沒有任何門檻被觸發 —— 是 9/9 以來第一次。
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

DATE = "2026-09-16"
DATA_AS_OF = "2026-09-16 17:20 JST (UTC 08:20)"

T = "18:00 JST（看板 17:00 台北）"

GAMES = [
    BoardGame(
        date=DATE, start_time=T,
        away_team="東北樂天金鷲", home_team="千葉羅德",
        away_starter="莊司康誠 (右)", home_starter="毛利海大 (左)",
        venue="ZOZOマリンスタジアム (露天)",
        # ⚠️ 讓球是純小數 0.5；讓球不定價，audit_for("total") 不受影響。
        handicap_raw="0.5", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7-75", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-20", f5_total_raw="4-25",
    ),
    BoardGame(
        date=DATE, start_time=T,
        away_team="福岡軟銀鷹", home_team="歐力士猛牛",
        away_starter="上沢直之 (右)", home_starter="九里亜蓮 (右)",
        venue="京セラD大阪 (巨蛋)",
        handicap_raw="2+60", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7.5", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1+30", f5_total_raw="4平",
        # 純小數 = 字面上的半球盤，永不和局。使用者 2026-08-13 已目視確認。
        attested_fields=frozenset({"total"}),
    ),
]

JP = {
    "東北樂天金鷲": "楽天", "千葉羅德": "ロッテ",
    "福岡軟銀鷹": "ソフトバンク", "歐力士猛牛": "オリックス",
}
PARK_KEY = {
    "ZOZOマリンスタジアム (露天)": "ZOZOマリン",
    "京セラD大阪 (巨蛋)": "京セラD大阪",
}

OPEN_AIR = {"ZOZOマリン"}
"""京セラD大阪 是巨蛋。"""

NEUTRAL_PARK_FACTOR = 1.0
"""配適資料裡沒有的球場採用的中性值。今日六場都在主要球場，未用到。"""


def park_factor(game: BoardGame) -> float:
    return cal.PARK_FACTORS_2026.get(PARK_KEY[game.venue], NEUTRAL_PARK_FACTOR)


DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限，比 Bankroll 的 5,000 更緊。"""

OPEN_AIR_MIN_EV = GATE_OPEN_AIR_MIN_EV
"""露天球場的 EV 門檻，由 `bethero.gates` 統一定義（2026-09-02 起 = 0.04）。"""

STARTED: set[str] = set()
"""本報告產出時 (17:20 JST) 兩場皆未開賽，18:00 開打。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "ZOZOマリン": "露天，臨海、風的影響在十二座球場中最大。未取得逐時預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。
今日四人全部通過，最低是毛利海大 74.3 局 —— 安全邊際很大。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。今日未用到。"""

# (顯示名, 收縮後失分率係數, 今日預期局數, 說明, 季內 IP/G)
STARTERS = {
    "楽天": ("荘司康誠", 1.105, 6.23,
             "22 場 137.0 局 失分率 4.14、每場 6.2 局", 6.23),
    "ロッテ": ("毛利海大", 1.256, 4.65,
              "16 場 74.1 局 失分率 **5.33** —— 本日最差，每場僅 4.7 局", 4.65),
    "ソフトバンク": ("上沢直之", 0.935, 6.12,
                  "19 場 116.1 局 失分率 3.25、每場 6.1 局 —— 本日最佳", 6.12),
    "オリックス": ("九里亜蓮", 1.152, 6.03,
                "24 場 144.2 局 失分率 4.04、每場 6.0 局", 6.03),
}

STARTER_IP = {
    "楽天": 137.0, "ロッテ": 74.3, "ソフトバンク": 116.3, "オリックス": 144.7,
}

ROLE_CHANGED: set[str] = set()
"""今日無角色轉換案例 —— 四人的季內 IP/G 都在 4.65-6.23 之間，全是先發型態。"""

BULLPEN_NOTE = {
    "楽天": "9/15 用 4 人（伊藤樹 6 局 100 球失 0，牛棚 3 人 43 球；1-0 完封勝）"
            "—— 充分；但牛棚係數 1.344 是全聯盟最差",
    "ロッテ": "9/15 用 5 人（田中晴也 5.2 局 95 球失 4，牛棚 4 人 58 球；7-6 險勝）"
              "—— 正常",
    "ソフトバンク": "9/15 用 4 人（モイネロ 6 局 87 球失 2，牛棚 3 人 50 球；5-3 勝）"
                  "—— 充分，牛棚係數 0.860 是全聯盟第 2 佳",
    "オリックス": "9/15 用 5 人（ジェリー 5.1 局 102 球失 5，牛棚 4 人 51 球；3-5 敗）"
                "—— 正常；但牛棚係數 1.254 是全聯盟第 2 差",
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
            lineup_note="17:20 JST 尚未公布，依使用者指示略過",
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
        "⚠️ **9/15 新加的新鮮度防護今天第一次上工就抓到真問題**：今早的自動"
        "結算把重配適接了 `| head -4`，`head` 關掉管線後 python 收到 SIGPIPE，"
        "**在寫檔之前就死了**，而 `head` 回 0 讓 `&&` 一路往下跑 —— "
        "當時的回報寫著「校準已更新到 777 場」，實際仍停在 771 場／9/14。"
        "已改成先寫檔再輸出，並實測接 `| head -2` 仍正確寫檔。"
        "9/15 的結算損益不受影響（只看賽果與盤口），但該報告的模型預期總分"
        "已用正確校準重跑。",
        "四位先發的 **姓名與投球側 4/4 相符**。看板「**莊**司康誠」= "
        "npb.jp「**荘**司康誠」，又一組非 NFKC 相容的異體字，已加入等價表。",
        "**今天沒有任何門檻被觸發** —— 四人全部越過 25 局（最低 74.3 局）、"
        "也全部是先發用法（IP/G 4.65-6.23）。是 9/9 以來第一次。",
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
