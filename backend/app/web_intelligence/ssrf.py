"""SSRF- und Netzwerk-Sicherheitspolicy für die Web Intelligence Engine.

Geltungsbereich: Abrufe **untrusteder URLs** – Suchergebnisse, Links aus
Webseiten, Weiterleitungsziele. Konfigurierte Dienst-Endpunkte (SearXNG,
Ollama) sind bewusst **ausgenommen**: Sie sind Nutzereinstellungen
(Konfiguration, kein Webinhalt) und dürfen localhost verwenden.

Regelwerk (Phase 3, Mindestanforderungen):

- Nur ``http``/``https`` (kein ``file:``, ``ftp:``, ``data:``, …)
- Nur Ports 80/443 (explizite Port-Angabe außerhalb → blockiert)
- ``localhost`` und Metadaten-Hostnamen blockiert
- Private, Loopback-, Link-Local-, Reserved-, Multicast- und Unspecified-IPs
  blockiert (IPv4 **und** IPv6, inkl. IPv4-mapped IPv6)
- Cloud-Metadaten-Endpunkte explizit blockiert (169.254.169.254, fd00:ec2::254)
- DNS-Auflösung wird geprüft: Ein Hostname, der zu **einer** blockierten
  Adresse auflöst, wird abgewiesen (Rebind-Schutz)
- Weiterleitungen werden **jederzeit** neu validiert (Browser-Engine ruft
  ``check_url`` pro Hop auf)
- Zeit- und Größenlimits als Konstanten (Browser-Engine setzt sie um)

Alle Prüfungen sind reine Funktionen + eine DNS-Auflösungsfunktion – damit
 offline testbar (Tests mocken ``socket.getaddrinfo``).
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

from app.core.exceptions import WebSecurityError

#: Zulässige URL-Schemata für Webabrufrufe.
ALLOWED_SCHEMES = frozenset({"http", "https"})
#: Zulässige Ports (Standardports für http/https).
ALLOWED_PORTS = frozenset({80, 443})
#: Explizit blockierte Hostnamen (Localhost-Varianten + Cloud-Metadaten).
BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "ip6-loopback",
        "metadata.google.internal",
        "metadata.goog",
        "metadata.internal",
        "instance-data",
        "instance-data.ec2.internal",
    }
)
#: Cloud-Metadaten-Endpunkte (AWS/GCP/Azure-Cluster) als IP-Adressen.
METADATA_ENDPOINT_IPS = frozenset({"169.254.169.254", "fd00:ec2::254"})

#: Sicherheitslimits (von der Browser Engine zu respektieren).
MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 3_000_000
DEFAULT_TIMEOUT_S = 20.0
CONNECT_TIMEOUT_S = 10.0
#: Höflicher, ehrlicher User-Agent (keine Browser-Tarnung).
USER_AGENT = "ZENJI-Recherche/0.5 (+local research assistant; respektiert robots.txt)"


@dataclass(slots=True)
class CheckedURL:
    """Ergebnis einer Sicherheitsprüfung (normalisierte URL + aufgelöste IPs)."""

    url: str
    scheme: str
    hostname: str
    port: int
    resolved_ips: tuple[str, ...] = ()


def validate_url(url: str) -> CheckedURL:
    """Prüft URL ohne DNS: Schema, Port, Hostname-Blocklist.

    Raises:
        WebSecurityError: bei ungültigem/blockiertem Schema, Port oder Host.
    """
    raw = (url or "").strip()
    if not raw:
        raise WebSecurityError("Leere URL kann nicht abgerufen werden.")
    try:
        parts = urlsplit(raw)
    except ValueError as exc:
        raise WebSecurityError(f"URL nicht parsebar: {raw!r}") from exc

    scheme = (parts.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise WebSecurityError(
            f"URL-Schema '{scheme or 'leer'}' ist nicht erlaubt (nur http/https)."
        )
    hostname = (parts.hostname or "").strip().lower().rstrip(".")
    if not hostname:
        raise WebSecurityError(f"URL ohne Hostnamen: {raw!r}")
    if hostname in BLOCKED_HOSTNAMES:
        raise WebSecurityError(f"Hostname '{hostname}' ist blockiert (interne Endpunkte).")

    port = parts.port  # None → impliziter Standardport
    if port is None:
        port = 443 if scheme == "https" else 80
    if port not in ALLOWED_PORTS:
        raise WebSecurityError(
            f"Port {port} ist nicht erlaubt (nur {sorted(ALLOWED_PORTS)})."
        )

    # IP-Literal direkt prüfen; Hostnamen wird erst bei ``check_url`` aufgelöst.
    _reject_if_ip_unsafe(hostname, explicit=True)

    # Fragment nie weitergeben; Pfad/Query konservieren.
    normalized = urlunsplit((scheme, f"{hostname}:{port}" if parts.port else parts.netloc, parts.path or "/", parts.query, ""))
    return CheckedURL(url=normalized, scheme=scheme, hostname=hostname, port=port)


def resolve_host(hostname: str) -> tuple[str, ...]:
    """Löst einen Hostnamen über DNS auf (A/AAAA). Leere Liste = unauffindbar."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except (OSError, UnicodeError):
        return ()
    addresses: list[str] = []
    for info in infos:
        address = str(info[4][0])
        if address not in addresses:
            addresses.append(address)
    return tuple(addresses)


def _reject_if_ip_unsafe(hostname: str, *, explicit: bool) -> None:
    """Prüft, ob der Hostname eine IP-Adresse ist und blockiert werden muss."""
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return  # echter Hostname – DNS-Prüfung macht den Rest
    if _ip_is_unsafe(ip):
        kind = "explizit angegebene" if explicit else "aufgelöste"
        raise WebSecurityError(
            f"{kind.capitalize()} Adresse '{hostname}' ist blockiert "
            "(privat/loopback/link-local/reserviert oder Metadaten-Endpunkt)."
        )


def _ip_is_unsafe(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True, wenn die IP nicht ins öffentliche Internet gehört."""
    # IPv4-mapped IPv6 (z. B. ::ffff:10.0.0.1) auf die IPv4-Prüfung abbilden:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if str(ip) in METADATA_ENDPOINT_IPS:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def check_url(url: str, *, resolver=resolve_host) -> CheckedURL:
    """Vollständige Prüfung **vor jedem Abruf**: URL-Policy + DNS + IP-Policy.

    ``resolver`` ist injizierbar (Tests mocken DNS ohne Netzwerk).
    """
    checked = validate_url(url)
    _reject_if_ip_unsafe(checked.hostname, explicit=True)
    if _is_ip_literal(checked.hostname):
        return checked  # IP-Literal wurde bereits geprüft
    resolved = resolver(checked.hostname)
    if not resolved:
        raise WebSecurityError(
            f"Hostname '{checked.hostname}' kann nicht aufgelöst werden."
        )
    for address in resolved:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue  # exotische Resolver-Antworten ignorieren
        if _ip_is_unsafe(ip):
            raise WebSecurityError(
                f"Hostname '{checked.hostname}' löst zu blockierter Adresse "
                f"'{address}' auf (SSRF-Schutz)."
            )
    return CheckedURL(
        url=checked.url,
        scheme=checked.scheme,
        hostname=checked.hostname,
        port=checked.port,
        resolved_ips=resolved,
    )


def check_redirect(
    base_url: str, location: str | None, *, resolver=resolve_host
) -> str:
    """Prüft ein Weiterleitungsziel **neu** (Policy + DNS) und normalisiert es.

    Ohne ``Location``-Header ist kein Ziel vorhanden → Fehler; relative Ziele
    werden gegen die Ursprungs-URL aufgelöst.  ``resolver`` ist injizierbar
    (Tests mocken DNS ohne Netzwerk).
    """
    if not location:
        raise WebSecurityError(
            "Weiterleitung ohne Ziel-Header ist nicht auflösbar."
        )
    target = urljoin(base_url, location.strip())
    check_url(target, resolver=resolver)
    return target


def _is_ip_literal(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return True


def absolute_url(base_url: str, href: str | None) -> str | None:
    """Löst relative Links gegen eine Basis-URL auf (kein Abruf, keine Prüfung)."""
    if not href:
        return None
    resolved = urljoin(base_url, href.strip())
    return resolved if resolved.startswith(("http://", "https://")) else None


__all__ = [
    "ALLOWED_PORTS",
    "ALLOWED_SCHEMES",
    "BLOCKED_HOSTNAMES",
    "CheckedURL",
    "DEFAULT_TIMEOUT_S",
    "MAX_REDIRECTS",
    "MAX_RESPONSE_BYTES",
    "METADATA_ENDPOINT_IPS",
    "USER_AGENT",
    "absolute_url",
    "check_redirect",
    "check_url",
    "resolve_host",
    "validate_url",
]
