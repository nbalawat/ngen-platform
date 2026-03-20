"""Workflow shared state and safe condition evaluation."""

from __future__ import annotations

import ast
import asyncio
import operator
from typing import Any

from workflow_engine.errors import ConditionEvalError

# ---------------------------------------------------------------------------
# Safe condition evaluator
# ---------------------------------------------------------------------------

# Whitelisted comparison and boolean operators for condition evaluation.
_SAFE_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
    ast.And: None,  # handled specially
    ast.Or: None,
    ast.Not: operator.not_,
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
}


def _safe_eval_node(node: ast.AST, state: dict[str, Any]) -> Any:
    """Recursively evaluate an AST node against the state dict."""
    if isinstance(node, ast.Expression):
        return _safe_eval_node(node.body, state)

    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        if node.id in state:
            return state[node.id]
        raise ConditionEvalError(
            ast.dump(node), f"Unknown variable '{node.id}'"
        )

    if isinstance(node, ast.Attribute):
        # Allow state["obj"].attr style — evaluate the value, then getattr
        value = _safe_eval_node(node.value, state)
        if isinstance(value, dict):
            if node.attr in value:
                return value[node.attr]
            raise ConditionEvalError(
                ast.dump(node), f"Key '{node.attr}' not found"
            )
        raise ConditionEvalError(
            ast.dump(node), "Attribute access only supported on dict values"
        )

    if isinstance(node, ast.Subscript):
        value = _safe_eval_node(node.value, state)
        key = _safe_eval_node(node.slice, state)
        try:
            return value[key]
        except (KeyError, IndexError, TypeError) as exc:
            raise ConditionEvalError(ast.dump(node), str(exc)) from exc

    if isinstance(node, ast.Compare):
        left = _safe_eval_node(node.left, state)
        for op_node, comparator in zip(node.ops, node.comparators):
            op_type = type(op_node)
            if op_type not in _SAFE_OPS:
                raise ConditionEvalError(
                    ast.dump(node), f"Unsupported operator: {op_type.__name__}"
                )
            right = _safe_eval_node(comparator, state)
            op_fn = _SAFE_OPS[op_type]
            if not op_fn(left, right):
                return False
            left = right
        return True

    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(_safe_eval_node(v, state) for v in node.values)
        if isinstance(node.op, ast.Or):
            return any(_safe_eval_node(v, state) for v in node.values)
        raise ConditionEvalError(
            ast.dump(node), f"Unsupported boolean op: {type(node.op).__name__}"
        )

    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.Not):
            return not _safe_eval_node(node.operand, state)
        raise ConditionEvalError(
            ast.dump(node), f"Unsupported unary op: {type(node.op).__name__}"
        )

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPS:
            raise ConditionEvalError(
                ast.dump(node), f"Unsupported binary op: {op_type.__name__}"
            )
        left = _safe_eval_node(node.left, state)
        right = _safe_eval_node(node.right, state)
        return _SAFE_OPS[op_type](left, right)

    if isinstance(node, (ast.List, ast.Tuple)):
        return [_safe_eval_node(el, state) for el in node.elts]

    raise ConditionEvalError(
        ast.dump(node), f"Unsupported AST node: {type(node).__name__}"
    )


def safe_eval_condition(condition: str, state: dict[str, Any]) -> bool:
    """Safely evaluate a condition string against workflow state.

    Only allows comparisons, boolean logic, variable lookups, and literals.
    No function calls, imports, or builtins access.

    Returns:
        True if the condition evaluates to a truthy value, False otherwise.

    Raises:
        ConditionEvalError: If the condition contains unsafe constructs or
            references unknown variables.
    """
    try:
        tree = ast.parse(condition, mode="eval")
    except SyntaxError as exc:
        raise ConditionEvalError(condition, f"Syntax error: {exc}") from exc

    # Walk the AST and reject any dangerous nodes
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            raise ConditionEvalError(condition, "Function calls are not allowed")
        if isinstance(node, ast.Import | ast.ImportFrom):
            raise ConditionEvalError(condition, "Imports are not allowed")

    result = _safe_eval_node(tree, state)
    return bool(result)


# ---------------------------------------------------------------------------
# Workflow state container
# ---------------------------------------------------------------------------


class WorkflowState:
    """Thread-safe shared state container for workflow execution.

    Holds key-value state data and per-agent output history.
    All mutations are guarded by an asyncio.Lock.
    """

    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = dict(initial) if initial else {}
        self._agent_outputs: dict[str, list[dict[str, Any]]] = {}
        self._current_agent: str | None = None
        self._lock = asyncio.Lock()

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the state (lock-free read)."""
        return self._data.get(key, default)

    async def set(self, key: str, value: Any) -> None:
        """Set a value in the state."""
        async with self._lock:
            self._data[key] = value

    async def merge(self, other: dict[str, Any]) -> None:
        """Merge a dictionary into the state."""
        async with self._lock:
            self._data.update(other)

    async def record_agent_output(
        self, agent_name: str, output: dict[str, Any]
    ) -> None:
        """Record an agent's output."""
        async with self._lock:
            if agent_name not in self._agent_outputs:
                self._agent_outputs[agent_name] = []
            self._agent_outputs[agent_name].append(output)

    @property
    def current_agent(self) -> str | None:
        return self._current_agent

    async def set_current_agent(self, agent_name: str | None) -> None:
        async with self._lock:
            self._current_agent = agent_name

    @property
    def agent_outputs(self) -> dict[str, list[dict[str, Any]]]:
        return dict(self._agent_outputs)

    def to_dict(self) -> dict[str, Any]:
        """Return a snapshot of the current state data."""
        return dict(self._data)
