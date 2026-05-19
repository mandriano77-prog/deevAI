"""Sandboxed interpreter for the DV360 custom-bidding DSL.

This is the runtime counterpart of :mod:`sandbox_validator`. The
validator says "this script *could* be DV360-legal". The interpreter
says "for *this* impression's signals, the script evaluates to *this*
score (or None)".

Why we need it
--------------
DV360 only tells you what a script does after you upload it and let
real money run through it. Before that, we want to simulate the script
locally against historical Floodlight / Bid Manager Reporting rows so
the customer can see the score distribution *before* anything is
billed.

Security stance
---------------
The script the interpreter runs is generated from user-supplied slider
values and (in the longer term) custom criteria. We therefore treat
the DSL source as **untrusted code** and refuse to use ``eval`` or
``exec`` under any circumstance.

The implementation is a hand-rolled AST walker:

- Parse with :func:`ast.parse`.
- Re-validate every node against the same whitelist used at upload
  time (we import :data:`sandbox_validator._ALLOWED_NODES` as the
  source of truth).
- Walk the tree node-by-node and dispatch to ``_eval_*`` helpers.
- Free names resolve to per-impression signal values via a
  ``SignalResolver`` callback.

No node type that isn't in the whitelist is ever evaluated. No
attribute access, no subscripting, no comprehension — those would
already be rejected at the static-validation step, but we double-check
at runtime too in case the interpreter is invoked on an un-validated
script.
"""

from __future__ import annotations

import ast
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from .feature_catalog import (
    AGGREGATE_FUNCTIONS,
    CASTING_FUNCTIONS,
    FUNCTIONS_BY_NAME,
    MATH_FUNCTIONS,
    SIGNALS_BY_NAME,
)
from .sandbox_validator import _ALLOWED_NODES, validate_script


# ─────────────────────────────────────────────────────────────────── errors


class DSLError(Exception):
    """Base class for all interpreter errors."""


class DSLValidationError(DSLError):
    """Raised when the script can't pass the static sandbox check.

    The interpreter refuses to run an un-validated script, so this
    error surfaces whatever the validator would have surfaced at
    upload time.
    """


class DSLRuntimeError(DSLError):
    """Raised when a structurally-valid script fails at evaluation
    time — e.g. ``log`` of a non-positive number, division by zero, or
    a signal returning an incompatible type."""


# ──────────────────────────────────────────────────────────── value helpers


# Signal-resolver protocol: given (signal_name, *args) → value (or None).
# Variable-style signals receive an empty arg tuple; callable signals
# (e.g. total_conversion_value) receive the call's positional args.
SignalResolver = Callable[[str, tuple[Any, ...]], Any]


@dataclass
class _EvalContext:
    """Per-impression execution state.

    ``resolver`` is the only side-channel into the world — every signal
    read goes through it, and the interpreter records which names were
    consulted (and whether they yielded a non-None value) so callers
    can compute feature-coverage stats.
    """
    resolver: SignalResolver
    used_signals: set[str] = field(default_factory=set)
    used_non_none: set[str] = field(default_factory=set)


def _is_truthy(value: Any) -> bool:
    """DV360 truthiness mirrors Python — but None always falsy.

    We special-case the comparison-result sentinel (``NotImplemented``)
    as falsy so a buggy `in` against a non-list doesn't propagate.
    """
    if value is None or value is NotImplemented:
        return False
    return bool(value)


# ────────────────────────────────────────────────────────── compile + run


@dataclass(frozen=True)
class CompiledScript:
    """A parsed-and-validated DSL script, ready for repeated evaluation.

    Re-parsing on every impression would be wasteful (DV360 scripts can
    be re-evaluated millions of times in a simulator run). We parse
    once, hold the AST, and reuse it for every call to :func:`evaluate`.
    """
    tree: ast.Module
    source: str


def compile_script(source: str) -> CompiledScript:
    """Parse + validate a DSL script.

    Raises:
        DSLValidationError: if the static validator finds anything
            wrong. We surface the validator issues verbatim — they
            already carry line numbers.
    """
    report = validate_script(source)
    if report.has_errors:
        details = "\n".join(str(i) for i in report.issues)
        raise DSLValidationError(f"DSL script failed sandbox validation:\n{details}")

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:  # pragma: no cover — validator already caught this
        raise DSLValidationError(str(exc)) from exc

    return CompiledScript(tree=tree, source=source)


def evaluate(
    compiled: CompiledScript,
    resolver: SignalResolver,
) -> tuple[Any, set[str], set[str]]:
    """Evaluate the script for one impression.

    Returns ``(value, used_signals, used_non_none)``:
      - ``value``: the script's return — a number (the score), or ``None``
        if the script chose to exclude this impression.
      - ``used_signals``: set of signal names that were read at least
        once during evaluation (regardless of value).
      - ``used_non_none``: subset of ``used_signals`` whose resolver
        returned a non-None value.

    Raises:
        DSLRuntimeError: if the script triggers an arithmetic or type
            error during evaluation.
    """
    ctx = _EvalContext(resolver=resolver)
    try:
        # The module body is a sequence of statements. The only
        # statement types we allow are If and Return (validator
        # enforces this), so we iterate top-level and dispatch.
        return_value = _exec_block(compiled.tree.body, ctx)
    except _ReturnSignal as ret:
        return_value = ret.value
    return return_value, ctx.used_signals, ctx.used_non_none


# ──────────────────────────────────────────────────────────── execution


class _ReturnSignal(Exception):
    """Internal control-flow exception that carries a return value out
    of nested ``if`` blocks. Using an exception (vs a sentinel) keeps
    the recursion simple and avoids a return-value bubble pattern in
    every helper.
    """
    def __init__(self, value: Any):
        self.value = value


def _exec_block(stmts: list[ast.stmt], ctx: _EvalContext) -> Any:
    """Execute a list of statements; raises _ReturnSignal on return.

    If we fall off the end without a return, that's an error — the
    validator should already have caught it, but we double-check.
    """
    for stmt in stmts:
        _exec_stmt(stmt, ctx)
    raise DSLRuntimeError("Script terminated without returning a value.")


def _exec_stmt(stmt: ast.stmt, ctx: _EvalContext) -> None:
    if type(stmt) not in _ALLOWED_NODES:
        raise DSLValidationError(
            f"Statement node {type(stmt).__name__} is not allowed."
        )

    if isinstance(stmt, ast.Return):
        if stmt.value is None:
            # Bare ``return`` — validator forbids it, but defend anyway.
            raise DSLRuntimeError("Bare `return` is not allowed.")
        value = _eval_expr(stmt.value, ctx)
        raise _ReturnSignal(value)

    if isinstance(stmt, ast.If):
        cond = _eval_expr(stmt.test, ctx)
        body = stmt.body if _is_truthy(cond) else stmt.orelse
        for inner in body:
            _exec_stmt(inner, ctx)
        return

    if isinstance(stmt, ast.Expr):
        # Top-level bare expression — DV360 doesn't really use this, but
        # eval it for side-effect-free completeness.
        _eval_expr(stmt.value, ctx)
        return

    raise DSLValidationError(
        f"Statement type {type(stmt).__name__} is not supported."
    )


# ──────────────────────────────────────────────────────────── expressions


def _eval_expr(node: ast.expr, ctx: _EvalContext) -> Any:
    """Recursive AST evaluator — explicit dispatch, no `eval`."""
    if type(node) not in _ALLOWED_NODES:
        raise DSLValidationError(
            f"Expression node {type(node).__name__} is not allowed."
        )

    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        return _resolve_name(node.id, ctx)

    if isinstance(node, ast.List):
        return [_eval_expr(elt, ctx) for elt in node.elts]

    if isinstance(node, ast.Tuple):
        return tuple(_eval_expr(elt, ctx) for elt in node.elts)

    if isinstance(node, ast.BinOp):
        return _eval_binop(node, ctx)

    if isinstance(node, ast.UnaryOp):
        return _eval_unaryop(node, ctx)

    if isinstance(node, ast.BoolOp):
        return _eval_boolop(node, ctx)

    if isinstance(node, ast.Compare):
        return _eval_compare(node, ctx)

    if isinstance(node, ast.IfExp):
        cond = _eval_expr(node.test, ctx)
        chosen = node.body if _is_truthy(cond) else node.orelse
        return _eval_expr(chosen, ctx)

    if isinstance(node, ast.Call):
        return _eval_call(node, ctx)

    raise DSLValidationError(
        f"Unsupported expression node {type(node).__name__}."
    )


def _resolve_name(name: str, ctx: _EvalContext) -> Any:
    """Resolve a free identifier — could be a builtin constant or a
    variable-style signal. Callable signals/functions are handled in
    :func:`_eval_call`."""
    if name == "None":
        return None
    if name == "True":
        return True
    if name == "False":
        return False
    if name in SIGNALS_BY_NAME and not SIGNALS_BY_NAME[name].is_callable:
        value = ctx.resolver(name, ())
        ctx.used_signals.add(name)
        if value is not None:
            ctx.used_non_none.add(name)
        return value
    if name in FUNCTIONS_BY_NAME:
        # A builtin function used as a bare name (not called) doesn't
        # have a useful value in DV360 — disallow.
        raise DSLRuntimeError(f"Built-in `{name}` must be called with `()`.")
    if name in SIGNALS_BY_NAME and SIGNALS_BY_NAME[name].is_callable:
        raise DSLRuntimeError(
            f"Signal `{name}` is callable — use `{name}(...)`."
        )
    raise DSLValidationError(f"Unknown identifier: `{name}`")


# ──────────────────────────────────────────────────────────── operators


_BINOP_TABLE = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a ** b,
}


def _eval_binop(node: ast.BinOp, ctx: _EvalContext) -> Any:
    left = _eval_expr(node.left, ctx)
    right = _eval_expr(node.right, ctx)
    op_cls = type(node.op)
    fn = _BINOP_TABLE.get(op_cls)
    if fn is None:
        raise DSLValidationError(f"Binary op {op_cls.__name__} not allowed.")
    # Coerce None to 0 for arithmetic — DV360 docs say missing signals
    # behave as their zero-value, and this matches the validator's
    # tolerance of None constants.
    if left is None:
        left = 0
    if right is None:
        right = 0
    try:
        return fn(left, right)
    except ZeroDivisionError as exc:
        raise DSLRuntimeError(f"Division by zero in script: {exc}") from exc
    except TypeError as exc:
        raise DSLRuntimeError(
            f"Type error in binary op {op_cls.__name__}: {exc}"
        ) from exc


def _eval_unaryop(node: ast.UnaryOp, ctx: _EvalContext) -> Any:
    val = _eval_expr(node.operand, ctx)
    if isinstance(node.op, ast.USub):
        return -val if val is not None else 0
    if isinstance(node.op, ast.UAdd):
        return +val if val is not None else 0
    if isinstance(node.op, ast.Not):
        return not _is_truthy(val)
    raise DSLValidationError(f"Unary op {type(node.op).__name__} not allowed.")


def _eval_boolop(node: ast.BoolOp, ctx: _EvalContext) -> Any:
    """Short-circuit `and` / `or` — matches Python semantics."""
    if isinstance(node.op, ast.And):
        last: Any = True
        for v in node.values:
            last = _eval_expr(v, ctx)
            if not _is_truthy(last):
                return last
        return last
    if isinstance(node.op, ast.Or):
        for v in node.values:
            val = _eval_expr(v, ctx)
            if _is_truthy(val):
                return val
        return val  # last falsy
    raise DSLValidationError(f"Bool op {type(node.op).__name__} not allowed.")


_COMPARE_TABLE = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
}


def _eval_compare(node: ast.Compare, ctx: _EvalContext) -> bool:
    """Chained comparisons (a < b < c) AND together — exactly Python."""
    left = _eval_expr(node.left, ctx)
    for op, right_node in zip(node.ops, node.comparators):
        right = _eval_expr(right_node, ctx)
        if isinstance(op, ast.In):
            ok = _in(left, right)
        elif isinstance(op, ast.NotIn):
            ok = not _in(left, right)
        else:
            op_cls = type(op)
            fn = _COMPARE_TABLE.get(op_cls)
            if fn is None:
                raise DSLValidationError(
                    f"Comparator {op_cls.__name__} not allowed."
                )
            # None == None is True; None == 0 is False. None compared
            # to a number with </> is treated as 0 to mirror missing
            # data in real Floodlight rows.
            try:
                ok = fn(left if left is not None else 0,
                        right if right is not None else 0) if op_cls not in (ast.Eq, ast.NotEq) \
                    else fn(left, right)
            except TypeError as exc:
                raise DSLRuntimeError(
                    f"Type error in compare {op_cls.__name__}: {exc}"
                ) from exc
        if not ok:
            return False
        left = right
    return True


def _in(needle: Any, haystack: Any) -> bool:
    """Implementation of `in` / `not in`. Lists, tuples, and strings
    are supported; anything else returns False (rather than raising)
    to mimic DV360's tolerant runtime."""
    if haystack is None:
        return False
    if isinstance(haystack, (list, tuple, str)):
        try:
            return needle in haystack
        except TypeError:
            return False
    return False


# ──────────────────────────────────────────────────────────────── calls


def _eval_call(node: ast.Call, ctx: _EvalContext) -> Any:
    """Dispatch a call to one of: aggregate, cast, math, or callable
    signal. Anything else is rejected."""
    if not isinstance(node.func, ast.Name):
        raise DSLValidationError(
            "Only direct function calls are allowed (no attribute calls)."
        )
    if node.keywords:
        raise DSLValidationError("Keyword arguments are not allowed in DSL calls.")

    fname = node.func.id
    args = [_eval_expr(a, ctx) for a in node.args]

    # Aggregates take a list of (criteria_list, weight) pairs.
    if fname in AGGREGATE_FUNCTIONS:
        return _eval_aggregate(fname, args)

    if fname in CASTING_FUNCTIONS:
        return _eval_cast(fname, args)

    if fname in MATH_FUNCTIONS:
        return _eval_math(fname, args)

    if fname in SIGNALS_BY_NAME and SIGNALS_BY_NAME[fname].is_callable:
        ctx.used_signals.add(fname)
        value = ctx.resolver(fname, tuple(args))
        if value is not None:
            ctx.used_non_none.add(fname)
        return value

    raise DSLValidationError(f"Call to unknown function `{fname}`.")


def _eval_aggregate(fname: str, args: list[Any]) -> float:
    """Evaluate one of the three DV360 aggregate functions.

    Argument shape (from the DV360 doc): a single list, whose elements
    are pairs ``(criteria_list, weight)``. ``criteria_list`` is itself a
    list of bool-ish values; the criterion is true iff *all* are truthy.
    """
    if len(args) != 1 or not isinstance(args[0], list):
        raise DSLRuntimeError(
            f"{fname} expects a single list argument, got {len(args)} arg(s)."
        )

    pairs = args[0]
    contributions: list[float] = []

    for entry in pairs:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise DSLRuntimeError(
                f"{fname}: each entry must be a 2-tuple `([criteria], weight)`."
            )
        criteria, weight = entry
        if not isinstance(criteria, (list, tuple)):
            raise DSLRuntimeError(
                f"{fname}: criteria slot must be a list of conditions."
            )
        all_true = all(_is_truthy(c) for c in criteria)
        if all_true:
            try:
                w = float(weight) if weight is not None else 0.0
            except (TypeError, ValueError) as exc:
                raise DSLRuntimeError(
                    f"{fname}: weight `{weight!r}` is not numeric: {exc}"
                ) from exc
            contributions.append(w)

    if not contributions:
        return 0.0

    if fname == "sum_aggregate":
        return float(sum(contributions))
    if fname == "max_aggregate":
        return float(max(contributions))
    if fname == "first_match_aggregate":
        return float(contributions[0])

    raise DSLValidationError(f"Unknown aggregate `{fname}`.")  # pragma: no cover


def _eval_cast(fname: str, args: list[Any]) -> Any:
    if len(args) != 1:
        raise DSLRuntimeError(f"{fname}() takes exactly 1 argument.")
    x = args[0]
    try:
        if fname == "bool":
            return _is_truthy(x)
        if fname == "int":
            return int(x) if x is not None else 0
        if fname == "float":
            return float(x) if x is not None else 0.0
        if fname == "str":
            return str(x) if x is not None else ""
    except (TypeError, ValueError) as exc:
        raise DSLRuntimeError(f"{fname}() cast failed on {x!r}: {exc}") from exc
    raise DSLValidationError(f"Unknown cast `{fname}`.")  # pragma: no cover


def _eval_math(fname: str, args: list[Any]) -> float:
    if fname == "log":
        if len(args) not in (1, 2):
            raise DSLRuntimeError("log() takes 1 or 2 arguments.")
        x = args[0]
        if x is None or x <= 0:
            raise DSLRuntimeError(f"log() requires positive argument, got {x!r}.")
        if len(args) == 1:
            return math.log(x)
        base = args[1]
        if base is None or base <= 0 or base == 1:
            raise DSLRuntimeError(f"log() base must be positive ≠ 1, got {base!r}.")
        return math.log(x) / math.log(base)
    raise DSLValidationError(f"Unknown math fn `{fname}`.")  # pragma: no cover


# ─────────────────────────────────────────────────────────── conveniences


def run_with_signals(source: str, signals: Mapping[str, Any]) -> Any:
    """Convenience: compile + evaluate against a plain signal dict.

    Callable signals (e.g. ``total_conversion_value``) can be supplied
    as plain callables in the dict, or as 0-arity values (in which case
    the args are ignored). This is mostly useful for unit tests.
    """
    compiled = compile_script(source)

    def resolver(name: str, args: tuple[Any, ...]) -> Any:
        if name not in signals:
            return None
        v = signals[name]
        if callable(v):
            return v(*args)
        return v

    value, _used, _non_none = evaluate(compiled, resolver)
    return value
