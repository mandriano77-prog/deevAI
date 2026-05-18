# bidagent

**Working name.** A closed-loop CPV (Cost Per Visit) optimizer for
**Google DV360** (Reporting + bid modifier API). Once a week it
reads what happened, decides what to adjust, applies changes via the DSP
API, and writes a narrative digest for the client.

Legacy Beeswax-shaped demos (`python -m bidagent demo`) remain for local
testing; production DeevAI uses the DV360 adapters
under `bidagent/providers/dv360/`.

> Goal of the product, not the code: turn programmatic optimization into
> something the client *reads* on Monday morning, not something they
> have to log in to see.

---

## Status (this build)

- [x] Decision engine (`decision_engine.py`)
- [x] Synthetic data generator (`mock_data.py`)
- [x] Config loader (`config.py`, `config.example.yaml`)
- [x] CLI with a `demo` command
- [ ] Antenna SQL extractor → **next**
- [ ] Buzz REST API client → **next**
- [ ] Weekly digest generator (LLM) → **next**
- [ ] Lambda handler + Terraform → **next**
- [ ] Runbook / onboarding doc → **next**

You can run the `demo` command today and see the engine produce
decisions on a synthetic week.

---

## Quick start (demo on synthetic data)

```bash
cd outputs
python3 -m bidagent demo
```

You should see a printed Plan: target CPV, blended observed CPV,
the list of decisions per term with reasons, and any Line Item-level
`max_bid` change.

Other options:

```bash
python3 -m bidagent demo --verbose        # also show unchanged terms
python3 -m bidagent demo --format json    # machine-readable output
python3 -m bidagent demo --seed 7         # different mock dataset
```

No external dependencies needed for `demo` beyond standard library
(PyYAML is only used by `config.py`, not by the demo path).

---

## How the engine decides (one paragraph)

For each targeting term (e.g. "Safari browser", "Lombardia", "00-06
weekday daypart") we:

1. Apply **hygiene gates** first: anomalous CTR (>4%) → zero immediately
   (click-farm filter); viewability < 40% (if tracked) → zero; under-volume
   (<500 impressions) → hold previous modifier; impressions but zero
   visits → strong cut.
2. Compute observed CPV = spend / visits.
3. Compare to target CPV. Ratio is mapped to a target modifier through
   a small step function (under target → 1.10/1.25/1.50; on target → 1.00;
   over target → 0.80/0.60/0.40; >3x over → 0.0).
4. **Smooth**: never move a modifier by more than `max_step_per_run`
   (default 0.30) per pass. Slow and explainable beats fast and chaotic.
5. **Exploration revive**: terms that have been zeroed for N runs get
   promoted back to a small modifier (default 0.50) so we don't go
   permanently blind on segments we cut earlier.

At the Line Item level we also nudge `max_bid` by ±10% when the blended
CPV is meaningfully off target.

Every decision carries a `reason` enum and a `note` string, which is what
the digest generator turns into one-line natural-language explanations.

---

## File layout

```
bidagent/
  __init__.py
  __main__.py            # CLI: demo | run
  config.py              # YAML → dataclasses
  config.example.yaml    # template, copy to bidagent.yaml
  decision_engine.py     # the brain
  mock_data.py           # fake Antenna output for demo + tests
  models.py              # dataclasses (TermMetric, Plan, …)
  requirements.txt
  README.md              # ← you are here
```

What's coming in the next turns:

```
  antenna.py             # SQL extractor (window_days rolling)
  buzz_client.py         # REST client (PUT /bid_modifier, PUT /line_items)
  digest.py              # narrative weekly digest (LLM-assisted)
  lambda_handler.py      # AWS Lambda entry point
  terraform/             # IaC for Lambda + EventBridge + Secrets Manager
  runbook.md             # operational doc
```

---

## Safety defaults

- `dry_run: true` in config is the **default**. Nothing is PUT to Buzz
  unless you explicitly pass `--apply` AND set `dry_run: false`.
- Smoothing caps prevent any single bad decision from being a disaster
  (max ±0.30 on a modifier, ±10% on max_bid, per run).
- Anomalous CTR filter is hard-coded as a first-class safety check, not
  an optimization heuristic — it fires regardless of CPV target.

---

## Naming

`bidagent` is a working name. Replace globally with the commercial brand
when ready:

```bash
# example, do once
find . -type f -name "*.py" -exec sed -i '' 's/bidagent/yourname/g' {} +
```

(The product probably wants a name that signals the *weekly ritual*
rather than the *bidder mechanics* — e.g. *Monday Brief*, *Weekly Tune*.
TBD with Adriano.)
