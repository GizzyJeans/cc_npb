"""本金與風控參數。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Bankroll:
    """資金配置規則。"""

    total: float = 100_000.0
    """初始本金 (單位)。使用者設定為 10 萬單位。"""

    kelly_multiplier: float = 0.25
    """預設 0.25 Kelly。"""

    max_stake: float = 1_000.0
    """單注上限。"""

    max_daily_exposure_pct: float = 0.05
    """單日總下注上限占本金比例。"""

    allow_parlay: bool = False
    """不推薦串關。"""

    @property
    def max_daily_exposure(self) -> float:
        return self.total * self.max_daily_exposure_pct

    def clamp(self, stake: float, already_staked: float = 0.0) -> float:
        """套用單注上限與單日總曝險上限。"""
        stake = min(stake, self.max_stake)
        remaining = max(0.0, self.max_daily_exposure - already_staked)
        return round(min(stake, remaining), 0)


__all__ = ["Bankroll"]
