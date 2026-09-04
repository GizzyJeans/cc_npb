"""2026-09-04 NPB 五場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_09_04.py``

資料狀況
--------
* **十名先發全部乾淨**: 局數最少的 高梨裕稔 也有 59.1 局、每場局數最低的
  髙島泰都 也有 4.30 局。無開局投手、無季中角色轉換、無樣本不足 ——
  9/2 那種「首度先發的後援投手 + 無球場係數」今天一項都沒有。
* **五場全部在主場球場**。連續兩天出現的中性場地 (秋田、盛岡、京セラ 代打
  東京巨蛋) 今天結束: 樂天回到樂天生命、軟銀在みずほPayPay。
  仍然是逐場對照官方賽程的球場欄位確認，不是從隊名推的。

⚠️ 先發核對的來源與 8/27、8/29 相同
----------------------------------
npb.jp 的 9/4 官方預告先發已取不到 —— 該頁只保留隔日場次，
產出時 (15:40 JST) 已翻到 9/5。改用兩個替代來源:

1. **賽程頁的 `pit` 欄位**（官方，但只給主隊）: 五場主隊先發與看板
   **全部一致** —— 高梨／森下／古謝／髙島／前田悠。
2. **各隊本季投手成績表**: 五名客隊先發都確認在正確球隊且有充分樣本。

也就是說主隊先發是官方確認、客隊先發只有看板來源加名單佐證。
`starters_confirmed` 仍記為 True（依據是看板主隊五場全中），
但這個弱化必須寫在這裡。

9/3 的兩場比賽 (阪神 7-4 養樂多、廣島 5-2 中日) 未取得盤口，未定價，
僅納入校準。
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

DATE = "2026-09-04"
DATA_AS_OF = "2026-09-04 15:40 JST (UTC 06:40)"

GAMES = [
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="西武獅", home_team="福岡軟銀鷹",
        away_starter="髙橋光成 (右)", home_starter="前田悠伍 (左)",
        venue="みずほPayPay (巨蛋)",
        handicap_raw="1-65", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7平", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1+60", f5_total_raw="3.5",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="讀賣巨人", home_team="廣島鯉魚",
        away_starter="竹丸和幸 (左)", home_starter="森下暢仁 (右)",
        venue="マツダスタジアム (露天)",
        handicap_raw="1+60", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6.5", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-20", f5_total_raw="3.5",
        # 使用者於 2026-08-13 確認: 裸小數就是字面上的半球盤，不會走盤。
        attested_fields=frozenset({"total"}),
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="千葉羅德", home_team="歐力士猛牛",
        away_starter="ジャクソン (右)", home_starter="髙島泰都 (右)",
        venue="京セラD大阪 (巨蛋)",
        handicap_raw="1+80", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7平", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-20", f5_total_raw="4+75",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="日本火腿", home_team="東北樂天金鷲",
        away_starter="北山亘基 (右)", home_starter="古謝樹 (左)",
        venue="楽天モバイル (露天)",
        handicap_raw="1-55", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6-50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-80", f5_total_raw="3-50",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="中日龍", home_team="養樂多燕子",
        away_starter="髙橋宏斗 (右)", home_starter="高梨裕稔 (右)",
        venue="神宮 (露天)",
        handicap_raw="1+55", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7-75", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-40", f5_total_raw="4-25",
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
    "みずほPayPay (巨蛋)": "みずほPayPay",
    "マツダスタジアム (露天)": "マツダスタジアム",
    "京セラD大阪 (巨蛋)": "京セラD大阪",
    "楽天モバイル (露天)": "楽天モバイル",
    "神宮 (露天)": "神宮",
}

OPEN_AIR = {"マツダスタジアム", "楽天モバイル", "神宮"}

NEUTRAL_PARK_FACTOR = 1.0
"""配適資料裡沒有 (或場次太少不足以估計) 的球場採用的中性值。今日未用到。"""


def park_factor(game: BoardGame) -> float:
    """球場係數；資料不足的球場退回中性值並由門檻揭露。"""
    return cal.PARK_FACTORS_2026.get(PARK_KEY[game.venue], NEUTRAL_PARK_FACTOR)


DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限，比 Bankroll 的 5,000 更緊。"""

OPEN_AIR_MIN_EV = GATE_OPEN_AIR_MIN_EV
"""露天球場的 EV 門檻，由 `bethero.gates` 統一定義（2026-09-02 起 = 0.04）。"""

STARTED: set[str] = set()
"""本報告產出時已開賽的場次 (以主隊記)。今日五場全部 18:00 開賽，無。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "マツダスタジアム": "露天。未取得逐時風向／氣溫預報",
    "楽天モバイル": "露天。未取得逐時風向／氣溫預報",
    "神宮": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。今日十人全部通過
（最低 高梨裕稔 59.1 局）。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。今日未用到。"""

# (顯示名, 收縮後失分率係數, 今日預期局數, 說明, 季內 IP/G)
STARTERS = {
    "西武": ("髙橋光成", 0.869, 6.60,
             "19 場 125.1 局 防禦率 2.51、每場 6.6 局，但 42 四球偏多", 6.60),
    "ソフトバンク": ("前田悠伍", 0.705, 5.93,
                  "15 場 89 局 防禦率 1.82、失分全為自責 —— 本日最佳", 5.93),
    "巨人": ("竹丸和幸", 1.153, 5.72,
             "18 場 103 局 防禦率 3.93、失分率 4.54、32 四球 —— 本日最差之一", 5.72),
    "広島": ("森下暢仁", 1.108, 5.93,
             "18 場 106.2 局 防禦率 3.88、失分率 4.22、**40 四球**", 5.93),
    "ロッテ": ("ジャクソン", 0.989, 6.09,
              "22 場 134 局 防禦率 3.43、每場 6.1 局，但 **52 四球最多**", 6.09),
    "オリックス": ("髙島泰都", 1.207, 4.30,
                "19 場 81.2 局 防禦率 4.19、失分率 4.52，每場 4.3 局偏短", 4.30),
    "日本ハム": ("北山亘基", 0.856, 6.20,
                "20 場 124 局 防禦率 2.40、每場 6.2 局 —— 本日次佳", 6.20),
    "楽天": ("古謝樹", 1.055, 5.69,
             "16 場 91 局 防禦率 3.46（失分率 3.96）", 5.69),
    "中日": ("髙橋宏斗", 1.020, 6.31,
             "15 場 94.2 局 防禦率 3.23（失分率 3.71）、32 四球", 6.31),
    "ヤクルト": ("高梨裕稔", 0.853, 5.93,
                "10 場 59.1 局 防禦率 2.73（失分率 3.03）、僅 13 四球", 5.93),
}

STARTER_IP = {
    "西武": 125.3, "ソフトバンク": 89.0, "巨人": 103.0, "広島": 106.7,
    "ロッテ": 134.0, "オリックス": 81.7, "日本ハム": 124.0, "楽天": 91.0,
    "中日": 94.7, "ヤクルト": 59.3,
}

ROLE_CHANGED: set[str] = set()
"""今日無季中角色轉換者 —— 十人季內每場局數全部 >= 4.30。"""

BULLPEN_NOTE = {
    "西武": "9/2 輪空、9/3 輪空 —— 牛棚全休",
    "ソフトバンク": "9/2 打滿 12 局和局用 6 人、9/3 輪空 —— 已恢復但 12 局消耗大",
    "巨人": "9/2 用 4 人（延長 10 局）、9/3 輪空 —— 已恢復",
    "広島": "9/2 用 4 人、9/3 用 4 人（5-2 勝）—— 正常",
    "ロッテ": "9/2 輪空、9/3 輪空 —— 牛棚全休",
    "オリックス": "9/2 用 4 人（被完封）、9/3 輪空 —— 已恢復",
    "日本ハム": "9/2 打滿 12 局和局用 6 人、9/3 輪空 —— 已恢復但 12 局消耗大",
    "楽天": "9/2 用 3 人（4-0 完封勝）、9/3 輪空 —— 充分",
    "中日": "9/2 用 4 人、9/3 用 5 人（被打 5 分）—— 略吃緊",
    "ヤクルト": "9/2 用 4 人、9/3 用 5 人（被打 7 分）—— 略吃緊",
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
            lineup_note="15:30 JST 尚未公布，依使用者指示略過",
            bullpen_note=f"{game.home_team}：{BULLPEN_NOTE[home]}；"
                         f"{game.away_team}：{BULLPEN_NOTE[away]}",
            park_weather_note=(
                f"球場係數 {park_factor(game):.3f}"
                + ("（2026 實測）。" if PARK_KEY[game.venue] in cal.PARK_FACTORS_2026
                   else "（⚠️ 本季零場次，採中性值 1.0）。")
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
            f"校準已更新到 9/3 收盤（{cal.SAMPLE_GAMES} 場）。"
            f"聯盟每隊每場得分 {cal.LEAGUE_RPG:.4f}、主場係數 {cal.HOME_EDGE:.4f}。"
            "9/3 只有兩場（阪神 7-4 養樂多、廣島 5-2 中日），未取得盤口故未定價，"
            "僅納入校準。",
            "**十名先發全部乾淨**：局數最少的 高梨裕稔 也有 59.1 局、"
            "每場局數最低的 髙島泰都 也有 4.30 局。無開局投手、無季中角色轉換、"
            "無樣本不足 —— 9/2 那種「首度先發的後援投手 + 無球場係數」今天一項都沒有。",
            "**五場全部在主場球場。** 連續兩天的中性場地（秋田、盛岡、"
            "京セラ 代打東京巨蛋）今天結束：樂天回到樂天生命、軟銀在みずほPayPay。"
            "仍然是逐場對照官方賽程的球場欄位確認，不是從隊名推的。",
            "⚠️ **9/4 的官方預告先發已取不到**（該頁只保留隔日場次，"
            "產出時 15:40 JST 已翻到 9/5），與 8/27、8/29 同一個問題。"
            "改用賽程頁的 `pit` 欄位（官方，但只給主隊）—— 五場主隊先發與看板"
            "**全部一致**；客隊五人也都確認在正確球隊且有充分樣本。"
            "主隊是官方確認、客隊只有看板來源加名單佐證，這個弱化必須揭露。",
            "⚠️ **首選的分歧幅度是至今下注過最大的**：火腿 @ 樂天，"
            "模型 8.02 vs 市場等效盤口約 6.25，差 1.77 分，EV +29.3%。"
            "模型的理由是樂天牛棚全聯盟最差（1.342）加上火腿第三強的打線；"
            "但市場把它開成低分局，兩邊的分歧不是小事。",
            "  相關的追蹤數字：9/2 收盤時模型 **押大分的 34 場** 「實際−模型」"
            "為 −0.97 分（押小分 59 場是 +0.53），也就是模型押大分時"
            "有系統性高估的跡象（約 1.6 個標準誤，未達行動門檻）。"
            "今天的首選正是一注大分、且分歧極大 —— 兩者疊在一起，這注的"
            "不確定性比 EV 數字看起來的高。仍然依規則下注，但要知道這件事。",
            "**得分水位確定沒有問題。** 9/2 收盤時 93 場的整體偏誤 −0.02 分"
            "（0.0 個標準誤），未下注對照組的「實際 − 盤口」+0.00。"
            "兩週來沒有動 `league_rpg` 是對的。",
            "露天三場（マツダ、樂天生命、神宮）適用 **已降回的 +4% 門檻**"
            "（2026-09-02 撤除 +7% 溢價）。今天三場露天的 EV 分別是 "
            "+29.3%、+9.4%、+0.3%，門檻高低不影響任何一場的結論。",
            "讓分與上半場盤全數不定價。理由是結構性的：模型的 Var(分差) 被"
            "共享環境因子壓窄約 2.3 倍，且數學上與 dispersion_k 無關。"
            "見 analysis/diagnose_margin.py。",
        ],
        sources=[
            "https://npb.jp/games/2026/schedule_09_detail.html"
            "（賽程、9/3 比分、**主隊先發 pit 欄位**、球場欄位）",
            "https://npb.jp/bis/2026/stats/idp1_<team>.html（個人投手成績）",
            "https://npb.jp/scores/2026/<date>/<slug>/box.html（牛棚用球數）",
            "⚠️ https://npb.jp/announcement/starter/ 今日 **無法取得**"
            "（該頁只保留隔日場次，已翻到 9/5）",
            "賠率：使用者提供之看板截圖（2026-09-04）",
        ],
    )


if __name__ == "__main__":
    print(build_report().render())
