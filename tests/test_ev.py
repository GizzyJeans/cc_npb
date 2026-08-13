from fractions import Fraction

import pytest

from bethero.bankroll import Bankroll
from bethero.ev import (
    devig_power,
    devig_proportional,
    evaluate,
    hk_to_decimal,
    implied_prob,
    overround,
)
from bethero.gates import DataReadiness, Grade, grade


class TestOdds:
    def test_hk_to_decimal(self):
        assert hk_to_decimal(0.95) == pytest.approx(1.95)
        assert hk_to_decimal(0.93) == pytest.approx(1.93)

    def test_implied_prob(self):
        assert implied_prob(0.95) == pytest.approx(1 / 1.95)

    def test_overround_of_board_prices(self):
        """看板上 0.95/0.95 的讓分盤約 2.6% 水錢。"""
        assert overround([0.95, 0.95]) == pytest.approx(1.0256, abs=1e-4)

    def test_total_prices_carry_more_vig(self):
        """0.93/0.93 的大小分水錢比讓分盤重。"""
        assert overround([0.93, 0.93]) > overround([0.95, 0.95])


class TestDevig:
    def test_symmetric_prices_devig_to_half(self):
        assert devig_proportional([0.95, 0.95]) == pytest.approx([0.5, 0.5])
        assert devig_power([0.95, 0.95]) == pytest.approx([0.5, 0.5])

    def test_devig_sums_to_one(self):
        for fn in (devig_proportional, devig_power):
            assert sum(fn([1.35, 0.65])) == pytest.approx(1.0)

    def test_power_differs_from_proportional_on_skewed_prices(self):
        prop = devig_proportional([1.60, 0.50])
        power = devig_power([1.60, 0.50])
        assert prop != pytest.approx(power)
        # 次方法把較多水錢算在冷門端 (favourite-longshot bias)，
        # 因此冷門的真實機率低於比例去水、熱門則高於比例去水。
        assert power[0] < prop[0]
        assert power[1] > prop[1]


class TestEvaluate:
    def test_fair_odds_and_zero_ev_point(self):
        probs = {Fraction(1): 0.55, Fraction(-1): 0.45}
        ev = evaluate(probs, offered_hk=0.95, bankroll=100_000, market_prob=0.50)
        assert ev.model_prob == pytest.approx(0.55)
        assert ev.fair_hk == pytest.approx(0.45 / 0.55)
        # 以最低可接受賠率下注時 EV 恰為零
        breakeven = evaluate(
            probs, offered_hk=ev.min_hk, bankroll=100_000, market_prob=0.50
        )
        assert breakeven.ev == pytest.approx(0.0, abs=1e-9)

    def test_positive_ev_when_model_beats_price(self):
        probs = {Fraction(1): 0.55, Fraction(-1): 0.45}
        ev = evaluate(probs, 0.95, 100_000, 0.50)
        assert ev.ev == pytest.approx(0.55 * 0.95 - 0.45)
        assert ev.ev > 0
        assert ev.edge_pp == pytest.approx(5.0)

    def test_negative_ev_gets_zero_stake(self):
        probs = {Fraction(1): 0.45, Fraction(-1): 0.55}
        ev = evaluate(probs, 0.95, 100_000, 0.50)
        assert ev.ev < 0
        assert ev.kelly_fraction == 0.0
        assert ev.stake == 0.0

    def test_push_excluded_from_model_prob(self):
        probs = {Fraction(1): 0.40, Fraction(0): 0.20, Fraction(-1): 0.40}
        ev = evaluate(probs, 0.95, 100_000, 0.50)
        assert ev.push_prob == pytest.approx(0.20)
        assert ev.model_prob == pytest.approx(0.5)

    def test_stake_capped_at_1000(self):
        probs = {Fraction(1): 0.90, Fraction(-1): 0.10}
        ev = evaluate(probs, 0.95, 100_000, 0.50)
        assert ev.stake == 1000.0

    def test_quarter_kelly_is_smaller_than_full(self):
        probs = {Fraction(1): 0.56, Fraction(-1): 0.44}
        ev = evaluate(probs, 0.95, 100_000, 0.50, kelly_multiplier=0.25)
        full = ev.kelly_fraction * 100_000
        assert ev.stake < full
        assert ev.stake == pytest.approx(min(full * 0.25, 1000.0))

    def test_kelly_on_quarter_line_accounts_for_half_loss(self):
        """半贏/半輸的盤口不是二元賭局，一般化 Kelly 應比課本公式保守。"""
        binary = {Fraction(1): 0.55, Fraction(-1): 0.45}
        quarter = {Fraction(1): 0.55, Fraction(-1, 2): 0.30, Fraction(-1): 0.15}
        b = evaluate(binary, 0.95, 100_000, 0.50)
        q = evaluate(quarter, 0.95, 100_000, 0.50)
        assert q.ev > b.ev  # 半輸讓損失變小
        assert q.kelly_fraction > 0


class TestBankroll:
    def test_daily_exposure_cap(self):
        bank = Bankroll()
        assert bank.max_daily_exposure == 5000.0
        assert bank.clamp(1000, already_staked=4500) == 500
        assert bank.clamp(1000, already_staked=5000) == 0

    def test_single_stake_cap(self):
        assert Bankroll().clamp(9999) == 1000

    def test_no_parlay(self):
        assert Bankroll().allow_parlay is False


class TestGates:
    def full_data(self):
        return DataReadiness(
            line_type_confirmed=True,
            starters_confirmed=True,
            lineups_confirmed=True,
            bullpen_usage_known=True,
            team_rates_known=True,
            park_factor_known=True,
            weather_known=True,
            injuries_known=True,
            market_prices_known=True,
        )

    def test_recommend_requires_everything(self):
        g = grade(ev=0.06, edge_pp=4.0, readiness=self.full_data())
        assert g.grade is Grade.RECOMMEND

    def test_ev_below_threshold_blocks(self):
        g = grade(ev=0.03, edge_pp=4.0, readiness=self.full_data())
        assert g.grade is Grade.NO_BET

    def test_edge_below_threshold_blocks(self):
        g = grade(ev=0.06, edge_pp=2.0, readiness=self.full_data())
        assert g.grade is Grade.NO_BET

    def test_missing_lineups_downgrades_to_observe(self):
        data = self.full_data()
        data.lineups_confirmed = False
        g = grade(ev=0.08, edge_pp=5.0, readiness=data)
        assert g.grade is Grade.OBSERVE
        assert "正式先發打線尚未公布" in g.reasons

    def test_unconfirmed_line_type_downgrades(self):
        data = self.full_data()
        data.line_type_confirmed = False
        g = grade(ev=0.10, edge_pp=6.0, readiness=data)
        assert g.grade is Grade.OBSERVE

    def test_thin_data_downgrades_even_with_big_edge(self):
        data = DataReadiness(
            line_type_confirmed=True,
            starters_confirmed=True,
            lineups_confirmed=True,
        )
        g = grade(ev=0.20, edge_pp=12.0, readiness=data)
        assert g.grade is Grade.OBSERVE
        assert "資料完整度不足" in g.reasons

    def test_no_data_cannot_produce_recommendation(self):
        """核心安全性質: 空的資料狀態永遠不可能推薦。"""
        for ev in (0.05, 0.5, 5.0):
            g = grade(ev=ev, edge_pp=50.0, readiness=DataReadiness())
            assert g.grade is not Grade.RECOMMEND


class TestBreakeven:
    def test_binary_line_needs_51_28_percent(self):
        """半球盤無走盤: 0.95 的價格要 51.28% 才不虧。"""
        from bethero.breakeven import required_win_prob
        from bethero.lines import ICHI_YU_NI_EI

        p = required_win_prob(ICHI_YU_NI_EI, 0.95, "primary", p_edge=0.0)
        assert p == pytest.approx(1 / 1.95, abs=1e-6)

    def test_push_lowers_the_bar(self):
        """走盤機率越高，所需勝率越低。"""
        from bethero.breakeven import required_win_prob
        from bethero.lines import parse_board_line

        flat = parse_board_line("1平")
        no_push = required_win_prob(flat, 0.95, "primary", p_edge=0.0)
        with_push = required_win_prob(flat, 0.95, "primary", p_edge=0.20)
        assert with_push < no_push

    def test_partial_win_lowers_the_bar_more_than_partial_loss(self):
        from bethero.breakeven import required_win_prob
        from bethero.lines import parse_board_line

        plus = parse_board_line("1+80")   # 落在 1 時主方贏 80%
        minus = parse_board_line("1-80")  # 落在 1 時主方輸 80%
        p_plus = required_win_prob(plus, 0.95, "primary", p_edge=0.20)
        p_minus = required_win_prob(minus, 0.95, "primary", p_edge=0.20)
        assert p_plus < p_minus

    def test_target_ev_raises_the_bar(self):
        from bethero.breakeven import analyse
        from bethero.lines import parse_board_line

        b = analyse(parse_board_line("1平"), 0.95, "primary", 0.15, target_ev=0.04)
        assert b.target_prob > b.breakeven_prob
        assert b.required_edge_over_breakeven() == pytest.approx(4.0 / 1.95, abs=1e-6)

    def test_ev_at_required_prob_hits_the_target(self):
        """反推的機率代回 EV 公式應剛好等於目標。"""
        from bethero.breakeven import _edge_payoff, required_win_prob
        from bethero.lines import parse_board_line

        line = parse_board_line("1-60")
        hk, p_edge, target = 0.95, 0.18, 0.04
        p_win = required_win_prob(line, hk, "primary", p_edge, target)
        e = _edge_payoff(line, "primary", hk)
        ev = p_win * hk + p_edge * e - (1 - p_win - p_edge)
        assert ev == pytest.approx(target, abs=1e-9)

    def test_vig_cost(self):
        from bethero.breakeven import vig_cost

        assert vig_cost(0.95) == pytest.approx(1.282, abs=1e-3)
        assert vig_cost(0.93) > vig_cost(0.95)
