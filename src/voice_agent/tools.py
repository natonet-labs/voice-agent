"""Tools available to the agent.

Keyless and safe by design (no external API keys required yet). The
remember_fact / recall_facts pair gives the agent persistent long-term memory
via memory_store. Add new tools here and append them to TOOLS.
"""

import ast
import operator
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain_core.tools import tool

from voice_agent import memory_store


@tool
def get_current_time() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


@tool
def get_time_in_timezone(tz_name: str) -> str:
    """Return the current time in an IANA timezone, e.g. 'America/New_York'."""
    try:
        return datetime.now(ZoneInfo(tz_name)).isoformat()
    except (ZoneInfoNotFoundError, ValueError):
        return f"Unknown timezone: {tz_name!r}"


# Bounds for calculate(). Spoken expressions are short, and without a cap a
# single power like 9**9**9 runs for minutes and ties up a server thread.
_MAX_EXPRESSION_CHARS = 200
_MAX_RESULT_BITS = 10_000


def _bounded_pow(base, exponent):
    if (
        isinstance(base, int)
        and isinstance(exponent, int)
        and abs(base) > 1
        and exponent > 0
        and base.bit_length() * exponent > _MAX_RESULT_BITS
    ):
        raise ValueError("result too large")
    return operator.pow(base, exponent)


# Safe arithmetic: walk the AST and allow only numeric literals and these ops.
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: _bounded_pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("unsupported expression")


@tool
def calculate(expression: str) -> str:
    """Evaluate a basic arithmetic expression: + - * / // % ** and parentheses.

    For a percentage, pass the arithmetic form — e.g. "15% of 80" -> "0.15 * 80".
    """
    if len(expression) > _MAX_EXPRESSION_CHARS:
        return f"Expression too long (max {_MAX_EXPRESSION_CHARS} characters)."
    try:
        tree = ast.parse(expression, mode="eval")
        return str(_safe_eval(tree.body))
    except Exception:
        return f"Could not evaluate: {expression!r}"


@tool
def remember_fact(fact: str) -> str:
    """Persist a fact the user wants remembered across conversations.

    Use when the user shares something to recall later (a preference, a name,
    a date). `fact` should be one self-contained statement.
    """
    memory_store.save_fact(fact)
    return f"Saved: {fact}"


@tool
def recall_facts() -> str:
    """Return everything previously saved with remember_fact."""
    facts = memory_store.list_facts()
    if not facts:
        return "No facts saved yet."
    return "\n".join(f"- {f}" for f in facts)


TOOLS = [get_current_time, get_time_in_timezone, calculate, remember_fact, recall_facts]
