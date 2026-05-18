"""CLI entry point.

Usage:
    python -m bidagent demo               # mock data, generic shape
    python -m bidagent demo-dv360         # mock data, DV360-shaped dimensions
    python -m bidagent run --config bidagent.yaml [--apply]
    python -m bidagent dry-run --config bidagent.yaml

`demo` and `demo-dv360` prove the decision engine works without needing
any live API credentials. They use the same engine code — the difference
is just the shape of the input dimensions."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timedelta

from .decision_engine import build_plan, decide_multi_objective
from .models import HygieneRules, OptimizationProfile, OptimizerConfig
from .mock_data import fake_current_modifiers, fake_runs_since_zeroed, fake_week_metrics
from .multi_objective import build_metric_baselines, build_plan_metric_agnostic, build_strategy_spec

# DV360 mock data
from .providers.dv360.mock_data import (
    fake_dv360_week_metrics,
    fake_current_bid_multipliers,
    fake_runs_since_zeroed as fake_runs_since_zeroed_dv360,
)
from .providers.dv360.bid_client import build_bulk_edit_body


def _print_plan(plan, verbose: bool = False) -> None:
    s = plan.summary_dict()
    week = plan.week_label or "current"
    print("=" * 70)
    print(f"Plan • Line Item #{plan.line_item_id} • {plan.line_item_name}")
    print(f"Settimana: {week}")
    print(f"Target CPV: {plan.cpv_target:.2f}€   "
          f"Osservato: {plan.blended_cpv_observed:.2f}€   "
          f"Visite: {plan.blended_visits:,}   Spend: {plan.blended_spend:.2f}€")
    print("-" * 70)
    print(f"Termini valutati: {s['n_terms_evaluated']}   "
          f"Modificati: {s['n_terms_changed']} "
          f"(boost {s['n_terms_boosted']} | cut {s['n_terms_cut']} | "
          f"azzerati {s['n_terms_zeroed']})")

    if plan.line_item_changes:
        print()
        print("Modifiche a livello Line Item:")
        for c in plan.line_item_changes:
            print(f"  • {c.field}: {c.previous_value} → {c.new_value}")
            print(f"    {c.reason}")

    print()
    print("Decisioni sui modifier:")
    # Sort: changed first (largest delta), then unchanged
    changed = sorted(
        plan.changed_decisions, key=lambda d: -abs(d.delta)
    )
    unchanged = [d for d in plan.decisions if not d.changed]

    for d in changed:
        arrow = "↑" if d.delta > 0 else "↓"
        print(f"  {arrow} {d.term.field_label or d.term.value:32s} "
              f"{d.previous_modifier:.2f} → {d.new_modifier:.2f}  "
              f"[{d.reason.value}]")
        print(f"      {d.note}")

    if verbose and unchanged:
        print()
        print("(Invariati)")
        for d in unchanged:
            print(f"  = {d.term.field_label or d.term.value:32s} "
                  f"{d.previous_modifier:.2f}  [{d.reason.value}]")

    print("=" * 70)


def _parse_metric_flag(raw: str) -> tuple[str, float, float]:
    name, target, weight = raw.split(":")
    return name.strip(), float(target), float(weight)


def _strategy_from_cli(args: argparse.Namespace) -> object | None:
    mode = getattr(args, "mode", None)
    if not mode:
        return None
    metrics: list[tuple[str, float, float]] = []
    if args.metric1:
        metrics.append(_parse_metric_flag(args.metric1))
    if args.metric2:
        metrics.append(_parse_metric_flag(args.metric2))
    if args.metric3:
        metrics.append(_parse_metric_flag(args.metric3))
    if mode == "single" and metrics:
        name, target, weight = metrics[0]
        return build_strategy_spec(
            mode="single",
            primary_metric=name,
            primary_target=target,
            primary_weight=weight,
        )
    if mode == "blended_2" and len(metrics) >= 2:
        return build_strategy_spec(
            mode="blended_2",
            primary_metric=metrics[0][0],
            primary_target=metrics[0][1],
            primary_weight=metrics[0][2],
            secondary_metric=metrics[1][0],
            secondary_target=metrics[1][1],
            secondary_weight=metrics[1][2],
        )
    if mode == "blended_3" and len(metrics) >= 3:
        return build_strategy_spec(
            mode="blended_3",
            primary_metric=metrics[0][0],
            primary_target=metrics[0][1],
            primary_weight=metrics[0][2],
            secondary_metric=metrics[1][0],
            secondary_target=metrics[1][1],
            secondary_weight=metrics[1][2],
            tertiary_metric=metrics[2][0],
            tertiary_target=metrics[2][1],
            tertiary_weight=metrics[2][2],
        )
    raise SystemExit(f"--mode {mode} requires metric1[:metric3] flags NAME:TARGET:WEIGHT")


def cmd_demo(args: argparse.Namespace) -> int:
    """Run the decision engine on fully synthetic data."""

    cfg = OptimizerConfig(
        cpv_target=0.60,            # 60 cent per visit
        tolerance_band=0.20,
        max_step_per_run=0.30,
    )
    hygiene = HygieneRules(
        min_impressions_for_action=500,
        anomalous_ctr_threshold=0.04,
        min_viewability=0.40,
    )

    metrics = fake_week_metrics(seed=args.seed)
    current_mods = fake_current_modifiers(metrics)
    runs_since_zeroed = fake_runs_since_zeroed()

    today = datetime.utcnow().date()
    week_start = today - timedelta(days=today.weekday() + 7)
    week_label = f"{week_start.isoformat()} → {(week_start + timedelta(days=6)).isoformat()}"

    metric_spec = _strategy_from_cli(args)
    if metric_spec is not None:
        metric_spec.tolerance_band = cfg.tolerance_band
        metric_spec.metric_baselines = build_metric_baselines(metrics)
        plan = build_plan_metric_agnostic(
            line_item_id=1_001,
            line_item_name="Demo Campaign — Display+Native IT",
            week_label=week_label,
            metrics=metrics,
            current_modifiers=current_mods,
            runs_since_zeroed=runs_since_zeroed,
            current_max_bid=5.00,
            cfg=cfg,
            hygiene=hygiene,
            strategy=metric_spec,
        )
    else:
        strategy = OptimizationProfile(
            profile=args.profile,
            primary_objective_metric=(
                "blended_cpa" if args.profile == "minimize_blended_cpa" else "cpv"
            ),
            primary_objective_target=cfg.cpv_target if args.profile == "minimize_cpv" else 4.50,
            tolerance_band=cfg.tolerance_band,
        )
        if args.profile == "minimize_cpv":
            plan = build_plan(
                line_item_id=1_001,
                line_item_name="Demo Campaign — Display+Native IT",
                week_label=week_label,
                metrics=metrics,
                current_modifiers=current_mods,
                runs_since_zeroed=runs_since_zeroed,
                current_max_bid=5.00,
                cfg=cfg,
                hygiene=hygiene,
            )
        else:
            plan = decide_multi_objective(
                line_item_id=1_001,
                line_item_name="Demo Campaign — Display+Native IT",
                week_label=week_label,
                metrics=metrics,
                current_modifiers=current_mods,
                runs_since_zeroed=runs_since_zeroed,
                current_max_bid=5.00,
                cfg=cfg,
                hygiene=hygiene,
                strategy=strategy,
            )

    if args.format == "json":
        payload = {
            "summary": plan.summary_dict(),
            "decisions": [
                {
                    "label": d.term.field_label or d.term.value,
                    "module": d.term.targeting_module,
                    "key": d.term.targeting_key,
                    "value": d.term.value,
                    "previous_modifier": d.previous_modifier,
                    "new_modifier": d.new_modifier,
                    "reason": d.reason.value,
                    "cpv": d.observed_cpv if d.observed_cpv != float("inf") else None,
                    "visits": d.observed_visits,
                    "impressions": d.observed_impressions,
                    "note": d.note,
                }
                for d in plan.decisions
            ],
        }
        print(json.dumps(payload, indent=2, default=str))
    else:
        _print_plan(plan, verbose=args.verbose)

    return 0


def cmd_demo_dv360(args: argparse.Namespace) -> int:
    """Run the decision engine on synthetic DV360-shaped data."""

    cfg = OptimizerConfig(
        cpv_target=0.40,            # 40 cent per visit
        tolerance_band=0.20,
        max_step_per_run=0.30,
    )
    hygiene = HygieneRules(
        min_impressions_for_action=500,
        anomalous_ctr_threshold=0.04,
        min_viewability=0.40,
    )

    metrics = fake_dv360_week_metrics(seed=args.seed)
    current_mods = fake_current_bid_multipliers(metrics)
    runs_since_zeroed = fake_runs_since_zeroed_dv360()

    today = datetime.utcnow().date()
    week_start = today - timedelta(days=today.weekday() + 7)
    week_label = f"{week_start.isoformat()} → {(week_start + timedelta(days=6)).isoformat()}"

    plan = build_plan(
        line_item_id=900_001,
        line_item_name="Brand Amico — Display+Native IT (DV360)",
        week_label=week_label,
        metrics=metrics,
        current_modifiers=current_mods,
        runs_since_zeroed=runs_since_zeroed,
        current_max_bid=4.50,
        cfg=cfg,
        hygiene=hygiene,
    )

    if args.format == "json":
        payload = {
            "summary": plan.summary_dict(),
            "decisions": [
                {
                    "label": d.term.field_label or d.term.value,
                    "module": d.term.targeting_module,
                    "key": d.term.targeting_key,
                    "value": d.term.value,
                    "previous_modifier": d.previous_modifier,
                    "new_modifier": d.new_modifier,
                    "reason": d.reason.value,
                    "cpv": d.observed_cpv if d.observed_cpv != float("inf") else None,
                    "visits": d.observed_visits,
                    "impressions": d.observed_impressions,
                    "note": d.note,
                }
                for d in plan.decisions
            ],
        }
        print(json.dumps(payload, indent=2, default=str))
        return 0

    _print_plan(plan, verbose=args.verbose)

    # Extra: show the DV360 bulkEdit payload
    if args.show_payload:
        try:
            body = build_bulk_edit_body(plan)
            print()
            print("Payload DV360 lineItems.bulkEditAssignedTargetingOptions (preview):")
            print(json.dumps(body, indent=2))
        except (ValueError, NotImplementedError) as e:
            print(f"\n(Payload non disponibile: {e})")

    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Full pipeline: DV360 Reporting → engine → DV360 bulkEdit. Not yet wired to a config."""
    print(
        "Comando 'run' non ancora collegato a credenziali live. "
        "Per ora gira: python -m bidagent demo-dv360",
        file=sys.stderr,
    )
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bidagent",
        description="Closed-loop CPV optimizer (DV360).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # demo (Beeswax-shaped mock)
    p_demo = sub.add_parser("demo", help="Run on Beeswax-shaped synthetic data")
    p_demo.add_argument("--seed", type=int, default=42)
    p_demo.add_argument(
        "--profile",
        default="minimize_cpv",
        choices=["minimize_cpv", "minimize_blended_cpa"],
    )
    p_demo.add_argument(
        "--mode",
        choices=["single", "blended_2", "blended_3"],
        help="Metric-agnostic strategy (overrides --profile when set)",
    )
    p_demo.add_argument(
        "--metric1",
        help="Primary metric NAME:TARGET:WEIGHT_PCT (e.g. cpa:4.50:70)",
    )
    p_demo.add_argument("--metric2", help="Secondary metric NAME:TARGET:WEIGHT_PCT")
    p_demo.add_argument("--metric3", help="Tertiary metric NAME:TARGET:WEIGHT_PCT")
    p_demo.add_argument("--verbose", "-v", action="store_true")
    p_demo.add_argument("--format", choices=["text", "json"], default="text")
    p_demo.set_defaults(func=cmd_demo)

    # demo-dv360 (DV360-shaped mock)
    p_demo_dv = sub.add_parser("demo-dv360",
                               help="Run on DV360-shaped synthetic data")
    p_demo_dv.add_argument("--seed", type=int, default=7)
    p_demo_dv.add_argument("--verbose", "-v", action="store_true")
    p_demo_dv.add_argument("--format", choices=["text", "json"], default="text")
    p_demo_dv.add_argument("--show-payload", action="store_true",
                           help="Print the DV360 bulkEdit API payload preview")
    p_demo_dv.set_defaults(func=cmd_demo_dv360)

    p_run = sub.add_parser("run", help="Run against live AMC + DSP API (TODO)")
    p_run.add_argument("--config", required=True)
    p_run.add_argument("--apply", action="store_true",
                       help="Actually PUT changes to the API (default is dry-run)")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
