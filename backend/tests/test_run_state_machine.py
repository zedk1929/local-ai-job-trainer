import pytest
import asyncio
from app.services.run_store import RunStore
from app.database import init_db

@pytest.mark.asyncio
async def test_run_creation_and_cancellation():
    await init_db()
    store = RunStore()

    # Create dummy project
    proj = await store.create_project(
        name="Test Cafe",
        job_id="survey-cleaner",
        description="Testing run state machine",
        survey_context="Cafe survey",
        taxonomy=[{"id": "service", "name": "Service"}],
        coding_rules=["Rule 1"]
    )

    run = await store.create_run(proj["id"], "survey-cleaner", {"epochs": 1})
    assert run["status"] == "queued"
    assert run["current_stage"] == "check_setup"

    # Test event logging
    await store.log_event(run["id"], "check_setup", "info", "Testing event logging")
    events = await store.get_run_events(run["id"])
    assert len(events) >= 1
    assert any("Testing event logging" in e["message"] for e in events)

    # Test stage progression
    await store.update_run_stage(run["id"], "prepare_examples", "running")
    updated = await store.get_run(run["id"])
    assert updated["status"] == "running"
    assert updated["current_stage"] == "prepare_examples"

    # Test safe cancellation completion
    await store.complete_run(run["id"], {"canceled": True}, status="canceled")
    completed = await store.get_run(run["id"])
    assert completed["status"] == "canceled"
