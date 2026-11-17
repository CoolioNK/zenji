"""Datenbank-Engine und Sitzungsverwaltung.

Zwei Modi:

- **Supabase/Postgres** (``supabase_enabled``): alle Nutzerdaten in der Cloud,
  getrennt durch Row-Level-Security.  Pro Transaktion wird der Nutzer-Kontext
  (``request.jwt.claims``) gesetzt.
- **Lokal/SQLite**: eine Datei auf der externen SSD (Single-User).  Schlägt ein
  Zugriff fehl – etwa weil die SSD getrennt wurde – wird der Fehler in eine
  klare ``StorageUnavailableError``-Meldung übersetzt.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.context import get_current_user_id
from app.core.exceptions import DatabaseError, StorageUnavailableError
from app.core.logging import get_logger
from app.database.models import Base

log = get_logger("database")

_DISK_ERRORS = ("disk I/O", "unable to open database file", "readonly database", "disk full")

#: Tabellen mit Nutzerdaten. Für jede wird eine RLS-Policy aktiviert, die
#: ``user_id = auth.uid()`` erzwingt – damit sieht jeder Account nur seine Daten.
_RLS_TABLES = (
    "conversations",
    "messages",
    "settings",
    "personalities",
    "policies",
    "memories",
    "research_sessions",
    "search_queries",
    "search_results",
    "sources",
    "source_snapshots",
    "citations",
    "research_cache",
)


class Database:
    """Kapselt Engine, Schema-Erstellung und Sitzungen.

    Zwei Betriebsarten:

    - **Supabase/Postgres** (``supabase_enabled``): Alle Nutzerdaten liegen in
      Supabase.  Jede Sitzung setzt ``request.jwt.claims`` auf den aktuellen
      Nutzer; Postgres-RLS trennt die Accounts.
    - **Lokal/SQLite** (Fallback für Tests/Offline): eine Datei, Single-User.
    """

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

    @property
    def is_postgres(self) -> bool:
        return self._engine is not None and self._engine.dialect.name == "postgresql"

    def _create_engine(self) -> Engine:
        if self._settings.supabase_enabled and self._settings.supabase_db_url:
            return self._create_postgres_engine(self._settings.supabase_db_url)
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

    @staticmethod
    def _create_postgres_engine(db_url: str) -> Engine:
        url = db_url.strip()
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://") :]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://") :]
        return create_engine(
            url,
            pool_pre_ping=True,
            # Cloud (Supabase Pooler): Der Pooler trennt ungenutzte Verbindungen
            # nach einiger Zeit – rechtzeitig selbst recyceln, damit pre_ping
            # seltener neu verbinden muss (jede neue Verbindung kostet DNS/TLS).
            pool_recycle=240,
            # Bei Pool-Erschöpfung schnell scheitern statt minutenlang zu
            # warten (blockiert sonst Anfragen und im schlimmsten Fall den
            # Event-Loop → Render startet die Instanz neu).
            pool_timeout=15,
            # Neue Verbindungen nicht unbegrenzt warten lassen.
            connect_args={"connect_timeout": 10},
            future=True,
        )

    def create_schema(self) -> None:
        """Erstellt das Schema, falls es noch nicht existiert (idempotent)."""
        try:
            Base.metadata.create_all(self.engine)
            if self.engine.dialect.name == "postgresql":
                self.apply_rls_policies()
        except OperationalError as exc:
            raise self._translate(exc, "Schema-Erstellung") from exc

    def apply_rls_policies(self) -> None:
        """Aktiviert Row-Level-Security für alle Nutzer-Tabellen (idempotent).

        Wird nur bei Postgres/Supabase ausgeführt.  Die Policies erlauben der
        Rolle ``authenticated`` ausschließlich Zeilen mit
        ``user_id = auth.uid()``; ``profiles`` wird über ``id = auth.uid()``
        geschützt.
        """
        statements: list[str] = [
            "GRANT USAGE ON SCHEMA public TO authenticated",
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO authenticated",
        ]
        for table in _RLS_TABLES:
            statements.extend(
                [
                    f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY",
                    f'DROP POLICY IF EXISTS "{table}_own" ON public.{table}',
                    f'CREATE POLICY "{table}_own" ON public.{table} FOR ALL TO authenticated '
                    f"USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid())",
                ]
            )
        statements.extend(
            [
                "ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY",
                'DROP POLICY IF EXISTS "profiles_own" ON public.profiles',
                'CREATE POLICY "profiles_own" ON public.profiles FOR ALL TO authenticated '
                "USING (id = auth.uid()) WITH CHECK (id = auth.uid())",
                # Technische Tabelle: für ``authenticated`` sperren (Migrationen
                # laufen als Admin).
                "ALTER TABLE public.schema_version ENABLE ROW LEVEL SECURITY",
            ]
        )
        with self.engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))
        log.info("Row-Level-Security für %d Tabellen aktiviert.", len(_RLS_TABLES) + 1)

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
        """Sitzungskontext mit Fehlerübersetzung für SSD-/Festplattenprobleme.

        In Supabase wird pro Transaktion der Nutzer-Kontext gesetzt, damit RLS
        greift.  Für administrative Aufgaben (Schema, Migrationen, Seed) bitte
        ``admin_session`` verwenden.
        """
        with self._session(admin=False) as session:
            yield session

    @contextmanager
    def admin_session(self) -> Iterator[Session]:
        """Sitzung ohne Nutzer-RLS (Schema, Migrationen, globaler Seed)."""
        with self._session(admin=True) as session:
            yield session

    @contextmanager
    def _session(self, *, admin: bool) -> Iterator[Session]:
        if self._session_factory is None:
            self._session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)
        session = self._session_factory()
        try:
            if self.engine.dialect.name == "postgresql" and not admin:
                self._apply_rls_claims(session)
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
    def _apply_rls_claims(session: Session) -> None:
        """Setzt ``request.jwt.claims`` + Rolle für die aktuelle Transaktion."""
        user_id = get_current_user_id()
        claims: dict[str, str] = {"role": "authenticated"}
        if user_id:
            claims["sub"] = user_id
        # Ohne Nutzer (z. B. öffentliche Status-Endpunkte) bleibt ``sub`` weg –
        # ``auth.uid()`` ist dann NULL und RLS gibt keine Zeilen frei.
        session.execute(
            text("SELECT set_config('request.jwt.claims', :claims, true)"),
            {"claims": json.dumps(claims, ensure_ascii=False)},
        )
        # Ab hier gilt die Rolle ``authenticated`` → RLS-Policies greifen.
        session.execute(text("SET LOCAL ROLE authenticated"))

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
