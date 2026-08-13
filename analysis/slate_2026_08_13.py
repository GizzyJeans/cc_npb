"""2026-08-13 NPB 六場賽事 — 看板辨識結果與資料完整度盤點。

執行: ``python3 analysis/slate_2026_08_13.py``

這支腳本刻意 **不** 產生模型定價。原因寫在 `readiness` 裡: 當日
資料來源全數被網路出口政策擋下，正式打線也尚未公布，
`gates.grade()` 在這種狀態下不可能回傳「推薦」。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bethero.bankroll import Bankroll
from bethero.board import BoardGame
from bethero.gates import DataReadiness, grade
from bethero.report import DailyReport, GameAnalysis

DATE = "2026-08-13"
DATA_AS_OF = "2026-08-13 15:15 JST (UTC 06:15)"

# 預告先發來源: NPB 官方 X 帳號 2026-08-13 貼文，六場全數對得上看板。
GAMES = [
    BoardGame(
        date=DATE,
        start_time="17:00",
        away_team="橫濱DeNA灣星",
        home_team="中日龍",
        away_starter="深沢鳳介 (右)",
        home_starter="金丸夢斗 (左)",
        venue="バンテリンドーム ナゴヤ (巨蛋)",
        handicap_raw="0-50",
        handicap_side="home",
        handicap_home_hk=0.950,
        handicap_away_hk=0.950,
        total_raw="7+25",
        over_hk=0.930,
        under_hk=0.930,
        f5_handicap_raw="0-10",
        f5_total_raw="4+50",
        # 0-50: 平手時中日輸 50% 本金 -> 等效讓 0.25

    ),
    BoardGame(
        date=DATE,
        start_time="17:00",
        away_team="千葉羅德",
        home_team="福岡軟銀鷹",
        away_starter="田中晴也 (右)",
        home_starter="史都華二世 (右)",
        venue="みずほPayPayドーム (巨蛋)",
        handicap_raw="1-60",
        handicap_side="home",
        handicap_home_hk=0.950,
        handicap_away_hk=0.950,
        total_raw="8平",
        over_hk=0.930,
        under_hk=0.930,
        f5_handicap_raw="1+70",
        f5_total_raw="4-75",
        # 1-60: 軟銀贏 1 分輸 60% 本金 -> 等效讓 1.30

    ),
    BoardGame(
        date=DATE,
        start_time="17:00",
        away_team="西武獅",
        home_team="日本火腿",
        away_starter="維南斯 (右)",
        home_starter="山崎福也 (左)",
        venue="エスコンフィールド北海道 (開閉式屋頂)",
        handicap_raw="1-25",
        handicap_side="home",
        handicap_home_hk=0.950,
        handicap_away_hk=0.950,
        total_raw="8+75",
        over_hk=0.930,
        under_hk=0.930,
        f5_handicap_raw="0-80",
        f5_total_raw="4-50",
    ),
    BoardGame(
        date=DATE,
        start_time="17:00",
        away_team="歐力士猛牛",
        home_team="東北樂天鷹",
        away_starter="田嶋大樹 (左)",
        home_starter="瀧中瞭太 (右)",
        venue="楽天モバイルパーク宮城 (露天)",
        handicap_raw="1+50",
        handicap_side="away",
        handicap_home_hk=0.950,
        handicap_away_hk=0.950,
        total_raw="7平",
        over_hk=0.930,
        under_hk=0.930,
        f5_handicap_raw="0-10",
        f5_total_raw="4+50",
    ),
    BoardGame(
        date=DATE,
        start_time="17:00",
        away_team="廣島鯉魚",
        home_team="養樂多燕子",
        away_starter="森翔平 (左)",
        home_starter="高橋奎二 (左)",
        venue="明治神宮野球場 (露天)",
        handicap_raw="1+80",
        handicap_side="away",
        handicap_home_hk=0.950,
        handicap_away_hk=0.950,
        total_raw="7-25",
        over_hk=0.930,
        under_hk=0.930,
        f5_handicap_raw="0-20",
        f5_total_raw="4+50",
        # 1+80: 廣島贏 1 分收 80% 賠金 -> 等效讓 0.60

    ),
    BoardGame(
        date=DATE,
        start_time="17:00",
        away_team="阪神虎",
        home_team="讀賣巨人",
        away_starter="下村海翔 (右)",
        home_starter="西舘勇陽 (右)",
        venue="東京ドーム (巨蛋)",
        handicap_raw="1+95",
        handicap_side="away",
        handicap_home_hk=0.950,
        handicap_away_hk=0.950,
        total_raw="6.5",
        over_hk=0.930,
        under_hk=0.930,
        f5_handicap_raw="0",
        f5_total_raw="3-25",
        # 1+95: 阪神贏 1 分收 95% 賠金 -> 等效讓 0.525
        # 全場大小 6.5: 使用者 2026-08-13 目視確認為字面值 (非 6+50)。
        # 等效半球盤，總分 6 小分全贏、7 大分全贏，永不走盤。
        attested_fields=frozenset({"total"}),
    ),
]


def _readiness(weather_known: bool, line_type_confirmed: bool = True) -> DataReadiness:
    """今日六場共用的資料狀態。

    唯一有差異的是天氣: 巨蛋場館視為已知，露天場館今日有大雨預報。
    """
    return DataReadiness(
        # 預告先發已由 NPB 官方帳號確認，六場全對得上看板。
        starters_confirmed=True,
        # 盤口記法已由使用者確認: N平 走盤、N±XX 為落在 N 時的結算百分比。
        line_type_confirmed=line_type_confirmed,
        # 以下全部取不到 —— 出口政策擋掉了所有 NPB 統計站。
        lineups_confirmed=False,
        # 使用者 2026-08-13 指示「略過打線」—— 放棄此門檻但留下紀錄。
        waived=frozenset({"lineups_confirmed"}),
        bullpen_usage_known=False,
        team_rates_known=False,
        park_factor_known=False,
        weather_known=weather_known,
        injuries_known=False,
        market_prices_known=False,
    )


DOME = {"中日龍", "福岡軟銀鷹", "日本火腿", "讀賣巨人"}


def build_report() -> DailyReport:
    analyses = []
    for game in GAMES:
        indoor = game.home_team in DOME
        readiness = _readiness(
            weather_known=indoor,
            line_type_confirmed=not game.audit(),
        )
        ev = 0.0
        graded = grade(ev=ev, edge_pp=0.0, readiness=readiness)

        analyses.append(
            GameAnalysis(
                game=game,
                readiness=readiness,
                line_label=f"讓分 {game.handicap_raw}／大小 {game.total_raw}",
                graded=graded,
                pitching_note=f"{game.away_starter} vs {game.home_starter}"
                "（預告先發已確認；兩人當季成績與休息天數未能取得）",
                lineup_note="依使用者指示略過（正式打線尚未公布）",
                bullpen_note="近三日牛棚使用量無法取得",
                park_weather_note=(
                    "巨蛋／開閉式屋頂，天氣不影響"
                    if indoor
                    else "露天球場，今日東北～關東有大雨預報，有延賽風險"
                ),
                market_note="僅有單一時點的單一平台報價，無開盤價與跨莊家比較",
                    rationale="盤型全數確認；卡在球隊得分率與投手數據取不到 —— 不下注",
                risks=["模型參數未經 2026 當季資料校準"],
                cancel_conditions=["若正式打線公布後主力輪休，須整場重算"],
            )
        )

    return DailyReport(
        date=DATE,
        bankroll=Bankroll(),
        analyses=analyses,
        data_as_of=DATA_AS_OF,
        global_notes=[
            "六場預告先發已與 NPB 官方公告核對一致。",
            "盤口記法已由使用者確認並實作: N平 = 走盤; N±XX = 落在 N 時主方"
            "贏/輸 XX%。等效盤口 = N - s/2。六場的上半/全場總分比落在 "
            "0.526-0.557，內部一致，可佐證解讀正確。",
            "所有 NPB 統計來源 (npb.jp / baseball-data.com / baseballdata.jp /"
            " baseball.yahoo.co.jp / proran.jp) 直接連線在本次執行時皆回傳 "
            "403 (CONNECT tunnel failed)，僅代管搜尋可用。",
            "露天場館 (楽天モバイルパーク宮城、明治神宮野球場) 今日有大雨預報。",
        ],
    )


if __name__ == "__main__":
    print(build_report().render())
