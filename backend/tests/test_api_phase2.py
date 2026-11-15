"""Tests: Phase-2-API (Personality, Policies, Memory, Core, Chat-Integration)."""

from __future__ import annotations

import pytest

from tests.conftest import parse_sse


# --- Personality -------------------------------------------------------------------


async def test_personality_liste_mit_seed(client):
    http, _app = client
    response = await http.get("/api/personality")
    assert response.status_code == 200
    profiles = response.json()
    assert len(profiles) == 5
    assert profiles[0]["name"] == "Zenji"
    assert profiles[0]["is_active"] is True
    assert all(p["is_system"] for p in profiles)
    # Neue Eigenschaftsachsen werden mitgeliefert:
    assert set(profiles[0]) >= {
        "sarcasm", "cheekiness", "friendliness", "empathy", "curiosity", "initiative"
    }


async def test_personality_erstellen_aktivieren_bearbeiten(client):
    http, _app = client
    response = await http.post(
        "/api/personality",
        json={"name": "Mein Profil", "identity": "Test", "formality": 0.9},
    )
    assert response.status_code == 201
    profile = response.json()
    assert profile["is_system"] is False
    assert profile["situational_behavior"] == {}

    # Duplikat → 409:
    dup = await http.post("/api/personality", json={"name": "Mein Profil"})
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "PERSONALITY_NAME_TAKEN"

    # Bearbeiten:
    patch = await http.patch(
        f"/api/personality/{profile['id']}",
        json={"humor": 0.7, "situational_behavior": {"Fehler": "Ehrlich bleiben."}},
    )
    assert patch.status_code == 200
    assert patch.json()["humor"] == 0.7
    assert patch.json()["situational_behavior"] == {"Fehler": "Ehrlich bleiben."}

    # Aktivieren:
    activate = await http.post(f"/api/personality/{profile['id']}/activate")
    assert activate.status_code == 200
    assert activate.json()["is_active"] is True

    # Vorschau:
    preview = await http.get(f"/api/personality/{profile['id']}/preview")
    assert preview.status_code == 200
    assert preview.json()["name"] == "Mein Profil"
    assert "Name: Mein Profil" in preview.json()["compiled_text"]

    # Löschen: erst anderes Profil aktivieren (aktive Profile sind geschützt):
    all_profiles = (await http.get("/api/personality")).json()
    professional = next(p for p in all_profiles if p["name"] == "Professional")
    await http.post(f"/api/personality/{professional['id']}/activate")
    delete = await http.delete(f"/api/personality/{profile['id']}")
    assert delete.status_code == 204


async def test_personality_systemprofil_geschuetzt(client):
    http, _app = client
    profiles = (await http.get("/api/personality")).json()
    neutral = profiles[0]
    delete = await http.delete(f"/api/personality/{neutral['id']}")
    assert delete.status_code == 409
    assert delete.json()["error"]["code"] == "PERSONALITY_PROTECTED"


async def test_personality_validation(client):
    http, _app = client
    # base_personality ungültig:
    response = await http.post(
        "/api/personality", json={"name": "X", "base_personality": "wild"}
    )
    assert response.status_code == 422
    # formality außerhalb 0–1:
    response = await http.post("/api/personality", json={"name": "X", "formality": 2.5})
    assert response.status_code == 422
    # Name fehlt:
    response = await http.post("/api/personality", json={})
    assert response.status_code == 422


async def test_personality_404(client):
    http, _app = client
    response = await http.get("/api/personality/fehlt/preview")
    assert response.status_code == 404


# --- Policies ---------------------------------------------------------------------


async def test_policies_liste_mit_seed(client):
    http, _app = client
    response = await http.get("/api/policies")
    assert response.status_code == 200
    body = response.json()
    assert len(body["policies"]) == 8
    assert body["conflicts"] == []
    assert body["disabled_count"] == 0
    system_first = [p["source"] == "system" for p in body["policies"][:7]]
    assert all(system_first)


async def test_policy_erstellen_editieren_loeschen(client):
    http, _app = client
    response = await http.post(
        "/api/policies",
        json={"name": "Kurze Antworten", "instruction": "Antworte knapp.", "priority": 65},
    )
    assert response.status_code == 201
    policy = response.json()
    assert policy["id"] == "kurze_antworten"
    assert policy["source"] == "user"

    patch = await http.patch(
        f"/api/policies/{policy['id']}", json={"priority": 80, "enabled": False}
    )
    assert patch.status_code == 200
    assert patch.json()["enabled"] is False

    listed = (await http.get("/api/policies")).json()
    assert listed["disabled_count"] == 1

    delete = await http.delete(f"/api/policies/{policy['id']}")
    assert delete.status_code == 204


async def test_policy_systemregeln_geschuetzt(client):
    http, _app = client
    patch = await http.patch("/api/policies/zenji_identity", json={"priority": 10})
    assert patch.status_code == 403
    assert patch.json()["error"]["code"] == "POLICY_SYSTEM_PROTECTED"
    delete = await http.delete("/api/policies/zenji_identity")
    assert delete.status_code == 403


async def test_policy_validation_und_404(client):
    http, _app = client
    # source-Feld ist per Schema verboten (extra=forbid):
    response = await http.post(
        "/api/policies",
        json={"name": "X", "instruction": "Y", "source": "system"},
    )
    assert response.status_code == 422
    # priority > 100:
    response = await http.post(
        "/api/policies", json={"name": "X", "instruction": "Y", "priority": 150}
    )
    assert response.status_code == 422
    # unbekannte Regel:
    response = await http.patch("/api/policies/fehlt", json={"priority": 10})
    assert response.status_code == 404


# --- Memory -----------------------------------------------------------------------


async def test_memory_leer_liste(client):
    http, _app = client
    response = await http.get("/api/memory")
    assert response.status_code == 200
    body = response.json()
    assert body["memories"] == []
    assert body["stats"]["total"] == 0


async def test_memory_crud_und_suche(client):
    http, _app = client
    create = await http.post(
        "/api/memory",
        json={"content": "Der Nutzer arbeitet mit Python.", "memory_type": "project"},
    )
    assert create.status_code == 201
    memory = create.json()
    assert memory["source"] == "user"
    assert memory["status"] == "active"

    get = await http.get(f"/api/memory/{memory['id']}")
    assert get.status_code == 200

    patch = await http.patch(
        f"/api/memory/{memory['id']}", json={"relevance": 0.9}
    )
    assert patch.status_code == 200
    assert patch.json()["relevance"] == 0.9

    search = await http.post(
        "/api/memory/search", json={"query": "Python", "limit": 5}
    )
    assert search.status_code == 200
    results = search.json()
    assert len(results) == 1
    assert results[0]["memory"]["id"] == memory["id"]
    assert results[0]["score"] > 0

    delete = await http.delete(f"/api/memory/{memory['id']}")
    assert delete.status_code == 204
    gone = await http.get(f"/api/memory/{memory['id']}")
    assert gone.status_code == 404


async def test_memory_validation(client):
    http, _app = client
    response = await http.post("/api/memory", json={"content": ""})
    assert response.status_code == 422
    response = await http.post(
        "/api/memory", json={"content": "x", "memory_type": "falsch"}
    )
    assert response.status_code == 422
    response = await http.post("/api/memory", json={"content": "x", "relevance": 2})
    assert response.status_code == 422
    response = await http.get("/api/memory", params={"memory_type": "falsch"})
    assert response.status_code == 422


# --- Core -------------------------------------------------------------------------


async def test_core_status(client):
    http, _app = client
    response = await http.get("/api/core/status")
    assert response.status_code == 200
    status = response.json()
    assert status["personality"] == "Zenji"
    assert status["active_policies"] >= 7
    assert status["model"] == "qwen3:8b"
    assert status["memories"]["total"] == 0
    assert status["num_ctx"] == 8192
    assert status["communication_default_mode"] == "casual"
    mode_keys = {mode["key"] for mode in status["communication_modes"]}
    assert mode_keys == {"casual", "roast", "focus", "empathy", "open_talk"}


async def test_core_context_preview(client):
    http, _app = client
    response = await http.get(
        "/api/core/context-preview", params={"message": "Was kannst du?"}
    )
    assert response.status_code == 200
    body = response.json()
    keys = {s["key"] for s in body["sections"]}
    assert {"identity", "personality", "communication", "policies"} <= keys
    assert body["mode"] == "casual"
    assert body["messages"][0]["role"] == "system"
    assert body["budget_tokens"] == 8192 - 2048 - 256
    assert 0 <= body["usage_ratio"] <= 1
    assert body["system_text"].startswith("## Identität")


# --- Chat-Integration (Phase-2-Pfad über API) -----------------------------------------


async def test_chat_stream_mit_core_liefert_orchestrierten_kontext(client):
    http, _app = client
    response = await http.post(
        "/api/chat/stream", json={"message": "Merke dir: Ich arbeite an Projekt Vega"}
    )
    assert response.status_code == 200
    events = parse_sse(response.content)
    kinds = [event for event, _data in events]
    assert kinds[0] == "start"
    assert kinds[-1] == "done"

    # Erinnerung wurde über den Core nachgetragen:
    search = await http.post("/api/memory/search", json={"query": "Vega"})
    assert len(search.json()) == 1

    # Kontext-Preview mit Verlauf:
    preview = await http.get(
        "/api/core/context-preview",
        params={"message": "Neue Frage", "conversation_id": events[0][1]["conversation_id"]},
    )
    assert preview.status_code == 200
    assert preview.json()["history_kept"] >= 1


async def test_chat_stream_ohne_merkwort_kein_gedaechtnis(client):
    http, _app = client
    await http.post("/api/chat/stream", json={"message": "Hallo ZENJI!"})
    listed = await http.get("/api/memory")
    assert listed.json()["stats"]["total"] == 0
