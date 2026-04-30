"""
Tests for modules/trigger_expression.py

Covers:
  - _parse_window: valid units, invalid, edge cases
  - _tokenise: basic tokens, quoted strings, operators, error
  - _parse / AST construction: number, string, metric, aggregate,
    comparison, AND, OR, NOT, parentheses, errors
  - _eval_node: all operators, AND/OR short-circuit, NOT
  - _eval_metric: no store returns nan; state/uptime% paths;
    rtt/loss%/jitter latest vs aggregate
  - evaluate(): triggered, not triggered, error
  - preview_expression(): human-readable output
  - TriggerRule.validate(): valid/invalid expressions
  - load_rules / save_rules round-trip
  - new_rule_id: unique, correct length
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from types import SimpleNamespace
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from modules.trigger_expression import (
    ExpressionError,
    TriggerRule,
    _Number,
    _Str,
    _Metric,
    _BinOp,
    _UnaryOp,
    _eval_node,
    _parse,
    _parse_window,
    _tokenise,
    evaluate,
    load_rules,
    new_rule_id,
    preview_expression,
    save_rules,
)


# ── _parse_window ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("token,expected_s", [
    ("30s",  30.0),
    ("5m",   300.0),
    ("2h",   7200.0),
    ("1.5h", 5400.0),
    ("0s",   0.0),
    ("60S",  60.0),   # case-insensitive
    ("10M",  600.0),
])
def test_parse_window_valid(token, expected_s):
    assert _parse_window(token) == pytest.approx(expected_s)


@pytest.mark.parametrize("token", ["5x", "abc", "5", "", "5ms"])
def test_parse_window_invalid(token):
    with pytest.raises(ExpressionError):
        _parse_window(token)


# ── _tokenise ─────────────────────────────────────────────────────────────────

def test_tokenise_basic():
    tokens = _tokenise('rtt["1.2.3.4"] > 50')
    assert tokens == ['rtt', '[', '"1.2.3.4"', ']', '>', '50']


def test_tokenise_aggregate():
    tokens = _tokenise('avg(rtt["1.1.1.1"], 5m)')
    assert 'avg' in tokens
    assert '5m' in tokens


def test_tokenise_and_or():
    tokens = _tokenise('a AND b OR c')
    assert 'AND' in tokens
    assert 'OR' in tokens


def test_tokenise_bad_char():
    with pytest.raises(ExpressionError, match="Unexpected character"):
        _tokenise('rtt["1.2.3.4"] @ 50')


def test_tokenise_quoted_string():
    tokens = _tokenise('"DOWN"')
    assert tokens == ['"DOWN"']


# ── _parse: valid expressions ─────────────────────────────────────────────────

def test_parse_number():
    ast = _parse("50")
    assert isinstance(ast, _Number)
    assert ast.value == 50.0


def test_parse_metric_rtt():
    ast = _parse('rtt["1.2.3.4"]')
    assert isinstance(ast, _Metric)
    assert ast.func == "rtt"
    assert ast.ip == "1.2.3.4"
    assert ast.agg is None


def test_parse_metric_loss():
    ast = _parse('loss%["8.8.8.8"]')
    assert isinstance(ast, _Metric)
    assert ast.func == 'loss%'
    assert ast.ip == "8.8.8.8"


def test_parse_metric_state():
    ast = _parse('state["192.168.1.1"]')
    assert isinstance(ast, _Metric)
    assert ast.func == "state"


def test_parse_aggregate_avg():
    ast = _parse('avg(rtt["1.2.3.4"], 5m)')
    assert isinstance(ast, _Metric)
    assert ast.agg == "avg"
    assert ast.window_s == pytest.approx(300.0)


def test_parse_aggregate_max():
    ast = _parse('max(loss%["1.2.3.4"], 1h)')
    assert isinstance(ast, _Metric)
    assert ast.agg == "max"
    assert ast.func == 'loss%'


def test_parse_comparison():
    ast = _parse('rtt["1.1.1.1"] > 50')
    assert isinstance(ast, _BinOp)
    assert ast.op == ">"


def test_parse_and():
    ast = _parse('rtt["1.1.1.1"] > 50 AND loss%["1.1.1.1"] > 5')
    assert isinstance(ast, _BinOp)
    assert ast.op == "AND"


def test_parse_or():
    ast = _parse('rtt["1.1.1.1"] > 100 OR loss%["1.1.1.1"] > 10')
    assert isinstance(ast, _BinOp)
    assert ast.op == "OR"


def test_parse_not():
    ast = _parse('NOT rtt["1.1.1.1"] > 50')
    assert isinstance(ast, _UnaryOp)
    assert ast.op == "NOT"


def test_parse_parentheses():
    ast = _parse('(rtt["1.1.1.1"] > 50) AND (loss%["1.1.1.1"] > 5)')
    assert isinstance(ast, _BinOp)
    assert ast.op == "AND"


def test_parse_string_comparison():
    ast = _parse('state["192.168.1.1"] == "DOWN"')
    assert isinstance(ast, _BinOp)
    assert ast.op == "=="
    assert isinstance(ast.right, _Str)
    assert ast.right.value == "DOWN"


# ── _parse: error cases ───────────────────────────────────────────────────────

def test_parse_empty():
    with pytest.raises(ExpressionError, match="Empty"):
        _parse("")


def test_parse_unexpected_token():
    with pytest.raises(ExpressionError):
        _parse("rtt > 50 EXTRA")


def test_parse_missing_bracket():
    with pytest.raises(ExpressionError):
        _parse('rtt["1.2.3.4" > 50')


def test_parse_non_quoted_ip():
    with pytest.raises(ExpressionError):
        _parse("rtt[192.168.1.1] > 50")


# ── _eval_node: basic arithmetic comparisons ──────────────────────────────────

@pytest.mark.parametrize("op,lv,rv,expected", [
    (">",  60.0, 50.0, True),
    (">",  40.0, 50.0, False),
    ("<",  40.0, 50.0, True),
    (">=", 50.0, 50.0, True),
    ("<=", 50.0, 50.0, True),
    ("==", 5.0,  5.0,  True),
    ("!=", 5.0,  6.0,  True),
])
def test_eval_comparison(op, lv, rv, expected):
    node = _BinOp(op, _Number(lv), _Number(rv))
    assert _eval_node(node, None) is expected


def test_eval_and_both_true():
    node = _BinOp("AND",
                  _BinOp(">", _Number(60), _Number(50)),
                  _BinOp(">", _Number(10), _Number(5)))
    assert _eval_node(node, None) is True


def test_eval_and_one_false():
    node = _BinOp("AND",
                  _BinOp(">", _Number(40), _Number(50)),
                  _BinOp(">", _Number(10), _Number(5)))
    assert _eval_node(node, None) is False


def test_eval_or_one_true():
    node = _BinOp("OR",
                  _BinOp(">", _Number(40), _Number(50)),
                  _BinOp(">", _Number(10), _Number(5)))
    assert _eval_node(node, None) is True


def test_eval_not_true():
    node = _UnaryOp("NOT", _BinOp(">", _Number(40), _Number(50)))
    assert _eval_node(node, None) is True


def test_eval_string_equality():
    node = _BinOp("==", _Str("DOWN"), _Str("DOWN"))
    assert _eval_node(node, None) is True


def test_eval_string_inequality():
    node = _BinOp("!=", _Str("UP"), _Str("DOWN"))
    assert _eval_node(node, None) is True


# ── _eval_node with no store → NaN ───────────────────────────────────────────

def test_eval_metric_no_store_returns_nan():
    node = _Metric(func="rtt", ip="1.2.3.4")
    result = _eval_node(node, None)
    assert math.isnan(result)


# ── _eval_node with mock store ────────────────────────────────────────────────

def _make_store(rtt_samples: list, state_samples: list = None):
    RttPoint = SimpleNamespace
    store = MagicMock()
    store.query_rtt_history.return_value = [
        RttPoint(ts=0, host="x", rtt_ms=r, loss_pct=l, jitter_ms=j)
        for r, l, j in rtt_samples
    ]
    store.query_device_state_history.return_value = (
        [SimpleNamespace(state=s) for s in (state_samples or [])]
    )
    return store


def test_eval_metric_rtt_latest():
    store = _make_store([(10.0, 0.0, 1.0), (20.0, 0.0, 1.5)])
    node = _Metric(func="rtt", ip="1.2.3.4")
    assert _eval_node(node, store) == pytest.approx(20.0)


def test_eval_metric_loss_latest():
    store = _make_store([(10.0, 3.0, 1.0), (10.0, 7.0, 1.0)])
    node = _Metric(func="loss%", ip="1.2.3.4")
    assert _eval_node(node, store) == pytest.approx(7.0)


def test_eval_metric_jitter_latest():
    store = _make_store([(10.0, 0.0, 2.5), (10.0, 0.0, 4.0)])
    node = _Metric(func="jitter", ip="1.2.3.4")
    assert _eval_node(node, store) == pytest.approx(4.0)


def test_eval_metric_avg_rtt():
    store = _make_store([(10.0, 0.0, 0.0), (20.0, 0.0, 0.0), (30.0, 0.0, 0.0)])
    node = _Metric(func="rtt", ip="1.2.3.4", agg="avg", window_s=300)
    assert _eval_node(node, store) == pytest.approx(20.0)


def test_eval_metric_max_rtt():
    store = _make_store([(10.0, 0.0, 0.0), (50.0, 0.0, 0.0), (30.0, 0.0, 0.0)])
    node = _Metric(func="rtt", ip="x", agg="max", window_s=300)
    assert _eval_node(node, store) == pytest.approx(50.0)


def test_eval_metric_min_rtt():
    store = _make_store([(10.0, 0.0, 0.0), (50.0, 0.0, 0.0), (30.0, 0.0, 0.0)])
    node = _Metric(func="rtt", ip="x", agg="min", window_s=300)
    assert _eval_node(node, store) == pytest.approx(10.0)


def test_eval_metric_rtt_no_rows_nan():
    store = _make_store([])
    node = _Metric(func="rtt", ip="1.2.3.4")
    assert math.isnan(_eval_node(node, store))


def test_eval_metric_state():
    store = _make_store([], ["UP", "DOWN"])
    node = _Metric(func="state", ip="1.2.3.4")
    assert _eval_node(node, store) == "DOWN"


def test_eval_metric_state_unknown():
    store = _make_store([])
    store.query_device_state_history.return_value = []
    node = _Metric(func="state", ip="1.2.3.4")
    assert _eval_node(node, store) == "UNKNOWN"


def test_eval_metric_uptime_pct():
    store = _make_store([])
    store.query_device_state_history.return_value = [
        SimpleNamespace(state="UP"),
        SimpleNamespace(state="DOWN"),
        SimpleNamespace(state="UP"),
        SimpleNamespace(state="UP"),
    ]
    node = _Metric(func="uptime%", ip="1.2.3.4", window_s=3600)
    assert _eval_node(node, store) == pytest.approx(75.0)


# ── evaluate(): end-to-end ────────────────────────────────────────────────────

def test_evaluate_triggered():
    store = _make_store([(90.0, 0.0, 0.0)])
    rule = TriggerRule(id="x", name="x", expression='rtt["1.2.3.4"] > 80')
    triggered, lhs, err = evaluate(rule, store)
    assert triggered is True
    assert lhs == pytest.approx(90.0)
    assert err == ""


def test_evaluate_not_triggered():
    store = _make_store([(50.0, 0.0, 0.0)])
    rule = TriggerRule(id="x", name="x", expression='rtt["1.2.3.4"] > 80')
    triggered, lhs, err = evaluate(rule, store)
    assert triggered is False
    assert lhs == pytest.approx(50.0)


def test_evaluate_syntax_error():
    rule = TriggerRule(id="x", name="x", expression='rtt[1.2.3.4] > 50')
    triggered, lhs, err = evaluate(rule, None)
    assert triggered is False
    assert err != ""


def test_evaluate_no_store_not_triggered():
    rule = TriggerRule(id="x", name="x", expression='rtt["1.2.3.4"] > 50')
    triggered, lhs, err = evaluate(rule, None)
    assert triggered is False   # NaN > 50 is False


def test_evaluate_state_fired():
    store = _make_store([])
    store.query_device_state_history.return_value = [SimpleNamespace(state="DOWN")]
    rule = TriggerRule(id="x", name="x", expression='state["1.2.3.4"] == "DOWN"')
    triggered, lhs, err = evaluate(rule, store)
    assert triggered is True


# ── preview_expression ────────────────────────────────────────────────────────

def test_preview_empty():
    assert "Enter" in preview_expression("")


def test_preview_valid():
    p = preview_expression('rtt["1.2.3.4"] > 50')
    assert "rtt" in p
    assert "1.2.3.4" in p


def test_preview_syntax_error():
    p = preview_expression('rtt[1.2.3.4] > 50')
    assert "Syntax error" in p or "error" in p.lower()


def test_preview_avg():
    p = preview_expression('avg(rtt["1.2.3.4"], 5m)')
    assert "AVG" in p.upper() or "avg" in p.lower()
    assert "5m" in p or "over" in p


# ── TriggerRule.validate ──────────────────────────────────────────────────────

def test_rule_validate_ok():
    r = TriggerRule(id="a", name="a", expression='rtt["1.2.3.4"] > 50')
    assert r.validate() is None


def test_rule_validate_bad_expr():
    r = TriggerRule(id="a", name="a", expression='rtt[1.2.3.4] > 50')
    assert r.validate() is not None


def test_rule_validate_empty():
    r = TriggerRule(id="a", name="a", expression='')
    assert r.validate() is not None


# ── save_rules / load_rules ───────────────────────────────────────────────────

def test_save_load_roundtrip(tmp_path):
    rules = [
        TriggerRule(id="abc123", name="Test Rule",
                    expression='rtt["1.2.3.4"] > 80',
                    severity="WARNING", cooldown_s=120, enabled=True,
                    description="test"),
    ]
    with patch("modules.trigger_expression._rules_path", return_value=tmp_path / "r.json"):
        save_rules(rules)
        loaded = load_rules()
    assert len(loaded) == 1
    assert loaded[0].id == "abc123"
    assert loaded[0].name == "Test Rule"
    assert loaded[0].expression == 'rtt["1.2.3.4"] > 80'
    assert loaded[0].cooldown_s == 120


def test_load_rules_missing_file(tmp_path):
    with patch("modules.trigger_expression._rules_path",
               return_value=tmp_path / "nope.json"):
        loaded = load_rules()
    assert loaded == []


def test_load_rules_corrupt_file(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("not json", encoding="utf-8")
    with patch("modules.trigger_expression._rules_path", return_value=p):
        loaded = load_rules()
    assert loaded == []


# ── new_rule_id ───────────────────────────────────────────────────────────────

def test_new_rule_id_length():
    rid = new_rule_id()
    assert len(rid) == 12


def test_new_rule_id_unique():
    ids = {new_rule_id() for _ in range(100)}
    assert len(ids) == 100


def test_new_rule_id_hex():
    rid = new_rule_id()
    int(rid, 16)   # should not raise
