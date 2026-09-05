"""2026-09-05 NPB 全六場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_09_05.py``

資料狀況
--------
* **官方預告先發完整可取得**，六場十二人全數與看板一致（穆勒 = Ｋ．マラー、
  埃斯皮諾薩 = Ａ．エスピノーザ）。8/27、8/29、9/4 那種「公示頁已翻到隔日」
  的問題今天不存在。
* **十二人全部乾淨**: 局數最少的 玉村昇悟 也有 58 局、每場局數最低的
  尾形崇斗 也有 5.19 局。無開局投手、無季中角色轉換、無樣本不足。
* **六場全部在主場球場**（9/1-9/2 那種秋田／盛岡／京セラ 代打的中性場地
  已結束）。仍逐場對照官方球場欄位確認。

⚠️ 兩批開賽時間
--------------
* **14:00 JST**: 西武 @ 軟銀（みずほPayPay）、羅德 @ 歐力士（京セラ）
* **18:00 JST**: 其餘四場

本報告產出時 13:05 JST，14:00 那批還有約 55 分鐘，仍可下注 ——
但若你晚於 14:00 才看到這份報告，那兩場請依 `STARTED` 的原則視為
不可下注（賽前盤口已不可得）。
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

DATE = "2026-09-05"
DATA_AS_OF = "2026-09-05 13:05 JST (UTC 04:05)"

GAMES = [
    BoardGame(
        date=DATE, start_time="14:00 JST（看板 13:00 台北）",
        away_team="西武獅", home_team="福岡軟銀鷹",
        away_starter="隅田知一郎 (左)", home_starter="大津亮介 (右)",
        venue="みずほPayPay (巨蛋)",
        handicap_raw="1平", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7+50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-80", f5_total_raw="4+75",
    ),
    BoardGame(
        date=DATE, start_time="14:00 JST（看板 13:00 台北）",
        away_team="千葉羅德", home_team="歐力士猛牛",
        away_starter="小島和哉 (左)", home_starter="Ａ．エスピノーザ (右)",
        venue="京セラD大阪 (巨蛋)",
        handicap_raw="1平", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6.5", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-75", f5_total_raw="3-50",
        # 使用者於 2026-08-13 確認: 裸小數就是字面上的半球盤，不會走盤。
        attested_fields=frozenset({"total"}),
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="橫濱DeNA灣星", home_team="阪神虎",
        away_starter="尾形崇斗 (右)", home_starter="村上頌樹 (右)",
        venue="甲子園 (露天)",
        handicap_raw="1-10", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6+50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-70", f5_total_raw="3-25",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="讀賣巨人", home_team="廣島鯉魚",
        away_starter="田中将大 (右)", home_starter="玉村昇悟 (左)",
        venue="マツダスタジアム (露天)",
        handicap_raw="1+90", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6-50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-20", f5_total_raw="3-75",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="日本火腿", home_team="東北樂天金鷲",
        away_starter="伊藤大海 (右)", home_starter="早川隆久 (左)",
        venue="楽天モバイル (露天)",
        handicap_raw="1+10", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7+75", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-25", f5_total_raw="3.5",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="中日龍", home_team="養樂多燕子",
        away_starter="Ｋ．マラー (左)", home_starter="高橋奎二 (左)",
        venue="神宮 (露天)",
        handicap_raw="1+25", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7-25", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-40", f5_total_raw="4+25",
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
    "京セラD大阪 (巨蛋)": "京セラD大阪",
    "甲子園 (露天)": "甲子園",
    "マツダスタジアム (露天)": "マツダスタジアム",
    "楽天モバイル (露天)": "楽天モバイル",
    "神宮 (露天)": "神宮",
}

OPEN_AIR = {"甲子園", "マツダスタジアム", "楽天モバイル", "神宮"}

NEUTRAL_PARK_FACTOR = 1.0
"""配適資料裡沒有的球場採用的中性值。今日未用到。"""


def park_factor(game: BoardGame) -> float:
    """球場係數；資料不足的球場退回中性值並由門檻揭露。"""
    return cal.PARK_FACTORS_2026.get(PARK_KEY[game.venue], NEUTRAL_PARK_FACTOR)


DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限，比 Bankroll 的 5,000 更緊。"""

OPEN_AIR_MIN_EV = GATE_OPEN_AIR_MIN_EV
"""露天球場的 EV 門檻，由 `bethero.gates` 統一定義（2026-09-02 起 = 0.04）。"""

STARTED: set[str] = set()
"""本報告產出時 (13:05 JST) 尚無場次開賽。

⚠️ 14:00 那批（軟銀、歐力士）距開賽約 55 分鐘。若實際下注時間已過 14:00，
這兩場應視為 `prices_verified=False` —— 賽前盤口已不可得。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "甲子園": "露天。未取得逐時風向／氣溫預報",
    "マツダスタジアム": "露天。未取得逐時風向／氣溫預報",
    "楽天モバイル": "露天。未取得逐時風向／氣溫預報",
    "神宮": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。今日十二人全部通過。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。今日未用到。"""

# (顯示名, 收縮後失分率係數, 今日預期局數, 說明, 季內 IP/G)
STARTERS = {
    "西武": ("隅田知一郎", 0.829, 7.20,
             "20 場 144 局 防禦率 2.19、**每場 7.2 局全聯盟最深**、僅 20 四球", 7.20),
    "ソフトバンク": ("大津亮介", 0.872, 6.65,
                  "19 場 126.1 局 防禦率 2.49、每場 6.7 局", 6.65),
    "ロッテ": ("小島和哉", 1.077, 5.69,
              "16 場 91 局 防禦率 3.66、失分率 4.15、28 四球", 5.69),
    "オリックス": ("Ａ．エスピノーザ", 0.849, 6.47,
                "19 場 123 局 防禦率 2.49（失分率 2.56）", 6.47),
    "DeNA": ("尾形崇斗", 0.941, 5.19,
             "12 場 62.1 局 防禦率 3.18，但 **30 四球** 偏多", 5.19),
    "阪神": ("村上頌樹", 0.730, 6.88,
             "22 場 151.1 局 防禦率 1.84、失分率 2.08 —— 本日最佳", 6.88),
    "巨人": ("田中将大", 1.087, 5.30,
             "11 場 58.1 局 防禦率 3.70、失分率 4.32 —— 本日最差之一", 5.30),
    "広島": ("玉村昇悟", 0.954, 5.27,
             "11 場 58 局 防禦率 2.95（失分率 3.26）、僅 12 四球", 5.27),
    "日本ハム": ("伊藤大海", 0.968, 6.53,
                "22 場 143.2 局 防禦率 3.19、每場 6.5 局", 6.53),
    "楽天": ("早川隆久", 0.821, 6.78,
             "18 場 122 局 防禦率 2.51、每場 6.8 局 —— 本日次佳", 6.78),
    "中日": ("Ｋ．マラー", 0.845, 6.40,
             "16 場 102.1 局 防禦率 2.46（失分率 2.73）", 6.40),
    "ヤクルト": ("高橋奎二", 1.026, 5.49,
                "13 場 71.1 局 防禦率 4.29、失分全為自責、25 四球", 5.49),
}

STARTER_IP = {
    "西武": 144.0, "ソフトバンク": 126.3, "ロッテ": 91.0, "オリックス": 123.0,
    "DeNA": 62.3, "阪神": 151.3, "巨人": 58.3, "広島": 58.0,
    "日本ハム": 143.7, "楽天": 122.0, "中日": 102.3, "ヤクルト": 71.3,
}

ROLE_CHANGED: set[str] = set()
"""今日無季中角色轉換者 —— 十二人季內每場局數全部 >= 5.19。"""

BULLPEN_NOTE = {
    "西武": "9/4 用 5 人（2-8 敗）—— 略吃緊",
    "ソフトバンク": "9/4 用 3 人（8-2 勝）—— 充分",
    "ロッテ": "9/4 用 4 人 —— 正常",
    "オリックス": "9/4 用 3 人（3-1 勝）—— 充分",
    "DeNA": "9/3、9/4 連續輪空 —— 牛棚全休",
    "阪神": "9/3 用 4 人（7-4 勝）、9/4 輪空 —— 已恢復",
    "巨人": "9/4 用 4 人（3-1 勝）—— 正常",
    "広島": "9/3 用 4 人、9/4 用 4 人 —— 正常",
    "日本ハム": "9/4 用 4 人（5-2 勝）—— 正常",
    "楽天": "9/4 用 5 人（2-5 敗）—— 略吃緊",
    "中日": "9/4 打滿延長 10 局用 5 人 —— 吃緊",
    "ヤクルト": "9/4 打滿延長 10 局用 5 人 —— 吃緊",
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
            f"校準已更新到 9/4 收盤（{cal.SAMPLE_GAMES} 場）。"
            f"聯盟每隊每場得分 {cal.LEAGUE_RPG:.4f}、主場係數 {cal.HOME_EDGE:.4f}。",
            "**官方預告先發完整可取得**，六場十二人全數與看板一致"
            "（穆勒 = Ｋ．マラー、埃斯皮諾薩 = Ａ．エスピノーザ）。"
            "8/27、8/29、9/4 那種「公示頁已翻到隔日、今日取不到」的問題今天不存在。",
            "**十二人全部乾淨**：局數最少的 玉村昇悟 也有 58 局、每場局數最低的"
            "尾形崇斗 也有 5.19 局。無開局投手、無季中角色轉換、無樣本不足。"
            "**六場也全部在主場球場** —— 9/1-9/2 的秋田／盛岡／京セラ 代打東京巨蛋"
            "已結束，仍逐場對照官方球場欄位確認。",
            "⚠️ **兩批開賽**：14:00 JST 兩場（軟銀、歐力士）、18:00 JST 四場。"
            "本報告 13:05 JST 產出，14:00 那批還有約 55 分鐘。"
            "**結果上三注推薦都落在 18:00 那批**，所以時間問題今天不影響任何建議；"
            "但若你晚於 14:00 才看到，那兩場請一律視為賽前盤口已不可得。",
            "今天的 EV 幅度明顯比昨天溫和（最高 +8.0%，昨天是 +29.3%）—— "
            "六場的模型預期總分全部落在 5.89 到 7.38 之間，與市場沒有大分歧。"
            "這種日子的部位品質通常比「模型大喊有優勢」的日子更可靠。",
            "**追蹤中的訊號沒有改善**：9/4 收盤時模型押大分的 35 場「實際−模型」"
            "為 −0.95 分（押小分 63 場 +0.38），與前一次的 −0.97 幾乎相同。"
            "昨天那注大分贏了，但它贏在總分落到模型與市場之間，不是模型算對了。"
            "今天的三注是一大二小，方向較平衡。",
            "**得分水位維持不調**：98 場的整體偏誤 −0.10 分（0.3 個標準誤），"
            "「已下注 − 未下注」1.2 個標準誤，都在雜訊帶內。",
            "露天四場（甲子園、マツダ、樂天生命、神宮）適用 **已降回的 +4% 門檻**。"
            "今天露天場的 EV 是 +8.0%、+7.6%、+4.8%、+2.4% —— "
            "其中 +4.8% 那注（中日 @ 養樂多）在舊的 +7% 門檻下會被擋掉，"
            "**這是門檻改動第一次實際改變了下注單**。",
            "讓分與上半場盤全數不定價。理由是結構性的：模型的 Var(分差) 被"
            "共享環境因子壓窄約 2.3 倍，且數學上與 dispersion_k 無關。"
            "見 analysis/diagnose_margin.py。",
        ],
        sources=[
            "https://npb.jp/announcement/starter/（2026-09-05 預告先發公示，含球場欄位）",
            "https://npb.jp/games/2026/schedule_09_detail.html（賽程與 9/4 比分）",
            "https://npb.jp/bis/2026/stats/idp1_<team>.html（個人投手成績）",
            "https://npb.jp/scores/2026/<date>/<slug>/box.html（牛棚用球數）",
            "賠率：使用者提供之看板截圖（2026-09-05）",
        ],
    )


if __name__ == "__main__":
    print(build_report().render())
