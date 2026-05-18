"""LLM fallback path for meta-agent."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from deevai_api.services.meta_agent.runner import create_proposal_from_brief
from deevai_api.models import Advertiser, Integration, LineItem, Setting, Tenant


@pytest.mark.asyncio
async def test_llm_fallback_when_no_pattern_match(db_session) -> None:
    tenant = Tenant(name="LLM", slug="test-llm", plan="beta", status="active")
    db_session.add(tenant)
    await db_session.flush()
    setting = Setting(tenant_id=tenant.id, default_cpv_target=0.5)
    integration = Integration(tenant_id=tenant.id, name="Amazon", provider="amazon_dsp")
    db_session.add(integration)
    await db_session.flush()
    adv = Advertiser(
        tenant_id=tenant.id,
        integration_id=integration.id,
        amazon_advertiser_id="a1",
        name="Adv",
        currency="EUR",
        country="IT",
    )
    db_session.add(adv)
    await db_session.flush()
    li = LineItem(
        tenant_id=tenant.id,
        advertiser_id=adv.id,
        name="LI",
        amazon_line_item_id="1",
        cpv_target=0.5,
    )
    db_session.add(li)
    await db_session.flush()

    mock_llm = AsyncMock(
        return_value={
            "diagnosis": "Analisi LLM di test.",
            "proposed_changes": [],
            "expected_impact": {"confidence": "low"},
        },
    )

    with patch(
        "deevai_api.services.meta_agent.runner.quick_diagnose",
        return_value=None,
    ), patch(
        "deevai_api.services.meta_agent.runner.llm_diagnose",
        mock_llm,
    ), patch(
        "deevai_api.services.meta_agent.runner.assert_meta_agent_cooldown",
        AsyncMock(),
    ):
        proposal = await create_proposal_from_brief(
            db_session,
            tenant_id=tenant.id,
            line_item_id=li.id,
            brief="Situazione complessa non coperta dai pattern",
        )

    assert proposal.diagnosis == "Analisi LLM di test."
    mock_llm.assert_awaited_once()
