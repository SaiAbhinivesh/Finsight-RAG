"""The agent's calculator (M7): exact arithmetic, and nothing else."""

import pytest

from finsight.agent.tools import make_tools


@pytest.fixture
def calculator():
    log = []
    tools = make_tools(registry=[], log=log)
    calc = next(t for t in tools if t.name == "calculator")
    return lambda expression: calc.invoke({"expression": expression})


def test_ebitda_margin(calculator):
    assert float(calculator("(11512 + 2763) / 86392 * 100")) == pytest.approx(16.5235, abs=1e-4)


def test_thousands_separators_are_ignored(calculator):
    assert float(calculator("1,000 + 2")) == 1002


def test_negative_numbers_and_powers(calculator):
    assert float(calculator("-(2 ** 3) + 10")) == 2


def test_division_by_zero_is_an_error_not_a_crash(calculator):
    assert calculator("1 / 0").startswith("Error")


@pytest.mark.parametrize("expression", [
    "__import__('os').system('ls')",   # code execution
    "open('/etc/passwd').read()",      # file access
    "x + 1",                           # names
    "True + 1",                        # booleans are not numbers here
    "9 ** 9 ** 9",                     # would freeze the process
])
def test_anything_but_arithmetic_is_rejected(calculator, expression):
    assert calculator(expression).startswith("Error")


def test_calls_are_logged():
    log = []
    calc = next(t for t in make_tools(registry=[], log=log) if t.name == "calculator")
    calc.invoke({"expression": "1 + 1"})
    assert log == [{"name": "calculator", "args": {"expression": "1 + 1"}}]
