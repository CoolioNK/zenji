"""FastAPI-Abhängigkeiten (Dependency Injection über ``app.state``)."""

from __future__ import annotations

from fastapi import Request

from app.core.config import Settings
from app.core.extensions import ExtensionRegistry
from app.core.storage import StorageManager
from app.database.database import Database
from app.engines.context_engine import ContextEngine
from app.engines.llm_engine import LLMEngine
from app.engines.memory_engine import MemoryEngine
from app.engines.personality_engine import PersonalityEngine
from app.engines.policy_engine import PolicyEngine
from app.services.chat_service import ChatService
from app.services.conversation_service import ConversationService
from app.services.settings_service import SettingsService
from app.services.web_intelligence_service import WebIntelligenceService
from app.services.zenji_core import ZenjiCore


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


# --- Phase 2: Engines und Core ----------------------------------------------------


def get_personality_engine(request: Request) -> PersonalityEngine:
    return request.app.state.personality_engine


def get_policy_engine(request: Request) -> PolicyEngine:
    return request.app.state.policy_engine


def get_memory_engine(request: Request) -> MemoryEngine:
    return request.app.state.memory_engine


def get_context_engine(request: Request) -> ContextEngine:
    return request.app.state.context_engine


def get_zenji_core(request: Request) -> ZenjiCore:
    return request.app.state.zenji_core


# --- Phase 3: Web Intelligence ----------------------------------------------------


def get_web_intelligence(request: Request) -> "WebIntelligenceService":
    return request.app.state.web_intelligence
