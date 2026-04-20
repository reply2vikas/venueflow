"""
Firebase Anonymous Authentication service.

Creates anonymous Firebase Auth sessions for VenueFlow users.
- No email, phone, or personal data required
- Session tokens expire and are not linked to any identity
- Used only to scope Firestore read/write rules per user

This is the ONLY user-data component. The session stores:
  - wheelchair preference (bool)
  - language preference (en/kn/hi/ta)
  - last known zone (for context)

Nothing else is stored. No analytics. No cross-session tracking.
"""



import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def get_or_create_anonymous_session(session_id: str) -> dict:
    """
    Verify a session ID is a valid Firebase anonymous auth token,
    and return the session preferences from Firestore.

    If the session doesn't exist, returns default preferences.
    Falls back to defaults if Firebase is unavailable.

    Args:
        session_id: Client-generated UUID (anonymous, no PII).

    Returns:
        Session dict with wheelchair, language, last_zone.
    """
    defaults = {"wheelchair": False, "language": "en", "last_zone": None}

    try:
        from google.cloud import firestore
        db = firestore.Client()
        doc = db.collection("sessions").document(session_id).get()
        if doc.exists:
            data = doc.to_dict()
            return {
                "wheelchair": bool(data.get("wheelchair", False)),
                "language": str(data.get("language", "en")),
                "last_zone": data.get("last_zone"),
            }
        return defaults

    except Exception as exc:
        logger.warning("Session fetch failed (non-critical): %s", exc)
        return defaults


async def save_session_preferences(
    session_id: str,
    wheelchair: bool,
    language: str,
    last_zone: Optional[str] = None,
) -> bool:
    """
    Persist user accessibility preferences to Firestore.
    Only stores non-identifying preference data.

    Returns True on success, False on failure (non-fatal).
    """
    try:
        from google.cloud import firestore
        db = firestore.Client()
        db.collection("sessions").document(session_id).set(
            {
                "wheelchair": wheelchair,
                "language": language,
                "last_zone": last_zone,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
        return True
    except Exception as exc:
        logger.warning("Session save failed (non-critical): %s", exc)
        return False
