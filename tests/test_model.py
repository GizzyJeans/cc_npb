import pytest

from bethero.model import GameModel, NPBEnvironment, TeamInput

NPB_2026 = NPBEnvironment(
    league_rpg=3.85,
    source="prior — 待以當季 NPB 官方資料校準",
    as_of="2026-08-13",
)


def build(park=1.00, home_off=1.0, away_off=1.0, home_def=1.0, away_def=1.0):
    return GameModel(
        home=TeamInput("home", home_off, home_def),
        away=TeamInput("away", away_off, away_def),
        env=NPB_2026,
        park_factor=park,
    )


class TestScoreDistribution:
    def test_joint_grid_is_a_probability_distribution(self):
        grid = build().score_grid()
        total = sum(sum(row) for row in grid)
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_margin_and_total_pmfs_normalise(self):
        d = build().distributions()
        assert sum(d.margin_pmf.values()) == pytest.approx(1.0, abs=1e-6)
        assert sum(d.total_pmf.values()) == pytest.approx(1.0, abs=1e-6)

    def test_home_ninth_forfeit_suppresses_actual_runs(self):
        """主隊領先就不打九下，實際總分應略低於兩隊 lambda 相加。"""
        m = build()
        d = m.distributions()
        full_nine = m.lam_home + m.lam_away
        assert d.expected_total() < full_nine
        assert d.expected_total() > full_nine - 0.5


class TestNPBSpecifics:
    def test_scoring_environment_is_lower_than_mlb(self):
        """NPB 兩隊合計期望得分應明顯低於 MLB 的 ~9 分。"""
        d = build().distributions()
        assert 7.0 < d.expected_total() < 8.6

    def test_ties_are_possible(self):
        """NPB 延長賽上限 12 局，和局有實質機率。"""
        d = build().distributions()
        assert 0.02 < d.p_tie < 0.10

    def test_home_field_advantage(self):
        d = build().distributions()
        assert d.p_home_win() > d.p_away_win()
        assert 0.51 < d.p_home_win() / (d.p_home_win() + d.p_away_win()) < 0.56

    def test_one_run_games_are_common(self):
        """低得分環境 -> 一分差比例高。"""
        d = build().distributions()
        assert d.one_run_game_rate() > 0.20

    def test_pitcher_park_suppresses_scoring(self):
        neutral = build(park=1.00).distributions().expected_total()
        vantelin = build(park=0.85).distributions().expected_total()
        assert vantelin < neutral - 0.8

    def test_stronger_offense_raises_win_probability(self):
        weak = build(home_off=0.90).distributions().p_home_win()
        strong = build(home_off=1.15).distributions().p_home_win()
        assert strong > weak + 0.08


class TestCorrelation:
    def test_shared_environment_creates_positive_correlation(self):
        """共享環境因子必須讓兩隊得分正相關，否則大小分尾端會被低估。"""
        m = build()
        grid = m.score_grid()
        ex = ey = exy = 0.0
        for a, row in enumerate(grid):
            for h, p in enumerate(row):
                ex += a * p
                ey += h * p
                exy += a * h * p
        assert exy - ex * ey > 0.05

    def test_lower_k_means_fatter_tails(self):
        base = GameModel(
            home=TeamInput("h", 1.0, 1.0),
            away=TeamInput("a", 1.0, 1.0),
            env=NPBEnvironment(league_rpg=3.85, dispersion_k=9.0),
        ).distributions()
        fat = GameModel(
            home=TeamInput("h", 1.0, 1.0),
            away=TeamInput("a", 1.0, 1.0),
            env=NPBEnvironment(league_rpg=3.85, dispersion_k=4.0),
        ).distributions()
        p_big_base = sum(p for t, p in base.total_pmf.items() if t >= 13)
        p_big_fat = sum(p for t, p in fat.total_pmf.items() if t >= 13)
        assert p_big_fat > p_big_base
