import pytest

from finrag.eval.judge import cohen_kappa, within_tolerance


def test_tolerance_is_relative_one_percent():
    assert within_tolerance(1577, 1577.0)
    assert within_tolerance(10.3, 10.35)
    assert not within_tolerance(10.3, 10.65)
    assert within_tolerance(0, 0)
    assert not within_tolerance(0, 0.1)


def test_cohen_kappa_known_values():
    assert cohen_kappa([True, False, True, False], [True, False, True, False]) == 1.0
    # p_o = 0.5, p_e = 0.5 -> 0
    assert cohen_kappa([True, True, False, False], [True, False, True, False]) == 0.0
    # textbook 2x2: a=20 b=5 c=10 d=15 -> p_o=0.7, p_e=0.5 -> 0.4
    a = [True] * 25 + [False] * 25
    b = [True] * 20 + [False] * 5 + [True] * 10 + [False] * 15
    assert cohen_kappa(a, b) == pytest.approx(0.4)
