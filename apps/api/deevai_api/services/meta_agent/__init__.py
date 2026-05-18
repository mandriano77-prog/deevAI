"""Meta-agent: diagnose, propose, apply, post-mortem."""

from .apply import apply_proposed_changes
from .diagnose import quick_diagnose
from .governance import is_auto_applicable, validate_proposed_changes
from .llm import diagnose as llm_diagnose
from .post_mortem import run_due_post_mortems

__all__ = [
    "apply_proposed_changes",
    "quick_diagnose",
    "llm_diagnose",
    "is_auto_applicable",
    "validate_proposed_changes",
    "run_due_post_mortems",
]
