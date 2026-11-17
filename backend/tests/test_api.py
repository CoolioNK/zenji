"""Tests: API-Endpunkte (Health, Models, Settings, Conversations, Chat)."""

from __future__ import annotations

import pytest

from app.main import create_app
from tests.conftest import FAKE_REPLY, FakeProvider, make_provider_factory, open_app, parse_sse

pytestmark = pytest.mark.asyncio


# --- Health -----------------------------------------------------------------------


async def test_health_ok_mit_ssd(make_ssd, app_factory):
    make_ssd()
    app = app_factory()
    async with open_app(app):
        import httpx

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            response = await c.get("/api/health")
    data = response.json()
    assert response.status_code == 200
    assert data["status"] == "ok"
    assert data["storage"]["available"] is True
    assert data["database"]["ok"] is True
    assert data["ollama"]["available"] is True
    assert data["model"]["available"] is True
    assert data["model"]["model"] == "qwen3:8b"


async def test_health_degraded_ohne_ssd(client_no_ssd):
    client, app = client_no_ssd
    response = await client.get("/api/health")
    data = response.json()
    assert response.status_code == 200  # Health crashet nie
    assert data["status"] == "degraded"
    assert data["storage"]["available"] is False
    assert "SSD" in data["storage"]["message"]


# --- Models -------------------------------------------------------------------------


async def test_models_liste(client):
    client, _ = client
    response = await client.get("/api/models")
    data = response.json()
    assert response.status_code == 200
    assert data["provider"] == "fake"
    assert data["active_model"] == "qwen3:8b"
    assert data["available"] is True
    assert [m["name"] for m in data["models"]] == ["qwen3:8b"]


async def test_models_offline_liefert_klare_meldung(zenji_env, app_factory):
    app = create_app(provider_factory=make_provider_factory(FakeProvider(available=False)))
    async with open_app(app):
        import httpx

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            response = await c.get("/api/models")
    data = response.json()
    assert response.status_code == 200
    assert data["available"] is False
    assert "offline" in data["message"]


# --- Settings -----------------------------------------------------------------------


async def test_settings_struktur(client):
    client, _ = client
    response = await client.get("/api/settings")
    data = response.json()
    assert response.status_code == 200
    assert data["llm"]["model"] == "qwen3:8b"
    assert data["llm"]["temperature"] == 0.7
    assert data["providers"]["ollama"]["base_url"] == "http://testserver:11434"
    assert "Zenji Ango" in data["persona"]["system_prompt"]


async def test_settings_patch_persistiert(client):
    client, _ = client
    response = await client.patch(
        "/api/settings",
        json={"llm": {"temperature": 0.4}},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["llm"]["temperature"] == 0.4
    assert data["llm"]["model"] == "qwen3:8b"
    assert data["llm"]["top_k"] == 20  # unverändert

    # Persistenz: zweites Lesen zeigt dieselben Werte
    again = (await client.get("/api/settings")).json()
    assert again["llm"]["temperature"] == 0.4


async def test_settings_patch_ungueltiger_wert(client):
    client, _ = client
    response = await client.patch("/api/settings", json={"llm": {"temperature": 99}})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_settings_patch_unbekanntes_feld(client):
    client, _ = client
    response = await client.patch("/api/settings", json={"llm": {"bogus": 1}})
    assert response.status_code == 422


# --- Conversations ------------------------------------------------------------------


async def test_konversationen_lebenszyklus(client):
    client, _ = client
    created = await client.post("/api/conversations", json={"title": "Projektplanung"})
    assert created.status_code == 201
    conv_id = created.json()["id"]

    listed = (await client.get("/api/conversations")).json()
    assert len(listed) == 1
    assert listed[0]["title"] == "Projektplanung"
    assert listed[0]["message_count"] == 0

    renamed = await client.patch(f"/api/conversations/{conv_id}", json={"title": "ZENJI Phase 1"})
    assert renamed.json()["title"] == "ZENJI Phase 1"

    detail = (await client.get(f"/api/conversations/{conv_id}")).json()
    assert detail["id"] == conv_id and detail["messages"] == []

    deleted = await client.delete(f"/api/conversations/{conv_id}")
    assert deleted.status_code == 204
    missing = await client.get(f"/api/conversations/{conv_id}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


async def test_konversationen_404(client):
    client, _ = client
    response = await client.get("/api/conversations/unbekannte-id")
    assert response.status_code == 404


# --- Chat (nicht-streamend) -----------------------------------------------------------


async def test_chat_vollstaendige_antwort(client):
    client, _ = client
    response = await client.post("/api/chat", json={"message": "Was ist ZENJI?"})
    data = response.json()
    assert response.status_code == 200
    assert data["assistant_message"]["content"] == FAKE_REPLY
    assert data["user_message"]["role"] == "user"
    assert data["conversation_id"] == data["user_message"]["conversation_id"]


async def test_chat_in_bestehende_konversation(client):
    client, _ = client
    conv = (await client.post("/api/conversations", json={"title": "Bestehend"})).json()
    response = await client.post(
        "/api/chat", json={"conversation_id": conv["id"], "message": "Weiter geht's"}
    )
    data = response.json()
    assert data["conversation_id"] == conv["id"]
    detail = (await client.get(f"/api/conversations/{conv['id']}")).json()
    assert detail["message_count"] == 2


async def test_chat_unbekannte_konversation_404(client):
    client, _ = client
    response = await client.post(
        "/api/chat", json={"conversation_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "message": "x"}
    )
    assert response.status_code == 404


async def test_chat_fehlendes_modell_409(zenji_env, app_factory, make_ssd):
    make_ssd()
    app = app_factory(provider=FakeProvider(models=("llama3.1:8b",)))
    async with open_app(app):
        import httpx

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            response = await c.post("/api/chat", json={"message": "hallo"})
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "MODEL_NOT_FOUND"
    assert "ollama pull" in str(error)


async def test_chat_offline_provider_502(zenji_env, app_factory, make_ssd):
    make_ssd()
    app = app_factory(provider=FakeProvider(available=False))
    async with open_app(app):
        import httpx

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            response = await c.post("/api/chat", json={"message": "hallo"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "OLLAMA_UNAVAILABLE"


async def test_chat_ohne_ssd_503(client_no_ssd):
    client, _ = client_no_ssd
    response = await client.post("/api/chat", json={"message": "hallo"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "STORAGE_UNAVAILABLE"


# --- Chat-Streaming (SSE) ---------------------------------------------------------------


async def test_stream_sse_eventsequenz(client):
    client, _ = client
    async with client.stream("POST", "/api/chat/stream", json={"message": "Erzähle"}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        raw = b""
        async for chunk in response.aiter_bytes():
            raw += chunk
    events = parse_sse(raw)
    names = [e for e, _ in events]
    assert names[0] == "start"
    assert names.count("delta") >= 1
    assert names[-1] == "done"

    start_data = dict(events[0][1])
    assert start_data["assistant_message_id"] is None
    done = events[-1][1]
    assert done["content"] == FAKE_REPLY

    # Persistiert: Konversation + beide Nachrichten
    conversations = (await client.get("/api/conversations")).json()
    assert len(conversations) == 1
    assert conversations[0]["message_count"] == 2


async def test_stream_in_bestehende_konversation(client):
    client, _ = client
    conv = (await client.post("/api/conversations", json={"title": "Stream-Chat"})).json()
    async with client.stream(
        "POST", "/api/chat/stream", json={"conversation_id": conv["id"], "message": "Nochmal"}
    ) as response:
        raw = b""
        async for chunk in response.aiter_bytes():
            raw += chunk
    events = parse_sse(raw)
    assert events[0][1]["conversation_id"] == conv["id"]
    detail = (await client.get(f"/api/conversations/{conv['id']}")).json()
    assert detail["title"] == "Stream-Chat"
    assert detail["message_count"] == 2


async def test_stream_fehlendes_modell_http_409(zenji_env, app_factory, make_ssd):
    make_ssd()
    app = app_factory(provider=FakeProvider(models=("llama3.1:8b",)))
    async with open_app(app):
        import httpx

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            response = await c.post("/api/chat/stream", json={"message": "hi"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MODEL_NOT_FOUND"


async def test_stream_ohne_ssd_503(client_no_ssd):
    client, _ = client_no_ssd
    response = await client.post("/api/chat/stream", json={"message": "hi"})
    assert response.status_code == 503


async def test_stream_leere_nachricht_422(client):
    client, _ = client
    response = await client.post("/api/chat/stream", json={"message": ""})
    assert response.status_code == 422
