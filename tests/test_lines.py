from fractions import Fraction

import pytest

from bethero.lines import (
    Confidence,
    Line,
    cover_rate,
    handicap_outcome_probs,
    parse_board_line,
    push_rate,
    settle_handicap,
    settle_total,
)


def L(value: str) -> Line:
    return parse_board_line(value)


class TestParsing:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("8平", Fraction(8)),
            ("7平", Fraction(7)),
            ("7+25", Fraction(29, 4)),
            ("8+75", Fraction(35, 4)),
            ("7-25", Fraction(27, 4)),
            ("6.5", Fraction(13, 2)),
            ("0", Fraction(0)),
            ("1+50", Fraction(3, 2)),
            ("1-25", Fraction(3, 4)),
            ("0-50", Fraction(-1, 2)),
        ],
    )
    def test_offset_notation(self, raw, expected):
        assert parse_board_line(raw).value == expected

    def test_flat_anchors_the_convention(self):
        """``平`` 代表整數，這是推斷 +/- 是位移而非小數點的依據。"""
        assert L("8平").value == 8
        assert L("8+75").value == Fraction(35, 4)

    @pytest.mark.parametrize("raw", ["8平", "7+25", "8+75", "7-25", "6.5", "1+50"])
    def test_standard_lines_are_confirmed(self, raw):
        assert parse_board_line(raw).confidence is Confidence.CONFIRMED

    @pytest.mark.parametrize(
        "raw", ["1-60", "1+80", "1+95", "0-10", "0-20", "1+70", "0-50", "0-80"]
    )
    def test_non_standard_lines_are_flagged_not_guessed(self, raw):
        """不落在 0.25 級距的數值必須標為待確認，絕不四捨五入去猜。"""
        line = parse_board_line(raw)
        assert line.confidence is not Confidence.CONFIRMED
        assert not line.is_usable
        assert line.note

    @pytest.mark.parametrize("raw", ["", "   ", "abc", "大", None])
    def test_unreadable(self, raw):
        assert parse_board_line(raw).confidence is Confidence.UNREADABLE


class TestLegs:
    def test_whole_and_half_lines_have_one_leg(self):
        assert L("1平").legs() == (Fraction(1),)
        assert parse_board_line("1+50").legs() == (Fraction(3, 2),)

    def test_quarter_line_splits_into_two(self):
        assert parse_board_line("1-25").legs() == (Fraction(1, 2), Fraction(1))
        assert parse_board_line("7+25").legs() == (Fraction(7), Fraction(15, 2))


class TestHandicapSettlement:
    def test_whole_line_pushes_on_exact_margin(self):
        line = L("1平")
        assert settle_handicap(line, 1) == 0
        assert settle_handicap(line, 2) == 1
        assert settle_handicap(line, 0) == -1
        assert settle_handicap(line, -3) == -1

    def test_pick_em_treats_tie_as_push(self):
        line = L("0")
        assert settle_handicap(line, 0) == 0
        assert settle_handicap(line, 1) == 1
        assert settle_handicap(line, -1) == -1

    def test_half_line_never_pushes(self):
        line = parse_board_line("1+50")
        assert settle_handicap(line, 2) == 1
        assert settle_handicap(line, 1) == -1
        assert settle_handicap(line, 0) == -1

    def test_quarter_line_half_win_and_half_loss(self):
        """讓 0.75 (0.5/1): 贏 1 分 -> 半贏; 這就是所謂一輸二贏型盤口。"""
        line = parse_board_line("1-25")
        assert settle_handicap(line, 2) == 1
        assert settle_handicap(line, 1) == Fraction(1, 2)
        assert settle_handicap(line, 0) == -1

    def test_quarter_line_at_0_25(self):
        line = parse_board_line("0+25")
        assert settle_handicap(line, 1) == 1
        assert settle_handicap(line, 0) == Fraction(-1, 2)
        assert settle_handicap(line, -1) == -1


class TestTotalSettlement:
    def test_whole_total_pushes(self):
        line = L("8平")
        assert settle_total(line, 8, "over") == 0
        assert settle_total(line, 8, "under") == 0
        assert settle_total(line, 9, "over") == 1
        assert settle_total(line, 7, "under") == 1

    def test_quarter_total_splits(self):
        line = L("7+25")
        assert settle_total(line, 8, "over") == 1
        assert settle_total(line, 7, "over") == Fraction(-1, 2)
        assert settle_total(line, 7, "under") == Fraction(1, 2)
        assert settle_total(line, 6, "under") == 1

    def test_sides_are_zero_sum_before_vig(self):
        line = L("8+75")
        for total in range(0, 20):
            assert settle_total(line, total, "over") + settle_total(
                line, total, "under"
            ) == 0

    def test_bad_side_rejected(self):
        with pytest.raises(ValueError):
            settle_total(L("7平"), 7, "大")


class TestOutcomeProbs:
    def test_cover_rate_excludes_push(self):
        line = L("1平")
        # 讓分方: 40% 贏 2+、20% 剛好贏 1 (走盤)、40% 沒過盤
        pmf = {2: 0.40, 1: 0.20, 0: 0.25, -1: 0.15}
        probs = handicap_outcome_probs(line, pmf)
        assert push_rate(probs) == pytest.approx(0.20)
        assert cover_rate(probs) == pytest.approx(0.40 / 0.80)

    def test_probabilities_sum_to_one(self):
        pmf = {2: 0.40, 1: 0.20, 0: 0.25, -1: 0.15}
        probs = handicap_outcome_probs(L("1-25"), pmf)
        assert sum(probs.values()) == pytest.approx(1.0)
