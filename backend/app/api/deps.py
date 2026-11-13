"""FastAPI-Abhängigkeiten (Dependency Injection über ``app.state``)."""

from __future__ import annotations

from fastapi import Request

from app.core.config import Settings
from app.core.extensions import ExtensionRegistry
from app.core.storage import StorageManager
from app.database.database import Database
from app.engines.llm_engine import LLMEngine
from app.services.chat_service import ChatService
from app.services.conversation_service import ConversationService
from app.services.settings_service import SettingsService


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_storage(request: Request) -> StorageManager:
    return request.app.state.storage


def get_database(request: Request) -> Database:
    return request.app.state.database


def get_settings_service(request: Request) -> SettingsService:
    return request.app.state.settings_service


def get_conversation_service(request: Request) -> ConversationService:
    return request.app.state.conversation_service


def get_chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service


def get_llm_engine(request: Request) -> LLMEngine:
    return request.app.state.llm_engine


def get_extensions(request: Request) -> ExtensionRegistry:
    return request.app.state.extensions
