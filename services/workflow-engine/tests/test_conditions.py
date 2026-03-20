"""Tests for safe_eval_condition."""

from __future__ import annotations

import pytest

from workflow_engine.errors import ConditionEvalError
from workflow_engine.state import safe_eval_condition


class TestSafeEvalCondition:
    def test_simple_equality(self):
        assert safe_eval_condition("x == 1", {"x": 1}) is True
        assert safe_eval_condition("x == 1", {"x": 2}) is False

    def test_string_equality(self):
        assert safe_eval_condition("status == 'done'", {"status": "done"}) is True
        assert safe_eval_condition("status == 'done'", {"status": "pending"}) is False

    def test_comparisons(self):
        state = {"count": 10}
        assert safe_eval_condition("count > 5", state) is True
        assert safe_eval_condition("count < 5", state) is False
        assert safe_eval_condition("count >= 10", state) is True
        assert safe_eval_condition("count <= 10", state) is True
        assert safe_eval_condition("count != 5", state) is True

    def test_boolean_and(self):
        state = {"a": True, "b": True}
        assert safe_eval_condition("a and b", state) is True
        state["b"] = False
        assert safe_eval_condition("a and b", state) is False

    def test_boolean_or(self):
        state = {"a": False, "b": True}
        assert safe_eval_condition("a or b", state) is True
        state["b"] = False
        assert safe_eval_condition("a or b", state) is False

    def test_not(self):
        assert safe_eval_condition("not x", {"x": False}) is True
        assert safe_eval_condition("not x", {"x": True}) is False

    def test_combined(self):
        state = {"score": 85, "passed": True}
        assert safe_eval_condition("score > 80 and passed", state) is True
        assert safe_eval_condition("score > 90 or passed", state) is True
        assert safe_eval_condition("score > 90 and passed", state) is False

    def test_in_operator(self):
        state = {"role": "admin", "roles": ["admin", "user"]}
        assert safe_eval_condition("role in roles", state) is True
        assert safe_eval_condition("'admin' in roles", state) is True
        assert safe_eval_condition("'guest' in roles", state) is False

    def test_subscript_access(self):
        state = {"data": {"key": "value"}}
        assert safe_eval_condition("data['key'] == 'value'", state) is True

    def test_arithmetic(self):
        state = {"a": 3, "b": 4}
        assert safe_eval_condition("a + b == 7", state) is True
        assert safe_eval_condition("a * b == 12", state) is True

    def test_rejects_function_calls(self):
        with pytest.raises(ConditionEvalError, match="Function calls are not allowed"):
            safe_eval_condition("len(x) > 0", {"x": [1, 2]})

    def test_rejects_imports(self):
        with pytest.raises(ConditionEvalError, match="Function calls are not allowed"):
            safe_eval_condition("__import__('os')", {})

    def test_rejects_exec(self):
        with pytest.raises(ConditionEvalError, match="Function calls are not allowed"):
            safe_eval_condition("exec('print(1)')", {})

    def test_syntax_error(self):
        with pytest.raises(ConditionEvalError, match="Syntax error"):
            safe_eval_condition("x ==== y", {"x": 1, "y": 1})

    def test_unknown_variable(self):
        with pytest.raises(ConditionEvalError, match="Unknown variable"):
            safe_eval_condition("nonexistent > 0", {})

    def test_constants(self):
        assert safe_eval_condition("True", {}) is True
        assert safe_eval_condition("False", {}) is False
        assert safe_eval_condition("1 == 1", {}) is True

    def test_chained_comparison(self):
        assert safe_eval_condition("1 < x < 10", {"x": 5}) is True
        assert safe_eval_condition("1 < x < 10", {"x": 15}) is False
