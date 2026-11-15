"""SQLAlchemy-Modelle: Konversationen, Nachrichten, Einstellungen.

Phase 2 ergänzt: Persönlichkeitsprofile, Verhaltensregeln (Policies) und
Erinnerungen (Memory) – siehe ``app.database.migrations`` für den
Migrations-/Seed-Ablauf und ``docs/ARCHITECTURE.md`` für die Übersicht.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


ROLES = ("system", "user", "assistant")


class Base(DeclarativeBase):
    pass


class ConversationModel(Base):
    """Eine Chat-Konversation (mehrere Chats möglich)."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200), default="Neue Konversation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    messages: Mapped[list["MessageModel"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="MessageModel.created_at",
        lazy="selectin",
    )


class MessageModel(Base):
    """Eine einzelne Nachricht innerhalb einer Konversation."""

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('system','user','assistant')", name="ck_message_role"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped[ConversationModel] = relationship(back_populates="messages")


class SettingModel(Base):
    """Laufzeit-Einstellungen als Schlüssel/Wert-Speicher (JSON in Text)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


def touch(conversation: ConversationModel) -> None:
    """Aktualisiert ``updated_at`` explizit (SQLite setzt onupdate bei ORM-Flush)."""
    conversation.updated_at = utcnow()


# ---------------------------------------------------------------------------
# Phase 2: Personality · Policy · Memory
# ---------------------------------------------------------------------------

PERSONALITY_BASES = ("neutral", "professional", "friendly", "casual", "custom")
RESPONSE_LENGTHS = ("short", "balanced", "detailed")
MEMORY_TYPES = ("conversation", "long_term", "preference", "project")
MEMORY_STATUSES = ("active", "superseded", "archived")
POLICY_SCOPES = ("global", "personality", "conversation")
POLICY_SOURCES = ("system", "user")


def json_default(value: Any) -> str:
    """Serialisiert JSON-Felder robust (Fallback: String-Darstellung)."""
    return json.dumps(value, ensure_ascii=False)


class PersonalityModel(Base):
    """Ein konfigurierbares Persönlichkeitsprofil von ZENJI.

    Profile leben ausschließlich in der Datenbank (Seed über JSON-Dateien in
    ``backend/app/config/``) – nicht im Python-Code.  ``is_active`` kennzeichnet
    das aktuell verwendete Profil (genau eines aktiv).
    """

    __tablename__ = "personalities"
    __table_args__ = (
        CheckConstraint(
            "base_personality IN ('neutral','professional','friendly','casual','custom')",
            name="ck_personality_base",
        ),
        CheckConstraint(
            "response_length IN ('short','balanced','detailed')",
            name="ck_personality_length",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    identity: Mapped[str] = mapped_column(Text, default="")
    base_personality: Mapped[str] = mapped_column(String(20), default="neutral")
    communication_style: Mapped[str] = mapped_column(String(200), default="")
    formality: Mapped[float] = mapped_column(default=0.5)
    humor: Mapped[float] = mapped_column(default=0.2)
    directness: Mapped[float] = mapped_column(default=0.6)
    creativity: Mapped[float] = mapped_column(default=0.5)
    # v0.3.0 (Begleiter-Persönlichkeit): sechs zusätzliche Eigenschaftsachsen.
    # Werte bleiben 0–1 (UI zeigt Prozent) – Migration 2→3 ergänzt die Spalten
    # idempotent für bestehende Datenbanken.
    sarcasm: Mapped[float] = mapped_column(default=0.3)
    cheekiness: Mapped[float] = mapped_column(default=0.4)
    friendliness: Mapped[float] = mapped_column(default=0.7)
    empathy: Mapped[float] = mapped_column(default=0.6)
    curiosity: Mapped[float] = mapped_column(default=0.6)
    initiative: Mapped[float] = mapped_column(default=0.5)
    response_length: Mapped[str] = mapped_column(String(20), default="balanced")
    language: Mapped[str] = mapped_column(String(40), default="auto")
    situational_behavior: Mapped[str] = mapped_column(Text, default="{}")
    is_system: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    def behavior_map(self) -> dict[str, str]:
        """Situationsverhalten als Dict (robust gegen ungültiges JSON)."""
        try:
            data = json.loads(self.situational_behavior or "{}")
            return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
        except ValueError:
            return {}


class PolicyModel(Base):
    """Eine Verhaltensregel (Policy), modellunabhängig.

    ``scope``: global | personality | conversation
    ``source``: system (geschützt, Seed) | user (frei editierbar)
    ``priority``: 0–100, höhere Priorität gewinnt bei Konflikten.
    """

    __tablename__ = "policies"
    __table_args__ = (
        CheckConstraint("priority BETWEEN 0 AND 100", name="ck_policy_priority"),
        CheckConstraint(
            "scope IN ('global','personality','conversation')", name="ck_policy_scope"
        ),
        CheckConstraint("source IN ('system','user')", name="ck_policy_source"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    instruction: Mapped[str] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(default=50)
    enabled: Mapped[bool] = mapped_column(default=True)
    category: Mapped[str] = mapped_column(String(40), default="style")
    scope: Mapped[str] = mapped_column(String(20), default="global")
    source: Mapped[str] = mapped_column(String(20), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class MemoryModel(Base):
    """Eine Erinnerung des ZENJI-Gedächtnisses.

    Pflichtfelder gemäß Spezifikation: Inhalt, Kategorie, Erstell-/Änderungsdatum,
    Quelle, Relevanz, Status.  ``memory_type`` unterscheidet Conversation- /
    Long-Term-Memory / User-Preferences / Project-Memory.  ``content_hash``
    (normalisierter Text) dient der Duplikaterkennung.
    """

    __tablename__ = "memories"
    __table_args__ = (
        CheckConstraint(
            "memory_type IN ('conversation','long_term','preference','project')",
            name="ck_memory_type",
        ),
        CheckConstraint(
            "status IN ('active','superseded','archived')", name="ck_memory_status"
        ),
        CheckConstraint("relevance BETWEEN 0 AND 1", name="ck_memory_relevance"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True, default="")
    category: Mapped[str] = mapped_column(String(40), default="allgemein")
    memory_type: Mapped[str] = mapped_column(String(20), default="long_term")
    source: Mapped[str] = mapped_column(String(30), default="user")
    source_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    relevance: Mapped[float] = mapped_column(default=0.5)
    status: Mapped[str] = mapped_column(String(20), default="active")
    supersedes_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SchemaVersionModel(Base):
    """Migrations-Metadaten (genau eine Zeile mit ``version``)."""

    __tablename__ = "schema_version"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    version: Mapped[int] = mapped_column(default=0)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def normalize_content(text: str) -> str:
    """Normalisiert Inhalt für Hash-/Vergleichszwecke (Duplikaterkennung)."""
    collapsed = " ".join((text or "").lower().split())
    return collapsed.strip(".,;:!?")


def content_hash(text: str) -> str:
    """Stabiler Kurz-Hash des normalisierten Inhalts (SHA256, 32 Hexzeichen)."""
    import hashlib

    return hashlib.sha256(normalize_content(text).encode("utf-8")).hexdigest()[:32]
