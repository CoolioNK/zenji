"""API-Routen registrieren."""

from fastapi import APIRouter

from app.api.routes import (
    chat,
    conversations,
    core,
    health,
    memory,
    models,
    personality,
    policies,
    settings,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(models.router)
api_router.include_router(settings.router)
api_router.include_router(conversations.router)
api_router.include_router(chat.router)
api_router.include_router(personality.router)
api_router.include_router(policies.router)
api_router.include_router(memory.router)
api_router.include_router(core.router)
