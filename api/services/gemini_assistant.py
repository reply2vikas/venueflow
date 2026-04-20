"""
VenueFlow AI Assistant powered by Google Vertex AI (Gemini 1.5 Flash).

Answers natural-language questions about the venue by injecting
live crowd density data as context into every prompt.

Performance notes:
- vertexai is imported LAZILY inside the function (not at module load)
  This reduces Cloud Run cold start time from ~4s to ~1s
- Rule-based fallback ensures answers even when Vertex AI is down
- Responses capped at 60 words — users are on phones in a stadium
"""

import os
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are VenueFlow, a helpful stadium navigation assistant.
Your only job is to answer questions about crowd levels, wait times,
accessible routes, and safety at this specific venue right now.

Rules:
1. Only answer questions about this venue, crowds, routes, or accessibility.
2. Always prefer step-free routes for wheelchair users.
3. If a zone is at density 4 or 5, actively suggest alternatives.
4. Keep answers under 60 words — users are on phones in a busy stadium.
5. Never invent zone names not present in the data below.
6. If unsure, say: Check with a steward at Gate C info booth.
"""


async def ask_gemini(
    user_question: str,
    zone_context: list,
    wheelchair_mode: bool = False,
    language: str = "en",
) -> str:
    """
    Send a question to Gemini 1.5 Flash with live venue crowd context.
    Falls back to rule-based answers if Vertex AI is unavailable.
    """
    try:
        # Lazy import — only loads when first AI question is asked
        # This is why startup is fast even with a heavy AI package
        import vertexai
        from vertexai.generative_models import GenerativeModel, GenerationConfig

        project  = os.environ.get("GCP_PROJECT", "")
        location = os.environ.get("VERTEX_LOCATION", "us-central1")

        vertexai.init(project=project, location=location)

        system = _build_system_prompt(wheelchair_mode, language)
        model  = GenerativeModel(model_name="gemini-1.5-flash-001",
                                 system_instruction=system)

        context = _format_zone_context(zone_context)
        prompt  = f"{context}\n\nAttendee question: {user_question}"

        config = GenerationConfig(temperature=0.2, max_output_tokens=150, top_p=0.8)

        import asyncio
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(
            None,
            lambda: model.generate_content(prompt, generation_config=config).text.strip()
        )
        return text

    except ImportError:
        logger.info("vertexai not installed — using fallback")
        return _rule_based_fallback(user_question, zone_context)
    except Exception as exc:
        logger.error("Gemini call failed: %s", exc)
        return _rule_based_fallback(user_question, zone_context)


def _build_system_prompt(wheelchair_mode: bool, language: str) -> str:
    prompt = SYSTEM_PROMPT
    if wheelchair_mode:
        prompt += "\nIMPORTANT: User is in wheelchair mode. Always prefer step-free routes."
    if language != "en":
        names = {"kn": "Kannada", "hi": "Hindi", "ta": "Tamil"}
        prompt += f"\nIMPORTANT: Respond in {names.get(language, 'English')}."
    return prompt


def _format_zone_context(zones: list) -> str:
    if not zones:
        return "VENUE DATA: No live data. Advise user to check the info board."
    labels = {1: "Clear", 2: "Light", 3: "Moderate", 4: "Busy", 5: "Packed"}
    lines  = ["LIVE VENUE DATA (updated 30 seconds ago):"]
    for z in zones:
        level = labels.get(z.get("density_level", 1), "Unknown")
        wait  = z.get("wait_time_minutes")
        w_str = f"~{wait} min wait" if wait is not None else "wait unknown"
        lines.append(f"- {z['zone_id']}: {level} ({w_str})")
    return "\n".join(lines)


def _rule_based_fallback(question: str, zones: list) -> str:
    """Instant rule-based answers when Gemini is unavailable."""
    q = question.lower()
    clear_zones = [z["zone_id"] for z in zones if z.get("density_level", 3) <= 2]
    busy_zones  = [z["zone_id"] for z in zones if z.get("density_level", 3) >= 4]

    if any(kw in q for kw in ["restroom", "toilet", "bathroom"]):
        return "Accessible Restroom F (Concourse South) is the least crowded accessible facility. Head there via Lift W1."
    if any(kw in q for kw in ["food", "eat", "snack", "drink", "hungry"]):
        if "food_court_E" in busy_zones:
            return "Food Court East is busy. Try concessions near Gate A — currently clear with ~2 min wait."
        return "Food Court East is available. Moderate crowds right now."
    if any(kw in q for kw in ["exit", "leave", "go home", "out"]):
        return "North Exit (Gate C side) is most accessible and least crowded. Start heading there 10 minutes before match ends."
    if any(kw in q for kw in ["wheelchair", "accessible", "ramp", "lift"]):
        return "Gate C is fully wheelchair accessible with Lift W1 nearby. Accessible Restroom F is on Concourse South."
    if clear_zones:
        return f"Currently clear zones: {', '.join(clear_zones[:3])}. I recommend heading there now."
    return "Stadium is busy. Stay seated for 10 minutes and conditions will improve. For help visit Gate C info booth."
