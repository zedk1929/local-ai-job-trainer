"""Exercise the demo's public API end to end using isolated preview data."""
import csv
import io

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.services.baseline_runner import baseline_batch_runner as runner


async def completed_batch(client, batch_id):
    task = runner.active_tasks.get(batch_id)
    if task:
        await task
    response = await client.get(f'/api/baseline/batch/{batch_id}')
    assert response.status_code == 200, response.text
    batch = response.json()['batch']
    assert batch['status'] == 'completed', batch
    assert batch['processed_rows'] == batch['total_rows']
    return batch


@pytest.mark.asyncio
async def test_preview_import_to_comparison_export_survives_restart():
    settings.app_mode = 'preview'
    rows = [
        {'id': str(i), 'comment': text, 'human_topics': 'service',
         'human_sentiment': 'positive', 'human_review': 'false'}
        for i, text in enumerate([
            'Friendly staff and fast service.',
            'The cashier was helpful.',
            'Great service, thank you!',
            'The barista was kind.\nI will return.',
            'Quick and friendly staff.',
            'Excellent service from everyone.',
        ])
    ]
    rows.append({key: '' for key in rows[0]})
    rows[-1]['id'] = 'blank'
    csv_file = io.StringIO(newline='')
    writer = csv.DictWriter(csv_file, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    mappings = {
        'response_col': 'comment', 'id_col': 'id',
        'label_topics_col': 'human_topics', 'label_sentiment_col': 'human_sentiment',
        'label_needs_review_col': 'human_review',
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        async with app.router.lifespan_context(app):
            response = await client.post('/api/projects', json={
                'name': 'Isolated preview workflow',
                'taxonomy': [{'id': 'service', 'name': 'Service'}],
                'coding_rules': ['Assign only explicitly supported taxonomy IDs.'],
            })
            assert response.status_code == 200, response.text
            project = response.json()
            project_id = project['id']

            response = await client.post('/api/datasets/inspect', files={
                'file': ('workflow.csv', csv_file.getvalue().encode('utf-8-sig'), 'text/csv'),
            })
            assert response.status_code == 200, response.text
            inspection = response.json()
            assert inspection['row_count'] == len(rows)
            response = await client.post('/api/datasets/confirm', json={
                'project_id': project_id, 'temp_file_id': inspection['temp_file_id'],
                'filename': 'workflow.csv', **mappings,
            })
            assert response.status_code == 200, response.text
            dataset_id = response.json()['dataset']['id']
            confirmed_project = (await client.get(f'/api/projects/{project_id}')).json()
            assert confirmed_project['selected_dataset_id'] == dataset_id

            response = await client.post('/api/baseline/start', json={
                'project_id': project_id, 'dataset_id': dataset_id, **mappings,
            })
            assert response.status_code == 200, response.text
            source_id = response.json()['id']
            original = await completed_batch(client, source_id)
            assert original['metrics']['is_simulated'] is True
            assert original['metrics']['blank_rows'] == 1
            assert original['metrics']['attempted_rows'] == 6
            analysis_url = f'/api/baseline/batch/{source_id}/analysis'

            response = await client.post(analysis_url, json={})
            assert response.status_code == 200, response.text
            analysis = response.json()['analysis']
            assert analysis['status'] == 'ready', analysis
            assert analysis['report']['is_simulated'] is True
            assert analysis['report']['parent_model'] == 'offline-preview'
            development = set(analysis['report']['development_row_indices'])
            evaluation = set(analysis['report']['evaluation_row_indices'])
            assert development.isdisjoint(evaluation)
            assert development | evaluation == set(range(6))

            edited_rules = [*analysis['report']['proposed_rules'], 'Preserve the distinction between neutral and positive.']
            response = await client.patch(analysis_url + '/rules', json={
                'proposed_rules': edited_rules, 'base_revision': 1,
            })
            assert response.status_code == 200, response.text
            assert response.json()['analysis']['report']['rule_revision'] == 2

        # Exercise startup recovery and reload the saved proposal through public routes.
        async with app.router.lifespan_context(app):
            reloaded = (await client.get(analysis_url)).json()['analysis']
            assert reloaded['report']['proposed_rules'] == edited_rules
            assert reloaded['report']['rule_revision'] == 2
            response = await client.post(analysis_url + '/compare', json={
                'approved': True, 'rule_revision': 1, 'approved_rules': edited_rules,
            })
            assert response.status_code == 409
            response = await client.post(analysis_url + '/compare', json={
                'approved': True, 'rule_revision': 2, 'approved_rules': edited_rules,
            })
            assert response.status_code == 200, response.text
            candidate_id = response.json()['analysis']['comparison_batch_id']
            candidate = await completed_batch(client, candidate_id)
            assert candidate['snapshot']['coding_rules'] == edited_rules
            assert candidate['snapshot']['rule_revision'] == 2
            assert candidate['metrics']['is_simulated'] is True
            assert candidate['total_rows'] == len(evaluation)

            response = await client.post(f'/api/baseline/batch/{candidate_id}/export')
            assert response.status_code == 200, response.text
            exported = list(csv.DictReader(io.StringIO(response.text)))
            assert {int(row['id']) for row in exported} == evaluation
            for row in exported:
                for key, value in rows[int(row['id'])].items():
                    assert row[key] == value
                assert row['baseline_source_batch'] == source_id
                assert row['baseline_analysis_id'] == analysis['id']
                assert row['baseline_evaluation_role'] == 'development_comparison'
                assert row['baseline_is_simulated'] == 'YES'

            saved = (await client.get(analysis_url)).json()['analysis']
            assert saved['comparison']['status'] == 'completed'
            assert saved['report']['approved_revision'] == 2
            assert saved['report']['reference_metrics']['attempted_rows'] == len(evaluation)
            assert (await client.get(f'/api/projects/{project_id}')).json() == confirmed_project
            assert (await client.get(f'/api/baseline/batch/{source_id}')).json()['batch'] == original
