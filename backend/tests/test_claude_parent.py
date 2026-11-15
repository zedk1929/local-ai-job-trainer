import json
from unittest.mock import patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.services.supervisor_client import SupervisorClient
from app.api.routes_analysis import ask_parent


@pytest.mark.asyncio
async def test_claude_analysis_uses_messages_api_and_keeps_key_out_of_prompt(monkeypatch):
    monkeypatch.setattr(settings, 'supervisor_provider', 'anthropic')
    monkeypatch.setattr(settings, 'supervisor_model', 'claude-sonnet-5-5')
    monkeypatch.setattr(settings, 'supervisor_api_key', 'fictional-anthropic-secret')
    expected = {'summary': 'Review rules', 'groups': [], 'proposed_rules': ['Use explicit evidence']}
    original = httpx.AsyncClient
    requests = []

    def handler(request):
        requests.append(request)
        assert str(request.url) == 'https://api.anthropic.com/v1/messages'
        assert request.headers['x-api-key'] == 'fictional-anthropic-secret'
        assert request.headers['anthropic-version'] == '2026-10-21'
        assert 'fictional-anthropic-secret' not in request.content.decode()
        data = json.loads(request.content)
        assert data['model'] == 'claude-sonnet-5-5'
        assert data['max_tokens'] == 4096
        assert data['messages'][0]['role'] == 'user'
        return httpx.Response(200, json={'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': json.dumps(expected)}]})

    def client(*a, **kw):
        return original(*a, transport=httpx.MockTransport(handler), **kw)

    with patch('app.services.supervisor_client.httpx.AsyncClient', side_effect=client):
        result, model = await ask_parent({'development_rows': []})
    assert result == expected and model == 'claude-sonnet-5-5'
    assert len(requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('response', [
    httpx.Response(401, text='fictional-key-must-not-leak'),
    httpx.Response(200, json={'stop_reason': 'max_tokens', 'content': [{'type': 'text', 'text': '{'}]}),
    httpx.Response(200, json={'stop_reason': 'end_turn', 'content': []}),
])
async def test_claude_errors_and_truncation_are_honest_and_sanitized(response):
    original = httpx.AsyncClient
    def client(*a, **kw):
        return original(*a, transport=httpx.MockTransport(lambda req: response), **kw)
    with patch('app.services.supervisor_client.httpx.AsyncClient', side_effect=client):
        with pytest.raises(RuntimeError) as err:
            await SupervisorClient('anthropic', 'fictional-key-must-not-leak', 'claude-sonnet-5-5').generate_text('Fictional task')
    assert 'fictional-key-must-not-leak' not in str(err.value)
    assert 'no fixture' in str(err.value).lower()


@pytest.mark.asyncio
async def test_switching_provider_drops_old_key_and_setup_never_echoes_keys(monkeypatch):
    monkeypatch.setattr(settings, 'supervisor_provider', 'gemini')
    monkeypatch.setattr(settings, 'supervisor_model', 'gemini-2.5-pro')
    monkeypatch.setattr(settings, 'supervisor_api_key', 'old-gemini-key')
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        response = await c.post('/api/setup/supervisor', json={'provider': 'anthropic'})
        assert response.status_code == 200
        assert response.json()['configured'] is False
        assert response.json()['model'] == 'claude-sonnet-5-5'
        assert settings.supervisor_api_key == ''
        response = await c.post('/api/setup/supervisor', json={'provider': 'anthropic', 'api_key': 'new-fictional-claude-key'})
        assert response.json()['configured'] is True
        assert 'new-fictional-claude-key' not in response.text
        assert 'old-gemini-key' not in response.text
        assert settings.supervisor_model == 'claude-sonnet-5-5'
        assert (await c.post('/api/setup/supervisor', json={'provider': 'unsupported'})).status_code == 422


@pytest.mark.asyncio
async def test_claude_connection_test_uses_only_small_test_message():
    original = httpx.AsyncClient
    def handler(req):
        payload = json.loads(req.content)
        assert payload['max_tokens'] == 16
        assert payload['messages'][0]['content'] == 'Reply with OK only.'
        return httpx.Response(200, json={'content': [{'type': 'text', 'text': 'OK'}], 'stop_reason': 'end_turn'})
    def client(*a, **kw):
        return original(*a, transport=httpx.MockTransport(handler), **kw)
    with patch('app.services.supervisor_client.httpx.AsyncClient', side_effect=client):
        result = await SupervisorClient('anthropic', 'fictional-api-key', 'claude-sonnet-5-5').test_connection()
    assert result['connected'] is True
