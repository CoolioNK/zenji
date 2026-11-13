"""API-Routen registrieren."""

from fastapi import APIRouter

from app.api.routes import chat, conversations, health, models, settings

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(models.router)
api_router.include_router(settings.router)
api_router.include_router(conversations.router)
api_router.include_router(chat.router)
