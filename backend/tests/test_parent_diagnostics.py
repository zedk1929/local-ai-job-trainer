import json
from unittest.mock import patch

import httpx
import pytest
from app.services.supervisor_client import SupervisorClient


@pytest.mark.asyncio
async def test_gemini_check_is_metadata_only_and_normalizes_model_name():
    original = httpx.AsyncClient
    def handler(request):
        assert request.method == 'GET'
        assert str(request.url) == 'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash'
        assert request.headers['x-goog-api-key'] == 'fictional-secret'
        assert not request.content
        return httpx.Response(200, json={'supportedGenerationMethods': ['generateContent']})
    def client(*a, **kw):
        return original(*a, transport=httpx.MockTransport(handler), **kw)
    with patch('app.services.supervisor_client.httpx.AsyncClient', side_effect=client):
        result = await SupervisorClient('gemini', 'fictional-secret', 'models/gemini-3.8-flash').test_connection()
    assert result['connected'] is True
    assert 'without generation' in result['message']
    assert 'billing have not been tested' in result['message']


@pytest.mark.asyncio
@pytest.mark.parametrize('status,expected', [(403, 'permissions'), (404, 'model'), (429, 'quota'), (503, 'temporarily')])
async def test_gemini_error_status_is_useful_without_echoing_secrets(status, expected):
    original = httpx.AsyncClient
    def handler(req):
        return httpx.Response(status, json={'error': {'message': 'fictional-secret-must-not-leak'}})
    def client(*a, **kw):
        return original(*a, transport=httpx.MockTransport(handler), **kw)
    with patch('app.services.supervisor_client.httpx.AsyncClient', side_effect=client):
        result = await SupervisorClient('gemini', 'fictional-secret-must-not-leak', 'gemini-3.8-flash').test_connection()
    assert result['connected'] is False
    assert expected in result['message'].lower()
    assert f'HTTP {status}' in result['message']
    assert 'fictional-secret' not in json.dumps(result)


@pytest.mark.asyncio
async def test_invalid_key_reason_is_allowed_without_echoing_message():
    original = httpx.AsyncClient
    def handler(req):
        return httpx.Response(400, json={'error': {'message': 'fictional-secret', 'details': [{'reason': 'API_KEY_INVALID'}]}})
    def client(*a, **kw):
        return original(*a, transport=httpx.MockTransport(handler), **kw)
    with patch('app.services.supervisor_client.httpx.AsyncClient', side_effect=client):
        result = await SupervisorClient('gemini', 'fictional-secret', 'gemini-3.8-flash').test_connection()
    assert result['connected'] is False
    assert 'rejected the API key' in result['message']
    assert 'fictional-secret' not in result['message']


@pytest.mark.asyncio
async def test_certificate_failure_is_classified_without_disabling_verification():
    original = httpx.AsyncClient
    def handler(req):
        raise httpx.ConnectError('CERTIFICATE_VERIFY_FAILED fictional-secret', request=req)
    def client(*a, **kw):
        assert 'verify' not in kw or kw['verify'] is not False
        return original(*a, transport=httpx.MockTransport(handler), **kw)
    with patch('app.services.supervisor_client.httpx.AsyncClient', side_effect=client):
        result = await SupervisorClient('gemini', 'fictional-secret', 'gemini-3.8-flash').test_connection()
    assert 'certificate verification' in result['message']
    assert 'fictional-secret' not in result['message']
