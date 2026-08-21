"""Regression test: factory rollback restores a previous version (spec 45)."""

from __future__ import annotations

import uuid

from app.agent_factory.factory import AgentFactory
from app.agent_factory.lifecycle import AgentLifecycle


def test_factory_create_then_rollback():
    af = AgentFactory()
    cap = f"synthesize a quuxish lumivox datamap from raw telemetry {uuid.uuid4().hex[:8]}"
    r = af.create(cap)
    assert r.status == "CREATED", (r.status, r.errors)
    aid = r.agent_id
    # create a second version
    af.bump_version(aid, notes="regression bump")
    # rollback to previous
    rb = AgentLifecycle().rollback(aid)
    assert rb.status == "ROLLED_BACK", rb.status
    assert rb.agent_version  # a real version string restored
