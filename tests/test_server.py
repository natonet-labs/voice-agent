import pytest
from fastapi.testclient import TestClient

from voice_agent import server
from voice_agent.config import settings

BODY = {"messages": [{"role": "user", "content": "hi"}]}


@pytest.fixture
def client(monkeypatch):
    # Never call the real model: these tests cover the HTTP contract only.
    monkeypatch.setattr(server, "_run_agent", lambda messages: "hello")

    def fake_stream(messages, model):
        yield server._sse("id", 0, model, {"content": "hello"}, None)
        yield "data: [DONE]\n\n"

    monkeypatch.setattr(server, "_stream_agent_sse", fake_stream)
    return TestClient(server.app)


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer wrong-key"},
        {"Authorization": "Basic test-key"},
        {"Authorization": "test-key"},
    ],
    ids=["missing", "wrong-key", "wrong-scheme", "no-scheme"],
)
def test_rejects_bad_credentials(client, headers):
    resp = client.post("/v1/chat/completions", json=BODY, headers=headers)
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"


def test_rejects_streaming_without_key(client):
    resp = client.post("/v1/chat/completions", json={**BODY, "stream": True})
    assert resp.status_code == 401


def test_accepts_valid_key(client):
    resp = client.post(
        "/v1/chat/completions", json=BODY, headers={"Authorization": "Bearer test-key"}
    )
    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["content"] == "hello"


def test_streams_with_valid_key(client):
    resp = client.post(
        "/v1/chat/completions",
        json={**BODY, "stream": True},
        headers={"Authorization": "Bearer test-key"},
    )
    assert resp.status_code == 200
    assert resp.text.endswith("data: [DONE]\n\n")


def test_fails_closed_when_key_unset(client, monkeypatch):
    monkeypatch.setattr(settings, "voice_agent_api_key", "")
    resp = client.post(
        "/v1/chat/completions", json=BODY, headers={"Authorization": "Bearer "}
    )
    assert resp.status_code == 503


def test_health_stays_open_for_probes(client):
    assert client.get("/health").status_code == 200
