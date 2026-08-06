import pytest

from underdog_lab.forecasting.optimization import bounded_minimize


def test_bounded_minimize_finds_quadratic_minimum():
    result = bounded_minimize(lambda value: (value - 2.5) ** 2, -10.0, 10.0)

    assert result == pytest.approx(2.5, abs=1e-7)


def test_bounded_minimize_rejects_invalid_bounds():
    with pytest.raises(ValueError, match="lower bound"):
        bounded_minimize(lambda value: value * value, 1.0, 1.0)
