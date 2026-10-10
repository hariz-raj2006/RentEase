"""Application settings. Values come from environment variables (.env file)."""
import os
import secrets
from datetime import timedelta

from dotenv import load_dotenv

# Reads the .env file (if present) and loads its values into os.environ
load_dotenv()


class Config:
    # Signs the session cookie. If you forget to set one, a random key is used
    # (safe, but everyone gets logged out whenever the server restarts).
    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)

    # Database settings
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    DB_NAME = os.getenv("DB_NAME", "rentease")

    # Debug mode shows detailed errors. Local development only!
    DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"

    # Session cookie safety
    SESSION_COOKIE_HTTPONLY = True          # JavaScript cannot read the cookie
    SESSION_COOKIE_SAMESITE = "Lax"         # helps against cross-site attacks
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "0") == "1"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    # CSRF tokens stay valid as long as the session lasts
    WTF_CSRF_TIME_LIMIT = None

    # Reject request bodies bigger than 1 MB
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024