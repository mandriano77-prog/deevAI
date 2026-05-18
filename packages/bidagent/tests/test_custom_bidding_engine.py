"""End-to-end tests for the Custom Bidding engine.

Covers:
- feature_catalog: signal lookup, category filtering, name validity.
- objectives: weight validation, recipe expansion, country/hour
  formatting.
- script_generator: deterministic output, header content, size cap.
- sandbox_validator: parses generated scripts cleanly, rejects every
  category of bad input we care about.
- custom_bid_client: dry-run flow + real-HTTP flow with a mock session.

No real DV360 calls. All HTTP is mocked via a ``requests.Session``
stub that records what was sent and returns canned responses.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from bidagent.engines.custom_bidding import (
    BUILTIN_FUNCTIONS,
    Criterion,
    GeneratedScript,
    ObjectiveId,
    Recipe,
    Signal,
    SignalCategory,
    SignalType,
    SIGNALS,
    SIGNALS_BY_NAME,
    TenantConfig,
    ValidationReport,
    assert_valid,
    expand_objectives,
    explain,
    generate_script,
    is_allowed_identifier,
    render_diff,
    signal,
    signals_in_category,
    validate_script,
    validate_weights,
)


# ───────────────────────────────────────────────────── helpers / fixtures


def _basic_tenant_config(performance: float = 0.6,
                         quality: float = 0.3,
                         reach: float = 0.1) -> TenantConfig:
    return TenantConfig(
        weights={
            ObjectiveId.PERFORMANCE: performance,
            ObjectiveId.QUALITY: quality,
            ObjectiveId.REACH: reach,
        },
        floodlight_activity_id=987654 if performance > 0 else None,
        country_focus=("IT",),
    )


# ───────────────────────────────────────────────────── feature_catalog


class TestFeatureCatalog:
    def test_known_signals_have_unique_names(self):
        names = [s.name for s in SIGNALS]
        assert len(names) == len(set(names)), "duplicate signal name"

    def test_lookup_by_name_works(self):
        s = signal("device_type")
        assert isinstance(s, Signal)
        assert s.type == SignalType.INTEGER
        assert s.value_map and s.value_map[2] == "smartphone"

    def test_lookup_unknown_raises(self):
        with pytest.raises(KeyError, match="unknown"):
            signal("not_a_real_signal_42")

    def test_signals_in_category_filters_correctly(self):
        date_sigs = signals_in_category(SignalCategory.DATE_TIME)
        names = {s.name for s in date_sigs}
        assert {"date", "day_of_week", "hour_of_day"} <= names

    def test_is_allowed_identifier(self):
        # signals
        assert is_allowed_identifier("country_code")
        # builtins
        assert is_allowed_identifier("sum_aggregate")
        # literals
        assert is_allowed_identifier("None")
        assert is_allowed_identifier("True")
        # not allowed
        assert not is_allowed_identifier("os")
        assert not is_allowed_identifier("subprocess")

    def test_callable_signals_have_arg_names(self):
        cv = signal("total_conversion_value")
        assert cv.is_callable
        assert cv.arg_names == ("floodlight_activity_id", "attribution_model_id")

    def test_builtin_functions_include_aggregates(self):
        names = {f.name for f in BUILTIN_FUNCTIONS}
        assert {"sum_aggregate", "first_match_aggregate", "max_aggregate"} <= names


# ─────────────────────────────────────────────────────── objectives


class TestObjectives:
    def test_validate_weights_accepts_normal(self):
        validate_weights({
            ObjectiveId.PERFORMANCE: 0.5,
            ObjectiveId.QUALITY: 0.3,
            ObjectiveId.REACH: 0.2,
        })

    def test_validate_weights_rejects_non_unit_sum(self):
        with pytest.raises(ValueError, match="sum to 1.0"):
            validate_weights({
                ObjectiveId.PERFORMANCE: 0.5,
                ObjectiveId.QUALITY: 0.5,
                ObjectiveId.REACH: 0.5,
            })

    def test_validate_weights_rejects_negative(self):
        with pytest.raises(ValueError, match="out of range"):
            validate_weights({
                ObjectiveId.PERFORMANCE: -0.1,
                ObjectiveId.QUALITY: 0.6,
                ObjectiveId.REACH: 0.5,
            })

    def test_validate_weights_rejects_missing(self):
        with pytest.raises(ValueError, match="Missing"):
            validate_weights({
                ObjectiveId.PERFORMANCE: 0.5,
                ObjectiveId.QUALITY: 0.5,
            })

    def test_performance_requires_floodlight(self):
        cfg = TenantConfig(
            weights={
                ObjectiveId.PERFORMANCE: 1.0,
                ObjectiveId.QUALITY: 0.0,
                ObjectiveId.REACH: 0.0,
            },
            floodlight_activity_id=None,
        )
        with pytest.raises(ValueError, match="Floodlight"):
            expand_objectives(cfg)

    def test_zero_weight_skips_objective(self):
        cfg = TenantConfig(
            weights={
                ObjectiveId.PERFORMANCE: 0.0,
                ObjectiveId.QUALITY: 1.0,
                ObjectiveId.REACH: 0.0,
            },
        )
        expanded = expand_objectives(cfg)
        assert len(expanded) == 1
        recipe, slider = expanded[0]
        assert recipe.objective == ObjectiveId.QUALITY
        assert slider == 1.0

    def test_full_expansion_returns_all_three_in_order(self):
        cfg = _basic_tenant_config()
        expanded = expand_objectives(cfg)
        ids = [r.objective for r, _ in expanded]
        assert ids == [
            ObjectiveId.PERFORMANCE,
            ObjectiveId.QUALITY,
            ObjectiveId.REACH,
        ]


# ─────────────────────────────────────────────────────── script_generator


class TestScriptGenerator:
    def test_basic_generation_includes_header(self):
        cfg = _basic_tenant_config()
        script = generate_script(cfg, tenant_id="acme")
        assert "Auto-generated by deevAI" in script.source
        assert "Tenant: acme" in script.source
        assert "Performance: 0.600" in script.source
        assert script.aggregate_function == "sum_aggregate"
        assert script.n_criteria > 0

    def test_generation_is_deterministic(self):
        cfg = _basic_tenant_config()
        t = datetime(2026, 5, 18, 22, 0, tzinfo=timezone.utc)
        a = generate_script(cfg, tenant_id="acme", now=t)
        b = generate_script(cfg, tenant_id="acme", now=t)
        assert a.source == b.source
        assert a.digest_sha256 == b.digest_sha256

    def test_different_weights_produce_different_digests(self):
        a = generate_script(_basic_tenant_config(0.6, 0.3, 0.1), tenant_id="x")
        b = generate_script(_basic_tenant_config(0.4, 0.4, 0.2), tenant_id="x")
        assert a.digest_sha256 != b.digest_sha256

    def test_all_zero_weights_raises(self):
        cfg = TenantConfig(
            weights={
                ObjectiveId.PERFORMANCE: 0.0,
                ObjectiveId.QUALITY: 0.0,
                ObjectiveId.REACH: 0.0,
            },
        )
        with pytest.raises(ValueError, match="sum to 1.0"):
            generate_script(cfg, tenant_id="x")

    def test_invalid_aggregate_raises(self):
        cfg = _basic_tenant_config()
        with pytest.raises(ValueError, match="aggregate must be"):
            generate_script(cfg, tenant_id="x", aggregate="median_aggregate")

    def test_generated_source_under_size_cap(self):
        cfg = _basic_tenant_config()
        script = generate_script(cfg, tenant_id="x")
        assert len(script.source.encode("utf-8")) < 8 * 1024

    def test_explain_contains_metadata(self):
        cfg = _basic_tenant_config()
        script = generate_script(cfg, tenant_id="acme")
        text = explain(script)
        assert "acme" in text
        assert script.digest_sha256 in text
        assert "Criteria count" in text

    def test_render_diff_detects_identity(self):
        cfg = _basic_tenant_config()
        s = generate_script(cfg, tenant_id="acme")
        assert render_diff(s, s) == "(no changes)"

    def test_render_diff_detects_change(self):
        a = generate_script(_basic_tenant_config(0.6, 0.3, 0.1), tenant_id="x")
        b = generate_script(_basic_tenant_config(0.4, 0.4, 0.2), tenant_id="x")
        diff = render_diff(a, b)
        assert "no changes" not in diff
        assert "sha" in diff


# ─────────────────────────────────────────────────────── sandbox_validator


class TestSandboxValidator:
    def test_valid_script_passes(self):
        cfg = _basic_tenant_config()
        script = generate_script(cfg, tenant_id="x")
        report = validate_script(script.source)
        assert report.ok, [str(i) for i in report.issues]
        assert report.n_returns >= 1
        assert "country_code" in report.referenced_signals

    def test_assert_valid_does_not_raise_for_good_script(self):
        cfg = _basic_tenant_config()
        script = generate_script(cfg, tenant_id="x")
        assert_valid(script.source)  # no raise

    def test_unknown_signal_is_rejected(self):
        source = "return sum_aggregate([([magical_signal == 1], 100)])\n"
        report = validate_script(source)
        assert not report.ok
        assert any(i.kind == "unknown_name" for i in report.issues)
        assert any("magical_signal" in i.message for i in report.issues)

    def test_unknown_function_call_is_rejected(self):
        source = "return os_system_get('rm -rf /')\n"
        report = validate_script(source)
        assert not report.ok
        assert any(i.kind == "unknown_name" for i in report.issues)

    def test_syntax_error_is_caught(self):
        source = "return sum_aggregate([(\n"
        report = validate_script(source)
        assert not report.ok
        assert any(i.kind == "syntax" for i in report.issues)

    def test_missing_return_is_caught(self):
        source = "# only comments — no return\n"
        report = validate_script(source)
        assert not report.ok
        assert any("no `return`" in i.message for i in report.issues)

    def test_bare_return_is_caught(self):
        source = "return\n"
        report = validate_script(source)
        assert not report.ok
        assert any("Bare `return`" in i.message for i in report.issues)

    def test_assignment_is_rejected(self):
        # Assignments are not in the AST whitelist.
        source = "x = 10\nreturn x\n"
        report = validate_script(source)
        assert not report.ok
        assert any(i.kind == "forbidden_node" for i in report.issues)

    def test_function_def_is_rejected(self):
        source = "def helper():\n    return 1\nreturn helper()\n"
        report = validate_script(source)
        assert not report.ok
        # FunctionDef is not whitelisted.
        assert any(i.kind == "forbidden_node" for i in report.issues)

    def test_import_is_rejected(self):
        source = "import os\nreturn 1\n"
        report = validate_script(source)
        assert not report.ok
        assert any(i.kind == "forbidden_node" for i in report.issues)

    def test_lambda_is_rejected(self):
        source = "return (lambda x: x)(1)\n"
        report = validate_script(source)
        assert not report.ok

    def test_conditional_return_is_allowed(self):
        # Mimics the "Excluding slice" pattern from DV360 docs.
        source = (
            "if ad_type != 1:\n"
            "    return None\n"
            "return sum_aggregate([([video_completed == 1], 500)])\n"
        )
        report = validate_script(source)
        assert report.ok, [str(i) for i in report.issues]

    def test_conversion_callable_is_allowed(self):
        source = "return sum_aggregate([([total_conversion_value(123, 0) > 0], 700)])\n"
        report = validate_script(source)
        assert report.ok, [str(i) for i in report.issues]


# ─────────────────────────────────────────────────────── custom_bid_client


class _MockResponse:
    def __init__(self, status_code: int, json_body: dict | None = None,
                 text: str = ""):
        self.status_code = status_code
        self._json = json_body or {}
        self.text = text
        self.content = (text or str(json_body)).encode() if (text or json_body) else b""

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


class _MockSession:
    def __init__(self, responses: list[_MockResponse]):
        self._queue = list(responses)
        self.calls: list[dict] = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if not self._queue:
            raise AssertionError(f"unexpected extra call: {method} {url}")
        return self._queue.pop(0)


class _MockAuth:
    def headers(self, content_type: str = "application/json") -> dict:
        return {"Authorization": "Bearer fake-token", "Accept": "application/json"}


class TestCustomBidClient:
    def test_dry_run_short_circuits_create_algorithm(self):
        from bidagent.providers.dv360.custom_bid_client import Dv360CustomBidClient
        c = Dv360CustomBidClient(auth=_MockAuth(), dry_run=True)
        r = c.create_algorithm(
            display_name="deevAI Test",
            advertiser_id="123",
        )
        assert r.ok
        assert r.dry_run

    def test_create_algorithm_validates_exclusivity(self):
        from bidagent.providers.dv360.custom_bid_client import Dv360CustomBidClient
        c = Dv360CustomBidClient(auth=_MockAuth(), dry_run=True)
        with pytest.raises(ValueError, match="exactly one"):
            c.create_algorithm(display_name="x")  # neither
        with pytest.raises(ValueError, match="exactly one"):
            c.create_algorithm(  # both
                display_name="x", advertiser_id="1", partner_id="2",
            )

    def test_upload_full_script_walks_three_steps(self):
        from bidagent.providers.dv360.custom_bid_client import (
            Dv360CustomBidClient,
            UploadedScript,
        )

        session = _MockSession([
            # step 2: uploadScript → resourceName
            _MockResponse(200, {"resourceName": "customBiddingAlgorithms/A1/scriptRefs/abc"}),
            # step 3: media upload → 200 empty
            _MockResponse(200, {}),
            # step 4: scripts.create
            _MockResponse(200, {
                "customBiddingScriptId": "S42",
                "state": "PENDING",
                "customBiddingAlgorithmId": "A1",
            }),
        ])

        c = Dv360CustomBidClient(auth=_MockAuth(), session=session, dry_run=False)
        result = c.upload_full_script(
            "A1",
            "return sum_aggregate([([click == 1], 100)])\n",
            advertiser_id="123",
        )

        assert isinstance(result, UploadedScript)
        assert result.algorithm_id == "A1"
        assert result.script_id == "S42"
        assert result.state == "PENDING"
        # all three HTTP calls happened in order
        assert len(session.calls) == 3
        assert ":uploadScript" in session.calls[0]["url"]
        assert "/upload/media/" in session.calls[1]["url"]
        assert session.calls[2]["url"].endswith("/scripts")

    def test_upload_full_script_dry_run_returns_synthetic_upload(self):
        from bidagent.providers.dv360.custom_bid_client import Dv360CustomBidClient
        c = Dv360CustomBidClient(auth=_MockAuth(), dry_run=True)
        result = c.upload_full_script(
            "A1",
            "return 1\n",
            advertiser_id="123",
        )
        assert result.algorithm_id == "A1"
        assert result.script_id == "dryrun"
        assert result.state == "PENDING"

    def test_step2_failure_raises(self):
        from bidagent.providers.dv360.custom_bid_client import (
            Dv360CustomBidClient, Dv360CustomBidError,
        )
        session = _MockSession([
            _MockResponse(403, {"error": "no access"}),
        ])
        c = Dv360CustomBidClient(auth=_MockAuth(), session=session, dry_run=False)
        with pytest.raises(Dv360CustomBidError, match="step 2/4"):
            c.upload_full_script("A1", "return 1\n", advertiser_id="123")
