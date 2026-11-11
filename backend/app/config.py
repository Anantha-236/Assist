import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DATABASE_PATH = Path(os.environ.get("ASSIST_DB", "./data/assist.db"))
ADMIN_PASSWORD = os.environ.get("ASSIST_ADMIN_PASSWORD", "change-me")
JWT_SECRET = os.environ.get("ASSIST_JWT_SECRET", "dev-secret-change-me")
# ---- session cookie ----
SESSION_SECRET = os.environ.get(
    "ASSIST_SESSION_SECRET", "dev-session-secret-change-me"
)

# ---- email / SMTP ----
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL", SMTP_USER)
SMTP_FROM_NAME = os.environ.get("SMTP_FROM_NAME", "Assist")

# ---- Groq ----
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_BASE_URL = os.environ.get(
    "GROQ_BASE_URL", "https://api.groq.com/openai/v1"
)
GROQ_MODEL_PRIMARY = os.environ.get(
    "GROQ_MODEL_PRIMARY", "llama-3.1-8b-instant"
)
GROQ_MODEL_FALLBACK = os.environ.get(
    "GROQ_MODEL_FALLBACK", "llama-3.3-70b-versatile"
)

# ---- provider preference ----
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq").lower()

# ---- admin emails (list) ----
ADMIN_EMAILS = [
    e.strip().lower()
    for e in os.environ.get("ADMIN_EMAILS", "").split(",")
    if e.strip()
]
JWT_EXPIRE_DAYS = int(os.environ.get("ASSIST_JWT_EXPIRE_DAYS", "30"))

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.environ.get(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
)
# ---- meeting app detection ----
MEETING_APPS = {
    "Zoom": ["zoom.exe", "zoom"],
    "Teams": ["teams.exe", "ms-teams.exe", "teams"],
    "Webex": ["webex.exe", "webexmta.exe", "webex"],
    "GoTo": ["goto.exe", "gotomeeting.exe", "gotomeeting"],
    "Slack Huddle": ["slack.exe"],
    "Discord": ["discord.exe"],
}
MEETING_POLL_SEC = 3.0
MEETING_SILENCE_END_SEC = 30.0


def _split_env(name: str) -> list[str]:
    return [m.strip() for m in os.environ.get(name, "").split(",") if m.strip()]


OPENROUTER_MODELS_FAST = _split_env("OPENROUTER_MODELS_FAST")
OPENROUTER_MODELS_CHEAP = _split_env("OPENROUTER_MODELS_CHEAP")
OPENROUTER_MODELS_CODE = _split_env("OPENROUTER_MODELS_CODE")

QUOTA_REFRESH_SEC = int(os.environ.get("QUOTA_REFRESH_SEC", "300"))
QUOTA_WARN_FRACTION = float(os.environ.get("QUOTA_WARN_FRACTION", "0.20"))
DAILY_QUESTION_LIMIT = int(os.environ.get("DAILY_QUESTION_LIMIT", "200"))