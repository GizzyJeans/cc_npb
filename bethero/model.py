"""NPB 專屬得分分布模型。

刻意 **不** 沿用 MLB 參數。NPB 的得分環境明顯較低、先發投球局數較長、
有和局規則 (延長至 12 局)，這些都直接寫進模型裡。

模型結構
--------
每隊的期望得分:

    lam = league_rpg * off * opp_def * park * home_edge

得分分布用 **共享環境因子的 Poisson 混合**:

    G ~ Gamma(k, 1/k)              # 全場共用的「今天好不好打」
    R_home ~ Poisson(lam_home * G)
    R_away ~ Poisson(lam_away * G)

積分掉 G 之後，每隊的邊際分布是負二項 (捕捉棒球得分的過度離散)，
而且兩隊得分帶正相關 — 這正是球場、天氣、主審好球帶造成的效果，
用獨立 Poisson 會系統性低估大小分的尾端。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping

MAX_RUNS = 24
"""單隊得分的截斷上限，超過的機率併入最後一格。"""


@dataclass(frozen=True)
class NPBEnvironment:
    """NPB 聯盟層級的得分環境參數。

    每個欄位都要能追溯來源；`source` / `as_of` 不是裝飾用的，
    校準腳本會檢查它們。
    """

    league_rpg: float
    """單隊每場平均得分 (非兩隊合計)。"""

    dispersion_k: float = 9.0
    """Gamma 環境因子的形狀參數。k 越小，兩隊得分相關性與尾端越厚。"""

    home_edge: float = 1.030
    """主場優勢，以得分比呈現。對稱套用 (主隊進攻 ×h、客隊進攻 ÷h)，
    因此實際得分比為 h**2；h=1.03 對應約 .527 的主場勝率 (排除和局)。"""

    extras_resolve_rate: float = 0.62
    """九局打平後，在延長 10-12 局分出勝負的比例 (其餘為和局)。"""

    extras_runs_when_played: float = 0.95
    """進入延長時，兩隊合計多出的期望得分。"""

    source: str = ""
    as_of: str = ""


@dataclass(frozen=True)
class TeamInput:
    """單隊的模型輸入。"""

    name: str
    off_factor: float
    """相對聯盟平均的進攻乘數 (1.00 = 聯盟平均)。"""

    def_factor: float
    """今日先發 + 預期牛棚的整體失分壓制乘數 (< 1.00 = 比平均強)。"""

    starter_ip: float = 5.6
    """先發預期投球局數。NPB 先發普遍比 MLB 長。"""


@dataclass
class GameModel:
    """一場比賽的得分分布。"""

    home: TeamInput
    away: TeamInput
    env: NPBEnvironment
    park_factor: float = 1.00
    """球場得分因子 (1.00 = 中性)。"""

    weather_factor: float = 1.00
    """天氣/風向對得分的乘數修正。"""

    lam_home: float = field(init=False)
    lam_away: float = field(init=False)

    def __post_init__(self) -> None:
        base = self.env.league_rpg * self.park_factor * self.weather_factor
        edge = self.env.home_edge
        self.lam_home = base * self.home.off_factor * self.away.def_factor * edge
        self.lam_away = base * self.away.off_factor * self.home.def_factor / edge

    # -- 分布 ---------------------------------------------------------------

    def _gamma_nodes(self, nodes: int = 48) -> list[tuple[float, float]]:
        """把 Gamma(k, 1/k) 環境因子離散化成 (值, 權重)。

        用等機率分位數取樣; 均值為 1，變異數為 1/k。
        """
        k = self.env.dispersion_k
        out: list[tuple[float, float]] = []
        weight = 1.0 / nodes
        for i in range(nodes):
            q = (i + 0.5) / nodes
            out.append((_gamma_ppf(q, k) / k, weight))
        return out

    def score_grid(self) -> list[list[float]]:
        """回傳 9 局結束時 (客隊得分, 主隊得分) 的聯合機率表。

        主隊九局下領先就不用打 — 這會壓低主隊的實際得分，卻 **不該**
        壓低主隊的勝率。因此這裡把主隊拆成「前八局」與「九局下」兩段，
        只有在九上結束後主隊沒有領先時才把九局下的得分加進去。
        用單一 lambda 打折的做法會把主場優勢一起吃掉，是錯的。
        """
        grid = [[0.0] * (MAX_RUNS + 1) for _ in range(MAX_RUNS + 1)]
        ninth_share = 1.0 / 9.0
        for g, w in self._gamma_nodes():
            away_pmf = _poisson_pmf(self.lam_away * g, MAX_RUNS)
            home8_pmf = _poisson_pmf(self.lam_home * g * (1 - ninth_share), MAX_RUNS)
            home9_pmf = _poisson_pmf(self.lam_home * g * ninth_share, 9)
            for a in range(MAX_RUNS + 1):
                pa = away_pmf[a] * w
                if pa < 1e-12:
                    continue
                for h8 in range(MAX_RUNS + 1):
                    p = pa * home8_pmf[h8]
                    if p < 1e-14:
                        continue
                    if h8 > a:
                        # 主隊九上結束後領先 -> 不打九局下，比賽結束。
                        grid[a][h8] += p
                        continue
                    for r9, p9 in enumerate(home9_pmf):
                        final = min(h8 + r9, MAX_RUNS)
                        grid[a][final] += p * p9
        return grid

    def distributions(self) -> "GameDistributions":
        """把聯合分布轉成下注需要的邊際分布 (含延長局處理)。"""
        grid = self.score_grid()

        margin_pmf: dict[int, float] = {}
        total_pmf: dict[int, float] = {}
        p_tie9 = 0.0

        for a in range(MAX_RUNS + 1):
            for h in range(MAX_RUNS + 1):
                p = grid[a][h]
                if p < 1e-14:
                    continue
                if a == h:
                    p_tie9 += p
                    continue
                margin = h - a
                margin_pmf[margin] = margin_pmf.get(margin, 0.0) + p
                total_pmf[a + h] = total_pmf.get(a + h, 0.0) + p

        # 延長局: 九局打平的部分，一部分在 10-12 局分出勝負，其餘為和局。
        resolve = self.env.extras_resolve_rate
        extra_runs = _extras_run_pmf(self.env.extras_runs_when_played)

        tie9_total_pmf: dict[int, float] = {}
        for a in range(MAX_RUNS + 1):
            p = grid[a][a]
            if p > 1e-14:
                tie9_total_pmf[2 * a] = tie9_total_pmf.get(2 * a, 0.0) + p

        for base_total, p_base in tie9_total_pmf.items():
            for add, p_add in extra_runs.items():
                p = p_base * p_add
                total_pmf[base_total + add] = (
                    total_pmf.get(base_total + add, 0.0) + p
                )

        # 打平後分出勝負者，勝負分方向對稱、幾乎都是 1 分差。
        decided = p_tie9 * resolve
        for margin, share in ((1, 0.78), (2, 0.17), (3, 0.05)):
            half = decided * share / 2
            margin_pmf[margin] = margin_pmf.get(margin, 0.0) + half
            margin_pmf[-margin] = margin_pmf.get(-margin, 0.0) + half
        margin_pmf[0] = margin_pmf.get(0, 0.0) + p_tie9 * (1 - resolve)

        return GameDistributions(
            margin_pmf=margin_pmf,
            total_pmf=total_pmf,
            lam_home=self.lam_home,
            lam_away=self.lam_away,
            p_tie=p_tie9 * (1 - resolve),
        )


@dataclass(frozen=True)
class GameDistributions:
    """模型輸出的機率分布。`margin_pmf` 以主隊為正方向。"""

    margin_pmf: Mapping[int, float]
    total_pmf: Mapping[int, float]
    lam_home: float
    lam_away: float
    p_tie: float

    def margin_from(self, favourite: str) -> dict[int, float]:
        """把淨勝分轉成以指定一方為正方向。"""
        if favourite == "home":
            return dict(self.margin_pmf)
        return {-m: p for m, p in self.margin_pmf.items()}

    def p_home_win(self) -> float:
        return sum(p for m, p in self.margin_pmf.items() if m > 0)

    def p_away_win(self) -> float:
        return sum(p for m, p in self.margin_pmf.items() if m < 0)

    def expected_total(self) -> float:
        return sum(t * p for t, p in self.total_pmf.items())

    def one_run_game_rate(self) -> float:
        return sum(p for m, p in self.margin_pmf.items() if abs(m) == 1)

    def modal_score(self) -> tuple[int, int]:
        """最可能的比分 — 由期望值反推的近似值，僅供報告呈現。"""
        return (round(self.lam_home), round(self.lam_away))


# ---------------------------------------------------------------------------
# 數值工具
# ---------------------------------------------------------------------------


def _poisson_pmf(lam: float, n_max: int) -> list[float]:
    pmf = [0.0] * (n_max + 1)
    if lam <= 0:
        pmf[0] = 1.0
        return pmf
    term = math.exp(-lam)
    pmf[0] = term
    for k in range(1, n_max + 1):
        term *= lam / k
        pmf[k] = term
    tail = 1.0 - sum(pmf)
    if tail > 0:
        pmf[n_max] += tail
    return pmf


def _extras_run_pmf(mean_extra: float) -> dict[int, float]:
    """延長局多出來的總得分分布 (兩隊合計)，截斷在 8 分。"""
    pmf = _poisson_pmf(mean_extra, 8)
    return {i: p for i, p in enumerate(pmf) if p > 1e-12}


def _gamma_ppf(q: float, k: float) -> float:
    """Gamma(shape=k, scale=1) 的分位數函數，用二分法求解。"""
    lo, hi = 1e-9, max(50.0, k * 12.0)
    for _ in range(80):
        mid = (lo + hi) / 2
        if _gamma_cdf(mid, k) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _gamma_cdf(x: float, k: float) -> float:
    """下不完全 Gamma 函數的正規化形式 P(k, x)。"""
    if x <= 0:
        return 0.0
    if x < k + 1:
        # 級數展開
        term = 1.0 / k
        total = term
        n = k
        for _ in range(500):
            n += 1
            term *= x / n
            total += term
            if abs(term) < abs(total) * 1e-14:
                break
        return total * math.exp(-x + k * math.log(x) - math.lgamma(k))
    # 連分數展開 (Lentz 演算法)
    tiny = 1e-300
    b = x + 1 - k
    c = 1 / tiny
    d = 1 / b if b != 0 else 1 / tiny
    h = d
    for i in range(1, 500):
        an = -i * (i - k)
        b += 2
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-14:
            break
    q = math.exp(-x + k * math.log(x) - math.lgamma(k)) * h
    return 1 - q


__all__ = [
    "MAX_RUNS",
    "NPBEnvironment",
    "TeamInput",
    "GameModel",
    "GameDistributions",
]
