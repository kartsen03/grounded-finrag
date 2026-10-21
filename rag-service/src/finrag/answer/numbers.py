"""Numbers as printed in filings, and a safe evaluator for extract-then-compute formulas."""

from __future__ import annotations

import ast
import math
import operator
import re

# 1,577  (1,577)  -3.2  $5,363  12.5%  0.0000001
_NUM = re.compile(r"\(?-?\$?\d[\d,]*(?:\.\d+)?\)?%?")
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_UNARY = {ast.USub: operator.neg, ast.UAdd: operator.pos}


def parse_number(token: str) -> float | None:
    """'(1,577)' -> -1577.0, '$5,363' -> 5363.0, '12.5%' -> 12.5. None if not a number."""
    t = token.strip()
    negative = t.startswith("(") and t.endswith(")")
    t = t.strip("()").replace("$", "").replace(",", "").rstrip("%")
    try:
        value = float(t)
    except ValueError:
        return None
    return -value if negative else value


def numbers_in(text: str) -> list[float]:
    out = []
    for m in _NUM.finditer(text):
        v = parse_number(m.group(0))
        if v is not None:
            out.append(v)
    return out


def grounded(value: float, source_text: str, rel_tol: float = 1e-9) -> bool:
    """True if |value| appears among the numbers printed in the source (sign-insensitive,
    because statements print outflows as (1,577) while a model may extract 1577)."""
    target = abs(value)
    return any(math.isclose(abs(v), target, rel_tol=rel_tol, abs_tol=1e-9) for v in numbers_in(source_text))


class FormulaError(ValueError):
    pass


def evaluate(formula: str, variables: dict[str, float]) -> float:
    """Evaluate + - * / ( ) over named inputs and numeric literals. Nothing else is allowed:
    no calls, attributes or names outside the inputs, so model output cannot run code."""
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as e:
        raise FormulaError(f"formula is not valid arithmetic: {formula!r}") from e

    def walk(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Div) and right == 0:
                raise FormulaError("division by zero")
            return _OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            return _UNARY[type(node.op)](walk(node.operand))
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise FormulaError(f"formula uses unknown input {node.id!r}")
            return float(variables[node.id])
        raise FormulaError(f"formula contains a disallowed expression: {ast.dump(node)[:60]}")

    return walk(tree)
