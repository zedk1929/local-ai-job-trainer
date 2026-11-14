import pytest
from app.services.model_backend import LocalModelBackend

@pytest.mark.smoke
@pytest.mark.asyncio
async def test_ollama_endpoint_discovery():
    backend = LocalModelBackend(endpoint_url="http://127.0.0.1:11434", model_name="qwen2.5-coder:3b")
    try:
        models = await backend.list_available_ollama_models()
    except Exception as e:
        pytest.skip(f"Ollama server not reachable at http://127.0.0.1:11434: {e}")

    if not models:
        pytest.skip("Ollama server reachable, but no models found.")

    assert len(models) > 0
    caps = await backend.inspect_capabilities()
    assert caps["endpoint_url"] == "http://127.0.0.1:11434"
    assert caps["inference_available"] is True

@pytest.mark.smoke
@pytest.mark.asyncio
async def test_ollama_real_model_inference():
    """Live smoke test executing real inference against local Ollama model."""
    backend = LocalModelBackend(
        endpoint_url="http://127.0.0.1:11434",
        model_name="qwen2.5-coder:3b",
        app_mode="connected"
    )
    try:
        models = await backend.list_available_ollama_models()
    except Exception as e:
        pytest.skip(f"Ollama server not reachable: {e}")

    clean_models = [m.split(":")[0] for m in models]
    if "qwen2.5-coder" not in clean_models and "qwen2.5-coder:3b" not in models:
        pytest.skip("qwen2.5-coder:3b model not installed in Ollama.")

    result = await backend.infer_single(
        response_text="The iced latte was delicious but wait time was 20 minutes.",
        context="Campus café gathering feedback",
        taxonomy=[
            {"id": "drink_quality", "name": "Drink Quality"},
            {"id": "service", "name": "Service"}
        ],
        rules=["Assign relevant topics"],
        use_adapter=False,
        app_mode="connected"
    )
    assert isinstance(result, dict)
    assert "topics" in result
    assert isinstance(result["topics"], list)
    assert "sentiment" in result
    # In connected mode, it must NOT have is_simulated_fixture
    assert result.get("is_simulated_fixture", False) is False
