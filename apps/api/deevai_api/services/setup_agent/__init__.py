"""Setup Agent — configure tenant from a free-form brief."""

from .applier import apply_proposal
from .pipeline import run_setup_agent

__all__ = ["apply_proposal", "run_setup_agent"]
