"""Datenbank-Engine und Sitzungsverwaltung für SQLite.

Der Datenbankpfad kommt ausschließlich aus der Konfiguration (Standard:
``<SSD_ROOT>/ZENJI/data/zenji.db``).  Schlägt ein Zugriff fehl – etwa weil die
externe SSD während des Betriebs getrennt wurde – wird der Fehler in eine
klare ``StorageUnavailableError``-Meldung übersetzt statt als kryptische
SQLite-Ausnahme zu enden.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.exceptions import DatabaseError, StorageUnavailableError
from app.core.logging import get_logger
from app.database.models import Base

log = get_logger("database")

_DISK_ERRORS = ("disk I/O", "unable to open database file", "readonly database", "disk full")


class Database:
    """Kapselt Engine, Schema-Erstellung und Sitzungen."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._db_path: Path = settings.resolved_db_path
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            self._engine = self._create_engine()
        return self._engine

    def _create_engine(self) -> Engine:
        # Architekturregel: Ohne externe SSD wird **keine** Datenbank an einem
        # Ersatzpfad angelegt – es gibt eine klare Fehlermeldung.
        if not self._settings.ssd_root.exists():
            raise StorageUnavailableError(
                f"Externe SSD nicht verbunden – '{self._settings.ssd_root}' fehlt. "
                "Datenbankoperationen sind ohne SSD nicht möglich "
                "(kein Ersatzspeicherpfad, siehe docs/STORAGE.md)."
            )
        parent = self._db_path.parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageUnavailableError(
                f"Datenbankverzeichnis '{parent}' nicht beschreibbar: {exc}. "
                "Ist die externe SSD verbunden?"
            ) from exc

        engine = create_engine(
            f"sqlite:///{self._db_path}",
            connect_args={"check_same_thread": False, "timeout": 15},
            future=True,
        )

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _record) -> None:  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

        return engine

    def create_schema(self) -> None:
        """Erstellt das Schema, falls es noch nicht existiert (idempotent)."""
        try:
            Base.metadata.create_all(self.engine)
        except OperationalError as exc:
            raise self._translate(exc, "Schema-Erstellung") from exc

    def is_ready(self) -> bool:
        """True, wenn die Datenbank geöffnet und eine Abfrage möglich ist."""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:  # noqa: BLE001 – bewusst breit: Status, kein Crash
            return False

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Sitzungskontext mit Fehlerübersetzung für SSD-/Festplattenprobleme."""
        if self._session_factory is None:
            self._session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except OperationalError as exc:
            session.rollback()
            raise self._translate(exc, "Datenbankoperation") from exc
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _translate(exc: OperationalError, context: str) -> ZenjiDatabaseErrorLike:
        message = str(exc).lower()
        if any(marker in message for marker in _DISK_ERRORS):
            return StorageUnavailableError(
                f"Datenbankzugriff fehlgeschlagen ({context}): {exc}. "
                "Möglicherweise wurde die externe SSD getrennt."
            )
        return DatabaseError(f"Datenbankfehler ({context}): {exc}")

    def dispose(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            self._session_factory = None


# Nur für die Typannotation oben; zur Laufzeit wirkungslos.
ZenjiDatabaseErrorLike = StorageUnavailableError | DatabaseError
