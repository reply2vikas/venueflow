"""
Multi-language support via Google Cloud Translation API.

Translates zone labels, alert messages, and route instructions
into Kannada (kn), Hindi (hi), or Tamil (ta) for Indian venues.

Falls back to English gracefully if Translation API is unavailable.
Caches translations in-memory to avoid redundant API calls.
"""



import os
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

# Supported languages with their ISO codes
SUPPORTED_LANGUAGES = {
    "en": "English",
    "kn": "Kannada",
    "hi": "Hindi",
    "ta": "Tamil",
}

# Static translations for the most common UI strings
# Reduces API calls for known strings
STATIC_TRANSLATIONS: dict[str, dict[str, str]] = {
    "Gate A (North)": {"kn": "ಗೇಟ್ A (ಉತ್ತರ)", "hi": "गेट A (उत्तर)", "ta": "வாயில் A (வடக்கு)"},
    "Clear": {"kn": "ಸ್ಪಷ್ಟ", "hi": "साफ़", "ta": "தெளிவான"},
    "Busy": {"kn": "ಜನಸಂದಣಿ", "hi": "व्यस्त", "ta": "பிஸியான"},
    "Packed": {"kn": "ತುಂಬಿದೆ", "hi": "भरा हुआ", "ta": "நிரம்பியது"},
    "Step-free route": {"kn": "ಮೆಟ್ಟಿಲು ರಹಿತ ಮಾರ್ಗ", "hi": "सीढ़ी-रहित मार्ग", "ta": "படி இல்லாத பாதை"},
    "Exit now": {"kn": "ಈಗ ನಿರ್ಗಮಿಸಿ", "hi": "अभी बाहर जाएं", "ta": "இப்போது வெளியேறு"},
}


async def translate_text(text: str, target_language: str) -> str:
    """
    Translate text to target_language using Google Cloud Translation API.

    Args:
        text: The source text (always English from our system).
        target_language: ISO 639-1 code (kn, hi, ta, en).

    Returns:
        Translated text, or original English text on failure.
    """
    if target_language == "en" or not text.strip():
        return text

    # Check static cache first
    if text in STATIC_TRANSLATIONS:
        return STATIC_TRANSLATIONS[text].get(target_language, text)

    try:
        from google.cloud import translate_v2 as translate

        client = _get_translate_client()
        result = client.translate(text, target_language=target_language)
        translated: str = result["translatedText"]

        # Cache it for this process lifetime
        if text not in STATIC_TRANSLATIONS:
            STATIC_TRANSLATIONS[text] = {}
        STATIC_TRANSLATIONS[text][target_language] = translated

        return translated

    except ImportError:
        logger.warning("google-cloud-translate not installed")
        return text
    except Exception as exc:
        logger.error("Translation failed for '%s': %s", text[:50], exc)
        return text  # Graceful fallback — always return something


@lru_cache(maxsize=1)
def _get_translate_client():
    """Lazy singleton for the Translation client."""
    from google.cloud import translate_v2 as translate
    return translate.Client()


async def translate_alert(message: str, language: str) -> str:
    """Convenience wrapper for translating alert messages."""
    return await translate_text(message, language)


async def translate_route_notes(notes: str | None, language: str) -> str | None:
    """Translate route notes if present."""
    if notes is None:
        return None
    return await translate_text(notes, language)
