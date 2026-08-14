"""2026-08-14 NPB 六場賽事 —— 模型定價與資料完整度盤點。

執行: ``python3 analysis/slate_2026_08_14.py``

沿用 8/13 建立的作法:

* 校準值來自 `config.calibration_2026`（已更新到 8/13 收盤，623 場）。
* **只定價大小分**。讓分盤不定價 —— 全季回測顯示模型分差分布在 ±1 分
  堆積 6-7pp，屬結構性偏誤 (見 `config/npb_priors.py` 的 `KNOWN_BIASES`)。
  今天六場的讓分盤 base 落在 1 或 2 分上，同樣踩在偏誤區。
* 賠率由使用者提供的看板截圖確認。此平台固定賠率 (讓分 0.950／
  大小 0.930)、以 N±XX 結算百分比調價。
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

DATE = "2026-08-14"
DATA_AS_OF = "2026-08-14 16:25 JST (UTC 07:25)"
START_JST = "18:00 JST（看板 17:00 為台北時間）"

# 預告先發: https://npb.jp/announcement/starter/ 2026-08-14 公示，
# 六場十二人全部與看板一致 (全名核對)。
GAMES = [
    BoardGame(
        date=DATE, start_time=START_JST,
        away_team="讀賣巨人", home_team="中日龍",
        away_starter="霍華德 (右)", home_starter="髙橋宏斗 (右)",
        venue="バンテリンドーム ナゴヤ (巨蛋)",
        handicap_raw="1+80", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6-50", over_hk=0.930, under_hk=0.930,
    ),
    BoardGame(
        date=DATE, start_time=START_JST,
        away_team="東北樂天金鷲", home_team="福岡軟銀鷹",
        away_starter="藤井聖 (左)", home_starter="大津亮介 (右)",
        venue="みずほPayPayドーム (巨蛋)",
        handicap_raw="2-25", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="8+50", over_hk=0.930, under_hk=0.930,
    ),
    BoardGame(
        date=DATE, start_time=START_JST,
        away_team="阪神虎", home_team="廣島鯉魚",
        away_starter="才木浩人 (右)", home_starter="森下暢仁 (右)",
        venue="マツダスタジアム (露天)",
        handicap_raw="2+60", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6.5", over_hk=0.930, under_hk=0.930,
        # 看板慣例: N±XX 一律帶正負號，裸小數為字面半球盤。
        # 使用者 2026-08-13 已對同一平台的 6.5 目視確認為字面值，此處沿用。
        attested_fields=frozenset({"total"}),
    ),
    BoardGame(
        date=DATE, start_time=START_JST,
        away_team="日本火腿", home_team="歐力士猛牛",
        away_starter="達孝太 (右)", home_starter="髙島泰都 (右)",
        venue="京セラドーム大阪 (巨蛋)",
        handicap_raw="1-5", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="6.5", over_hk=0.930, under_hk=0.930,
        attested_fields=frozenset({"total"}),
        # 看板其餘欄位的結算比例都是兩位數 (80/50/25/60/10/75)，
        # 只有這一格是個位數。1-5 (輸 5% 本金) 與 1-50 (輸 50%) 的
        # 等效盤口差 0.225 分，不可自行猜測。
        unresolved=[
            "全場讓分「1-5」: 結算比例為個位數，與看板其餘欄位的兩位數"
            "寫法不一致，可能是 1-5 (5%) 或 1-50 (50%) 被截斷，"
            "等效盤口相差 0.225 分 —— 需人工確認"
        ],
    ),
    BoardGame(
        date=DATE, start_time=START_JST,
        away_team="千葉羅德", home_team="西武獅",
        away_starter="小島和哉 (左)", home_starter="髙橋光成 (右)",
        venue="ベルーナドーム (巨蛋)",
        handicap_raw="1+60", handicap_side="home",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="7+50", over_hk=0.930, under_hk=0.930,
    ),
    BoardGame(
        date=DATE, start_time=START_JST,
        away_team="橫濱DeNA灣星", home_team="養樂多燕子",
        away_starter="平良拳太郎 (右)", home_starter="奧川恭伸 (右)",
        venue="明治神宮野球場 (露天)",
        handicap_raw="1+10", handicap_side="away",
        handicap_home_hk=0.950, handicap_away_hk=0.950,
        total_raw="8+75", over_hk=0.930, under_hk=0.930,
    ),
]

JP = {
    "中日龍": "中日", "讀賣巨人": "巨人", "福岡軟銀鷹": "ソフトバンク",
    "東北樂天金鷲": "楽天", "廣島鯉魚": "広島", "阪神虎": "阪神",
    "歐力士猛牛": "オリックス", "日本火腿": "日本ハム",
    "西武獅": "西武", "千葉羅德": "ロッテ",
    "養樂多燕子": "ヤクルト", "橫濱DeNA灣星": "DeNA",
}
PARK_KEY = {
    "バンテリンドーム ナゴヤ (巨蛋)": "バンテリンドーム",
    "みずほPayPayドーム (巨蛋)": "みずほPayPay",
    "マツダスタジアム (露天)": "マツダスタジアム",
    "京セラドーム大阪 (巨蛋)": "京セラD大阪",
    "ベルーナドーム (巨蛋)": "ベルーナドーム",
    "明治神宮野球場 (露天)": "神宮",
}

# 今日先發: npb.jp idp1_<team>.html，2026-08-14 擷取。
# factor = 球場調整 + 向聯盟平均收縮 60 局後的失分率 / 聯盟平均。
STARTERS = {
    "中日": ("髙橋宏斗", 1.1674, 6.14, "12 場 73.2 局 防禦率 3.91"),
    "巨人": ("ハワード", 0.8930, 5.83, "4 場 23.1 局 防禦率 1.93（僅 4 場，樣本極小）"),
    "ソフトバンク": ("大津亮介", 0.8392, 6.58, "16 場 105.1 局 防禦率 2.56"),
    "楽天": ("藤井聖", 1.0004, 4.88, "8 場 39 局 防禦率 3.69（樣本小）"),
    "広島": ("森下暢仁", 1.1986, 5.64, "15 場 84.2 局 防禦率 4.36"),
    "阪神": ("才木浩人", 0.9246, 6.32, "19 場 120 局 防禦率 2.63、147 三振"),
    "オリックス": ("髙島泰都", 1.1724, 4.12, "16 場 66 局 防禦率 3.95（每場僅 4.1 局）"),
    "日本ハム": ("達孝太", 0.9276, 3.94, "21 場 82.2 局 防禦率 3.16（每場 3.9 局，非典型先發負荷）"),
    "西武": ("髙橋光成", 0.8646, 6.69, "17 場 113.2 局 防禦率 2.45"),
    "ロッテ": ("小島和哉", 0.9896, 5.69, "13 場 74 局 防禦率 3.41"),
    "ヤクルト": ("奧川恭伸", 0.8771, 6.77, "16 場 108.1 局 防禦率 2.99"),
    "DeNA": ("平良拳太郎", 0.9924, 4.91, "15 場 73.2 局 防禦率 3.42"),
}

# 牛棚近三日 (8/11-8/13)，取自各場 box.html 的投球數。
BULLPEN_NOTE = {
    "中日": "8/12 用 4 人、8/13 用 4 人（金丸 97 球）；草加連兩日登板",
    "巨人": "8/12 用 4 人、8/13 用 4 人",
    "ソフトバンク": "8/12 用 5 人、8/13 用 4 人；鈴木豪連兩日登板",
    "楽天": "8/12 用 3 人、8/13 用 5 人（瀧中 78 球、津留﨑 25 球）",
    "広島": "8/13 因雨中止未登板，8/12 僅用 3 人 —— **牛棚全休**",
    "阪神": "8/12 用 2 人、8/13 用 4 人（下村 94 球）；木下、工藤連兩日登板",
    "オリックス": "8/12 用 4 人、8/13 用 6 人（田嶋 82 球、片山 29 球）；富山連兩日登板，負荷最重",
    "日本ハム": "8/12 用 6 人、8/13 用 5 人；生田目連兩日登板",
    "西武": "8/12 用 3 人、8/13 用 5 人（ワイナンス 84 球）",
    "ロッテ": "8/12 用 5 人、8/13 用 4 人（田中 92 球）",
    "ヤクルト": "8/13 因雨中止未登板，8/12 用 4 人 —— **牛棚全休**",
    "DeNA": "8/12 用 3 人、8/13 用 4 人（深沢 94 球）",
}

OPEN_AIR = {"マツダスタジアム", "神宮"}
WEATHER = {
    "マツダスタジアム": "露天。廣島 8/14 雲多、有陣雨與雷擊／陣風注意 —— 延賽風險中等",
    "神宮": "露天。東京 8/14 降水機率 60%，最高 29°C —— 延賽風險中等"
            "（8/13 神宮同一組合已因雨中止一次）",
}

ENV = NPBEnvironment(
    league_rpg=cal.LEAGUE_RPG,
    dispersion_k=cal.DISPERSION_K,
    home_edge=cal.HOME_EDGE,
    extras_resolve_rate=cal.EXTRAS_RESOLVE_RATE,
    source="npb.jp 2026 逐場比分 623 場",
    as_of=cal.AS_OF,
)


def build_model(game: BoardGame) -> GameModel:
    home, away = JP[game.home_team], JP[game.away_team]

    def side(team: str) -> TeamInput:
        _, factor, ip_gs, _ = STARTERS[team]
        return TeamInput(
            name=team,
            off_factor=cal.TEAM_OFFENCE[team],
            def_factor=cal.blended_defence(factor, ip_gs, cal.BULLPEN_FACTOR[team]),
            starter_ip=ip_gs,
        )

    return GameModel(home=side(home), away=side(away), env=ENV,
                     park_factor=cal.PARK_FACTORS_2026[PARK_KEY[game.venue]])


def readiness_for(game: BoardGame) -> DataReadiness:
    park = PARK_KEY[game.venue]
    # audit() 只在該場的盤口有疑慮時才擋; 「1-5」那場的疑慮在讓分欄，
    # 而讓分盤本來就不定價 —— 但盤型未確認是硬性條件，仍照實記錄。
    return DataReadiness(
        line_type_confirmed=not game.audit(),
        starters_confirmed=True,
        lineups_confirmed=False,
        waived=frozenset({"lineups_confirmed"}),
        prices_verified=True,
        bullpen_usage_known=True,
        team_rates_known=True,
        park_factor_known=True,
        weather_known=park not in OPEN_AIR,
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
                f"{game.away_starter} {sp_a[3]}／{game.home_starter} {sp_h[3]}。"
                f"當日守備係數 主 {model.home.def_factor:.3f}、客 {model.away.def_factor:.3f}"
            ),
            lineup_note="16:25 JST 尚未公布，依使用者指示略過",
            bullpen_note=f"{game.home_team}：{BULLPEN_NOTE[home]}；"
                         f"{game.away_team}：{BULLPEN_NOTE[away]}",
            park_weather_note=(
                f"球場係數 {cal.PARK_FACTORS_2026[park]:.3f}（2026 實測）。"
                + WEATHER.get(park, "巨蛋，天氣不影響")
            ),
            market_note="賠率已由使用者看板截圖確認（固定賠率、以 N±XX 調價）；"
                        "無開盤價與跨莊家比對",
            rationale=(
                f"模型預期總分 {dists.expected_total():.2f}"
                f"（{home} {dists.lam_home:.2f} - {away} {dists.lam_away:.2f}）；"
                f"{label} 模型機率 {best.model_prob:.1%}、EV {best.ev:+.1%}"
            ),
            risks=[
                "讓分盤：模型 P(分差=±1) 高估 6-7pp，今日六場 base 落在 1-2 分，不定價",
                "全季回測為樣本內，技巧屬上界",
            ] + ([f"{sp_a[0]}／{sp_h[0]} 有小樣本先發，收縮假設影響大"]
                 if "樣本" in sp_a[3] or "樣本" in sp_h[3] else []),
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
            "校準值已更新到 8/13 收盤（623 場）。聯盟每隊每場得分 3.6035、"
            "主場乘數 1.0248；加入 8/13 後和局率 1.77%、一分差 29.21%，"
            "與前一版幾乎不動，因此 dispersion_k / extras_resolve 沿用。",
            "六場預告先發已對照 npb.jp 公示全名核對一致，球場與 18:00 JST "
            "開賽時間相符（看板 17:00 為台北時間）。",
            "**讓分盤全部不定價**：模型 P(分差=+1) 高估 5.96pp、P(分差=-1) "
            "高估 7.31pp，今日六場讓分 base 落在 1 或 2 分，正踩在偏誤區。",
            "**歐力士 vs 日本火腿的讓分「1-5」無法確認**：看板其餘結算比例"
            "都是兩位數，只有這格是個位數。1-5 與 1-50 的等效盤口差 0.225 分，"
            "依規範標為待確認、不猜測（此場讓分本來也不定價）。",
            "養樂多與廣島 8/13 因雨中止，兩隊牛棚今日全休 —— "
            "這對兩場的後段失分有實質影響，但模型的牛棚係數是全季平均，"
            "沒有把「今日特別充足」這件事計入。",
            "露天兩場（マツダ、神宮）天氣只有日級預報，逐時風向與溫度來源"
            "仍被出口政策擋下。",
        ],
        sources=[
            "https://npb.jp/announcement/starter/（2026-08-14 預告先發公示）",
            "https://npb.jp/games/2026/schedule_08_detail.html（賽程與 8/13 比分）",
            "https://npb.jp/bis/2026/stats/idp1_<team>.html（個人投手成績，12 隊）",
            "https://npb.jp/scores/2026/{0811,0812,0813}/<slug>/box.html（牛棚用球數）",
            "賠率：使用者提供之看板截圖（2026-08-14）",
            "天氣：代管搜尋摘要（廣島／東京 8/14），主來源被出口政策擋下",
        ],
    )


if __name__ == "__main__":
    print(build_report().render())
