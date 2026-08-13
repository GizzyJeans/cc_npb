"""損益兩平與「所需勝率」分析。

這是唯一 **不需要外部資料** 就能算的東西: 給定報價與盤口的結算結構，
反推「要下這注，你必須相信的機率是多少」。

對走盤型盤口 (``N平``) 與部分結算盤口 (``N±XX``)，這個門檻和一般
二元賭局不同 —— 走盤與半贏會把門檻拉低，忽略它會系統性低估自己的優勢。
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from .lines import Line


def _edge_payoff(line: Line, side: str, hk: float) -> float:
    """落在關鍵整數時，每 1 單位本金的損益。"""
    s = float(line.edge if side == "primary" else -line.edge)
    return s * hk if s > 0 else s


@dataclass(frozen=True)
class Breakeven:
    """一個投注選項的門檻。"""

    side: str
    offered_hk: float
    p_edge: float
    """落在關鍵整數 (走盤/部分結算) 的機率。"""

    breakeven_prob: float
    """EV = 0 所需的『完全勝出』機率。"""

    target_prob: float
    """達到目標 EV 所需的『完全勝出』機率。"""

    target_ev: float

    def required_edge_over_breakeven(self) -> float:
        return (self.target_prob - self.breakeven_prob) * 100


def required_win_prob(
    line: Line,
    offered_hk: float,
    side: str,
    p_edge: float,
    target_ev: float = 0.0,
) -> float:
    """反推達到 `target_ev` 所需的完全勝出機率。

    設 p_win = P(結果優於關鍵整數)、p_edge = P(結果等於關鍵整數)、
    p_lose = 1 - p_win - p_edge，則::

        EV = p_win * hk + p_edge * e - p_lose

    解出::

        p_win = [target + 1 - p_edge * (1 + e)] / (1 + hk)

    其中 e 是落在關鍵整數時的單位損益。
    """
    if side not in ("primary", "counter"):
        raise ValueError(f"side 必須是 'primary' 或 'counter'，收到 {side!r}")
    e = _edge_payoff(line, side, offered_hk)
    return (target_ev + 1.0 - p_edge * (1.0 + e)) / (1.0 + offered_hk)


def analyse(
    line: Line,
    offered_hk: float,
    side: str,
    p_edge: float,
    target_ev: float = 0.04,
) -> Breakeven:
    return Breakeven(
        side=side,
        offered_hk=offered_hk,
        p_edge=p_edge,
        breakeven_prob=required_win_prob(line, offered_hk, side, p_edge, 0.0),
        target_prob=required_win_prob(line, offered_hk, side, p_edge, target_ev),
        target_ev=target_ev,
    )


def vig_cost(offered_hk: float) -> float:
    """兩邊同價時，單邊要克服的水錢 (超過 50% 的部分，百分點)。"""
    return (1.0 / (1.0 + offered_hk) - 0.5) * 100


__all__ = ["Breakeven", "required_win_prob", "analyse", "vig_cost"]
