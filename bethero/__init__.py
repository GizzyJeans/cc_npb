"""bethero — NPB 量化投注分析引擎。

模組分工:

* `lines`    — 亞洲盤盤口解析與結算規則
* `board`    — 看板辨識結果的資料結構 (帶信心度)
* `model`    — NPB 專屬得分分布模型
* `ev`       — 去水、期望值、Kelly 注碼
* `gates`    — 推薦門檻 (資料不足時強制降級)
* `bankroll` — 本金與風控
* `report`   — 繁體中文報告輸出
"""

from .bankroll import Bankroll
from .board import BoardGame
from .ev import BetEvaluation, devig_power, devig_proportional, evaluate, overround
from .gates import DataReadiness, Grade, grade
from .lines import Confidence, Line, parse_board_line
from .model import GameModel, NPBEnvironment, TeamInput
from .report import DailyReport, GameAnalysis

__all__ = [
    "Bankroll",
    "BoardGame",
    "BetEvaluation",
    "devig_power",
    "devig_proportional",
    "evaluate",
    "overround",
    "DataReadiness",
    "Grade",
    "grade",
    "Confidence",
    "Line",
    "parse_board_line",
    "GameModel",
    "NPBEnvironment",
    "TeamInput",
    "DailyReport",
    "GameAnalysis",
]
