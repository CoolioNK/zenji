"""Chat-Routen: Nachricht senden (komplett) und streamen (SSE)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api import deps
from app.core.exceptions import ZenjiError
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", summary="Nachricht senden, komplette Antwort erhalten")
async def chat(
    payload: ChatRequest,
    chat_service: ChatService = Depends(deps.get_chat_service),
) -> ChatResponse:
    turn = await chat_service.send_message(payload)
    return ChatResponse(
        conversation_id=turn.conversation_id,
        user_message=turn.user_message,
        assistant_message=turn.assistant_message,
    )


@router.post("/stream", summary="Nachricht senden, Antwort als SSE streamen")
async def chat_stream(
    payload: ChatRequest,
    chat_service: ChatService = Depends(deps.get_chat_service),
) -> StreamingResponse:
    """Server-Sent Events: ``start`` → ``delta``* → ``done`` | ``error``.

    Fehler, die **vor** dem ersten Stream-Event auftreten (fehlende SSD, Ollama
    down, Modell nicht geladen, unbekannte Konversation), enden als saubere
    HTTP-Fehlermeldung – das Frontend kann sie direkt anzeigen.
    Fehler **während** des Streams werden als ``error``-Event übertragen.
    """
    try:
        await chat_service.preflight(payload)
        generator = chat_service.stream_message(payload)
        first = await generator.__anext__()
    except ZenjiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message, "detail": exc.detail},
        ) from exc

    async def _merged():
        yield first
        async for event in generator:
            yield event

    return StreamingResponse(
        _merged(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
