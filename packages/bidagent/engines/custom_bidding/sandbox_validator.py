"""Static validator for DV360 custom-bidding scripts.

DV360 silently rejects scripts that reference unknown signals or use
unsupported syntax — and you only see the error after upload. To keep
the deevAI feedback loop tight we lint scripts *before* they ever
leave the building.

How it works
------------
The DSL accepted by DV360 is a strict subset of Python expressions.
We tokenise the script with Python's own ``ast`` (this works because
every legal DV360 script is *also* legal Python at the parse level —
but not every legal Python program is legal DV360), then walk the AST
and reject any node that we don't explicitly allow.

If ``ast.parse`` raises, we surface the line/column directly. Either
way the validator returns a structured :class:`ValidationReport` —
never raises in normal use.

Limitations
-----------
- We cannot detect runtime errors (division by zero, type mismatches),
  only structural / static violations. That's by design: DV360's own
  runtime is the final arbiter.
- We allow ``log`` with 1 or 2 arguments (the doc says it's overloaded).
- We treat ``None``, ``True``, ``False`` as legal literals.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Iterable

from .feature_catalog import (
    AGGREGATE_FUNCTIONS,
    ALL_ALLOWED_NAMES,
    CASTING_FUNCTIONS,
    FUNCTIONS_BY_NAME,
    MATH_FUNCTIONS,
    SIGNALS_BY_NAME,
)


# ─────────────────────────────────────────────────────────────── data classes


@dataclass(frozen=True)
class ValidationIssue:
    """One problem found in a script."""

    kind: str             # "syntax" | "forbidden_node" | "unknown_name" | "shape"
    message: str
    line: int | None = None
    col: int | None = None

    def __str__(self) -> str:  # pragma: no cover (cosmetic)
        loc = f"L{self.line}" if self.line else "?"
        return f"[{self.kind}] {loc}: {self.message}"


@dataclass(frozen=True)
class ValidationReport:
    """The outcome of validating one script.

    ``ok`` is true iff no issues at all. ``has_errors`` is the more
    interesting flag — warnings (e.g. very low weight) can be emitted
    later without failing the upload.
    """

    ok: bool
    issues: tuple[ValidationIssue, ...] = field(default_factory=tuple)
    n_returns: int = 0
    n_calls: int = 0
    referenced_signals: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_errors(self) -> bool:
        return not self.ok

    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.kind != "warning"]


# ─────────────────────────────────────────────────────────────────── visitor


# Set of AST node types we explicitly permit anywhere in the script.
# Anything not in this set will cause a forbidden-node error.
_ALLOWED_NODES: frozenset[type[ast.AST]] = frozenset({
    ast.Module,
    ast.Expr,
    ast.Return,
    # Function-style calls (aggregate, casting, math, conversion-callables)
    ast.Call,
    ast.keyword,
    # Names + constants + load context
    ast.Name,
    ast.Load,
    ast.Constant,
    # Literal collections (lists of criteria, lists in `in` comparisons)
    ast.List,
    ast.Tuple,
    # Operators
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.IfExp,
    # Operator subclasses
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow, ast.FloorDiv,
    ast.USub, ast.UAdd,
    ast.And, ast.Or, ast.Not,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.In, ast.NotIn,
    # `if … : return …` is needed for the "excluding slice" pattern
    ast.If,
})


def _is_call_to(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name


def validate_script(source: str) -> ValidationReport:
    """Validate a DV360 custom-bidding script.

    The function never raises on malformed input — instead it returns a
    :class:`ValidationReport` with the appropriate issues. This keeps
    callers (UI, CI) simple.
    """
    issues: list[ValidationIssue] = []
    referenced: set[str] = set()
    n_returns = 0
    n_calls = 0

    # 1. Parse
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        issues.append(
            ValidationIssue(
                kind="syntax",
                message=f"Python parse error: {exc.msg}",
                line=exc.lineno,
                col=exc.offset,
            )
        )
        return ValidationReport(ok=False, issues=tuple(issues))

    # 2. Top-level must be at least one Return (or If…Return). DV360
    #    scripts must end in a return, so emit a hard error if there is
    #    no Return anywhere.
    has_return = False

    # 3. Walk every node — anything not whitelisted is rejected.
    for node in ast.walk(tree):
        if isinstance(node, ast.Return):
            has_return = True
            n_returns += 1
            # Bare ``return`` (no value) is not valid DV360 syntax.
            if node.value is None:
                issues.append(
                    ValidationIssue(
                        kind="shape",
                        message="Bare `return` is not allowed — use `return None` to exclude.",
                        line=node.lineno,
                    )
                )

        elif isinstance(node, ast.Call):
            n_calls += 1
            if isinstance(node.func, ast.Name):
                fname = node.func.id
                if fname in FUNCTIONS_BY_NAME:
                    # built-in: OK
                    pass
                elif fname in SIGNALS_BY_NAME and SIGNALS_BY_NAME[fname].is_callable:
                    referenced.add(fname)
                else:
                    issues.append(
                        ValidationIssue(
                            kind="unknown_name",
                            message=(
                                f"Call to unknown function `{fname}(...)`. "
                                "Only DV360 built-ins (aggregate/cast/log) and "
                                "conversion signals are callable."
                            ),
                            line=node.lineno,
                            col=node.col_offset,
                        )
                    )
            else:
                # Attribute calls (a.b()) and lambda calls — never legal.
                issues.append(
                    ValidationIssue(
                        kind="forbidden_node",
                        message="Only direct function calls are allowed.",
                        line=getattr(node, "lineno", None),
                    )
                )

        elif isinstance(node, ast.Name):
            # Names appearing in Load context are signals or builtins.
            # (Names appearing in Store context would mean assignment,
            # which we forbid via the node whitelist — see below.)
            if isinstance(node.ctx, ast.Load):
                ident = node.id
                if ident in SIGNALS_BY_NAME:
                    referenced.add(ident)
                elif ident in FUNCTIONS_BY_NAME or ident in ALL_ALLOWED_NAMES:
                    pass
                else:
                    issues.append(
                        ValidationIssue(
                            kind="unknown_name",
                            message=(
                                f"Reference to unknown identifier `{ident}`. "
                                "Allowed: DV360 signals + builtins (True/False/None)."
                            ),
                            line=node.lineno,
                            col=node.col_offset,
                        )
                    )

        # Whitelist enforcement — *every* node type must be in the set.
        if type(node) not in _ALLOWED_NODES:
            issues.append(
                ValidationIssue(
                    kind="forbidden_node",
                    message=(
                        f"AST node `{type(node).__name__}` is not allowed in "
                        "DV360 custom-bidding scripts."
                    ),
                    line=getattr(node, "lineno", None),
                )
            )

    if not has_return:
        issues.append(
            ValidationIssue(
                kind="shape",
                message="Script has no `return` statement — DV360 will reject it.",
            )
        )

    # Sort issues by line for stable presentation.
    issues.sort(key=lambda i: (i.line or 0, i.col or 0))

    return ValidationReport(
        ok=not issues,
        issues=tuple(issues),
        n_returns=n_returns,
        n_calls=n_calls,
        referenced_signals=tuple(sorted(referenced)),
    )


def assert_valid(source: str) -> ValidationReport:
    """Convenience: validate and raise ValueError on the first error.

    Useful in tests and in apply paths where you want a hard stop.
    """
    report = validate_script(source)
    if report.has_errors:
        details = "\n".join(str(i) for i in report.issues)
        raise ValueError(f"Script failed DV360 sandbox validation:\n{details}")
    return report
