"""
trigger_expression.py — Custom alert trigger expression language.

Syntax
──────
  avg(rtt["192.168.1.1"], 5m) > 50
  loss%["192.168.1.1"] > 10
  avg(rtt["8.8.8.8"], 1h) > 100 AND loss%["8.8.8.8"] > 5
  jitter["10.0.0.1"] > 20
  state["192.168.1.254"] == "DOWN"
  avg(rtt["192.168.1.1"], 5m) > 50 OR loss%["192.168.1.1"] > 10

Functions / metrics
───────────────────
  rtt["<ip>"]             — latest RTT (ms) for a host; -1 if unreachable
  loss%["<ip>"]           — latest packet-loss % for a host
  jitter["<ip>"]          — latest jitter (ms) for a host; -1 if unknown
  avg(rtt["<ip>"], <window>) — rolling average RTT over <window> (e.g. 5m, 1h)
  avg(loss%["<ip>"], <window>) — rolling average loss% over window
  max(rtt["<ip>"], <window>) — rolling max RTT over window
  min(rtt["<ip>"], <window>) — rolling min RTT over window
  state["<ip>"]           — most recent availability state string ("UP"/"DOWN"/"DEGRADED")
  uptime%["<ip>", <window>] — uptime percentage over window

Operators: >  <  >=  <=  ==  !=  AND  OR  NOT  ( )

Window units: s, m, h  (e.g. 30s, 5m, 2h)

Architecture
────────────
  Pure Python — no PyQt imports (ARCH RULE modules layer).
  MetricStore is injected at eval time; can be None (returns NaN for all metrics).
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from modules.utils import get_app_data_dir


# ── TriggerRule dataclass ────────────────────────────────────────────────────

@dataclass
class TriggerRule:
    """A named custom alert trigger."""
    id: str                           # unique slug
    name: str
    expression: str                   # raw expression text
    severity: str = "WARNING"         # INFO / WARNING / CRITICAL
    cooldown_s: int = 300
    enabled: bool = True
    description: str = ""

    def validate(self) -> Optional[str]:
        """Return an error string if the expression is invalid, else None."""
        try:
            _parse(self.expression)
            return None
        except ExpressionError as exc:
            return str(exc)


@dataclass
class TriggerFired:
    rule_id: str
    rule_name: str
    severity: str
    expression: str
    result_value: float   # the LHS value that caused the trigger
    message: str
    ts: int = field(default_factory=lambda: int(time.time()))


# ── Exceptions ────────────────────────────────────────────────────────────────

class ExpressionError(ValueError):
    """Raised for syntax or semantic errors in a trigger expression."""


# ── Window parsing ────────────────────────────────────────────────────────────

_WINDOW_RE = re.compile(r'^(\d+(?:\.\d+)?)\s*([smh])$', re.IGNORECASE)

def _parse_window(token: str) -> float:
    """Parse a window string like '5m', '30s', '2h' into seconds (float)."""
    m = _WINDOW_RE.match(token.strip())
    if not m:
        raise ExpressionError(
            f"Invalid window {token!r}. Use a number followed by s/m/h (e.g. 5m, 30s, 2h).")
    value, unit = float(m.group(1)), m.group(2).lower()
    return value * {"s": 1, "m": 60, "h": 3600}[unit]


# ── Tokeniser ─────────────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(
    r'"[^"]*"'           # quoted string
    r'|[a-zA-Z_%][a-zA-Z0-9_%]*'   # identifier (includes loss%, uptime%)
    r'|\d+(?:\.\d+)?(?:[smh])?'    # number, optionally with window suffix
    r'|[><=!]=|[><()\[\],]'        # operators and punctuation (includes [] and ,)
    r'|\s+'                         # whitespace (skipped)
)


def _tokenise(expr: str) -> List[str]:
    tokens = []
    pos = 0
    while pos < len(expr):
        m = _TOKEN_RE.match(expr, pos)
        if not m:
            raise ExpressionError(
                f"Unexpected character {expr[pos]!r} at position {pos}.")
        tok = m.group(0)
        if not tok.strip():   # skip whitespace
            pos = m.end()
            continue
        tokens.append(tok)
        pos = m.end()
    return tokens


# ── AST nodes ─────────────────────────────────────────────────────────────────

class _Expr:
    """Base AST node."""


@dataclass
class _Number(_Expr):
    value: float


@dataclass
class _Str(_Expr):
    value: str


@dataclass
class _Metric(_Expr):
    """rtt["ip"] / loss%["ip"] / jitter["ip"] / state["ip"]"""
    func: str     # "rtt" | "loss%" | "jitter" | "state" | "uptime%"
    ip: str
    window_s: Optional[float] = None   # for avg/max/min wrapper
    agg: Optional[str] = None          # "avg" | "max" | "min"


@dataclass
class _BinOp(_Expr):
    op: str
    left: _Expr
    right: _Expr


@dataclass
class _UnaryOp(_Expr):
    op: str
    operand: _Expr


# ── Parser ────────────────────────────────────────────────────────────────────

class _Parser:
    def __init__(self, tokens: List[str]):
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> Optional[str]:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _consume(self, expected: Optional[str] = None) -> str:
        tok = self._peek()
        if tok is None:
            raise ExpressionError("Unexpected end of expression.")
        if expected is not None and tok != expected:
            raise ExpressionError(
                f"Expected {expected!r} but got {tok!r}.")
        self._pos += 1
        return tok

    def parse(self) -> _Expr:
        node = self._parse_or()
        if self._peek() is not None:
            raise ExpressionError(
                f"Unexpected token {self._peek()!r} after expression.")
        return node

    def _parse_or(self) -> _Expr:
        left = self._parse_and()
        while self._peek() and self._peek().upper() == "OR":
            self._consume()
            right = self._parse_and()
            left = _BinOp("OR", left, right)
        return left

    def _parse_and(self) -> _Expr:
        left = self._parse_not()
        while self._peek() and self._peek().upper() == "AND":
            self._consume()
            right = self._parse_not()
            left = _BinOp("AND", left, right)
        return left

    def _parse_not(self) -> _Expr:
        if self._peek() and self._peek().upper() == "NOT":
            self._consume()
            return _UnaryOp("NOT", self._parse_not())
        return self._parse_comparison()

    def _parse_comparison(self) -> _Expr:
        left = self._parse_primary()
        op = self._peek()
        if op in (">", "<", ">=", "<=", "==", "!="):
            self._consume()
            right = self._parse_primary()
            return _BinOp(op, left, right)
        return left

    def _parse_primary(self) -> _Expr:
        tok = self._peek()
        if tok is None:
            raise ExpressionError("Expected a value or expression.")

        # Parenthesised sub-expression
        if tok == "(":
            self._consume("(")
            node = self._parse_or()
            self._consume(")")
            return node

        # Aggregate function: avg(metric, window) / max(…) / min(…)
        if tok.lower() in ("avg", "max", "min"):
            agg = tok.lower()
            self._consume()
            self._consume("(")
            metric = self._parse_metric()
            self._consume(",")
            win_tok = self._consume()
            window_s = _parse_window(win_tok)
            self._consume(")")
            metric.agg = agg
            metric.window_s = window_s
            return metric

        # Plain metric: rtt["ip"] / loss%["ip"] / jitter["ip"] / state["ip"] / uptime%["ip"]
        if tok.lower() in ("rtt", 'loss%', "jitter", "state", 'uptime%'):
            return self._parse_metric()

        # String literal  (e.g. "DOWN")
        if tok.startswith('"'):
            self._consume()
            return _Str(tok[1:-1])

        # Number
        try:
            val = float(tok)
            self._consume()
            return _Number(val)
        except ValueError:
            pass  # non-fatal

        raise ExpressionError(f"Unexpected token {tok!r}.")

    def _parse_metric(self) -> _Metric:
        """Parse rtt["ip"] / loss%["ip"] etc. (square-bracket subscript)."""
        func = self._consume().lower()
        self._consume("[")
        ip_tok = self._consume()
        if not ip_tok.startswith('"'):
            raise ExpressionError(
                f"Expected a quoted IP address after {func}[, got {ip_tok!r}.")
        ip = ip_tok[1:-1]
        self._consume("]")
        return _Metric(func=func, ip=ip)


def _parse(expression: str) -> _Expr:
    """Parse an expression string into an AST. Raises ExpressionError on failure."""
    tokens = _tokenise(expression)
    if not tokens:
        raise ExpressionError("Empty expression.")
    return _Parser(tokens).parse()


# ── Evaluator ─────────────────────────────────────────────────────────────────

def _eval_node(node: _Expr, store: Optional[object]) -> Any:
    """Recursively evaluate an AST node against MetricStore data."""

    if isinstance(node, _Number):
        return node.value

    if isinstance(node, _Str):
        return node.value

    if isinstance(node, _Metric):
        return _eval_metric(node, store)

    if isinstance(node, _UnaryOp):
        val = _eval_node(node.operand, store)
        if node.op == "NOT":
            return not bool(val)
        raise ExpressionError(f"Unknown unary operator {node.op!r}.")

    if isinstance(node, _BinOp):
        if node.op == "AND":
            return bool(_eval_node(node.left, store)) and bool(_eval_node(node.right, store))
        if node.op == "OR":
            return bool(_eval_node(node.left, store)) or bool(_eval_node(node.right, store))

        lv = _eval_node(node.left, store)
        rv = _eval_node(node.right, store)

        # Numeric comparisons
        if node.op == ">":   return float(lv) > float(rv)
        if node.op == "<":   return float(lv) < float(rv)
        if node.op == ">=":  return float(lv) >= float(rv)
        if node.op == "<=":  return float(lv) <= float(rv)
        if node.op == "==":  return lv == rv
        if node.op == "!=":  return lv != rv
        raise ExpressionError(f"Unknown operator {node.op!r}.")

    raise ExpressionError(f"Unknown AST node type: {type(node).__name__}")


def _eval_metric(node: _Metric, store: Optional[object]) -> Any:
    """Resolve a _Metric node to a float or string using MetricStore data."""
    if store is None:
        return math.nan

    ip = node.ip
    func = node.func
    window_s = node.window_s
    agg = node.agg

    # state["ip"] — return string
    if func == "state":
        rows = store.query_device_state_history(ip, hours=1.0)
        if not rows:
            return "UNKNOWN"
        return rows[-1].state

    # uptime%["ip"] — percentage of UP states in window
    if func == "uptime%":
        hours = (window_s or 3600) / 3600.0
        rows = store.query_device_state_history(ip, hours=hours)
        if not rows:
            return 0.0
        up = sum(1 for r in rows if r.state == "UP")
        return up / len(rows) * 100.0

    # RTT/loss/jitter metrics
    hours = (window_s or 300) / 3600.0
    rows = store.query_rtt_history(ip, hours=hours)

    if not rows:
        return math.nan

    if func == "rtt":
        values = [r.rtt_ms for r in rows if r.rtt_ms >= 0]
    elif func == "loss%":
        values = [r.loss_pct for r in rows]
    elif func == "jitter":
        values = [r.jitter_ms for r in rows if r.jitter_ms >= 0]
    else:
        return math.nan

    if not values:
        return math.nan

    if agg is None:
        return values[-1]   # latest sample
    if agg == "avg":
        return sum(values) / len(values)
    if agg == "max":
        return max(values)
    if agg == "min":
        return min(values)
    return math.nan


# ── Public API ────────────────────────────────────────────────────────────────

def evaluate(rule: TriggerRule, store: Optional[object]) -> Tuple[bool, float, str]:
    """
    Evaluate a TriggerRule against live MetricStore data.

    Returns
    -------
    (triggered: bool, lhs_value: float, error_message: str)
    error_message is non-empty only on ExpressionError.
    """
    try:
        ast = _parse(rule.expression)
        result = _eval_node(ast, store)
        # For comparisons the result is a bool; for bare metrics it's a number
        triggered = bool(result) if not isinstance(result, float) else (
            result > 0 and not math.isnan(result))
        # Try to extract the LHS numeric value for reporting
        lhs = _extract_lhs(ast, store)
        return triggered, lhs, ""
    except ExpressionError as exc:
        return False, math.nan, str(exc)
    except Exception as exc:
        return False, math.nan, f"Evaluation error: {exc}"


def _extract_lhs(ast: _Expr, store: Optional[object]) -> float:
    """Best-effort extraction of the LHS numeric metric value from a comparison."""
    if isinstance(ast, _BinOp) and ast.op in (">", "<", ">=", "<=", "==", "!="):
        v = _eval_node(ast.left, store)
        try:
            return float(v)
        except (TypeError, ValueError):
            pass  # non-fatal
    if isinstance(ast, _BinOp) and ast.op in ("AND", "OR"):
        v = _extract_lhs(ast.left, store)
        if not math.isnan(v):
            return v
        return _extract_lhs(ast.right, store)
    return math.nan


# ── Rule persistence ──────────────────────────────────────────────────────────

import json
import uuid


def _rules_path() -> Path:
    return get_app_data_dir() / "trigger_rules.json"


def load_rules() -> List[TriggerRule]:
    """Load saved TriggerRule list from disk. Returns [] if file absent."""
    p = _rules_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return [TriggerRule(**r) for r in data]
    except Exception:
        return []


def save_rules(rules: List[TriggerRule]) -> None:
    """Persist TriggerRule list to disk."""
    p = _rules_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps([r.__dict__ for r in rules], indent=2),
        encoding="utf-8",
    )


def new_rule_id() -> str:
    return uuid.uuid4().hex[:12]


# ── Expression preview helper ─────────────────────────────────────────────────

def preview_expression(expression: str) -> str:
    """
    Return a human-readable description of what an expression tests.
    Used by the rule builder UI for live preview.
    """
    if not expression.strip():
        return "Enter an expression above."
    try:
        ast = _parse(expression)
        return _describe(ast)
    except ExpressionError as exc:
        return f"Syntax error: {exc}"


def _describe(node: _Expr) -> str:
    if isinstance(node, _Number):
        return str(node.value)
    if isinstance(node, _Str):
        return repr(node.value)
    if isinstance(node, _Metric):
        window = ""
        if node.window_s is not None:
            s = node.window_s
            if s >= 3600 and s % 3600 == 0:
                window = f" over {int(s/3600)}h"
            elif s >= 60 and s % 60 == 0:
                window = f" over {int(s/60)}m"
            else:
                window = f" over {int(s)}s"
        agg = f"{node.agg.upper()} " if node.agg else "latest "
        return f"{agg}{node.func} for {node.ip}{window}"
    if isinstance(node, _UnaryOp):
        return f"NOT ({_describe(node.operand)})"
    if isinstance(node, _BinOp):
        if node.op in ("AND", "OR"):
            return f"({_describe(node.left)}) {node.op} ({_describe(node.right)})"
        return f"{_describe(node.left)} {node.op} {_describe(node.right)}"
    return "?"
