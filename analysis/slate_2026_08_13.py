"""2026-08-13 NPB 六場賽事 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_08_13.py``

與前一版的差別
--------------
前一版完全不做定價，因為當時所有 NPB 資料來源都被出口政策擋下。
這一次 npb.jp 連得上，所以:

* 球隊強弱、球場係數、先發投手與牛棚全部改用 2026 當季實際資料
  (`config.calibration_2026`，618 場)。
* **大小分** 有定價 —— 全季回測顯示總分的累積分布在每個關鍵整數
  誤差 < 1pp。
* **讓分盤沒有定價** —— 同一份回測顯示分差分布在 ±1 分堆積了 6-7pp，
  而看板六場的讓分盤全部結算在 0 或 1 分上。定價誤差比要求的優勢
  門檻還大，算了也只是雜訊。

賠率仍然無法覆核 (單一時點的單一平台截圖、六場數值完全一致)，
因此 `prices_verified=False`，所有選項最多只能到「觀察」。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bethero.bankroll import Bankroll
from bethero.board import BoardGame
from bethero.ev import devig_proportional, evaluate
from bethero.gates import DataReadiness, grade
from bethero.lines import total_outcome_probs
from bethero.model import GameModel, NPBEnvironment, TeamInput
from bethero.report import DailyReport, GameAnalysis
from config import calibration_2026 as cal

DATE = "2026-08-13"
DATA_AS_OF = "2026-08-13 16:20 JST (UTC 07:20)"

# 比賽時間: npb.jp 官方為 18:00 JST。看板寫 17:00，與台北時間 (UTC+8) 相符，
# 兩者相差正好一小時，因此判定看板用的是台北時間而非誤植。
START_JST = "18:00 JST（看板 17:00 為台北時間）"

# 預告先發: https://npb.jp/announcement/starter/ 2026-08-13 公示，
# 六場十二人全部與看板一致 (全名核對，非只比對姓氏)。
GAMES = [
    BoardGame(
        date=DATE, start_time=START_JST,
        away_team="橫濱DeNA灣星", home_team="中日龍",
        away_starter="深沢鳳介 (右)", home_starter="金丸夢斗 (左)",
        venue="バンテリンドーム ナゴヤ (巨蛋)",
        handicap_raw="0-50", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7+25", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-10", f5_total_raw="4+50",
    ),
    BoardGame(
        date=DATE, start_time=START_JST,
        away_team="千葉羅德", home_team="福岡軟銀鷹",
        away_starter="田中晴也 (右)", home_starter="史都華二世 (右)",
        venue="みずほPayPayドーム (巨蛋)",
        handicap_raw="1-60", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="8平", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="1+70", f5_total_raw="4-75",
    ),
    BoardGame(
        date=DATE, start_time=START_JST,
        away_team="西武獅", home_team="日本火腿",
        away_starter="維南斯 (右)", home_starter="山崎福也 (左)",
        venue="エスコンフィールド北海道 (開閉式屋頂)",
        handicap_raw="1-25", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="8+75", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-80", f5_total_raw="4-50",
    ),
    BoardGame(
        date=DATE, start_time=START_JST,
        away_team="歐力士猛牛", home_team="東北樂天金鷲",
        away_starter="田嶋大樹 (左)", home_starter="瀧中瞭太 (右)",
        venue="楽天モバイルパーク宮城 (露天)",
        handicap_raw="1+50", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7平", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-10", f5_total_raw="4+50",
    ),
    BoardGame(
        date=DATE, start_time=START_JST,
        away_team="廣島鯉魚", home_team="養樂多燕子",
        away_starter="森翔平 (左)", home_starter="高橋奎二 (左)",
        venue="明治神宮野球場 (露天)",
        handicap_raw="1+80", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7-25", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0-20", f5_total_raw="4+50",
    ),
    BoardGame(
        date=DATE, start_time=START_JST,
        away_team="阪神虎", home_team="讀賣巨人",
        away_starter="下村海翔 (右)", home_starter="西舘勇陽 (右)",
        venue="東京ドーム (巨蛋)",
        handicap_raw="1+95", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6.5", over_hk=0.930, under_hk=0.930,
        f5_handicap_raw="0", f5_total_raw="3-25",
        # 6.5: 使用者 2026-08-13 目視確認為字面值 (非 6+50)。
        attested_fields=frozenset({"total"}),
    ),
]

# 看板隊名 -> npb.jp 隊名 / 球場鍵
JP = {
    "中日龍": "中日", "橫濱DeNA灣星": "DeNA", "福岡軟銀鷹": "ソフトバンク",
    "千葉羅德": "ロッテ", "日本火腿": "日本ハム", "西武獅": "西武",
    "東北樂天金鷲": "楽天", "歐力士猛牛": "オリックス",
    "養樂多燕子": "ヤクルト", "廣島鯉魚": "広島",
    "讀賣巨人": "巨人", "阪神虎": "阪神",
}
PARK_KEY = {
    "バンテリンドーム ナゴヤ (巨蛋)": "バンテリンドーム",
    "みずほPayPayドーム (巨蛋)": "みずほPayPay",
    "エスコンフィールド北海道 (開閉式屋頂)": "エスコンＦ",
    "楽天モバイルパーク宮城 (露天)": "楽天モバイル",
    "明治神宮野球場 (露天)": "神宮",
    "東京ドーム (巨蛋)": "東京ドーム",
}

# 今日先發，取自 npb.jp idp1_<team>.html。factor 為球場調整 + 向聯盟平均
# 收縮 60 局後的失分率 / 聯盟平均; ip_gs 為每場先發平均局數。
STARTERS = {
    "中日": ("金丸夢斗", 0.8742, 6.41, "18 場 115.1 局 防禦率 2.50"),
    "DeNA": ("深沢鳳介", 1.0373, 5.39, "6 場 32.1 局 防禦率 2.78（失分率 4.18 高於防禦率）"),
    "ソフトバンク": ("スチュワート・ジュニア", 1.2352, 4.79, "13 場 62.1 局 防禦率 5.05"),
    "ロッテ": ("田中晴也", 1.1600, 5.03, "10 場 50.1 局 防禦率 4.83"),
    "日本ハム": ("山﨑福也", 0.8567, 2.75, "12 場 33 局 防禦率 2.45（每場僅 2.75 局，非典型先發負荷）"),
    "西武": ("ワイナンス", 1.0905, 5.52, "7 場 38.2 局 防禦率 4.19"),
    "楽天": ("瀧中瞭太", 0.8382, 5.62, "14 場 78.2 局 防禦率 2.63"),
    "オリックス": ("田嶋大樹", 1.4988, 4.25, "12 場 51 局 防禦率 6.88"),
    "ヤクルト": ("高橋奎二", 1.1099, 5.48, "11 場 60.1 局 防禦率 4.92"),
    "広島": ("森翔平", 0.9558, 5.73, "10 場 57.1 局 防禦率 2.98"),
    "巨人": ("西舘勇陽", 0.8674, 5.22, "6 場 31.1 局 防禦率 2.30"),
    "阪神": ("下村海翔", 1.0483, 5.50, "4 場 22 局 防禦率 2.05（樣本僅 22 局）"),
}

# 牛棚近三日 (8/11、8/12; 8/10 全聯盟休兵)，取自各場 box.html 的投球數。
BULLPEN_NOTE = {
    "中日": "8/11 用 4 人、8/12 用 4 人（涌井 91 球先發）；無連兩日登板",
    "DeNA": "8/11 用 5 人、8/12 用 3 人（東 99 球先發）；無連兩日登板",
    "ソフトバンク": "8/11 用 4 人、8/12 用 5 人；木村光連兩日登板",
    "ロッテ": "8/11 用 3 人、8/12 用 5 人（ロング 68 球、高野脩 49 球、髙橋 40 球）",
    "日本ハム": "8/11 用 3 人、8/12 用 6 人；島本連兩日登板，牛棚負荷最重",
    "西武": "8/11 用 3 人、8/12 用 3 人；ウィンゲンター、甲斐野連兩日登板",
    "楽天": "8/11 用 4 人、8/12 用 3 人（前田健 103 球先發）",
    "オリックス": "8/11 用 3 人、8/12 用 4 人",
    "ヤクルト": "8/11 因雨中止未用人、8/12 用 4 人；牛棚相對充足",
    "広島": "8/11 因雨中止未用人、8/12 用 3 人；牛棚相對充足",
    "巨人": "8/11 用 2 人、8/12 用 4 人（井上 107 球先發）",
    "阪神": "8/11 用 2 人、8/12 用 4 人；及川連兩日登板",
}

OPEN_AIR = {"楽天モバイル", "神宮"}
WEATHER = {
    "楽天モバイル": "露天。仙台 8/13 降水機率 80%、局部雷雨，最高 27°C —— 延賽風險高",
    "神宮": "露天。東京 8/13 降水機率 60%、有雷雨注意報 —— 延賽風險中等",
}

ENV = NPBEnvironment(
    league_rpg=cal.LEAGUE_RPG,
    dispersion_k=cal.DISPERSION_K,
    home_edge=cal.HOME_EDGE,
    extras_resolve_rate=cal.EXTRAS_RESOLVE_RATE,
    source="npb.jp 2026 逐場比分 618 場",
    as_of=cal.AS_OF,
)


def build_model(game: BoardGame) -> GameModel:
    home, away = JP[game.home_team], JP[game.away_team]
    park = PARK_KEY[game.venue]

    def side(team: str) -> TeamInput:
        _, factor, ip_gs, _ = STARTERS[team]
        return TeamInput(
            name=team,
            off_factor=cal.TEAM_OFFENCE[team],
            def_factor=cal.blended_defence(factor, ip_gs, cal.BULLPEN_FACTOR[team]),
            starter_ip=ip_gs,
        )

    return GameModel(home=side(home), away=side(away), env=ENV,
                     park_factor=cal.PARK_FACTORS_2026[park])


def readiness_for(game: BoardGame) -> DataReadiness:
    park = PARK_KEY[game.venue]
    return DataReadiness(
        # 盤型與結算規則已由使用者確認並實作。
        line_type_confirmed=not game.audit(),
        # 預告先發已對照 npb.jp 公示，全名核對一致。
        starters_confirmed=True,
        # 正式打線 16:20 JST 仍未公布 (18:00 開賽)；使用者先前指示略過。
        lineups_confirmed=False,
        waived=frozenset({"lineups_confirmed"}),
        # 賠率無法覆核: 單一時點的單一平台截圖，且六場的讓分 0.950 與
        # 大小 0.930 完全一致，不像實際會隨盤move的報價。
        prices_verified=False,
        # 以下這次真的取得了。
        bullpen_usage_known=True,
        team_rates_known=True,
        park_factor_known=True,
        # 天氣: 巨蛋/開閉式屋頂視為已知; 兩座露天球場只查到「日級」降水機率
        # (代管搜尋)，逐時風向與溫度的來源被出口政策擋下 -> 不算已知。
        weather_known=park not in OPEN_AIR,
        # 出場選手登錄/抹消與傷病名單這次沒有取得。
        injuries_known=False,
        market_prices_known=False,
    )


def build_report() -> DailyReport:
    analyses = []
    for game in GAMES:
        home, away = JP[game.home_team], JP[game.away_team]
        park = PARK_KEY[game.venue]
        model = build_model(game)
        dists = model.distributions()
        readiness = readiness_for(game)

        # --- 大小分定價 (讓分盤刻意不定價，理由見模組 docstring) ---
        market = devig_proportional([game.over_hk, game.under_hk])
        over = evaluate(total_outcome_probs(game.total, dists.total_pmf, "over"),
                        game.over_hk, Bankroll().total, market[0])
        under = evaluate(total_outcome_probs(game.total, dists.total_pmf, "under"),
                         game.under_hk, Bankroll().total, market[1])
        best, label = (over, "大分") if over.ev >= under.ev else (under, "小分")
        graded = grade(ev=best.ev, edge_pp=best.edge_pp, readiness=readiness)

        sp_h, sp_a = STARTERS[home], STARTERS[away]
        analyses.append(GameAnalysis(
            game=game,
            readiness=readiness,
            selection=f"{label} {game.total_raw}",
            line_label=f"讓分 {game.handicap_raw}／大小 {game.total_raw}",
            evaluation=best,
            graded=graded,
            dists=dists,
            pitching_note=(
                f"{game.away_starter} {sp_a[3]}／"
                f"{game.home_starter} {sp_h[3]}。"
                f"當日守備係數 主 {model.home.def_factor:.3f}、客 {model.away.def_factor:.3f}"
            ),
            lineup_note="16:20 JST 尚未公布，依使用者指示略過",
            bullpen_note=f"{game.home_team}：{BULLPEN_NOTE[home]}；"
                         f"{game.away_team}：{BULLPEN_NOTE[away]}",
            park_weather_note=(
                f"球場係數 {cal.PARK_FACTORS_2026[park]:.3f}（2026 實測）。"
                + WEATHER.get(park, "巨蛋／開閉式屋頂，天氣不影響")
            ),
            market_note="單一時點單一平台截圖；六場讓分皆 0.950、大小皆 0.930，"
                        "無開盤價與跨莊家比對，無法覆核",
            rationale=(
                f"模型預期總分 {dists.expected_total():.2f}"
                f"（{home} {dists.lam_home:.2f} - {away} {dists.lam_away:.2f}）；"
                f"{label} 模型機率 {best.model_prob:.1%}、EV {best.ev:+.1%}。"
                + ("賠率無法覆核，只能觀察" if best.ev >= 0.04
                   else "數值面未達門檻")
            ),
            risks=[
                "讓分盤：模型分差分布在 ±1 分高估 6-7pp，六場讓分全部結算在 0/1 分上，不定價",
                "球場係數收縮方式改變會讓部分場次的 EV 跨過 4% 門檻，邊際優勢在模型雜訊內",
                "全季回測為樣本內，技巧屬上界",
            ] + ([f"{sp_a[0]} 僅 {sp_a[3]}"] if "樣本" in sp_a[3] else []),
            cancel_conditions=[
                "正式打線公布後若主力輪休須重算",
                "先發臨時更換即作廢",
            ] + (["露天球場，達延賽標準即取消"] if park in OPEN_AIR else []),
        ))

    return DailyReport(
        date=DATE,
        bankroll=Bankroll(),
        analyses=analyses,
        data_as_of=DATA_AS_OF,
        global_notes=[
            "本次執行 npb.jp 可連線，聯盟／球場／球隊／投手／牛棚全部改用 "
            "2026 當季實際資料 (618 場，2026-03-27~08-12)。逐場比分加總出的"
            "各隊得分與官方 tmb_c/tmb_p 的「得点」欄 12/12 完全相符。",
            "六場預告先發已對照 npb.jp 公示逐一全名核對（廣島先發為森翔平，"
            "非同姓的森下暢仁或森浦大輔）。",
            "開賽時間為 18:00 JST；看板的 17:00 是台北時間，兩者一致。",
            "**讓分盤全部不定價**：618 場回測顯示模型 P(分差=+1) 高估 5.96pp、"
            "P(分差=-1) 高估 7.31pp，而六場讓分盤全部結算在 0 或 1 分上。"
            "掃描 k×extras_resolve 共 24 組都無法把一分差比例從 ~42% 壓到實測的 29.1%，"
            "屬結構性偏誤。",
            "**大小分可定價**：同一份回測中總分累積分布在每個關鍵整數誤差 < 1pp"
            "（P(>7) 模型 40.36% vs 實際 40.45%）。",
            "**賠率無法覆核**：六場讓分皆 0.950、大小皆 0.930，數值完全一致，"
            "且無開盤價與跨莊家比對。EV 是賠率的函數，賠率不可信則 EV 不可用，"
            "因此本日所有選項最多只到「觀察」。",
            "天氣來源 (api.open-meteo.com、weather.yahoo.co.jp) 仍被出口政策擋下，"
            "露天兩場只有日級降水機率（仙台 80%、東京 60%），無逐時風向與溫度。",
        ],
        sources=[
            "https://npb.jp/games/2026/schedule_08_detail.html（賽程與逐場比分）",
            "https://npb.jp/announcement/starter/（預告先發公示）",
            "https://npb.jp/bis/2026/stats/tmb_c.html、tmb_p.html、tmp_c.html、tmp_p.html（球隊成績）",
            "https://npb.jp/bis/2026/stats/idp1_<team>.html（個人投手成績，12 隊）",
            "https://npb.jp/scores/2026/{0811,0812}/<slug>/box.html（牛棚用球數）",
            "天氣：代管搜尋摘要（仙台／東京 8/13 降水機率），主來源被出口政策擋下",
        ],
    )


if __name__ == "__main__":
    print(build_report().render())
