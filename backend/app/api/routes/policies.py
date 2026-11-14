"""``/api/policies`` – Verhaltensregeln (Phase 2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api import deps
from app.core.exceptions import ZenjiError
from app.engines.policy_engine import PolicyEngine
from app.schemas.policy import (
    PolicyConflictOut,
    PolicyCreate,
    PolicyOut,
    PoliciesResponse,
    PolicyUpdate,
)

router = APIRouter(prefix="/policies", tags=["policies"])


def _db_session(request: Request):
    database = deps.get_database(request)
    with database.session() as session:
        yield session


@router.get("", summary="Alle Regeln inkl. Konfliktbericht")
def list_policies(
    session: Session = Depends(_db_session),
    engine: PolicyEngine = Depends(deps.get_policy_engine),
) -> PoliciesResponse:
    policies = engine.list(session)
    compilation = engine.compile(session)
    return PoliciesResponse(
        policies=[PolicyOut.model_validate(rule) for rule in policies],
        conflicts=[
            PolicyConflictOut(
                winner_id=conflict.winner_id,
                winner_name=conflict.winner_name,
                dropped_id=conflict.dropped_id,
                dropped_name=conflict.dropped_name,
                similarity=conflict.similarity,
                reason=conflict.reason,
            )
            for conflict in compilation.conflicts
        ],
        disabled_count=compilation.disabled_count,
    )


@router.post("", status_code=status.HTTP_201_CREATED, summary="Nutzerregel anlegen")
def create_policy(
    payload: PolicyCreate,
    session: Session = Depends(_db_session),
    engine: PolicyEngine = Depends(deps.get_policy_engine),
) -> PolicyOut:
    try:
        policy = engine.create(session, payload.model_dump())
    except ZenjiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return PolicyOut.model_validate(policy)


@router.patch("/{policy_id}", summary="Nutzerregel bearbeiten")
def update_policy(
    policy_id: str,
    payload: PolicyUpdate,
    session: Session = Depends(_db_session),
    engine: PolicyEngine = Depends(deps.get_policy_engine),
) -> PolicyOut:
    try:
        policy = engine.update(
            session, policy_id, payload.model_dump(exclude_unset=True)
        )
    except ZenjiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return PolicyOut.model_validate(policy)


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Nutzerregel löschen")
def delete_policy(
    policy_id: str,
    session: Session = Depends(_db_session),
    engine: PolicyEngine = Depends(deps.get_policy_engine),
) -> None:
    try:
        engine.delete(session, policy_id)
    except ZenjiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
