"""Weekly digest generator — the prose narrator of the bidagent.

Takes a Plan + optional previous-week deltas and produces a 3-paragraph
Italian (or English) narrative for the customer's Monday morning email.

Three providers, picked in priority order:
  1. Anthropic Claude (best output, needs ANTHROPIC_API_KEY)
  2. OpenAI         (alt, needs OPENAI_API_KEY)
  3. Template       (always works, no LLM, "ok but flat" quality)

The template fallback is intentionally good enough to be shipped to a
first customer — it's based on Jinja-like substitution over the Plan's
decisions and uses pre-built sentence fragments per ActionReason.

Caller chooses language via the `language` param. Italian is default.

Usage:
    from bidagent.digest_generator import generate_digest
    text = generate_digest(plan, language="it")
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Literal, Optional

from .models import ActionReason, Plan

log = logging.getLogger(__name__)

Language = Literal["it", "en"]


# ───────────────────────────────────────────────────────────────
# Configuration
# ───────────────────────────────────────────────────────────────


@dataclass
class DigestConfig:
    provider: Literal["anthropic", "openai", "template", "auto"] = "auto"
    model: str = "claude-sonnet-4-6"
    language: Language = "it"
    temperature: float = 0.7
    max_tokens: int = 800
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None

    @classmethod
    def from_env(cls) -> "DigestConfig":
        return cls(
            provider="auto",
            model=os.environ.get("LLM_MODEL", "claude-sonnet-4-6"),
            language=os.environ.get("DIGEST_LANGUAGE", "it"),  # type: ignore[arg-type]
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
        )


# ───────────────────────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────────────────────


def generate_digest(
    plan: Plan,
    *,
    previous_week_cpv: Optional[float] = None,
    previous_week_visits: Optional[int] = None,
    config: Optional[DigestConfig] = None,
    language: Optional[Language] = None,
) -> str:
    """Generate a weekly digest for the given Plan.

    `previous_week_cpv` / `previous_week_visits` are optional — they let the
    digest say things like "il CPV è sceso del 5%" or "le visite sono salite
    del 12%" (the customer notices delta, not absolute numbers).
    """
    cfg = config or DigestConfig.from_env()
    if language:
        cfg.language = language

    provider = _pick_provider(cfg)
    context = _build_context(plan, previous_week_cpv, previous_week_visits)

    if provider == "anthropic":
        try:
            return _generate_with_anthropic(context, cfg)
        except Exception as e:  # noqa: BLE001
            log.warning("Anthropic digest failed (%s) — falling back to template", e)
            return _generate_with_template(context, cfg)

    if provider == "openai":
        try:
            return _generate_with_openai(context, cfg)
        except Exception as e:  # noqa: BLE001
            log.warning("OpenAI digest failed (%s) — falling back to template", e)
            return _generate_with_template(context, cfg)

    return _generate_with_template(context, cfg)


# ───────────────────────────────────────────────────────────────
# Provider selection
# ───────────────────────────────────────────────────────────────


def _pick_provider(cfg: DigestConfig) -> str:
    if cfg.provider == "anthropic" and cfg.anthropic_api_key:
        return "anthropic"
    if cfg.provider == "openai" and cfg.openai_api_key:
        return "openai"
    if cfg.provider == "auto":
        if cfg.anthropic_api_key:
            return "anthropic"
        if cfg.openai_api_key:
            return "openai"
    return "template"


# ───────────────────────────────────────────────────────────────
# Context building (shared by all providers)
# ───────────────────────────────────────────────────────────────


@dataclass
class DigestContext:
    line_item_name: str
    week_label: str
    cpv_target: float
    cpv_observed: float
    cpv_delta_pct: Optional[float]
    visits: int
    visits_delta_pct: Optional[float]
    spend: float
    n_decisions: int
    n_boosted: int
    n_cut: int
    n_zeroed: int
    top_movers: list[dict]
    line_item_changes: list[dict]
    language: Language


def _build_context(
    plan: Plan,
    previous_week_cpv: Optional[float],
    previous_week_visits: Optional[int],
) -> DigestContext:
    summary = plan.summary_dict()
    cpv_delta_pct: Optional[float] = None
    if previous_week_cpv and previous_week_cpv > 0:
        cpv_delta_pct = (plan.blended_cpv_observed - previous_week_cpv) / previous_week_cpv
    visits_delta_pct: Optional[float] = None
    if previous_week_visits and previous_week_visits > 0:
        visits_delta_pct = (plan.blended_visits - previous_week_visits) / previous_week_visits

    # Top movers = the 5 decisions with biggest |delta|, excluding unchanged
    movers = sorted(plan.changed_decisions, key=lambda d: -abs(d.delta))[:5]
    top_movers = [
        {
            "label": d.term.field_label or d.term.value,
            "module": d.term.targeting_module,
            "key": d.term.targeting_key,
            "previous": d.previous_modifier,
            "new": d.new_modifier,
            "reason": d.reason.value,
            "note": d.note,
            "cpv": d.observed_cpv if d.observed_cpv != float("inf") else None,
            "visits": d.observed_visits,
            "impressions": d.observed_impressions,
        }
        for d in movers
    ]

    return DigestContext(
        line_item_name=plan.line_item_name,
        week_label=plan.week_label,
        cpv_target=plan.cpv_target,
        cpv_observed=plan.blended_cpv_observed,
        cpv_delta_pct=cpv_delta_pct,
        visits=plan.blended_visits,
        visits_delta_pct=visits_delta_pct,
        spend=plan.blended_spend,
        n_decisions=summary["n_terms_evaluated"],
        n_boosted=summary["n_terms_boosted"],
        n_cut=summary["n_terms_cut"],
        n_zeroed=summary["n_terms_zeroed"],
        top_movers=top_movers,
        line_item_changes=summary["line_item_changes"],
        language="it",
    )


# ───────────────────────────────────────────────────────────────
# LLM provider — Anthropic
# ───────────────────────────────────────────────────────────────


def _generate_with_anthropic(context: DigestContext, cfg: DigestConfig) -> str:
    import anthropic  # local import to avoid hard dep when not used

    prompt = _build_llm_prompt(context, cfg.language)
    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)

    response = client.messages.create(
        model=cfg.model,
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
        system=_system_prompt(cfg.language),
        messages=[{"role": "user", "content": prompt}],
    )
    # response.content is a list of TextBlock — take the text from the first
    parts = []
    for block in response.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _generate_with_openai(context: DigestContext, cfg: DigestConfig) -> str:
    # Placeholder — only wire OpenAI if Anthropic is unavailable.
    # We don't import openai unless this path is taken.
    raise NotImplementedError("OpenAI provider not implemented in MVP")


def _system_prompt(language: Language) -> str:
    if language == "it":
        return (
            "Sei un media buyer senior che scrive il digest settimanale di una campagna "
            "DV360 per un cliente non tecnico. Tono: chiaro, sicuro di sé, italiano "
            "fluente, frasi corte. Stile editoriale alla Stratechery: ogni paragrafo ha "
            "una tesi, supporto numerico, e una micro-conclusione. Mai marketing-speak, "
            "mai bullet point, mai emoji. Massimo 3 paragrafi. "
            "Usa i numeri esatti quando li hai, ma non inventarli mai."
        )
    return (
        "You are a senior media buyer writing the weekly digest of a DV360 "
        "campaign for a non-technical client. Tone: clear, confident, plain English, "
        "short sentences. Stratechery-style: every paragraph has a thesis, supporting "
        "numbers, and a micro-conclusion. No marketing-speak, no bullet points, no emojis. "
        "Maximum 3 paragraphs. Use exact numbers when you have them, never invent any."
    )


def _build_llm_prompt(c: DigestContext, language: Language) -> str:
    movers_str = "\n".join(
        f"- {m['label']} ({m['module']}.{m['key']}): "
        f"modifier {m['previous']:.2f} → {m['new']:.2f} "
        f"(reason: {m['reason']}, CPV osservato: "
        f"{m['cpv']:.2f}€" + (f", {m['visits']} visite, {m['impressions']} impression)" if m["cpv"] else "")
        for m in c.top_movers
    ) or "(nessun cambio significativo)"

    li_changes_str = "\n".join(
        f"- {ch['field']}: {ch['previous_value']} → {ch['new_value']} ({ch['reason']})"
        for ch in c.line_item_changes
    ) or "(nessuna modifica a livello line item)"

    if language == "it":
        delta_cpv_str = (
            f"variazione CPV vs settimana scorsa: {c.cpv_delta_pct:+.1%}"
            if c.cpv_delta_pct is not None
            else "settimana di riferimento iniziale (no delta)"
        )
        delta_visits_str = (
            f"variazione visite vs settimana scorsa: {c.visits_delta_pct:+.1%}"
            if c.visits_delta_pct is not None
            else ""
        )
        return (
            f"Genera il digest settimanale per il line item '{c.line_item_name}'.\n\n"
            f"Settimana: {c.week_label}\n"
            f"Target CPV: {c.cpv_target:.2f}€\n"
            f"CPV osservato: {c.cpv_observed:.2f}€\n"
            f"{delta_cpv_str}\n"
            f"Visite totali: {c.visits}\n"
            f"{delta_visits_str}\n"
            f"Spend: {c.spend:.2f}€\n\n"
            f"Decisioni dell'agente:\n"
            f"- termini valutati: {c.n_decisions}\n"
            f"- boost: {c.n_boosted} · cut: {c.n_cut} · azzerati: {c.n_zeroed}\n\n"
            f"Top movers (le 5 mosse più rilevanti della settimana):\n{movers_str}\n\n"
            f"Modifiche a livello line item:\n{li_changes_str}\n\n"
            f"Scrivi il digest in 3 paragrafi italiani:\n"
            f"  1. Cosa è successo questa settimana (KPI di alto livello, trend)\n"
            f"  2. Cosa hai fatto e perché (le mosse principali, con il 'why')\n"
            f"  3. Cosa guarderai la prossima settimana (1-2 focus area)\n"
        )
    # English fallback
    return (
        f"Generate the weekly digest for line item '{c.line_item_name}'.\n\n"
        f"Week: {c.week_label}\n"
        f"Target CPV: {c.cpv_target:.2f}\n"
        f"Observed CPV: {c.cpv_observed:.2f}\n"
        f"Visits: {c.visits}\n"
        f"Spend: {c.spend:.2f}\n\n"
        f"Top movers:\n{movers_str}\n"
        f"Line item changes:\n{li_changes_str}\n\n"
        f"Write in 3 paragraphs: what happened, what I did and why, what I'll watch."
    )


# ───────────────────────────────────────────────────────────────
# Template fallback — no LLM needed
# ───────────────────────────────────────────────────────────────


REASON_PHRASES_IT: dict[str, str] = {
    "anomalous_ctr": "ha azzerato il dominio per CTR sopra soglia anti-bot",
    "over_target": "ha ridotto il modifier perché il CPV è sopra il target",
    "under_target": "ha boostato perché il CPV è sotto il target",
    "on_target": "è in target, lascio invariato",
    "zero_visits": "ha tagliato perché impression senza visite",
    "low_viewability": "ha tagliato per viewability sotto soglia",
    "insufficient_volume": "volume non sufficiente per agire, attendiamo",
    "exploration_revive": "rimesso in esplorazione dopo settimane di pausa",
    "smoothed": "passo limitato dal cap settimanale",
}


def _generate_with_template(context: DigestContext, cfg: DigestConfig) -> str:
    """Compose a 3-paragraph digest using string templates.

    Lower quality than LLM but always works and costs nothing."""
    if cfg.language == "it":
        return _generate_template_it(context)
    return _generate_template_en(context)


def _generate_template_it(c: DigestContext) -> str:
    cpv_pct = c.cpv_observed / c.cpv_target if c.cpv_target else 1.0
    cpv_status = (
        f"al di sotto del target del {(1 - cpv_pct):.0%}"
        if cpv_pct < 1
        else f"al {(cpv_pct - 1):.0%} sopra il target"
        if cpv_pct > 1
        else "in linea col target"
    )
    cpv_delta_str = (
        f", {'in calo' if c.cpv_delta_pct and c.cpv_delta_pct < 0 else 'in salita'} "
        f"del {abs(c.cpv_delta_pct or 0):.0%} rispetto alla settimana scorsa"
        if c.cpv_delta_pct is not None
        else ""
    )
    visits_delta_str = (
        f" Le visite sono {'cresciute' if c.visits_delta_pct and c.visits_delta_pct > 0 else 'scese'} "
        f"del {abs(c.visits_delta_pct or 0):.0%} rispetto a sette giorni fa."
        if c.visits_delta_pct is not None
        else ""
    )

    para1 = (
        f"Questa settimana il CPV blended si è fermato a {c.cpv_observed:.2f}€, "
        f"{cpv_status}{cpv_delta_str}.{visits_delta_str} "
        f"Lo spend è stato di {c.spend:.0f}€ per {c.visits} visite totali."
    )

    # Paragraph 2 — top movers
    if c.top_movers:
        mosse_parts: list[str] = []
        for m in c.top_movers[:3]:
            phrase = REASON_PHRASES_IT.get(m["reason"], "ha modificato il modifier")
            cpv_clause = (
                f"con CPV {m['cpv']:.2f}€ contro target {c.cpv_target:.2f}€"
                if m["cpv"] is not None
                else "(nessuna visita registrata)"
            )
            mosse_parts.append(
                f"Su {m['label']} {phrase} "
                f"({m['previous']:.2f}× → {m['new']:.2f}×) — {cpv_clause}."
            )
        para2 = "Le mosse principali: " + " ".join(mosse_parts)
        if c.line_item_changes:
            ch = c.line_item_changes[0]
            para2 += (
                f" A livello line item ho mosso anche {ch['field']} "
                f"da {ch['previous_value']} a {ch['new_value']}."
            )
    else:
        para2 = (
            "Questa settimana non sono emerse decisioni che superassero le soglie "
            "di azione: tutti i termini sono dentro la banda di tolleranza."
        )

    # Paragraph 3 — what to watch
    focus_areas = _focus_areas(c)
    para3 = (
        f"La prossima settimana guarderò soprattutto {focus_areas}. "
        f"Se i numeri tengono, il loop continua; se il CPV non rientra, "
        f"valuto un'azione più aggressiva."
    )
    return f"{para1}\n\n{para2}\n\n{para3}"


def _focus_areas(c: DigestContext) -> str:
    """Pick the 1-2 dimensions to highlight as 'next-week focus'."""
    # Heuristics: any term that hit the smoothing cap probably needs another
    # week; any zeroed domain needs verification; any boost needs to be tested
    # for volume holding.
    candidates: list[str] = []
    for m in c.top_movers:
        if m["new"] == 0:
            candidates.append(f"se {m['label']} stava davvero generando traffico inquinato")
        elif m["new"] > m["previous"]:
            candidates.append(f"se il boost su {m['label']} regge il volume di visite")
        elif m["new"] < m["previous"]:
            candidates.append(f"se il taglio su {m['label']} fa effettivamente scendere il CPV blended")
    if not candidates:
        return "il trend del CPV blended e la stabilità delle visite"
    return " e ".join(candidates[:2])


def _generate_template_en(c: DigestContext) -> str:
    """English fallback. Minimal — flesh out when there's a first EN customer."""
    return (
        f"This week, blended CPV landed at €{c.cpv_observed:.2f} against a target "
        f"of €{c.cpv_target:.2f}, with {c.visits} visits and €{c.spend:.0f} spent.\n\n"
        f"The agent proposed {c.n_decisions} decisions "
        f"(boost: {c.n_boosted}, cut: {c.n_cut}, zeroed: {c.n_zeroed}). "
        f"The top movers will be applied once you approve them.\n\n"
        f"Next week, watch for volume stability and any term where the smoothing "
        f"cap delayed the full correction."
    )
