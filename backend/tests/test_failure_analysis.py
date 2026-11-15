import asyncio
import csv
import io
import json
from unittest.mock import patch

import aiosqlite
import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import HTTPException

from app.config import settings
from app.database import mark_interrupted_baseline_batches
from app.main import app
from app.api.routes_analysis import (
    recover_analyses,
    analysis_tasks,
    Proposal,
    FailureGroup,
    compute_field_outcomes,
    validate_evidence_references,
    check_rule_requirements,
)
from app.services.baseline_runner import baseline_batch_runner as runner
from app.services.run_store import run_store


async def settled(client, batch_id):
    for task in list(analysis_tasks.values()):
        await task
    return (await client.get(f'/api/baseline/batch/{batch_id}/analysis')).json()['analysis']



async def baseline(mode='connected', count=8):
    settings.app_mode = mode
    settings.local_model_name = 'source-model'
    p = await run_store.create_project('Analysis test', 'survey-cleaner', '', 'Original context',
                                      [{'id': 'service', 'name': 'Service'}], ['Original rule'])
    rows = [{'id': str(i), 'comment': f'Fictional feedback {i}', 'human_sent': 'positive',
             'human_topics': 'service', 'human_review': 'false', 'unrelated_private_column': 'DO_NOT_SEND'} for i in range(count)]
    with patch('app.services.baseline_runner.LocalModelBackend.infer_single', return_value={}):
        b = await runner.create_and_start_batch(p['id'], 'inline_rows', rows, 'comment', 'id',
                                               'human_topics', 'human_sent', 'human_review')
        task = runner.active_tasks.get(b['id'])
        if task:
            await task
    return p, await runner.get_batch(b['id'])


def proposal(payload):
    return {'summary': 'Missing fields need review.',
            'groups': [{'title': 'Invalid outputs', 'explanation': 'Check required fields.',
                        'row_indices': [payload['development_rows'][0]['row_index']]}],
            'proposed_rules': ['Proposed rule']}


@pytest.mark.asyncio
async def test_consent_and_configuration_gate_prevent_external_calls(monkeypatch):
    _, b = await baseline()
    monkeypatch.setattr(settings, 'supervisor_api_key', '')
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        with patch('app.api.routes_analysis.ask_parent') as parent:
            r = await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={})
            assert r.status_code == 400
            r = await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={'consent_to_share_responses': True})
            assert r.status_code == 503
            parent.assert_not_called()
        assert (await c.get(f"/api/baseline/batch/{b['id']}/analysis")).json()['analysis'] is None


@pytest.mark.asyncio
async def test_parent_sees_only_development_rows_and_approval_runs_frozen_comparison(monkeypatch):
    p, b = await baseline()
    monkeypatch.setattr(settings, 'supervisor_api_key', 'fictional-test-key')
    monkeypatch.setattr(settings, 'supervisor_provider', 'gemini')
    payloads = []

    async def parent(payload, client=None):
        payloads.append(payload)
        return proposal(payload), 'mocked-parent'

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        with patch('app.api.routes_analysis.ask_parent', side_effect=parent):
            r = await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={'consent_to_share_responses': True})
            assert r.status_code == 202, r.text
            analysis = await settled(c, b['id'])
            # Refresh/repeated analyze returns the saved proposal, not another parent request.
            assert (await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={})).json()['analysis']['id'] == analysis['id']
        assert len(payloads) == 1
        report = analysis['report']
        dev = set(report['development_row_indices'])
        evaluation = set(report['evaluation_row_indices'])
        assert dev.isdisjoint(evaluation) and len(dev | evaluation) == 8
        assert {r['row_index'] for r in payloads[0]['development_rows']} == dev
        assert 'DO_NOT_SEND' not in json.dumps(payloads)
        assert 'evaluation_rows' not in payloads[0]
        assert (await run_store.get_project(p['id']))['coding_rules'] == ['Original rule']
        assert analysis['comparison_batch_id'] is None
        assert (await c.post(f"/api/baseline/batch/{b['id']}/analysis/compare", json={'approved': False})).status_code == 422
        await run_store.update_project(p['id'], coding_rules=['Unrelated later edit'], survey_context='New context')
        settings.app_mode = 'preview'
        settings.local_model_name = 'different-model'
        calls = []

        async def infer(**kwargs):
            calls.append(kwargs)
            return {'topics': ['service'], 'sentiment': 'positive', 'needs_review': False}

        with patch('app.services.baseline_runner.LocalModelBackend.infer_single', side_effect=infer):
            r = await c.post(
                f"/api/baseline/batch/{b['id']}/analysis/compare",
                json={
                    'approved': True,
                    'rule_revision': 1,
                    'approved_rules': ['Proposed rule'],
                    'acknowledged_removed_rules': ['Original rule']
                }
            )
            assert r.status_code == 200, r.text
            candidate_id = r.json()['analysis']['comparison_batch_id']
            task = runner.active_tasks.get(candidate_id)
            if task:
                await task
        assert len(calls) == len(evaluation)
        for call in calls:
            assert call['app_mode'] == 'connected'
            assert call['model_name'] == 'source-model'
            assert call['context'] == 'Original context'
            assert call['rules'] == ['Proposed rule']
            assert call['use_adapter'] is False
        candidate = await runner.get_batch(candidate_id)
        assert candidate['snapshot']['source_batch_id'] == b['id']
        assert candidate['metrics']['sentiment_accuracy'] == 100
        assert report['reference_metrics']['sentiment_accuracy'] == 0
        assert report['reference_metrics']['sentiment_labeled_rows'] == len(evaluation)
        assert (await runner.get_batch(b['id']))['snapshot'] == b['snapshot']
        assert (await run_store.get_project(p['id']))['coding_rules'] == ['Unrelated later edit']
        repeat_compare = await c.post(
            f"/api/baseline/batch/{b['id']}/analysis/compare",
            json={
                'approved': True,
                'rule_revision': 1,
                'approved_rules': ['Proposed rule'],
                'acknowledged_removed_rules': ['Original rule']
            }
        )
        assert repeat_compare.json()['analysis']['comparison_batch_id'] == candidate_id
        export = await c.post(f'/api/baseline/batch/{candidate_id}/export')
        exported = list(csv.DictReader(io.StringIO(export.text)))
        assert {int(r['id']) for r in exported} == evaluation
        assert all(r['baseline_source_batch'] == b['id'] for r in exported)
        assert all(r['baseline_analysis_id'] == analysis['id'] for r in exported)


@pytest.mark.asyncio
async def test_preview_proposal_is_labeled_and_restart_retry_keeps_comparison_rows():
    _, b = await baseline('preview')
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        with patch('app.api.routes_analysis.ask_parent') as parent:
            r = await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={})
            assert r.status_code == 200
            parent.assert_not_called()
        analysis = r.json()['analysis']
        assert analysis['report']['is_simulated'] is True
        assert analysis['report']['parent_model'] == 'offline-preview'
        gate = asyncio.Event()

        async def slow(**kwargs):
            await gate.wait()
            return {'topics': [], 'sentiment': 'neutral', 'needs_review': False}

        with patch('app.services.baseline_runner.LocalModelBackend.infer_single', side_effect=slow):
            result = await c.post(
                f"/api/baseline/batch/{b['id']}/analysis/compare",
                json={
                    'approved': True,
                    'rule_revision': analysis['report']['rule_revision'],
                    'approved_rules': analysis['report']['proposed_rules']
                }
            )
            candidate_id = result.json()['analysis']['comparison_batch_id']
            # Interrupt after the worker enters inference.
            await asyncio.sleep(.02)
            task = runner.active_tasks.get(candidate_id)
            runner.cancel_batch(candidate_id)
            if task:
                await task
        with patch('app.services.baseline_runner.LocalModelBackend.infer_single', return_value={'topics': [], 'sentiment': 'neutral', 'needs_review': False}):
            retried = await runner.retry_batch(candidate_id)
            task = runner.active_tasks.get(retried['id'])
            if task:
                await task
        retried = await runner.get_batch(retried['id'])
        assert retried['total_rows'] == len(analysis['report']['evaluation_row_indices'])
        assert retried['snapshot']['source_row_indices'] == analysis['report']['evaluation_row_indices']
        assert retried['snapshot']['coding_rules'] == analysis['report']['proposed_rules']
        saved = (await c.get(f"/api/baseline/batch/{b['id']}/analysis")).json()['analysis']
        assert saved['comparison_batch_id'] == retried['id']


@pytest.mark.asyncio
async def test_invalid_parent_evidence_fails_without_fixture_substitution(monkeypatch):
    _, b = await baseline()
    monkeypatch.setattr(settings, 'supervisor_api_key', 'fictional-test-key')
    monkeypatch.setattr(settings, 'supervisor_provider', 'gemini')

    async def parent(payload, client=None):
        result = proposal(payload)
        result['groups'][0]['row_indices'] = [999]
        return result, 'mocked-parent'

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        with patch('app.api.routes_analysis.ask_parent', side_effect=parent):
            r = await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={'consent_to_share_responses': True})
            assert r.status_code == 202
            saved = await settled(c, b['id'])
        assert saved['status'] == 'failed' and saved['report'] == {}


@pytest.mark.asyncio
async def test_restart_recovers_analysis_reservations():
    p, b = await baseline('preview')
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("INSERT INTO failure_analyses (id,source_batch_id,project_id,status,comparison_batch_id,created_at) VALUES ('a',?,?, 'analyzing','starting','now')", (b['id'], p['id']))
        await db.commit()
    await recover_analyses()
    async with aiosqlite.connect(settings.db_path) as db:
        row = await (await db.execute("SELECT status,comparison_batch_id FROM failure_analyses WHERE id='a'")).fetchone()
    assert row == ('failed', None)


@pytest.mark.asyncio
async def test_unlabeled_or_incomplete_baseline_cannot_generate_proposal():
    _, b = await baseline('preview', count=2)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        r = await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={})
        assert r.status_code == 400
        assert 'four' in r.json()['detail']


@pytest.mark.asyncio
async def test_parent_http_failure_is_sanitized_and_never_simulated(monkeypatch):
    _, b = await baseline()
    monkeypatch.setattr(settings, 'supervisor_api_key', 'fictional-secret-must-not-leak')
    monkeypatch.setattr(settings, 'supervisor_provider', 'gemini')
    original_client = httpx.AsyncClient

    def handler(request):
        assert request.headers['x-goog-api-key'] == 'fictional-secret-must-not-leak'
        assert 'key=' not in str(request.url)
        return httpx.Response(403, text='fictional-secret-must-not-leak')

    def mock_client(*args, **kwargs):
        return original_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    async with original_client(transport=ASGITransport(app=app), base_url='http://test') as c:
        with patch('app.api.routes_analysis.httpx.AsyncClient', side_effect=mock_client):
            r = await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={'consent_to_share_responses': True})
            assert r.status_code == 202
            saved = await settled(c, b['id'])
        assert 'fictional-secret' not in json.dumps(saved)
        assert saved['status'] == 'failed'
        assert saved['report'] == {}


@pytest.mark.asyncio
async def test_slow_parent_runs_in_background_without_duplicate_requests(monkeypatch):
    p, b = await baseline()
    monkeypatch.setattr(settings, 'supervisor_api_key', 'fictional-original-key')
    monkeypatch.setattr(settings, 'supervisor_provider', 'gemini')
    gate = asyncio.Event()
    started = asyncio.Event()
    calls = []

    async def slow_parent(payload, client=None):
        calls.append(client)
        started.set()
        await gate.wait()
        assert client.provider == 'gemini'
        assert client.api_key == 'fictional-original-key'
        return proposal(payload), 'mocked-slow-parent'

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        with patch('app.api.routes_analysis.ask_parent', side_effect=slow_parent):
            try:
                first = await asyncio.wait_for(c.post(f"/api/baseline/batch/{b['id']}/analysis", json={'consent_to_share_responses': True}), timeout=1)
                assert first.status_code == 202
                await asyncio.wait_for(started.wait(), timeout=1)
                state = (await c.get(f"/api/baseline/batch/{b['id']}/analysis")).json()['analysis']
                assert state['status'] == 'analyzing'
                again = await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={})
                assert again.status_code == 202
                assert again.json()['analysis']['id'] == state['id']
                assert len(calls) == 1
                monkeypatch.setattr(settings, 'supervisor_provider', 'anthropic')
                monkeypatch.setattr(settings, 'supervisor_api_key', 'fictional-other-key')
            finally:
                gate.set()
                for task in list(analysis_tasks.values()):
                    await task
            state = await settled(c, b['id'])
            assert state['status'] == 'ready'
            assert state['report']['parent_provider'] == 'gemini'
            assert (await run_store.get_project(p['id']))['coding_rules'] == ['Original rule']


@pytest.mark.asyncio
async def test_timeout_is_saved_and_retry_uses_the_same_development_split(monkeypatch):
    p, b = await baseline()
    monkeypatch.setattr(settings, 'supervisor_provider', 'gemini')
    monkeypatch.setattr(settings, 'supervisor_api_key', 'fictional-key')
    seen = []

    async def parent(payload, client=None):
        seen.append([r['row_index'] for r in payload['development_rows']])
        if len(seen) == 1:
            raise HTTPException(504, 'Parent response timed out. No fixture was substituted.')
        return proposal(payload), 'mocked-parent'

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        with patch('app.api.routes_analysis.ask_parent', side_effect=parent):
            response = await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={'consent_to_share_responses': True})
            assert response.status_code == 202
            failed = await settled(c, b['id'])
            assert failed['status'] == 'failed'
            assert 'timed out' in failed['error_message']
            assert failed['report'] == {}
            response = await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={'consent_to_share_responses': True})
            assert response.status_code == 202
            ready = await settled(c, b['id'])
            assert ready['status'] == 'ready'
            assert seen[0] == seen[1]
        assert (await run_store.get_project(p['id']))['coding_rules'] == ['Original rule']


def test_correctly_predicted_review_flag_rejected_as_evidence_for_missed_flag_claim():
    # Simulates row index 51 (DEV_52): ground truth review=true, predicted review=true (match)
    dev_outcomes = {
        51: {
            "review_flag": {
                "label_status": "valid_label",
                "ground_truth": True,
                "prediction_status": "match",
                "predicted": True,
            },
            "topics": {"label_status": "valid_label", "prediction_status": "match", "ground_truth": ["service"]},
            "sentiment": {"label_status": "valid_label", "prediction_status": "match", "ground_truth": "positive"},
            "schema": {"is_valid": True, "errors": [], "transport_status": "success"},
            "is_failure": False,
        }
    }
    proposal_obj = Proposal(
        summary="Test summary",
        groups=[
            FailureGroup(
                title="Missed Safety and Hygiene Review Flag",
                failure_type="missed_review_flag",
                explanation="Model missed safety review flag.",
                row_indices=[51],
            )
        ],
        proposed_rules=["Always flag safety issues."],
    )
    errors, warnings = validate_evidence_references(proposal_obj, dev_outcomes, strict=False)
    assert len(errors) == 1
    assert "row 51 review prediction matched the human label" in errors[0]

    with pytest.raises(ValueError, match="matched the human label"):
        validate_evidence_references(proposal_obj, dev_outcomes, strict=True)


def test_genuine_missed_and_unnecessary_flags_accepted():
    # Row 48: ground truth review=True, predicted review=False -> missed_flag
    # Row 20: ground truth review=False, predicted review=True -> unnecessary_flag
    dev_outcomes = {
        48: {
            "review_flag": {
                "label_status": "valid_label",
                "ground_truth": True,
                "prediction_status": "missed_flag",
                "predicted": False,
            },
            "topics": {"label_status": "valid_label", "prediction_status": "match", "ground_truth": ["service"]},
            "sentiment": {"label_status": "valid_label", "prediction_status": "match", "ground_truth": "positive"},
            "schema": {"is_valid": True, "errors": [], "transport_status": "success"},
            "is_failure": True,
        },
        20: {
            "review_flag": {
                "label_status": "valid_label",
                "ground_truth": False,
                "prediction_status": "unnecessary_flag",
                "predicted": True,
            },
            "topics": {"label_status": "valid_label", "prediction_status": "match", "ground_truth": ["service"]},
            "sentiment": {"label_status": "valid_label", "prediction_status": "match", "ground_truth": "positive"},
            "schema": {"is_valid": True, "errors": [], "transport_status": "success"},
            "is_failure": True,
        },
    }
    proposal_obj = Proposal(
        summary="Test summary",
        groups=[
            FailureGroup(
                title="Missed safety flags",
                failure_type="missed_review_flag",
                explanation="Model missed safety review flag on row 48.",
                row_indices=[48],
            ),
            FailureGroup(
                title="Unnecessary review flags",
                failure_type="unnecessary_review_flag",
                explanation="Model flagged ordinary complaints on row 20.",
                row_indices=[20],
            ),
        ],
        proposed_rules=["Only flag genuine safety issues."],
    )
    errors, warnings = validate_evidence_references(proposal_obj, dev_outcomes, strict=True)
    assert errors == []


def test_missing_and_invalid_human_labels_excluded_from_mismatch_claims():
    # Row 10: missing human sentiment label
    # Row 11: invalid human topic label (e.g. unknown topic ID)
    dev_outcomes = {
        10: {
            "sentiment": {"label_status": "missing_label"},
            "review_flag": {"label_status": "valid_label", "prediction_status": "match", "ground_truth": False, "predicted": False},
            "topics": {"label_status": "valid_label", "prediction_status": "match", "ground_truth": []},
            "schema": {"is_valid": True, "errors": [], "transport_status": "success"},
            "is_failure": False,
        },
        11: {
            "topics": {"label_status": "invalid_label", "error": "Unknown topic ID 'nonexistent'"},
            "sentiment": {"label_status": "valid_label", "prediction_status": "match", "ground_truth": "neutral", "predicted": "neutral"},
            "review_flag": {"label_status": "valid_label", "prediction_status": "match", "ground_truth": False, "predicted": False},
            "schema": {"is_valid": True, "errors": [], "transport_status": "success"},
            "is_failure": False,
        },
    }
    proposal_obj = Proposal(
        summary="Test summary",
        groups=[
            FailureGroup(
                title="Sentiment mismatch",
                failure_type="sentiment_mismatch",
                explanation="Model predicted neutral instead of missing label.",
                row_indices=[10],
            ),
            FailureGroup(
                title="Topic mismatch",
                failure_type="topics_mismatch",
                explanation="Model did not match invalid label.",
                row_indices=[11],
            ),
        ],
        proposed_rules=["Rule 1"],
    )
    errors, _ = validate_evidence_references(proposal_obj, dev_outcomes, strict=False)
    assert len(errors) == 2
    assert "missing human sentiment label" in errors[0]
    assert "invalid human topic label" in errors[1]


def test_invalid_predicted_fields_distinguished_from_valid_mismatches():
    # Row 30: model output was invalid prediction
    # Row 31: model output was completely valid
    dev_outcomes = {
        30: {
            "sentiment": {
                "label_status": "valid_label",
                "ground_truth": "positive",
                "prediction_status": "invalid_prediction",
                "predicted": None,
            },
            "topics": {"label_status": "valid_label", "prediction_status": "invalid_prediction", "ground_truth": ["service"]},
            "review_flag": {"label_status": "valid_label", "prediction_status": "invalid_prediction", "ground_truth": False},
            "schema": {"is_valid": False, "errors": ["Missing field 'sentiment'"], "transport_status": "success"},
            "is_failure": True,
        },
        31: {
            "sentiment": {"label_status": "valid_label", "ground_truth": "positive", "prediction_status": "match", "predicted": "positive"},
            "topics": {"label_status": "valid_label", "ground_truth": ["service"], "prediction_status": "match", "predicted": ["service"]},
            "review_flag": {"label_status": "valid_label", "ground_truth": False, "prediction_status": "match", "predicted": False},
            "schema": {"is_valid": True, "errors": [], "transport_status": "success"},
            "is_failure": False,
        },
    }
    proposal_invalid_claimed_as_mismatch = Proposal(
        summary="Summary",
        groups=[
            FailureGroup(
                title="Sentiment Mismatch",
                failure_type="sentiment_mismatch",
                explanation="Sentiment did not match.",
                row_indices=[30],
            )
        ],
        proposed_rules=["Rule 1"],
    )
    errors, _ = validate_evidence_references(proposal_invalid_claimed_as_mismatch, dev_outcomes, strict=False)
    assert len(errors) == 1
    assert "row 30 sentiment prediction was invalid" in errors[0]

    proposal_valid_claimed_as_invalid_output = Proposal(
        summary="Summary",
        groups=[
            FailureGroup(
                title="Invalid Schema",
                failure_type="invalid_output",
                explanation="Model output failed schema.",
                row_indices=[31],
            )
        ],
        proposed_rules=["Rule 1"],
    )
    errors, _ = validate_evidence_references(proposal_valid_claimed_as_invalid_output, dev_outcomes, strict=False)
    assert len(errors) == 1
    assert "row 31 output is completely valid" in errors[0]


def test_check_rule_requirements_detects_dropped_unclear_sentiment():
    orig_rules = [
        "Assign only listed topics.",
        "Assign sentiment unclear and set needs_review=true for incomprehensible or unintelligible text."
    ]
    prop_rules_missing_unclear = [
        "Assign only listed topics.",
        "Set needs_review=true for safety issues or incomprehensible text."
    ]
    warns = check_rule_requirements(orig_rules, prop_rules_missing_unclear)
    assert len(warns) >= 1
    assert any("unclear" in w for w in warns)

    prop_rules_preserved = [
        "Assign only listed topics.",
        "Set needs_review=true and assign sentiment unclear for incomprehensible text."
    ]
    warns_ok = check_rule_requirements(orig_rules, prop_rules_preserved)
    assert not any("unclear" in w for w in warns_ok)


@pytest.mark.asyncio
async def test_rule_edits_persist_across_refresh():
    p, b = await baseline('preview')
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        r = await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={})
        assert r.status_code == 200
        analysis = r.json()['analysis']
        assert analysis['report']['rule_revision'] == 1

        new_rules = ["Edited rule 1: preserve unclear sentiment", "Edited rule 2: flag safety hazards"]
        patch_res = await c.patch(
            f"/api/baseline/batch/{b['id']}/analysis/rules",
            json={"proposed_rules": new_rules}
        )
        assert patch_res.status_code == 200
        patched_analysis = patch_res.json()['analysis']
        assert patched_analysis['report']['proposed_rules'] == new_rules
        assert patched_analysis['report']['rule_revision'] == 2

        # Verify persistence across a fresh GET (simulating page refresh)
        get_res = await c.get(f"/api/baseline/batch/{b['id']}/analysis")
        assert get_res.status_code == 200
        refreshed_analysis = get_res.json()['analysis']
        assert refreshed_analysis['report']['proposed_rules'] == new_rules
        assert refreshed_analysis['report']['rule_revision'] == 2


@pytest.mark.asyncio
async def test_edits_reset_approval():
    p, b = await baseline('preview')
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={})

        # Set approved_revision to 1 directly in DB to simulate prior approval
        analysis = (await c.get(f"/api/baseline/batch/{b['id']}/analysis")).json()['analysis']
        report = analysis['report']
        report['approved_revision'] = 1
        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute('UPDATE failure_analyses SET report = ? WHERE id = ?', (json.dumps(report), analysis['id']))
            await db.commit()

        check = (await c.get(f"/api/baseline/batch/{b['id']}/analysis")).json()['analysis']
        assert check['report']['approved_revision'] == 1

        # Now edit rules
        patch_res = await c.patch(
            f"/api/baseline/batch/{b['id']}/analysis/rules",
            json={"proposed_rules": ["Revised rule"]}
        )
        assert patch_res.status_code == 200
        patched = patch_res.json()['analysis']
        # Approval MUST be reset to None
        assert patched['report']['approved_revision'] is None
        assert patched['report']['rule_revision'] == 2


@pytest.mark.asyncio
async def test_stale_revision_approval_rejected():
    p, b = await baseline('preview')
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={})

        # Update rules so revision advances to 2
        await c.patch(
            f"/api/baseline/batch/{b['id']}/analysis/rules",
            json={"proposed_rules": ["Revision 2 rule"]}
        )

        # Attempt to approve stale revision 1
        stale_res = await c.post(
            f"/api/baseline/batch/{b['id']}/analysis/compare",
            json={"approved": True, "rule_revision": 1, "approved_rules": ["Revision 2 rule"]}
        )
        assert stale_res.status_code == 409
        assert "Stale rule revision" in stale_res.json()['detail']
        assert "current revision is 2" in stale_res.json()['detail']

        # Also test rule content mismatch rejection
        mismatch_res = await c.post(
            f"/api/baseline/batch/{b['id']}/analysis/compare",
            json={"approved": True, "rule_revision": 2, "approved_rules": ["Different rule"]}
        )
        assert mismatch_res.status_code == 409
        assert "Rule content mismatch" in mismatch_res.json()['detail']


@pytest.mark.asyncio
async def test_comparison_receives_exactly_approved_rules():
    p, b = await baseline('preview')
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={})

        # Edit proposed rules
        approved_rules = ["Custom rule A: preserve unclear", "Custom rule B: precision tagging"]
        await c.patch(
            f"/api/baseline/batch/{b['id']}/analysis/rules",
            json={"proposed_rules": approved_rules}
        )

        # Approve comparison with current revision 2
        comp_res = await c.post(
            f"/api/baseline/batch/{b['id']}/analysis/compare",
            json={
                "approved": True,
                "rule_revision": 2,
                "approved_rules": approved_rules,
                "acknowledged_removed_rules": ["Original rule"]
            }
        )
        assert comp_res.status_code == 200, comp_res.text
        candidate_id = comp_res.json()['analysis']['comparison_batch_id']

        # Wait for candidate task if running
        task = runner.active_tasks.get(candidate_id)
        if task:
            await task

        candidate = await runner.get_batch(candidate_id)
        assert candidate['snapshot']['coding_rules'] == approved_rules
        assert candidate['snapshot']['rule_revision'] == 2
        assert candidate['snapshot']['evaluation_role'] == 'development_comparison'
        assert candidate['snapshot']['source_batch_id'] == b['id']

        # Verify editing rules after comparison has started is forbidden (HTTP 409)
        edit_locked = await c.patch(
            f"/api/baseline/batch/{b['id']}/analysis/rules",
            json={"proposed_rules": ["Try editing after start"]}
        )
        assert edit_locked.status_code == 409
        assert "Cannot edit proposed rules after a comparison run has started" in edit_locked.json()['detail']


@pytest.mark.asyncio
async def test_original_rules_and_results_remain_unchanged():
    p, b = await baseline('preview')
    original_rules = list(p['coding_rules'])
    original_snapshot = dict(b['snapshot'])

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={})
        await c.patch(
            f"/api/baseline/batch/{b['id']}/analysis/rules",
            json={"proposed_rules": ["Radically different proposed rule"]}
        )
        comp_res = await c.post(
            f"/api/baseline/batch/{b['id']}/analysis/compare",
            json={
                "approved": True,
                "rule_revision": 2,
                "approved_rules": ["Radically different proposed rule"],
                "acknowledged_removed_rules": ["Original rule"]
            }
        )
        assert comp_res.status_code == 200, comp_res.text
        candidate_id = comp_res.json()['analysis']['comparison_batch_id']
        task = runner.active_tasks.get(candidate_id)
        if task:
            await task

    # Verify project coding_rules in DB are unchanged
    project = await run_store.get_project(p['id'])
    assert project['coding_rules'] == original_rules

    # Verify source baseline batch snapshot and results are unchanged
    source_batch = await runner.get_batch(b['id'])
    assert source_batch['snapshot']['coding_rules'] == original_snapshot['coding_rules']
    assert source_batch['status'] == 'completed'


@pytest.mark.asyncio
async def test_comparison_rows_absent_from_parent_payload(monkeypatch):
    p, b = await baseline()
    monkeypatch.setattr(settings, 'supervisor_api_key', 'fictional-test-key')
    monkeypatch.setattr(settings, 'supervisor_provider', 'gemini')
    captured_payloads = []

    async def parent(payload, client=None):
        captured_payloads.append(payload)
        return proposal(payload), 'mocked-parent'

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        with patch('app.api.routes_analysis.ask_parent', side_effect=parent):
            r = await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={'consent_to_share_responses': True})
            assert r.status_code == 202
            analysis = await settled(c, b['id'])

    assert len(captured_payloads) == 1
    sent_payload = captured_payloads[0]
    dev_indices = set(analysis['report']['development_row_indices'])
    eval_indices = set(analysis['report']['evaluation_row_indices'])

    # Verify payload only contains development rows
    payload_indices = {r['row_index'] for r in sent_payload['development_rows']}
    assert payload_indices == dev_indices
    # Evaluation rows must be completely absent
    assert payload_indices.isdisjoint(eval_indices)
    assert 'evaluation_rows' not in sent_payload
    # Unmapped private column from original data must not be leaked into payload
    serialized_payload = json.dumps(sent_payload)
    assert 'DO_NOT_SEND' not in serialized_payload
    assert 'unrelated_private_column' not in serialized_payload


@pytest.mark.asyncio
async def test_missing_approval_revision_or_content_rejected():
    p, b = await baseline('preview')
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={})

        # Missing rule_revision and approved_rules
        res1 = await c.post(f"/api/baseline/batch/{b['id']}/analysis/compare", json={"approved": True})
        assert res1.status_code == 422

        # Missing approved_rules
        res2 = await c.post(f"/api/baseline/batch/{b['id']}/analysis/compare", json={"approved": True, "rule_revision": 1})
        assert res2.status_code == 422

        # Missing rule_revision
        res3 = await c.post(f"/api/baseline/batch/{b['id']}/analysis/compare", json={"approved": True, "approved_rules": ["Rule"]})
        assert res3.status_code == 422


@pytest.mark.asyncio
async def test_concurrent_saves_conflict():
    p, b = await baseline('preview')
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        res = await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={})
        analysis = res.json()['analysis']
        assert analysis['report']['rule_revision'] == 1

        # Session A and Session B both read revision 1
        # Session A saves rules A with base_revision=1
        res_a = await c.patch(
            f"/api/baseline/batch/{b['id']}/analysis/rules",
            json={"proposed_rules": ["Rule A"], "base_revision": 1}
        )
        assert res_a.status_code == 200
        assert res_a.json()['analysis']['report']['rule_revision'] == 2
        assert res_a.json()['analysis']['report']['proposed_rules'] == ["Rule A"]

        # Session B attempts to save rules B with stale base_revision=1
        res_b = await c.patch(
            f"/api/baseline/batch/{b['id']}/analysis/rules",
            json={"proposed_rules": ["Rule B"], "base_revision": 1}
        )
        assert res_b.status_code == 409
        assert "Conflict" in res_b.json()['detail']
        assert "current revision is 2" in res_b.json()['detail']

        # After reading revision 2, Session B can save revision 3
        res_b_ok = await c.patch(
            f"/api/baseline/batch/{b['id']}/analysis/rules",
            json={"proposed_rules": ["Rule B"], "base_revision": 2}
        )
        assert res_b_ok.status_code == 200
        assert res_b_ok.json()['analysis']['report']['rule_revision'] == 3
        assert res_b_ok.json()['analysis']['report']['proposed_rules'] == ["Rule B"]


@pytest.mark.asyncio
async def test_save_versus_approval_race():
    p, b = await baseline('preview')
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        res = await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={})
        analysis = res.json()['analysis']
        rules = analysis['report']['proposed_rules']
        rev = analysis['report']['rule_revision']

        # Approval starts comparison
        comp_res = await c.post(
            f"/api/baseline/batch/{b['id']}/analysis/compare",
            json={"approved": True, "rule_revision": rev, "approved_rules": rules}
        )
        assert comp_res.status_code == 200

        # Race: simultaneous rule save must be rejected because comparison has started
        save_res = await c.patch(
            f"/api/baseline/batch/{b['id']}/analysis/rules",
            json={"proposed_rules": ["Rule while starting"], "base_revision": rev}
        )
        assert save_res.status_code == 409
        assert "Cannot edit proposed rules after a comparison run has started" in save_res.json()['detail']


@pytest.mark.asyncio
async def test_failed_save_approval_blocked():
    p, b = await baseline('preview')
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        res = await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={})
        analysis = res.json()['analysis']

        # Client attempts to save empty rules -> rejected
        save_res = await c.patch(
            f"/api/baseline/batch/{b['id']}/analysis/rules",
            json={"proposed_rules": [""]}
        )
        assert save_res.status_code == 422

        # Client tries to approve empty rule list or modified rules without saving
        comp_res_empty = await c.post(
            f"/api/baseline/batch/{b['id']}/analysis/compare",
            json={"approved": True, "rule_revision": 1, "approved_rules": []}
        )
        assert comp_res_empty.status_code == 422

        comp_res_mismatch = await c.post(
            f"/api/baseline/batch/{b['id']}/analysis/compare",
            json={"approved": True, "rule_revision": 1, "approved_rules": ["Unsaved edited rule text"]}
        )
        assert comp_res_mismatch.status_code == 409
        assert "Rule content mismatch" in comp_res_mismatch.json()['detail']


@pytest.mark.asyncio
async def test_contradictory_evidence_blocks_proposal_and_comparison(monkeypatch):
    p, b = await baseline()
    monkeypatch.setattr(settings, 'supervisor_api_key', 'fictional-key')
    monkeypatch.setattr(settings, 'supervisor_provider', 'gemini')

    async def contradictory_parent(payload, client=None):
        return {
            'summary': 'Contradictory proposal',
            'groups': [{
                'title': 'Missed review flag on matching row',
                'failure_type': 'missed_review_flag',
                'explanation': 'Contradictory claim',
                'row_indices': [payload['development_rows'][0]['row_index']]
            }],
            'proposed_rules': ['Rule 1']
        }, 'mock-parent'

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        with patch('app.api.routes_analysis.ask_parent', side_effect=contradictory_parent):
            r = await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={'consent_to_share_responses': True})
            assert r.status_code == 202
            analysis = await settled(c, b['id'])

        # Proposal status must be invalid_proposal
        assert analysis['status'] == 'invalid_proposal'
        assert analysis['report']['has_blocking_errors'] is True
        assert len(analysis['report']['validation_errors']) >= 1

        # Approval must be rejected
        comp_res = await c.post(
            f"/api/baseline/batch/{b['id']}/analysis/compare",
            json={"approved": True, "rule_revision": 1, "approved_rules": ['Rule 1']}
        )
        assert comp_res.status_code == 422
        assert "invalid or contradictory evidence" in comp_res.json()['detail']

        # Rule editing must be rejected on invalid proposal
        edit_res = await c.patch(
            f"/api/baseline/batch/{b['id']}/analysis/rules",
            json={"proposed_rules": ["Edited rule"]}
        )
        assert edit_res.status_code == 422
        assert "Cannot edit rules for an invalid proposal" in edit_res.json()['detail']

        # Deliberate regeneration clears invalid proposal and runs fresh
        async def valid_parent(payload, client=None):
            return {
                'summary': 'Valid proposal',
                'groups': [{
                    'title': 'Valid schema failure',
                    'failure_type': 'invalid_output',
                    'explanation': 'Row 0 schema invalid',
                    'row_indices': [payload['development_rows'][0]['row_index']]
                }],
                'proposed_rules': ['Original rule', 'Rule 1']
            }, 'mock-parent'

        with patch('app.api.routes_analysis.ask_parent', side_effect=valid_parent):
            regen_res = await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={'consent_to_share_responses': True})
            assert regen_res.status_code == 202
            fresh = await settled(c, b['id'])
            assert fresh['status'] == 'ready'
            assert fresh['report']['has_blocking_errors'] is False


@pytest.mark.asyncio
async def test_unsupported_failure_types_rejected(monkeypatch):
    p, b = await baseline()
    monkeypatch.setattr(settings, 'supervisor_api_key', 'fictional-key')
    monkeypatch.setattr(settings, 'supervisor_provider', 'gemini')

    async def bad_parent(payload, client=None):
        return {
            'summary': 'Unsupported failure type',
            'groups': [{
                'title': 'Hallucination check',
                'failure_type': 'unsupported_hallucination_type',
                'explanation': 'Unsupported type',
                'row_indices': [payload['development_rows'][0]['row_index']]
            }],
            'proposed_rules': ['Rule 1']
        }, 'mock-parent'

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        with patch('app.api.routes_analysis.ask_parent', side_effect=bad_parent):
            r = await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={'consent_to_share_responses': True})
            assert r.status_code == 202
            analysis = await settled(c, b['id'])

        assert analysis['status'] == 'invalid_proposal'
        assert any("unsupported failure type 'unsupported_hallucination_type'" in e for e in analysis['report']['validation_errors'])


@pytest.mark.asyncio
async def test_removal_of_arbitrary_original_rule_requires_acknowledgment():
    proj = await run_store.create_project(
        'Rule Removal Test',
        'survey-cleaner',
        '',
        'Context',
        [{'id': 'service', 'name': 'Service'}],
        ['Never include respondent names or contact details in summaries.', 'Assign only listed topics.']
    )
    rows = [{'id': str(i), 'comment': f'Feedback {i}', 'human_sent': 'positive',
             'human_topics': 'service', 'human_review': 'false'} for i in range(8)]
    with patch('app.services.baseline_runner.LocalModelBackend.infer_single', return_value={}):
        b = await runner.create_and_start_batch(
            proj['id'], 'inline_rows', rows, 'comment', 'id', 'human_topics', 'human_sent', 'human_review'
        )
        task = runner.active_tasks.get(b['id'])
        if task:
            await task

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={})

        # Edit rules to omit 'Never include respondent names or contact details in summaries.'
        reduced_rules = ['Assign only listed topics.', 'Assign neutral sentiment.']
        patch_res = await c.patch(
            f"/api/baseline/batch/{b['id']}/analysis/rules",
            json={"proposed_rules": reduced_rules, "base_revision": 1}
        )
        assert patch_res.status_code == 200
        report = patch_res.json()['analysis']['report']
        assert 'Never include respondent names or contact details in summaries.' in report['removed_original_rules']
        assert report['is_fully_preserved'] is False

        # Attempt to approve without acknowledging the removed original rule
        unack_res = await c.post(
            f"/api/baseline/batch/{b['id']}/analysis/compare",
            json={"approved": True, "rule_revision": 2, "approved_rules": reduced_rules}
        )
        assert unack_res.status_code == 422
        assert "explicit acknowledgment of all removed original rules" in unack_res.json()['detail']
        assert "Never include respondent names or contact details in summaries." in unack_res.json()['detail']

        # Approve with explicit acknowledgment
        ack_res = await c.post(
            f"/api/baseline/batch/{b['id']}/analysis/compare",
            json={
                "approved": True,
                "rule_revision": 2,
                "approved_rules": reduced_rules,
                "acknowledged_removed_rules": ["Never include respondent names or contact details in summaries."]
            }
        )
        assert ack_res.status_code == 200, ack_res.text
        candidate_id = ack_res.json()['analysis']['comparison_batch_id']
        candidate = await runner.get_batch(candidate_id)
        assert candidate['snapshot']['coding_rules'] == reduced_rules
        assert candidate['snapshot']['rule_revision'] == 2


@pytest.mark.asyncio
async def test_genuinely_concurrent_interleaving_save_wins_and_approval_rejected():
    import app.api.routes_analysis as routes_analysis
    p, b = await baseline('preview')
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        res = await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={})
        analysis = res.json()['analysis']
        rules = analysis['report']['proposed_rules']
        rev = analysis['report']['rule_revision']
        assert rev == 1

        save_started = asyncio.Event()
        compare_started = asyncio.Event()
        proceed_save = asyncio.Event()
        proceed_compare = asyncio.Event()

        async def pre_save():
            save_started.set()
            await proceed_save.wait()

        async def pre_compare():
            compare_started.set()
            await proceed_compare.wait()

        routes_analysis._pre_save_hook = pre_save
        routes_analysis._pre_compare_hook = pre_compare

        try:
            new_rules = ["Genuinely concurrent new rule"]
            save_task = asyncio.create_task(
                c.patch(
                    f"/api/baseline/batch/{b['id']}/analysis/rules",
                    json={"proposed_rules": new_rules, "base_revision": rev}
                )
            )
            compare_task = asyncio.create_task(
                c.post(
                    f"/api/baseline/batch/{b['id']}/analysis/compare",
                    json={"approved": True, "rule_revision": rev, "approved_rules": rules}
                )
            )

            # Wait until both have completed reads and paused right before their atomic SQL queries
            await asyncio.wait_for(save_started.wait(), timeout=3.0)
            await asyncio.wait_for(compare_started.wait(), timeout=3.0)

            # Ordering 1: Save proceeds first and commits revision 2
            proceed_save.set()
            save_res = await save_task
            assert save_res.status_code == 200
            assert save_res.json()['analysis']['report']['rule_revision'] == 2
            assert save_res.json()['analysis']['report']['proposed_rules'] == new_rules

            # Approval proceeds second and must fail atomically with 409 Conflict
            proceed_compare.set()
            compare_res = await compare_task
            assert compare_res.status_code == 409
            assert "Conflict" in compare_res.json()['detail']

            # Verify saved rules were not discarded and comparison was not launched with old rules
            check = await c.get(f"/api/baseline/batch/{b['id']}/analysis")
            final_report = check.json()['analysis']['report']
            assert final_report['rule_revision'] == 2
            assert final_report['proposed_rules'] == new_rules
            assert check.json()['analysis']['comparison_batch_id'] is None
        finally:
            routes_analysis._pre_save_hook = None
            routes_analysis._pre_compare_hook = None


@pytest.mark.asyncio
async def test_genuinely_concurrent_interleaving_approval_wins_and_save_rejected():
    import app.api.routes_analysis as routes_analysis
    p, b = await baseline('preview')
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        res = await c.post(f"/api/baseline/batch/{b['id']}/analysis", json={})
        analysis = res.json()['analysis']
        rules = analysis['report']['proposed_rules']
        rev = analysis['report']['rule_revision']
        assert rev == 1

        save_started = asyncio.Event()
        compare_started = asyncio.Event()
        proceed_save = asyncio.Event()
        proceed_compare = asyncio.Event()

        async def pre_save():
            save_started.set()
            await proceed_save.wait()

        async def pre_compare():
            compare_started.set()
            await proceed_compare.wait()

        routes_analysis._pre_save_hook = pre_save
        routes_analysis._pre_compare_hook = pre_compare

        try:
            new_rules = ["Genuinely concurrent new rule 2"]
            save_task = asyncio.create_task(
                c.patch(
                    f"/api/baseline/batch/{b['id']}/analysis/rules",
                    json={"proposed_rules": new_rules, "base_revision": rev}
                )
            )
            compare_task = asyncio.create_task(
                c.post(
                    f"/api/baseline/batch/{b['id']}/analysis/compare",
                    json={"approved": True, "rule_revision": rev, "approved_rules": rules}
                )
            )

            # Wait until both have completed reads and paused right before their atomic SQL queries
            await asyncio.wait_for(save_started.wait(), timeout=3.0)
            await asyncio.wait_for(compare_started.wait(), timeout=3.0)

            # Ordering 2: Approval proceeds first and reserves comparison lock
            proceed_compare.set()
            compare_res = await compare_task
            assert compare_res.status_code == 200
            candidate_id = compare_res.json()['analysis']['comparison_batch_id']
            assert candidate_id and candidate_id != 'starting'

            # Save proceeds second and must fail atomically with 409 Conflict (comparison_batch_id is not null)
            proceed_save.set()
            save_res = await save_task
            assert save_res.status_code == 409
            assert "Conflict" in save_res.json()['detail']
            assert "comparison run" in save_res.json()['detail']

            # Verify approved rules are frozen in candidate snapshot and DB was not overwritten
            candidate = await runner.get_batch(candidate_id)
            assert candidate['snapshot']['coding_rules'] == rules
            assert candidate['snapshot']['rule_revision'] == 1
        finally:
            routes_analysis._pre_save_hook = None
            routes_analysis._pre_compare_hook = None



