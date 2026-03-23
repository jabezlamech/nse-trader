"""
Kite Connect credential management.
Reads from .env file or environment variables.
Access token is persisted to kite_token.json so it survives restarts within a trading day.
"""

import os
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load .env from repo root (one level up from backend/)
load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

TOKEN_FILE = Path(__file__).parent / "kite_token.json"


def get_api_key() -> str:
    return os.getenv("KITE_API_KEY", "")


def get_api_secret() -> str:
    return os.getenv("KITE_API_SECRET", "")


def save_access_token(access_token: str) -> None:
    TOKEN_FILE.write_text(json.dumps({"access_token": access_token}))
    logger.info("Kite access token saved.")


def load_access_token() -> str:
    """Return access token from env var first, then from saved file."""
    # Environment variable takes priority
    env_token = os.getenv("KITE_ACCESS_TOKEN", "").strip()
    if env_token:
        return env_token

    if TOKEN_FILE.exists():
        try:
            data = json.loads(TOKEN_FILE.read_text())
            return data.get("access_token", "")
        except Exception:
            pass
    return ""


def is_configured() -> bool:
    """Return True if API key and secret are set."""
    return bool(get_api_key() and get_api_secret())


def is_authenticated() -> bool:
    """Return True if a valid-looking access token is available."""
    return bool(is_configured() and load_access_token())
