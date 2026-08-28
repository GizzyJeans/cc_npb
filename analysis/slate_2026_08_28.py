"""2026-08-28 NPB 全六場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_08_28.py``

**這是本輪資料品質最乾淨的一天。** 十二名先發全部是正規輪值:
最少的 ハワード 也有 34.1 局、每場局數最低的 尾形崇斗 也有 5.18 局。
沒有開局投手、沒有季中角色轉換、沒有樣本不足 —— 過去四天每天都要處理的
那些修正，今天一項都不需要。這不是運氣好，是新系列賽第一天各隊都推正規
輪值先發。

先發核對已回到正常程序: npb.jp 的 8/28 予告先發公示六場十二人全數與看板
一致，包含「霍華德」= Ｓ．ハワード、「埃斯皮諾薩」= Ａ．エスピノーザ。
（昨天該頁只保留隔日場次、今日公示取不到的問題，今天不存在。）

值得注意的盤口: 巨人 @ 阪神 開在 **5平** —— 全季最低的大小盤之一。
甲子園球場係數 0.873（全聯盟最低）、村上頌樹 144.1 局防禦率 1.87、
ハワード 失分率 1.57，兩隊先發都是頂級。市場把這些全部定價進去了。
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

DATE = "2026-08-28"
DATA_AS_OF = "2026-08-28 14:00 JST (UTC 05:00)"

GAMES = [
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="讀賣巨人", home_team="阪神虎",
        away_starter="Ｓ．ハワード (右)", home_starter="村上頌樹 (右)",
        venue="甲子園 (露天)",
        handicap_raw="1平", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="5平", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-60", f5_total_raw="3+50",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="養樂多燕子", home_team="廣島鯉魚",
        away_starter="奥川恭伸 (右)", home_starter="森下暢仁 (右)",
        venue="マツダスタジアム (露天)",
        handicap_raw="1+80", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6.5", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-20", f5_total_raw="4+75",
        # 使用者於 2026-08-13 確認: 裸小數就是字面上的半球盤，不會走盤。
        attested_fields=frozenset({"total"}),
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="千葉羅德", home_team="日本火腿",
        away_starter="小島和哉 (左)", home_starter="北山亘基 (右)",
        venue="エスコンＦ (巨蛋)",
        handicap_raw="2+40", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="8+50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1平", f5_total_raw="4-50",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="福岡軟銀鷹", home_team="歐力士猛牛",
        away_starter="前田悠伍 (左)", home_starter="Ａ．エスピノーザ (右)",
        venue="京セラD大阪 (巨蛋)",
        handicap_raw="1平", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7+50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-35", f5_total_raw="3-75",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="東北樂天金鷲", home_team="西武獅",
        away_starter="瀧中瞭太 (右)", home_starter="髙橋光成 (右)",
        venue="ベルーナドーム (巨蛋)",
        handicap_raw="1+20", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7-50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-35", f5_total_raw="4+50",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="中日龍", home_team="橫濱DeNA灣星",
        away_starter="髙橋宏斗 (右)", home_starter="尾形崇斗 (右)",
        venue="横浜 (露天)",
        handicap_raw="1+50", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7-50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-30", f5_total_raw="4-25",
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
    "甲子園 (露天)": "甲子園",
    "マツダスタジアム (露天)": "マツダスタジアム",
    "エスコンＦ (巨蛋)": "エスコンＦ",
    "京セラD大阪 (巨蛋)": "京セラD大阪",
    "ベルーナドーム (巨蛋)": "ベルーナドーム",
    "横浜 (露天)": "横浜",
}

OPEN_AIR = {"甲子園", "マツダスタジアム", "横浜"}

DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限，比 Bankroll 的 5,000 更緊。"""

OPEN_AIR_MIN_EV = 0.07
"""露天球場的 EV 門檻 (一般為 +4%)，2026-08-16 使用者決定。
scorecard.py 追蹤其依據: 8/27 收盤時露天 +0.38 分 (n=31) vs
巨蛋 +0.38 分 (n=33)，差距 **0.0 個標準誤** —— 完全沒有差別。
門檻維持不動，但若再累積若干天仍是零，就該考慮把它降回 +4%。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "甲子園": "露天。未取得逐時風向／氣溫預報",
    "マツダスタジアム": "露天。未取得逐時風向／氣溫預報",
    "横浜": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。今日十二人全部通過
（最低 ハワード 34.1 局）。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。今日未用到。"""

# (顯示名, 收縮後失分率係數, 今日預期局數, 說明, 季內 IP/G)
STARTERS = {
    "巨人": ("Ｓ．ハワード", 0.784, 5.72,
             "6 場 34.1 局 防禦率 1.31、失分率 1.57、40 三振；樣本偏薄已重收縮", 5.72),
    "阪神": ("村上頌樹", 0.741, 6.87,
             "21 場 144.1 局 防禦率 1.87、每場 6.9 局 —— 本日最佳", 6.87),
    "ヤクルト": ("奥川恭伸", 0.867, 6.72,
                "18 場 121 局 防禦率 3.05、每場 6.7 局", 6.72),
    "広島": ("森下暢仁", 1.099, 5.92,
             "17 場 100.2 局 防禦率 3.84、失分率 4.20、36 四球 —— 本日最差", 5.92),
    "ロッテ": ("小島和哉", 1.000, 5.73,
              "15 場 86 局 防禦率 3.24（失分率 3.77）", 5.73),
    "日本ハム": ("北山亘基", 0.830, 6.18,
                "19 場 117.1 局 防禦率 2.22、109 三振", 6.18),
    "ソフトバンク": ("前田悠伍", 0.743, 5.86,
                  "14 場 82 局 防禦率 1.98（失分全為自責）—— 本日次佳", 5.86),
    "オリックス": ("Ａ．エスピノーザ", 0.840, 6.50,
                "18 場 117 局 防禦率 2.46、104 三振", 6.50),
    "楽天": ("瀧中瞭太", 0.906, 5.67,
             "16 場 90.2 局 防禦率 2.98，但僅 54 三振", 5.67),
    "西武": ("髙橋光成", 0.846, 6.59,
             "18 場 118.2 局 防禦率 2.35，但 38 四球最多", 6.59),
    "中日": ("髙橋宏斗", 1.059, 6.26,
             "14 場 87.2 局 防禦率 3.39（失分率 3.90）、31 四球", 6.26),
    "DeNA": ("尾形崇斗", 0.935, 5.18,
             "11 場 57 局 防禦率 3.16，但 28 四球偏多", 5.18),
}

STARTER_IP = {
    "巨人": 34.3, "阪神": 144.3, "ヤクルト": 121.0, "広島": 100.7,
    "ロッテ": 86.0, "日本ハム": 117.3, "ソフトバンク": 82.0, "オリックス": 117.0,
    "楽天": 90.7, "西武": 118.7, "中日": 87.7, "DeNA": 57.0,
}

ROLE_CHANGED: set[str] = set()
"""今日無季中角色轉換者 —— 十二人季內每場局數全部 >= 5.18。"""

BULLPEN_NOTE = {
    "巨人": "8/27 用 3 人（マタ 116 球）—— 充分",
    "阪神": "8/27 用 4 人 —— 正常",
    "ヤクルト": "8/27 用 5 人（石川 0.1 局即退場，牛棚吃掉 8.2 局）—— **最吃緊**",
    "広島": "8/27 用 5 人 —— 正常",
    "ロッテ": "8/27 用 5 人 —— 正常",
    "日本ハム": "8/26 系列賽結束後 8/27 輪空 —— 牛棚全休",
    "ソフトバンク": "8/27 用 5 人 —— 正常",
    "オリックス": "8/27 用 5 人（ジェリー 2.2 局失 8 分，牛棚吃掉 6.1 局）—— 吃緊",
    "楽天": "8/27 用 4 人（前田健 99 球投 6 局）—— 正常",
    "西武": "8/26 系列賽結束後 8/27 輪空 —— 牛棚全休",
    "中日": "8/27 用 4 人 —— 正常",
    "DeNA": "8/27 用 4 人 —— 正常",
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
            f"校準已更新到 8/27 收盤（{cal.SAMPLE_GAMES} 場）。"
            f"聯盟每隊每場得分 {cal.LEAGUE_RPG:.4f}、主場係數 {cal.HOME_EDGE:.4f}。",
            "**十二名先發全部與 npb.jp 8/28 予告先發公示一致**，"
            "包含「霍華德」= Ｓ．ハワード、「埃斯皮諾薩」= Ａ．エスピノーザ。"
            "昨天公示頁只保留隔日場次、今日公示取不到的問題，今天不存在。",
            "**本輪資料品質最乾淨的一天**：十二人全是正規輪值先發，"
            "最少的 ハワード 也有 34.1 局、每場局數最低的 尾形崇斗 也有 5.18 局。"
            "沒有開局投手、沒有季中角色轉換、沒有樣本不足 —— "
            "過去四天每天都要做的修正，今天一項都不需要。"
            "這是新系列賽第一天各隊都推正規輪值的結果。",
            "巨人 @ 阪神 開在 **5平**，是全季最低的大小盤之一。"
            "甲子園球場係數 0.873（全聯盟最低）、村上頌樹 144.1 局防禦率 1.87、"
            "ハワード 失分率 1.57 —— 市場把這些全部定價進去了。",
            "**得分水位仍不調整**。8/27 收盤時累計偏誤來到 +0.38 分"
            "（0.9 個標準誤，64 場已結算部位），連四次上升值得追蹤，但："
            "(a) 4-6月 vs 7-8月 的水位差證據 **停滯不前** —— 8/15 時 629 場是 "
            "1.13 個標準誤，8/28 時 686 場是 1.29 個標準誤，多了 57 場幾乎沒變強；"
            "(b) 市場自己的偏誤 +0.55 分 **比模型還大**，這不是模型獨有的問題；"
            "(c) 我方 64 場有選擇效果（40 場押小分）。詳見 config 的 "
            "LEAGUE_RPG_RECENT_* 說明。",
            "露天三場（甲子園、マツダ、横浜）維持 +7% EV 門檻，"
            "但這個門檻的依據正在消失：8/27 收盤時露天誤差 +0.38 分（n=31）"
            "vs 巨蛋 +0.38 分（n=33），差距 **0.0 個標準誤**。"
            "再累積若干天仍是零的話，就該考慮降回 +4%。",
            "讓分與上半場盤全數不定價。讓分的理由是結構性的："
            "模型的 Var(分差) 被共享環境因子壓窄約 2.3 倍，且數學上與 "
            "dispersion_k 無關。見 analysis/diagnose_margin.py。",
            "8/27 的教訓已驗證：養樂多先發石川雅規本季零登板，"
            "模型算出小分 +31.7% 被 `starter_stats_known` 擋下 —— "
            "他實際投 0.1 局失 6 分，總分 11，那注若下會輸。"
            "今天沒有任何一場觸發這道門檻。",
        ],
        sources=[
            "https://npb.jp/announcement/starter/（2026-08-28 預告先發公示）",
            "https://npb.jp/games/2026/schedule_08_detail.html（賽程與 8/27 比分）",
            "https://npb.jp/bis/2026/stats/idp1_<team>.html（個人投手成績）",
            "https://npb.jp/scores/2026/<date>/<slug>/box.html"
            "（牛棚用球數、逐場先發順位）",
            "賠率：使用者提供之看板截圖（2026-08-28）",
        ],
    )


if __name__ == "__main__":
    print(build_report().render())
