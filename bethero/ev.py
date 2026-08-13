"""賠率轉換、去水 (de-vig)、期望值與 Kelly 注碼。

看板上的 ``0.950`` / ``0.930`` 是 **香港盤賠率**: 押 1 單位贏 0.95 單位。
歐洲盤 (decimal) = 香港盤 + 1。
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Mapping, Sequence


def hk_to_decimal(hk: float) -> float:
    return hk + 1.0


def decimal_to_hk(dec: float) -> float:
    return dec - 1.0


def implied_prob(hk: float) -> float:
    """含水機率。"""
    return 1.0 / hk_to_decimal(hk)


def overround(hk_prices: Sequence[float]) -> float:
    """兩邊 (或多邊) 含水機率總和。1.00 = 無水。"""
    return sum(implied_prob(p) for p in hk_prices)


def devig_proportional(hk_prices: Sequence[float]) -> list[float]:
    """比例去水: 直接把含水機率等比例縮回 1。"""
    raw = [implied_prob(p) for p in hk_prices]
    total = sum(raw)
    return [r / total for r in raw]


def devig_power(hk_prices: Sequence[float], tol: float = 1e-12) -> list[float]:
    """次方去水: 找 n 使 sum(p_i ** n) == 1。

    對兩邊價格不對稱的盤 (例如強弱懸殊的獨贏) 比比例去水更貼近真實，
    因為它不會把水錢平均攤在冷熱門身上。
    """
    raw = [implied_prob(p) for p in hk_prices]
    lo, hi = 0.5, 3.0
    for _ in range(200):
        n = (lo + hi) / 2
        s = sum(r**n for r in raw)
        if abs(s - 1.0) < tol:
            break
        if s > 1.0:
            lo = n
        else:
            hi = n
    n = (lo + hi) / 2
    out = [r**n for r in raw]
    total = sum(out)
    return [o / total for o in out]


@dataclass(frozen=True)
class BetEvaluation:
    """單一投注選項的完整評估。"""

    model_prob: float
    """模型有效過盤率 (已排除走盤)。"""

    market_prob: float
    """市場去水後機率。"""

    fair_hk: float
    """模型公平香港盤賠率。"""

    offered_hk: float
    ev: float
    """每 1 單位注碼的期望值 (小數，0.04 = +4%)。"""

    edge_pp: float
    """模型機率 - 市場機率，以百分點計。"""

    min_hk: float
    """EV 歸零的最低可接受賠率。"""

    kelly_fraction: float
    """全 Kelly 建議下注比例。"""

    stake: float
    """套用 0.25 Kelly、上限與本金限制後的建議注碼。"""

    push_prob: float


def evaluate(
    outcome_probs: Mapping[Fraction, float],
    offered_hk: float,
    bankroll: float,
    market_prob: float,
    kelly_multiplier: float = 0.25,
    max_stake: float = 1000.0,
) -> BetEvaluation:
    """評估一個投注選項。

    `outcome_probs` 是 {結算比例: 機率}，比例取值於
    {-1, -0.5, 0, +0.5, +1}，由 `lines` 模組產生。
    """
    push = sum(p for r, p in outcome_probs.items() if r == 0)
    win = sum(p * float(r) for r, p in outcome_probs.items() if r > 0)
    live = 1.0 - push
    model_prob = win / live if live > 1e-12 else 0.0

    ev = _ev(outcome_probs, offered_hk)
    fair_hk = (1.0 - model_prob) / model_prob if model_prob > 1e-9 else float("inf")
    min_hk = fair_hk

    kelly = _kelly(outcome_probs, offered_hk)
    stake = min(bankroll * kelly * kelly_multiplier, max_stake)
    stake = max(stake, 0.0)

    return BetEvaluation(
        model_prob=model_prob,
        market_prob=market_prob,
        fair_hk=fair_hk,
        offered_hk=offered_hk,
        ev=ev,
        edge_pp=(model_prob - market_prob) * 100.0,
        min_hk=min_hk,
        kelly_fraction=kelly,
        stake=stake,
        push_prob=push,
    )


def _ev(outcome_probs: Mapping[Fraction, float], hk: float) -> float:
    """每 1 單位注碼的期望損益。走盤退回 = 0。"""
    total = 0.0
    for result, prob in outcome_probs.items():
        r = float(result)
        total += prob * (r * hk if r > 0 else r)
    return total


def _kelly(outcome_probs: Mapping[Fraction, float], hk: float) -> float:
    """一般化 Kelly: 數值最大化 E[log(1 + f * R)]。

    半贏 / 半輸的走盤盤口不是二元賭局，用課本的 (bp-q)/b 會高估注碼，
    所以這裡直接對 log 財富做黃金分割搜尋。
    """
    returns = []
    for result, prob in outcome_probs.items():
        r = float(result)
        returns.append((r * hk if r > 0 else r, prob))

    if _ev(outcome_probs, hk) <= 0:
        return 0.0

    worst = min(r for r, _ in returns)
    hi = 0.999 if worst >= -1e-12 else min(0.999, -0.999 / worst)
    lo = 0.0

    def growth(f: float) -> float:
        total = 0.0
        for r, p in returns:
            arg = 1.0 + f * r
            if arg <= 1e-12:
                return -1e18
            total += p * __import__("math").log(arg)
        return total

    phi = (5**0.5 - 1) / 2
    a, b = lo, hi
    c, d = b - phi * (b - a), a + phi * (b - a)
    for _ in range(200):
        if growth(c) > growth(d):
            b = d
        else:
            a = c
        c, d = b - phi * (b - a), a + phi * (b - a)
    return max(0.0, (a + b) / 2)


__all__ = [
    "hk_to_decimal",
    "decimal_to_hk",
    "implied_prob",
    "overround",
    "devig_proportional",
    "devig_power",
    "BetEvaluation",
    "evaluate",
]
