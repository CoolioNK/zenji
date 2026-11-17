"""Repository für Persönlichkeitsprofile."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.context import get_current_user_id
from app.database.models import PersonalityModel, new_id, utcnow


class PersonalityRepository:
    """CRUD für Profile. Mapping zu Schemata macht der Service."""

    def list_all(self, session: Session) -> list[PersonalityModel]:
        stmt = select(PersonalityModel).order_by(
            PersonalityModel.is_active.desc(), PersonalityModel.created_at.asc()
        )
        return list(session.scalars(stmt))

    def get(self, session: Session, personality_id: str) -> PersonalityModel | None:
        return session.get(PersonalityModel, personality_id)

    def get_by_name(self, session: Session, name: str) -> PersonalityModel | None:
        stmt = select(PersonalityModel).where(PersonalityModel.name == name)
        return session.scalars(stmt).first()

    def create(self, session: Session, **fields) -> PersonalityModel:  # noqa: ANN003
        profile = PersonalityModel(id=new_id(), user_id=get_current_user_id(), **fields)
        session.add(profile)
        session.flush()
        return profile

    def activate(self, session: Session, personality_id: str) -> bool:
        """Genau ein Profil aktiv: erst alle deaktivieren, dann Ziel aktivieren."""
        profile = self.get(session, personality_id)
        if profile is None:
            return False
        session.execute(update(PersonalityModel).values(is_active=False))
        profile.is_active = True
        profile.updated_at = utcnow()
        session.flush()
        return True

    def delete(self, session: Session, personality_id: str) -> bool:
        profile = self.get(session, personality_id)
        if profile is None:
            return False
        session.delete(profile)
        session.flush()
        return True

    def active(self, session: Session) -> PersonalityModel | None:
        stmt = select(PersonalityModel).where(PersonalityModel.is_active.is_(True))
        return session.scalars(stmt).first()
