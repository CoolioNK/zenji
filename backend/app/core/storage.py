"""Speicherverwaltung: externe SSD als Hauptspeicher.

Alle Daten von ZENJI (Datenbank, Logs, Modelle, venv) liegen auf der externen
SSD unter ``ZENJI_SSD_ROOT`` (Standard ``/Volumes/ZENJI-SSD``).  Fehlt die SSD,
wird **kein** Ersatzpfad erfunden: ZENJI startet zwar (damit ``/api/health``
und das Frontend verständliche Statusmeldungen liefern können), alle
datenbank- oder speicherbezogenen Operationen liefern aber einen klaren
Fehler (HTTP 503, ``STORAGE_UNAVAILABLE``).

Während des Betriebs wird ein SSD-Trennen erkannt über:

- Schreibfehler (OSError/OperationalError), die zu ``StorageUnavailableError``
  übersetzt werden, und
- ``/api/health``, das den Speicherpfad aktiv prüft.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.core.exceptions import StorageUnavailableError
from app.core.logging import get_logger

log = get_logger("storage")

# Verzeichnisse, die ZENJI auf der SSD erwartet (spec-konform).
SSD_STRUCTURE = ("ZENJI", "models", "datasets", "backups", "environments", "logs")


@dataclass(slots=True)
class StorageStatus:
    available: bool
    root: str
    message: str


class StorageManager:
    """Verwaltet und überwacht den Speicherort auf der externen SSD."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # --- Pfade --------------------------------------------------------------
    @property
    def ssd_root(self) -> Path:
        return self._settings.ssd_root

    @property
    def storage_dir(self) -> Path:
        return self._settings.resolved_storage_dir

    @property
    def data_dir(self) -> Path:
        return self._settings.data_dir

    @property
    def db_path(self) -> Path:
        return self._settings.resolved_db_path

    @property
    def log_dir(self) -> Path:
        return self._settings.resolved_log_dir

    @property
    def models_dir(self) -> Path:
        return self._settings.models_dir

    # --- Prüfung --------------------------------------------------------------
    def status(self) -> StorageStatus:
        """Prüft, ob die SSD verbunden **und** beschreibbar ist (kein Schreiben)."""
        root = self.ssd_root
        if not root.exists():
            return StorageStatus(
                available=False,
                root=str(root),
                message=(
                    f"Externe SSD nicht verbunden – '{root}' existiert nicht. "
                    "Bitte SSD anschließen (oder ZENJI_SSD_ROOT korrekt setzen)."
                ),
            )
        if not root.is_dir():
            return StorageStatus(
                available=False,
                root=str(root),
                message=f"'{root}' ist kein Verzeichnis (Kein Mountpoint?).",
            )
        probe = root / ".zenji-write-probe"
        try:
            with tempfile.NamedTemporaryFile(prefix="probe-", dir=root, delete=False) as fh:
                fh.write(b"zenji")
                tmp = Path(fh.name)
            tmp.unlink(missing_ok=True)
        except OSError:
            tmp = probe  # existiert nicht, aber Pfad bekannt
            return StorageStatus(
                available=False,
                root=str(root),
                message=f"Speicherort '{root}' ist vorhanden, aber nicht beschreibbar (SSD evtl. schreibgeschützt).",
            )
        return StorageStatus(available=True, root=str(root), message="Speicherort verfügbar.")

    # --- Aufbau ----------------------------------------------------------------
    def ensure_structure(self) -> None:
        """Erstellt die vorgesehene Ordnerstruktur. Idempotent, löscht nichts."""
        if not self.ssd_root.exists():
            raise StorageUnavailableError(
                f"Externe SSD nicht verbunden – '{self.ssd_root}' fehlt. "
                "Es wird kein Ersatzspeicherpfad verwendet."
            )
        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            self.data_dir.mkdir(parents=True, exist_ok=True)
            for name in ("models", "datasets", "backups", "environments", "logs"):
                (self.ssd_root / name).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageUnavailableError(
                f"Ordnerstruktur konnte nicht erstellt werden: {exc}"
            ) from exc
        log.info("Speicherstruktur verifiziert unter %s", self.ssd_root)

    # --- Fehlerübersetzung -------------------------------------------------------
    @staticmethod
    def translate_os_error(exc: OSError, context: str) -> StorageUnavailableError:
        """Übersetzt plötzliche Speicherausfälle in eine klare fachliche Meldung."""
        return StorageUnavailableError(
            f"Speicherzugriff fehlgeschlagen ({context}): {exc}. "
            "Möglicherweise wurde die externe SSD während des Betriebs getrennt."
        )
