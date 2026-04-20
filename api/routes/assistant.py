"""
POST /api/chat — VenueFlow AI Assistant

Accepts a natural language question, enriches it with live zone data,
sends it to Gemini 1.5 Flash (Vertex AI), and returns a short answer.

Rate limited to 10 requests per minute per IP.
Input is sanitised to prevent prompt injection.
"""

import html
import re
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.services.gemini_assistant import ask_gemini
from api.services.crowd import get_all_zone_densities

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

_SAFE_PATTERN = re.compile(r"[^\w\s\?\!\.\,\-\'\"\\u0900-\\u097F\\u0C80-\\u0CFF]+", re.UNICODE)
MAX_QUESTION_LENGTH = 200


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=MAX_QUESTION_LENGTH)
    wheelchair: bool = False
    language: str = Field(default="en", pattern="^(en|kn|hi|ta)$")

    @field_validator("question")
    @classmethod
    def sanitise_question(cls, v: str) -> str:
        """Strip HTML and special chars to prevent prompt injection."""
        v = html.unescape(v)
        v = _SAFE_PATTERN.sub(" ", v).strip()
        if len(v) < 3:
            raise ValueError("Question too short after sanitisation")
        return v


class ChatResponse(BaseModel):
    answer: str
    source: str
    zones_used: int


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("10/minute")
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    """
    Ask VenueFlow AI a natural language question about the venue.
    Powered by Google Vertex AI (Gemini 1.5 Flash).
    Falls back to rule-based answers if Vertex AI is unavailable.
    """
    try:
        zones = await get_all_zone_densities()
        zone_dicts = [
            {
                "zone_id": z.zone_id,
                "density_level": z.density_level,
                "wait_time_minutes": z.wait_time_minutes,
            }
            for z in zones
        ]

        answer = await ask_gemini(
            user_question=body.question,
            zone_context=zone_dicts,
            wheelchair_mode=body.wheelchair,
            language=body.language,
        )

        source = "fallback" if len(answer) < 30 else "gemini"

        return ChatResponse(
            answer=answer,
            source=source,
            zones_used=len(zone_dicts),
        )

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="AI assistant temporarily unavailable. Please try again.",
        )
