from fractions import Fraction

import pytest

from bethero.lines import (
    ICHI_YU_NI_EI,
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
        "raw,base,edge",
        [
            ("8平", 8, Fraction(0)),
            ("7平", 7, Fraction(0)),
            ("0", 0, Fraction(0)),
            ("0-50", 0, Fraction(-1, 2)),
            ("1-60", 1, Fraction(-3, 5)),
            ("1-25", 1, Fraction(-1, 4)),
            ("1+50", 1, Fraction(1, 2)),
            ("1+80", 1, Fraction(4, 5)),
            ("1+95", 1, Fraction(19, 20)),
            ("7+25", 7, Fraction(1, 4)),
            ("8+75", 8, Fraction(3, 4)),
            ("7-25", 7, Fraction(-1, 4)),
        ],
    )
    def test_percentage_notation(self, raw, base, edge):
        line = parse_board_line(raw)
        assert line.base == base
        assert line.edge == edge
        assert line.confidence is Confidence.CONFIRMED

    @pytest.mark.parametrize(
        "raw,effective",
        [
            ("0-50", Fraction(1, 4)),  # 標準 0/0.5 盤
            ("1+50", Fraction(3, 4)),  # 標準 0.5/1 盤
            ("1-50", Fraction(5, 4)),  # 標準 1/1.5 盤
            ("1平", Fraction(1)),  # 標準整數盤
            ("1-60", Fraction(13, 10)),  # 標準階梯做不出來
            ("1+95", Fraction(21, 40)),
            ("7+25", Fraction(55, 8)),
            ("7-25", Fraction(57, 8)),
        ],
    )
    def test_effective_line(self, raw, effective):
        assert parse_board_line(raw).effective == effective

    def test_user_confirmed_example_0_50(self):
        """0-50: 平手時讓分方輸 50% 本金，受讓方贏 50% 賠金。"""
        line = L("0-50")
        assert settle_handicap(line, 0) == Fraction(-1, 2)
        assert settle_handicap(line, 1) == 1
        assert settle_handicap(line, -1) == -1

    def test_user_confirmed_example_1_60(self):
        """1-60: 讓分方贏一分輸 60% 本金，受讓方贏 60% 賠金。"""
        line = L("1-60")
        assert settle_handicap(line, 1) == Fraction(-3, 5)
        assert settle_handicap(line, 2) == 1
        assert settle_handicap(line, 0) == -1

    def test_attested_decimal_is_taken_literally(self):
        """使用者目視確認後，6.5 就是 6.5 —— 等效半球盤，永不走盤。"""
        line = parse_board_line("6.5", attested=True)
        assert line.confidence is Confidence.CONFIRMED
        assert line.effective == Fraction(13, 2)
        assert line.base == 6 and line.edge == Fraction(-1)
        assert settle_total(line, 6, "over") == -1
        assert settle_total(line, 7, "over") == 1
        for total in range(0, 16):
            assert settle_total(line, total, "over") != 0

    @pytest.mark.parametrize(
        "effective,base,edge",
        [
            (Fraction(13, 2), 6, Fraction(-1)),    # 6.5  半球盤
            (Fraction(27, 4), 7, Fraction(1, 2)),  # 6.75
            (Fraction(25, 4), 6, Fraction(-1, 2)), # 6.25
            (Fraction(7), 7, Fraction(0)),         # 整數盤
            (Fraction(13, 10), 1, Fraction(-3, 5)),# 1.30 -> 1-60
        ],
    )
    def test_from_effective_roundtrip(self, effective, base, edge):
        line = Line.from_effective(effective)
        assert (line.base, line.edge) == (base, edge)
        assert line.effective == effective

    def test_decimal_form_is_flagged_for_confirmation(self):
        """純小數不是看板慣用寫法 —— 6.5 可能是 6-50 或 6+50，差 0.5 分。"""
        line = L("6.5")
        assert line.confidence is Confidence.UNCONFIRMED
        assert "6-50" in line.note and "6+50" in line.note

    @pytest.mark.parametrize("raw", ["", "   ", "abc", "大", None])
    def test_unreadable(self, raw):
        assert parse_board_line(raw).confidence is Confidence.UNREADABLE

    def test_percentage_over_100_rejected(self):
        assert L("1+150").confidence is Confidence.UNREADABLE


class TestIchiYuNiEi:
    def test_is_a_1_5_run_line(self):
        """一輸二贏 = 讓/受讓 1.5 分。"""
        assert ICHI_YU_NI_EI.effective == Fraction(3, 2)

    def test_win_by_one_loses_win_by_two_wins(self):
        assert settle_handicap(ICHI_YU_NI_EI, 1) == -1
        assert settle_handicap(ICHI_YU_NI_EI, 2) == 1

    def test_never_pushes(self):
        for margin in range(-6, 7):
            assert settle_handicap(ICHI_YU_NI_EI, margin) in (Fraction(1), Fraction(-1))


class TestHandicapSettlement:
    def test_flat_line_pushes_on_exact_margin(self):
        line = L("1平")
        assert settle_handicap(line, 1) == 0
        assert settle_handicap(line, 2) == 1
        assert settle_handicap(line, 0) == -1

    def test_pick_em_treats_tie_as_push(self):
        line = L("0")
        assert settle_handicap(line, 0) == 0
        assert settle_handicap(line, 1) == 1
        assert settle_handicap(line, -1) == -1

    def test_plus_gives_partial_win_at_the_edge(self):
        """1+95: 讓分方贏 1 分仍收 95% 賠金 —— 幾乎等於 0.5 盤。"""
        line = L("1+95")
        assert settle_handicap(line, 1) == Fraction(19, 20)
        assert settle_handicap(line, 0) == -1
        assert abs(float(line.effective) - 0.5) < 0.03

    def test_equivalence_with_standard_quarter_line(self):
        """1+50 應與標準 0.5/1 盤逐一結算相同。"""
        line = L("1+50")
        assert settle_handicap(line, 2) == 1
        assert settle_handicap(line, 1) == Fraction(1, 2)
        assert settle_handicap(line, 0) == -1


class TestTotalSettlement:
    def test_flat_total_pushes(self):
        line = L("8平")
        assert settle_total(line, 8, "over") == 0
        assert settle_total(line, 8, "under") == 0
        assert settle_total(line, 9, "over") == 1
        assert settle_total(line, 7, "under") == 1

    def test_over_is_the_primary_side(self):
        """7+25: 總分剛好 7 時大分贏 25% 賠金、小分輸 25% 本金。"""
        line = L("7+25")
        assert settle_total(line, 7, "over") == Fraction(1, 4)
        assert settle_total(line, 7, "under") == Fraction(-1, 4)

    def test_minus_penalises_over(self):
        line = L("7-25")
        assert settle_total(line, 7, "over") == Fraction(-1, 4)
        assert settle_total(line, 7, "under") == Fraction(1, 4)

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
        pmf = {2: 0.40, 1: 0.20, 0: 0.25, -1: 0.15}
        probs = handicap_outcome_probs(line, pmf)
        assert push_rate(probs) == pytest.approx(0.20)
        assert cover_rate(probs) == pytest.approx(0.40 / 0.80)

    def test_partial_settlement_lines_never_push(self):
        pmf = {2: 0.40, 1: 0.20, 0: 0.25, -1: 0.15}
        probs = handicap_outcome_probs(L("1-60"), pmf)
        assert push_rate(probs) == pytest.approx(0.0)

    def test_probabilities_sum_to_one(self):
        pmf = {2: 0.40, 1: 0.20, 0: 0.25, -1: 0.15}
        probs = handicap_outcome_probs(L("1-25"), pmf)
        assert sum(probs.values()) == pytest.approx(1.0)
