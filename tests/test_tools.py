import time

import pytest

from voice_agent.tools import calculate


def calc(expression: str) -> str:
    return calculate.invoke({"expression": expression})


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("0.15 * 80", "12.0"),
        ("(2 + 3) * 4", "20"),
        ("2**10", "1024"),
        ("-3**2", "-9"),
        ("2**-1", "0.5"),
    ],
)
def test_basic_arithmetic(expression, expected):
    assert calc(expression) == expected


@pytest.mark.parametrize("expression", ["9**9**9", "10**100000", "(2**100)**100"])
def test_rejects_huge_powers_quickly(expression):
    start = time.perf_counter()
    assert calc(expression).startswith("Could not evaluate")
    assert time.perf_counter() - start < 1


def test_allows_large_but_bounded_power():
    assert calc("2**4000") == str(2**4000)


def test_rejects_long_expressions():
    assert calc("1+" * 150 + "1").startswith("Expression too long")


@pytest.mark.parametrize(
    "expression", ["__import__('os')", "open('x')", "1 if 1 else 2"]
)
def test_rejects_non_arithmetic(expression):
    assert calc(expression).startswith("Could not evaluate")
