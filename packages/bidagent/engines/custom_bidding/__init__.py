"""deevAI Custom Bidding engine — DV360 scoring-script generation.

This package implements Engine B of deevAI: the multi-objective
custom-bidding script generator + sandbox validator.

Public surface:

- :mod:`feature_catalog` — every DV360 signal and built-in function,
  with type info and category. Single source of truth.
- :mod:`objectives` — the three canonical product sliders
  (Performance / Quality / Reach) and their recipes.
- :mod:`script_generator` — convert a TenantConfig into the raw DSL
  text that DV360 expects.
- :mod:`sandbox_validator` — AST-based linter that guarantees the
  generated script is acceptable to DV360 before upload.

Quick example::

    from bidagent.engines.custom_bidding import (
        TenantConfig, ObjectiveId, generate_script, assert_valid,
    )

    cfg = TenantConfig(
        weights={
            ObjectiveId.PERFORMANCE: 0.6,
            ObjectiveId.QUALITY: 0.3,
            ObjectiveId.REACH: 0.1,
        },
        floodlight_activity_id=123456,
        country_focus=("IT",),
    )
    script = generate_script(cfg, tenant_id="acme")
    assert_valid(script.source)
    # script.source → upload to DV360
"""

from .feature_catalog import (
    BUILTIN_FUNCTIONS,
    BuiltinFunction,
    Signal,
    SignalCategory,
    SignalType,
    SIGNALS,
    SIGNALS_BY_NAME,
    is_allowed_identifier,
    signal,
    signals_in_category,
)
from .objectives import (
    Criterion,
    ObjectiveId,
    Recipe,
    TenantConfig,
    expand_objectives,
    validate_weights,
)
from .sandbox_validator import (
    ValidationIssue,
    ValidationReport,
    assert_valid,
    validate_script,
)
from .script_generator import (
    GeneratedScript,
    explain,
    generate_script,
    render_diff,
)
from .dsl_interpreter import (
    CompiledScript,
    DSLError,
    DSLRuntimeError,
    DSLValidationError,
    compile_script,
    evaluate,
    run_with_signals,
)
from .score_simulator import (
    ImpressionRow,
    ImpressionScoreBreakdown,
    ScoreSimulator,
    SimulationDataset,
    SimulationReport,
    generate_synthetic_dataset,
    simulate_tenant_config,
)

__all__ = [
    # feature_catalog
    "BUILTIN_FUNCTIONS",
    "BuiltinFunction",
    "Signal",
    "SignalCategory",
    "SignalType",
    "SIGNALS",
    "SIGNALS_BY_NAME",
    "is_allowed_identifier",
    "signal",
    "signals_in_category",
    # objectives
    "Criterion",
    "ObjectiveId",
    "Recipe",
    "TenantConfig",
    "expand_objectives",
    "validate_weights",
    # script_generator
    "GeneratedScript",
    "explain",
    "generate_script",
    "render_diff",
    # sandbox_validator
    "ValidationIssue",
    "ValidationReport",
    "assert_valid",
    "validate_script",
    # dsl_interpreter
    "CompiledScript",
    "DSLError",
    "DSLRuntimeError",
    "DSLValidationError",
    "compile_script",
    "evaluate",
    "run_with_signals",
    # score_simulator
    "ImpressionRow",
    "ImpressionScoreBreakdown",
    "ScoreSimulator",
    "SimulationDataset",
    "SimulationReport",
    "generate_synthetic_dataset",
    "simulate_tenant_config",
]
