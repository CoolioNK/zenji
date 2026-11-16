"""Tests: SSRF-/Netzwerk-Sicherheitspolicy (Phase 3, offline).

Alle Tests laufen ohne echten Netzwerkzugriff: DNS wird per Injektion
(``resolver``) bzw. ``monkeypatch`` simuliert.
"""

from __future__ import annotations

import pytest

from app.core.exceptions import WebSecurityError
from app.web_intelligence import ssrf


def _resolver(*addresses: str):
    def _resolve(hostname: str) -> tuple[str, ...]:
        return tuple(addresses)

    return _resolve


# --- URL-Policy (ohne DNS) ----------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/artikel",
        "http://example.com",
        "https://EXAMPLE.com/Pfad?query=1",
        "https://docs.python.org/3/library/http.client.html",
        "http://93.184.216.34/x",  # öffentliches IP-Literal
    ],
)
def test_valide_urls_passieren_policy(url):
    checked = ssrf.validate_url(url)
    assert checked.scheme in {"http", "https"}
    assert checked.port in {80, 443}
    assert checked.hostname


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/datei",
        "data:text/html,hallo",
        "javascript:alert(1)",
        "gopher://example.com",
        "nicht-ein-schema://example.com",
    ],
)
def test_nur_http_und_https_erlaubt(url):
    with pytest.raises(WebSecurityError):
        ssrf.validate_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com:8443/x",
        "https://example.com:22/x",
        "http://example.com:8080/",
        "https://[::1]:443/",
    ],
)
def test_nicht_erlaubte_ports_blockiert(url):
    with pytest.raises(WebSecurityError):
        ssrf.validate_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/x",
        "http://LOCALHOST:80/x",
        "https://localhost./x",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://instance-data/latest/meta-data/",
        "http://127.0.0.1/ollama",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/intern",
        "http://192.168.1.1/router",
        "http://172.16.0.9/intern",
        "https://[::1]/",
        "https://[fe80::1]/",
        "https://[fd00:ec2::254]/",
        "https://[::ffff:10.0.0.1]/",
        "http://0.0.0.0/",
    ],
)
def test_interne_ziele_blockiert(url):
    with pytest.raises(WebSecurityError):
        ssrf.validate_url(url)


def test_leere_und_fehlende_urls_blockiert():
    with pytest.raises(WebSecurityError):
        ssrf.validate_url("")
    with pytest.raises(WebSecurityError):
        ssrf.validate_url("   ")
    with pytest.raises(WebSecurityError):
        ssrf.validate_url("https://")


# --- DNS-Prüfung (gemockter Resolver) -------------------------------------------------


def test_hostname_zu_privater_ip_blockiert():
    with pytest.raises(WebSecurityError):
        ssrf.check_url("https://example.com/x", resolver=_resolver("10.1.2.3"))


def test_hostname_zu_metadata_endpoint_blockiert():
    with pytest.raises(WebSecurityError):
        ssrf.check_url(
            "https://intern.example/x", resolver=_resolver("169.254.169.254")
        )


def test_dns_rebinding_alle_adressen_geprueft():
    """Erste Adresse öffentlich, zweite privat → trotzdem blockiert."""
    with pytest.raises(WebSecurityError):
        ssrf.check_url(
            "https://rebind.example/x",
            resolver=_resolver("93.184.216.34", "192.168.0.10"),
        )


def test_alle_aufgeloesten_adressen_oefentlich_erlaubt():
    checked = ssrf.check_url(
        "https://example.com/x", resolver=_resolver("93.184.216.34", "2606:2800:220:1::1")
    )
    assert checked.resolved_ips == ("93.184.216.34", "2606:2800:220:1::1")


def test_nicht_auflösbarer_hostname_blockiert():
    with pytest.raises(WebSecurityError):
        ssrf.check_url("https://nicht-existiert.example/x", resolver=_resolver())


def test_ip_literal_umgeht_dns_nicht():
    """Öffentliche IP-Literal ist erlaubt, privates nicht – ohne DNS."""
    assert ssrf.check_url("http://93.184.216.34/", resolver=_resolver()).hostname == "93.184.216.34"
    with pytest.raises(WebSecurityError):
        ssrf.check_url("http://10.9.8.7/", resolver=_resolver())


# --- Weiterleitungen -------------------------------------------------------------------


def test_redirect_zu_internem_ziel_blockiert():
    with pytest.raises(WebSecurityError):
        ssrf.check_redirect(
            "https://example.com/start", "http://169.254.169.254/latest/meta-data/"
        )


def test_redirect_relative_url_wird_aufgeloest_und_geprueft():
    target = ssrf.check_redirect("https://example.com/a/b", "../neu?x=1")
    assert target == "https://example.com/neu?x=1"


def test_redirect_ohne_location_blockiert():
    with pytest.raises(WebSecurityError):
        ssrf.check_redirect("https://example.com/", None)


def test_redirect_ziel_wird_voll_geprueft():
    """Redirect-Ziel läuft durch dieselbe Policy (URL + gemocktes DNS)."""
    resolver = _resolver("93.184.216.34")
    # Ziel öffentlich → erlaubt:
    assert (
        ssrf.check_redirect("https://example.com/x", "https://anders.example/y", resolver=resolver)
        == "https://anders.example/y"
    )
    # Ziel privat → blockiert:
    with pytest.raises(WebSecurityError):
        ssrf.check_redirect("https://example.com/x", "http://localhost:8080/admin", resolver=resolver)
    with pytest.raises(WebSecurityError):
        ssrf.check_redirect("https://example.com/x", "http://192.168.5.5/x", resolver=resolver)


# --- Limits & Konstanten -----------------------------------------------------------------


def test_sicherheitslimits_sind_werkseitig_gesetzt():
    assert ssrf.MAX_REDIRECTS <= 5
    assert ssrf.MAX_RESPONSE_BYTES <= 5_000_000
    assert ssrf.DEFAULT_TIMEOUT_S <= 30
    assert "ZENJI" in ssrf.USER_AGENT


def test_absolute_url_loest_relative_links_auf():
    assert (
        ssrf.absolute_url("https://example.com/a/", "seite.html")
        == "https://example.com/a/seite.html"
    )
    assert ssrf.absolute_url("https://example.com/", None) is None
    assert ssrf.absolute_url("https://example.com/", "javascript:void(0)") is None
