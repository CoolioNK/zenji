"""Tests: Konfigurationssystem & Validierung."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings, SettingsConfigDict  # noqa: F401
from app.core.config import DEFAULT_PERSONA


def test_start_defaults_sind_spec_konform():
    settings = Settings(_env_file=None)
    assert settings.llm.model == "qwen3:8b"
    assert settings.llm.provider == "ollama"
    assert settings.llm.temperature == 0.7
    assert settings.llm.top_p == 0.9
    assert settings.llm.top_k == 20
    assert settings.llm.repeat_penalty == 1.05
    assert settings.llm.num_predict == 2048
    assert settings.llm.num_ctx == 8192
    assert settings.llm.stream is True


def test_env_override_von_allgemeinen_parametern(monkeypatch):
    monkeypatch.setenv("ZENJI_LLM__TEMPERATURE", "0.3")
    monkeypatch.setenv("ZENJI_LLM__MODEL", "llama3.1:8b")
    monkeypatch.setenv("ZENJI_LLM__STREAM", "false")
    settings = Settings(_env_file=None)
    assert settings.llm.temperature == 0.3
    assert settings.llm.model == "llama3.1:8b"
    assert settings.llm.stream is False


def test_env_override_provider_spezifisch(monkeypatch):
    monkeypatch.setenv("ZENJI_OLLAMA__TIMEOUT", "60")
    monkeypatch.setenv("ZENJI_OLLAMA__KEEP_ALIVE", "30m")
    settings = Settings(_env_file=None)
    assert settings.ollama.timeout == 60
    assert settings.ollama.keep_alive == "30m"


def test_temperature_außerhalb_bereich_wird_abgelehnt():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm={"temperature": 3.5})  # type: ignore[arg-type]


def test_top_p_muss_in_bereich_liegen():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm={"top_p": 1.5})  # type: ignore[arg-type]


def test_unbekannter_log_level_wird_abgelehnt():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, log_level="VERBOSE")  # type: ignore[arg-type]


def test_abgeleitete_pfade_folgen_der_ssd(tmp_path):
    settings = Settings(_env_file=None, ssd_root=tmp_path)  # type: ignore[arg-type]
    assert settings.resolved_storage_dir == tmp_path / "ZENJI"
    assert settings.resolved_db_path == tmp_path / "ZENJI" / "data" / "zenji.db"
    assert settings.resolved_log_dir == tmp_path / "logs"
    assert settings.models_dir == tmp_path / "models"


def test_explizite_overrides_haben_vorrang(tmp_path):
    settings = Settings(
        _env_file=None,  # type: ignore[arg-type]
        ssd_root=tmp_path,  # type: ignore[arg-type]
        storage_dir=tmp_path / "eigener" / "pfad",  # type: ignore[arg-type]
        db_path=tmp_path / "eigene.db",  # type: ignore[arg-type]
    )
    assert settings.resolved_storage_dir == tmp_path / "eigener" / "pfad"
    assert settings.resolved_db_path == tmp_path / "eigene.db"


def test_ollama_base_url_validierung():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ollama_base_url="localhost:11434")  # type: ignore[arg-type]
    ok = Settings(_env_file=None, ollama_base_url="http://localhost:11434/")  # type: ignore[arg-type]
    assert ok.ollama_base_url == "http://localhost:11434"


def test_cors_origins_werden_geparst():
    settings = Settings(_env_file=None, cors_origins="http://a:1, http://b:2")  # type: ignore[arg-type]
    assert settings.cors_origin_list == ["http://a:1", "http://b:2"]


def test_default_persona_ist_gesetzt():
    settings = Settings(_env_file=None)
    assert "Zenji Ango" in settings.persona_system_prompt
    assert settings.persona_system_prompt == DEFAULT_PERSONA
