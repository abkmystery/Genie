from fastapi.testclient import TestClient

from app.main import app


def test_gateway_chat_returns_mock_answer():
    client = TestClient(app)
    response = client.post(
        "/v1/chat",
        json={
            "prompt": "What is on screen?",
            "profile_id": "demo",
            "evidence": [{"id": "1", "label": "[Screen]", "kind": "screen", "quote": "Example"}],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_used"] in {"demo-gateway:mock-fallback", "ollama:gemma2:2b"}
    assert "Prompt:" in payload["answer"] or "User question:" in payload["answer"]


def test_gateway_fallback_when_ollama_unavailable(monkeypatch):
    monkeypatch.setenv("DEMO_GATEWAY_PROVIDER", "ollama")
    monkeypatch.setenv("DEMO_OLLAMA_HOST", "http://127.0.0.1:65530")
    monkeypatch.setenv("DEMO_OLLAMA_MODEL", "gemma2:2b")

    from importlib import reload
    import app.main as main_module

    reload(main_module)
    client = TestClient(main_module.app)
    response = client.post("/v1/chat", json={"prompt": "hello", "profile_id": "demo", "evidence": []})
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_used"] == "demo-gateway:mock-fallback"
