"""Tests: Produktions-Härtung (Security Header, CORS)."""

from __future__ import annotations

import pytest

from app.core.config import Settings


def test_public_base_url_wird_zu_cors_hinzugefuegt():
    settings = Settings(
        _env_file=None,  # type: ignore[arg-type]
        cors_origins="http://localhost:5173",
        public_base_url="https://zenji.pages.dev/",
    )
    assert settings.cors_origin_list == [
        "http://localhost:5173",
        "https://zenji.pages.dev",
    ]


def test_public_base_url_ohne_scheme_wird_abgelehnt():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            public_base_url="zenji.pages.dev",
        )


@pytest.mark.asyncio
async def test_health_hat_sicherheits_header(client):
    client, _ = client
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "default-src 'self'" in response.headers["content-security-policy"]