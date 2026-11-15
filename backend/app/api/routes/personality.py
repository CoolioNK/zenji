"""``/api/personality`` – Persönlichkeitsprofile (Phase 2)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api import deps
from app.core.exceptions import ZenjiError
from app.database.models import PersonalityModel
from app.schemas.personality import (
    PersonalityCreate,
    PersonalityOut,
    PersonalityPreview,
    PersonalityUpdate,
)
from app.engines.personality_engine import PersonalityEngine

router = APIRouter(prefix="/personality", tags=["personality"])


def _db_session(request: Request):
    database = deps.get_database(request)
    with database.session() as session:
        yield session


def _out(profile: PersonalityModel) -> PersonalityOut:
    return PersonalityOut(
        id=profile.id,
        name=profile.name,
        identity=profile.identity,
        base_personality=profile.base_personality,
        communication_style=profile.communication_style,
        formality=profile.formality,
        humor=profile.humor,
        sarcasm=profile.sarcasm,
        cheekiness=profile.cheekiness,
        directness=profile.directness,
        friendliness=profile.friendliness,
        empathy=profile.empathy,
        curiosity=profile.curiosity,
        initiative=profile.initiative,
        creativity=profile.creativity,
        response_length=profile.response_length,
        language=profile.language,
        situational_behavior=profile.behavior_map(),
        is_system=profile.is_system,
        is_active=profile.is_active,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.get("", summary="Alle Persönlichkeitsprofile (aktives zuerst)")
def list_personalities(
    session: Session = Depends(_db_session),
    engine: PersonalityEngine = Depends(deps.get_personality_engine),
) -> list[PersonalityOut]:
    return [_out(profile) for profile in engine.list(session)]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Eigenes Profil anlegen")
def create_personality(
    payload: PersonalityCreate,
    session: Session = Depends(_db_session),
    engine: PersonalityEngine = Depends(deps.get_personality_engine),
) -> PersonalityOut:
    try:
        profile = engine.create(session, payload.model_dump())
    except ZenjiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return _out(profile)


@router.get("/{personality_id}/preview", summary="Kompilierte Persönlichkeit (Vorschau)")
def preview_personality(
    personality_id: str,
    session: Session = Depends(_db_session),
    engine: PersonalityEngine = Depends(deps.get_personality_engine),
) -> PersonalityPreview:
    try:
        profile = engine.get(session, personality_id)
    except ZenjiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return PersonalityPreview(
        name=profile.name,
        is_active=profile.is_active,
        compiled_text=engine.compile_context(profile),
    )


@router.patch("/{personality_id}", summary="Profil bearbeiten")
def update_personality(
    personality_id: str,
    payload: PersonalityUpdate,
    session: Session = Depends(_db_session),
    engine: PersonalityEngine = Depends(deps.get_personality_engine),
) -> PersonalityOut:
    try:
        fields = payload.model_dump(exclude_unset=True)
        if payload.situational_behavior is not None:
            fields["situational_behavior"] = json.dumps(
                payload.situational_behavior, ensure_ascii=False
            )
        profile = engine.update(session, personality_id, fields)
    except ZenjiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return _out(profile)


@router.post("/{personality_id}/activate", summary="Profil aktivieren (genau eines aktiv)")
def activate_personality(
    personality_id: str,
    session: Session = Depends(_db_session),
    engine: PersonalityEngine = Depends(deps.get_personality_engine),
) -> PersonalityOut:
    try:
        profile = engine.activate(session, personality_id)
    except ZenjiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return _out(profile)


@router.delete("/{personality_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Profil löschen")
def delete_personality(
    personality_id: str,
    session: Session = Depends(_db_session),
    engine: PersonalityEngine = Depends(deps.get_personality_engine),
) -> None:
    try:
        engine.delete(session, personality_id)
    except ZenjiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
