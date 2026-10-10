"""Safe, deliberately limited JSONLogic-style evaluator for registry rules."""
from __future__ import annotations
import re
from datetime import datetime, date
from typing import Any

SUPPORTED = {"var", "and", "or", "!", "==", "!=", ">", ">=", "<", "<=", "in", "regex", "if", "toNumber", "substr"}

class RuleEvaluationError(ValueError):
    pass

def _truthy(value: Any) -> bool:
    return bool(value)

def _resolve(expr: Any, record: dict[str, Any]) -> Any:
    if not isinstance(expr, dict):
        if isinstance(expr, list):
            return [_resolve(x, record) for x in expr]
        return expr
    if len(expr) != 1:
        raise RuleEvaluationError("Each rule expression object must contain exactly one operator.")
    op, args = next(iter(expr.items()))
    if op not in SUPPORTED:
        raise RuleEvaluationError(f"Unsupported operator: {op}")
    if op == "var":
        if isinstance(args, list):
            key = args[0] if args else ""
            default = args[1] if len(args) > 1 else None
        else:
            key, default = args, None
        value = record.get(key, default)
        return default if value is None and default is not None else value
    if op in ("and", "or"):
        if not isinstance(args, list):
            raise RuleEvaluationError(f"{op} expects an array.")
        values = [_resolve(x, record) for x in args]
        return all(_truthy(x) for x in values) if op == "and" else any(_truthy(x) for x in values)
    if op == "!":
        return not _truthy(_resolve(args, record))
    if op == "if":
        if not isinstance(args, list) or len(args) < 3:
            raise RuleEvaluationError("if expects [condition, then, else].")
        for i in range(0, len(args)-1, 2):
            if _truthy(_resolve(args[i], record)):
                return _resolve(args[i+1], record)
        return _resolve(args[-1], record)
    if op == "toNumber":
        value = _resolve(args, record)
        if value is None or value == "":
            raise RuleEvaluationError("Cannot convert an empty value to a number.")
        try:
            return float(value)
        except (TypeError, ValueError):
            raise RuleEvaluationError(f"Cannot convert {value!r} to a number.")
    if op == "substr":
        if not isinstance(args, list) or len(args) < 2:
            raise RuleEvaluationError("substr expects [value, start, length?].")
        value = _resolve(args[0], record)
        if value is None:
            return ""
        start = int(_resolve(args[1], record))
        length = int(_resolve(args[2], record)) if len(args) > 2 else None
        return str(value)[start:] if length is None else str(value)[start:start+length]
    if op == "regex":
        if not isinstance(args, list) or len(args) != 2:
            raise RuleEvaluationError("regex expects [value, pattern].")
        # The supplied seed JSON uses field-name strings in regex operands; support that
        # legacy shape while preferring explicit {"var": "Field"} expressions.
        if isinstance(args[0], str) and args[0] in record:
            value = record.get(args[0])
        else:
            value = _resolve(args[0], record)
        pattern = _resolve(args[1], record)
        if value is None or value == "":
            return False
        try:
            return re.fullmatch(str(pattern), str(value)) is not None
        except re.error as exc:
            raise RuleEvaluationError(f"Invalid regex: {exc}")
    if op == "in":
        if not isinstance(args, list) or len(args) != 2:
            raise RuleEvaluationError("in expects [value, list-or-string].")
        left, right = (_resolve(x, record) for x in args)
        try:
            return left in right
        except TypeError:
            raise RuleEvaluationError("Right-hand operand of 'in' must be a list or string.")
    if not isinstance(args, list) or len(args) != 2:
        raise RuleEvaluationError(f"{op} expects two operands.")
    left, right = (_resolve(x, record) for x in args)
    if op == "==": return left == right
    if op == "!=": return left != right
    if left is None or right is None:
        return False
    try:
        if op == ">": return left > right
        if op == ">=": return left >= right
        if op == "<": return left < right
        if op == "<=": return left <= right
    except TypeError:
        # Numeric comparison is only performed when values can safely be normalized.
        try:
            a, b = float(left), float(right)
            return {">": a > b, ">=": a >= b, "<": a < b, "<=": a <= b}[op]
        except (TypeError, ValueError):
            raise RuleEvaluationError(f"Incompatible values for operator {op}: {left!r}, {right!r}")
    raise RuleEvaluationError(f"Unsupported operator: {op}")

def evaluate_rule(rule: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Return PASS/FAIL/SKIP/ERROR; applicability is explicit and never guessed."""
    try:
        applies_when = rule.get("applies_when")
        if applies_when is not None and not _truthy(_resolve(applies_when, record)):
            return {"status": "SKIP", "reason": "Rule does not apply to this trade."}
        result = _resolve(rule.get("logic"), record)
        if not isinstance(result, bool):
            raise RuleEvaluationError("Rule expression did not evaluate to a boolean.")
        return {"status": "PASS" if result else "FAIL",
                "reason": None if result else (rule.get("impact") or rule.get("description") or "Rule condition failed.")}
    except RuleEvaluationError as exc:
        return {"status": "ERROR", "reason": str(exc)}
