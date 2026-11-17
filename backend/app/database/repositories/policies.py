"""Repository für Verhaltensregeln (Policies)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.context import get_current_user_id, scope_entity_id
from app.database.models import PolicyModel


class PolicyRepository:
    """CRUD für Regeln. IDs sind feste Slugs (system) bzw. generierte Slugs (user)."""

    def list_all(self, session: Session) -> list[PolicyModel]:
        stmt = select(PolicyModel).order_by(
            PolicyModel.source.asc(),  # 'system' vor 'user'
            PolicyModel.priority.desc(),
            PolicyModel.name.asc(),
        )
        return list(session.scalars(stmt))

    def list_enabled(self, session: Session, scope: str | None = None) -> list[PolicyModel]:
        stmt = (
            select(PolicyModel)
            .where(PolicyModel.enabled.is_(True))
            .order_by(PolicyModel.priority.desc(), PolicyModel.name.asc())
        )
        if scope is not None:
            stmt = stmt.where(PolicyModel.scope == scope)
        return list(session.scalars(stmt))

    def get(self, session: Session, policy_id: str) -> PolicyModel | None:
        return session.get(PolicyModel, policy_id)

    def create(self, session: Session, **fields) -> PolicyModel:  # noqa: ANN003
        if fields.get("id"):
            fields["id"] = scope_entity_id(str(fields["id"]))
        fields["user_id"] = get_current_user_id()
        policy = PolicyModel(**fields)
        session.add(policy)
        session.flush()
        return policy

    def delete(self, session: Session, policy_id: str) -> bool:
        policy = self.get(session, policy_id)
        if policy is None:
            return False
        session.delete(policy)
        session.flush()
        return True
