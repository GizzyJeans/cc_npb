"""2026-08-30 NPB 全六場 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_08_30.py``

資料狀況已回到正常
------------------
* npb.jp 的 8/30 官方預告先發完整可取得，**六場十二人全數與看板一致**。
  （8/27 與 8/29 那種「公示頁已翻到隔日、今日取不到」的問題今天不存在。）
* 十二人全部是正規輪值先發: 局數最少的 小川泰弘 也有 38 局、
  每場局數最低的 田中晴也 也有 5.28 局。無開局投手、無季中角色轉換、
  無樣本不足。

姓名比對
--------
廣島先發 **森翔平** 正是 2026-08-13 那次同姓誤配的當事人 ——
廣島同時有 森下暢仁、森浦大輔，當時用姓氏比對挑錯了人。
今天用官方公示的全名做精確比對（先試 `==`，失敗才退回子字串），
十二人全部唯一命中。

⚠️ 時間
-------
本報告產出時 (14:00 JST):
* 第一場 羅德 @ 火腿 13:00 開打 —— **已進行約 1 小時**
* 第二場 軟銀 @ 歐力士 14:00 開打 —— **正在開賽**
這兩場的定價僅供事後對帳，不是可下注的建議。
實際可下注的是 17:00 的樂天 @ 西武 與 18:00 的三場。

⚠️ 校準資料來源的一個例外
------------------------
npb.jp 的賽程頁在 8/29 賽後 15 小時仍未更新比分，若照舊只讀該頁，
校準會停在 697 場 (8/28)。8/29 那六場的比分我在昨天結算時已逐場由
box.html 讀出並與帳本核對，因此直接回填進 season.json，
校準才得以推進到 **703 場 (8/29)**。回填的是已驗證的資料，不是估計值。
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

DATE = "2026-08-30"
DATA_AS_OF = "2026-08-30 14:00 JST (UTC 05:00)"

GAMES = [
    BoardGame(
        date=DATE, start_time="13:00 JST（看板 12:00 台北）⚠️ 已開打",
        away_team="千葉羅德", home_team="日本火腿",
        away_starter="田中晴也 (右)", home_starter="有原航平 (右)",
        venue="エスコンＦ (巨蛋)",
        handicap_raw="1-40", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="8+50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1+40", f5_total_raw="4.5",
    ),
    BoardGame(
        date=DATE, start_time="14:00 JST（看板 13:00 台北）⚠️ 正在開賽",
        away_team="福岡軟銀鷹", home_team="歐力士猛牛",
        away_starter="松本晴 (左)", home_starter="曽谷龍平 (左)",
        venue="京セラD大阪 (巨蛋)",
        handicap_raw="1-45", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7+50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-65", f5_total_raw="3-75",
    ),
    BoardGame(
        date=DATE, start_time="17:00 JST（看板 16:00 台北）",
        away_team="東北樂天金鷲", home_team="西武獅",
        away_starter="岸孝之 (右)", home_starter="武内夏暉 (左)",
        venue="ベルーナドーム (巨蛋)",
        handicap_raw="1+40", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7+75", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-60", f5_total_raw="3.5",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="讀賣巨人", home_team="阪神虎",
        away_starter="小笠原慎之介 (左)", home_starter="才木浩人 (右)",
        venue="甲子園 (露天)",
        handicap_raw="1+5", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="5-50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-80", f5_total_raw="3+50",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="養樂多燕子", home_team="廣島鯉魚",
        away_starter="小川泰弘 (右)", home_starter="森翔平 (左)",
        venue="マツダスタジアム (露天)",
        handicap_raw="1+50", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7+50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-50", f5_total_raw="4+75",
    ),
    BoardGame(
        date=DATE, start_time="18:00 JST（看板 17:00 台北）",
        away_team="中日龍", home_team="橫濱DeNA灣星",
        away_starter="柳裕也 (右)", home_starter="篠木健太郎 (右)",
        venue="横浜 (露天)",
        handicap_raw="1+15", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="8+50", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-75", f5_total_raw="4.5",
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
    "エスコンＦ (巨蛋)": "エスコンＦ",
    "京セラD大阪 (巨蛋)": "京セラD大阪",
    "ベルーナドーム (巨蛋)": "ベルーナドーム",
    "甲子園 (露天)": "甲子園",
    "マツダスタジアム (露天)": "マツダスタジアム",
    "横浜 (露天)": "横浜",
}

OPEN_AIR = {"甲子園", "マツダスタジアム", "横浜"}

STARTED = {"日本ハム", "オリックス"}
"""本報告產出時 (14:00 JST) 已開賽的場次，以主隊記。

羅德 @ 火腿 13:00 開賽、軟銀 @ 歐力士 14:00 開賽。
**比賽開打後看板上的賽前盤口就拿不到了**，因此這兩場的
`prices_verified` 記為 False —— 那是硬性門檻，不可能成為推薦。
語意上這正是該欄位要問的事:「手上這個賠率是不是當下可取得的報價」。
定價仍會照算，但只供事後對帳。"""

DAILY_BUDGET = 3000.0
"""使用者指定的單日曝險上限，比 Bankroll 的 5,000 更緊。"""

OPEN_AIR_MIN_EV = 0.07
"""露天球場的 EV 門檻 (一般為 +4%)，2026-08-16 使用者決定。
scorecard 追蹤其依據，8/29 收盤時露天與巨蛋的誤差差距仍在 0 附近 ——
連續三天沒有差別。維持不動，但這個門檻已經站不太住，
資料乾淨且無其他變動的日子應該處理掉。"""

LINE_MOVES = {}
"""本日只取得單一時點的看板，無盤口移動可比對。"""

WEATHER = {
    "甲子園": "露天。未取得逐時風向／氣溫預報",
    "マツダスタジアム": "露天。未取得逐時風向／氣溫預報",
    "横浜": "露天。未取得逐時風向／氣溫預報",
}

MIN_STARTER_IP = 25.0
"""先發本季局數低於此值即視為「查無可用成績」。今日十二人全部通過
（最低 小川泰弘 38 局）。"""

DEFAULT_IP_PER_START = 5.50
"""查無先發紀錄時採用的聯盟典型先發局數。今日未用到。"""

# (顯示名, 收縮後失分率係數, 今日預期局數, 說明, 季內 IP/G)
STARTERS = {
    "ロッテ": ("田中晴也", 1.150, 5.28,
              "12 場 63.1 局 防禦率 4.55、失分率 4.83、26 四球", 5.28),
    "日本ハム": ("有原航平", 1.164, 6.36,
                "12 場 76.1 局 防禦率 4.13、失分率 4.83 —— 本日最差之一", 6.36),
    "ソフトバンク": ("松本晴", 0.919, 5.61,
                  "17 場 95.1 局 防禦率 3.02，但 33 四球偏多", 5.61),
    "オリックス": ("曽谷龍平", 1.107, 5.94,
                "11 場 65.1 局 防禦率 3.58（失分率 3.99）、僅 11 四球", 5.94),
    "楽天": ("岸孝之", 0.867, 6.12,
             "8 場 49 局 防禦率 2.39、失分率 2.57；樣本偏薄已重收縮", 6.12),
    "西武": ("武内夏暉", 0.931, 6.43,
             "18 場 115.2 局 防禦率 2.88、每場 6.4 局", 6.43),
    "巨人": ("小笠原慎之介", 0.799, 6.50,
             "6 場 39 局 防禦率 1.85、失分全為自責、僅 6 四球 —— 本日最佳", 6.50),
    "阪神": ("才木浩人", 0.926, 6.20,
             "20 場 124 局 防禦率 2.76、每場 6.2 局", 6.20),
    "ヤクルト": ("小川泰弘", 1.233, 5.43,
                "7 場 38 局 防禦率 5.45、**失分率 6.63** —— 本日最差", 5.43),
    "広島": ("森翔平", 0.950, 5.69,
             "12 場 68.1 局 防禦率 3.16（失分率 3.29）、22 四球", 5.69),
    "中日": ("柳裕也", 0.800, 6.24,
             "21 場 131 局 防禦率 2.47、失分率 2.54 —— 本日次佳", 6.24),
    "DeNA": ("篠木健太郎", 1.114, 5.58,
             "12 場 67 局 防禦率 4.57、23 四球", 5.58),
}

STARTER_IP = {
    "ロッテ": 63.3, "日本ハム": 76.3, "ソフトバンク": 95.3, "オリックス": 65.3,
    "楽天": 49.0, "西武": 115.7, "巨人": 39.0, "阪神": 124.0,
    "ヤクルト": 38.0, "広島": 68.3, "中日": 131.0, "DeNA": 67.0,
}

ROLE_CHANGED: set[str] = set()
"""今日無季中角色轉換者 —— 十二人季內每場局數全部 >= 5.28。"""

BULLPEN_NOTE = {
    "ロッテ": "8/29 用 5 人（先發 7 局失 9 分的比賽）—— 吃緊",
    "日本ハム": "8/29 用 5 人（贏 9-7 的高分戰）—— 吃緊",
    "ソフトバンク": "8/29 用 4 人 —— 正常",
    "オリックス": "8/29 用 4 人（1 分差勝）—— 正常",
    "楽天": "8/29 用 4 人（被完封 0-1）—— 正常",
    "西武": "8/29 用 3 人（1-0 完封勝）—— 充分",
    "巨人": "8/29 用 4 人 —— 正常",
    "阪神": "8/29 用 3 人 —— 充分",
    "ヤクルト": "8/29 用 3 人（9-1 大勝）—— 充分",
    "広島": "8/29 用 5 人（被打 9 分）—— 吃緊",
    "中日": "8/29 用 4 人（被完封 0-1）—— 正常",
    "DeNA": "8/29 用 3 人（1-0 完封勝）—— 充分",
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
        # 已開賽的場次，賽前盤口已不可得 —— 硬性門檻，不可能成為推薦。
        prices_verified=JP[game.home_team] not in STARTED,
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
            f"校準已更新到 8/29 收盤（{cal.SAMPLE_GAMES} 場）。"
            f"聯盟每隊每場得分 {cal.LEAGUE_RPG:.4f}、主場係數 {cal.HOME_EDGE:.4f}。",
            "⚠️ **校準資料來源的一個例外**：npb.jp 賽程頁在 8/29 賽後 15 小時"
            "仍未更新比分，照舊只讀該頁的話校準會停在 697 場（8/28）。"
            "8/29 那六場的比分昨天結算時已逐場由 box.html 讀出並與帳本核對，"
            "因此直接回填進 season.json，校準才推進到 703 場。"
            "回填的是已驗證的資料，不是估計值。",
            "**十二名先發全數與 npb.jp 8/30 官方預告先發公示一致。**"
            "8/27 與 8/29 那種「公示頁已翻到隔日、今日取不到」的問題今天不存在。",
            "廣島先發 **森翔平** 正是 2026-08-13 那次同姓誤配的當事人 —— "
            "廣島同時有 森下暢仁、森浦大輔，當時用姓氏比對挑錯了人。"
            "今天用官方全名做精確比對（先試 `==`，失敗才退回子字串），"
            "十二人全部唯一命中。",
            "資料品質乾淨：十二人全是正規輪值先發，局數最少的 小川泰弘 也有 38 局、"
            "每場局數最低的 田中晴也 也有 5.28 局。無開局投手、無季中角色轉換、"
            "無樣本不足。",
            "⚠️ **前兩場已開打**：羅德 @ 火腿 13:00 開賽（已進行約 1 小時）、"
            "軟銀 @ 歐力士 14:00 正在開賽。這兩場的定價僅供事後對帳，"
            "不是可下注的建議。實際可下注的是 17:00 的樂天 @ 西武 與 18:00 的三場。",
            "**得分水位仍不調整。** 8/29 收盤時整體偏誤 +0.27 分（0.7 個標準誤，"
            "76 場）；「已下注 vs 未下注」的差距由前一天的 1.7 個標準誤"
            "回落到 0.9，未下注對照組的「實際 − 盤口」+0.26 仍近乎零。"
            "前天那個看似要成立的選擇偏誤訊號，一天之後就退掉了一半 —— "
            "這正是不該在 1-2 個標準誤就動參數的理由。",
            "露天三場（甲子園、マツダ、横浜）維持 +7% EV 門檻，"
            "但它的依據已連續三天為零（露天與巨蛋的誤差差距在 0 附近）。"
            "這個門檻已經站不太住，應該在資料乾淨且無其他變動的日子處理掉。",
            "讓分與上半場盤全數不定價。讓分的理由是結構性的："
            "模型的 Var(分差) 被共享環境因子壓窄約 2.3 倍，"
            "且數學上與 dispersion_k 無關。見 analysis/diagnose_margin.py。",
            "**無資料先發的鐵律**：8/27 石川雅規（本季零登板、市場開 8.5 當日最高、"
            "實際總分 11）與 8/29 大川慈英（本季 0.2 局、市場開 9+75 當日最高、"
            "實際總分 16）兩次驗證 —— 遇到無資料先發且市場開高盤，一律不碰。"
            "今天十二人都有充分樣本，這道鐵律沒有觸發。",
        ],
        sources=[
            "https://npb.jp/announcement/starter/（2026-08-30 預告先發公示）",
            "https://npb.jp/games/2026/schedule_08_detail.html（賽程；8/29 比分至今未更新）",
            "https://npb.jp/scores/2026/0829/<slug>/box.html（8/29 比分，用於回填校準）",
            "https://npb.jp/bis/2026/stats/idp1_<team>.html（個人投手成績）",
            "賠率：使用者提供之看板截圖（2026-08-30）",
        ],
    )


if __name__ == "__main__":
    print(build_report().render())
