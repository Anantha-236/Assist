
"""SQLite storage: keys, usage, token usage, transcripts, settings, and admin OTPs."""

import json
import sqlite3
import hashlib
import secrets
import uuid as _uuid

from datetime import datetime, timedelta, timezone

from .config import DATABASE_PATH


def _conn():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DATABASE_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS activation_keys (
                key_id TEXT PRIMARY KEY,
                key_value TEXT UNIQUE NOT NULL,
                device_fingerprint TEXT,
                created_at TEXT NOT NULL,
                activated_at TEXT,
                revoked INTEGER DEFAULT 0,
                label TEXT,
                profile_json TEXT
            );

            CREATE TABLE IF NOT EXISTS usage (
                key_id TEXT NOT NULL,
                day TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (key_id, day)
            );

            CREATE TABLE IF NOT EXISTS transcripts (
                transcript_id TEXT PRIMARY KEY,
                key_id TEXT NOT NULL,
                session_started TEXT NOT NULL,
                session_ended TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                segments_json TEXT NOT NULL,
                segment_count INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_transcripts_key
                ON transcripts(key_id, session_started);

            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_id TEXT NOT NULL,
                day TEXT NOT NULL,
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_token_usage
                ON token_usage(key_id, day);

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admin_otps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                otp_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS admin_totp (
                email TEXT PRIMARY KEY,
                secret TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            -- Provider usage tracking

            CREATE TABLE IF NOT EXISTS provider_usage (
                key_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                model_id TEXT NOT NULL,
                day TEXT NOT NULL,
                requests INTEGER NOT NULL DEFAULT 0,
                tokens_in INTEGER NOT NULL DEFAULT 0,
                tokens_out INTEGER NOT NULL DEFAULT 0,
                suspended INTEGER DEFAULT 0,
                suspended_at TEXT,
                PRIMARY KEY (key_id, day)
            );

            CREATE INDEX IF NOT EXISTS idx_provider_usage_day
                ON provider_usage(day);
        """)

        # ---- Migrate activation_keys columns ----

        cols = {
            r["name"]
            for r in c.execute(
                "PRAGMA table_info(activation_keys)"
            ).fetchall()
        }

        if "tier" not in cols:
            c.execute(
                "ALTER TABLE activation_keys ADD COLUMN tier TEXT DEFAULT 'free'"
            )

        if "daily_limit" not in cols:
            c.execute(
                "ALTER TABLE activation_keys ADD COLUMN daily_limit INTEGER DEFAULT 200"
            )

        # ---- Migrate transcript session_id ----

        tcols = {
            r["name"]
            for r in c.execute(
                "PRAGMA table_info(transcripts)"
            ).fetchall()
        }

        if "session_id" not in tcols:
            c.execute(
                "ALTER TABLE transcripts ADD COLUMN session_id TEXT"
            )
            c.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_transcripts_session "
                "ON transcripts(session_id)"
            )

        # ---- Migrate activation_keys email ----

        kcols = {
            r["name"]
            for r in c.execute(
                "PRAGMA table_info(activation_keys)"
            ).fetchall()
        }

        if "email" not in kcols:
            c.execute(
                "ALTER TABLE activation_keys ADD COLUMN email TEXT"
            )


# ---- admin OTP ----

def create_admin_otp(email: str, ttl_minutes: int = 10) -> str:
    """Generate a 6-digit OTP, store its hash, return the plaintext code."""

    otp = str(secrets.randbelow(900_000) + 100_000)
    otp_hash = hashlib.sha256(otp.encode()).hexdigest()

    expires = (
        datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    ).isoformat()

    with _conn() as c:
        c.execute(
            "INSERT INTO admin_otps (email, otp_hash, expires_at) VALUES (?, ?, ?)",
            (email, otp_hash, expires),
        )

    return otp


def verify_admin_otp(email: str, otp: str) -> bool:
    """Verify and consume a one-time password."""

    otp_hash = hashlib.sha256(otp.encode()).hexdigest()
    now_iso = datetime.now(timezone.utc).isoformat()

    with _conn() as c:
        row = c.execute(
            "SELECT id FROM admin_otps WHERE email = ? AND otp_hash = ? "
            "AND used = 0 AND expires_at > ?",
            (email, otp_hash, now_iso),
        ).fetchone()

        if row:
            c.execute(
                "UPDATE admin_otps SET used = 1 WHERE id = ?",
                (row["id"],),
            )
            return True

    return False


# ---- admin TOTP ----

def get_totp_secret(email: str) -> str | None:
    """Retrieve the stored TOTP secret for an admin email."""

    with _conn() as c:
        row = c.execute(
            "SELECT secret FROM admin_totp WHERE email = ?",
            (email,),
        ).fetchone()

        return row["secret"] if row else None


def set_totp_secret(email: str, secret: str):
    """Create or update an admin's TOTP secret."""

    with _conn() as c:
        c.execute(
            "INSERT INTO admin_totp (email, secret, created_at) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(email) DO UPDATE SET secret = excluded.secret",
            (
                email,
                secret,
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def clear_totp_secret(email: str):
    """Delete an admin's stored TOTP secret."""

    with _conn() as c:
        c.execute(
            "DELETE FROM admin_totp WHERE email = ?",
            (email,),
        )


# ---- keys ----

def insert_key(key_id, key_value, label=None):
    with _conn() as c:
        c.execute(
            "INSERT INTO activation_keys (key_id, key_value, created_at, label) "
            "VALUES (?, ?, ?, ?)",
            (key_id, key_value, datetime.now(timezone.utc).isoformat(), label),
        )


def get_key_by_value(key_value):
    with _conn() as c:
        return c.execute(
            "SELECT * FROM activation_keys WHERE key_value = ?",
            (key_value,),
        ).fetchone()


def get_key_by_id(key_id):
    with _conn() as c:
        return c.execute(
            "SELECT * FROM activation_keys WHERE key_id = ?",
            (key_id,),
        ).fetchone()


def bind_key(key_id, fingerprint):
    with _conn() as c:
        c.execute(
            "UPDATE activation_keys SET device_fingerprint = ?, activated_at = ? "
            "WHERE key_id = ?",
            (fingerprint, datetime.now(timezone.utc).isoformat(), key_id),
        )


def revoke_key(key_id):
    with _conn() as c:
        c.execute(
            "UPDATE activation_keys SET revoked = 1 WHERE key_id = ?",
            (key_id,),
        )


def set_key_limit(key_id: str, tier: str, daily_limit: int):
    with _conn() as c:
        c.execute(
            "UPDATE activation_keys SET tier = ?, daily_limit = ? WHERE key_id = ?",
            (tier, daily_limit, key_id),
        )


def get_key_daily_limit(key_id: str, fallback: int) -> int:
    row = get_key_by_id(key_id)

    if row is None:
        return fallback

    try:
        return int(row["daily_limit"]) if row["daily_limit"] else fallback
    except (KeyError, TypeError, ValueError):
        return fallback


def set_profile(key_id, profile):
    with _conn() as c:
        c.execute(
            "UPDATE activation_keys SET profile_json = ? WHERE key_id = ?",
            (json.dumps(profile), key_id),
        )


def get_profile(key_id):
    row = get_key_by_id(key_id)

    if row is None or not row["profile_json"]:
        return None

    try:
        return json.loads(row["profile_json"])
    except Exception:
        return None


def list_keys():
    with _conn() as c:
        return [
            dict(r)
            for r in c.execute(
                "SELECT * FROM activation_keys ORDER BY created_at DESC"
            ).fetchall()
        ]


def count_keys():
    with _conn() as c:
        return c.execute(
            "SELECT COUNT(*) FROM activation_keys"
        ).fetchone()[0]


# ---- key email ----

def set_key_email(key_id, email):
    with _conn() as c:
        c.execute(
            "UPDATE activation_keys SET email = ? WHERE key_id = ?",
            (email, key_id),
        )


def get_key_email(key_id):
    row = get_key_by_id(key_id)
    return row["email"] if row and "email" in row.keys() else None


# ---- usage ----

def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_today_usage(key_id):
    with _conn() as c:
        row = c.execute(
            "SELECT count FROM usage WHERE key_id = ? AND day = ?",
            (key_id, _today()),
        ).fetchone()

        return row["count"] if row else 0


def try_increment_usage(key_id, limit):
    with _conn() as c:
        c.execute("BEGIN IMMEDIATE")

        row = c.execute(
            "SELECT count FROM usage WHERE key_id = ? AND day = ?",
            (key_id, _today()),
        ).fetchone()

        current = row["count"] if row else 0

        if current >= limit:
            return False

        c.execute(
            "INSERT INTO usage (key_id, day, count) VALUES (?, ?, 1) "
            "ON CONFLICT(key_id, day) DO UPDATE SET count = count + 1",
            (key_id, _today()),
        )

        return True


def get_today_usage_all():
    with _conn() as c:
        rows = c.execute(
            "SELECT key_id, count FROM usage WHERE day = ?",
            (_today(),),
        ).fetchall()

    total = sum(r["count"] for r in rows)

    return {
        "total": total,
        "by_key": {r["key_id"]: r["count"] for r in rows},
    }


def get_usage_history(key_id, days=30):
    with _conn() as c:
        return [
            dict(r)
            for r in c.execute(
                "SELECT day, count FROM usage WHERE key_id = ? "
                "ORDER BY day DESC LIMIT ?",
                (key_id, days),
            ).fetchall()
        ]


def get_total_usage_for_key(key_id):
    with _conn() as c:
        row = c.execute(
            "SELECT COALESCE(SUM(count), 0) AS total "
            "FROM usage WHERE key_id = ?",
            (key_id,),
        ).fetchone()

        return row["total"]


# ---- token usage ----

def record_token_usage(key_id, usage):
    with _conn() as c:
        c.execute(
            "INSERT INTO token_usage "
            "(key_id, day, prompt_tokens, completion_tokens) "
            "VALUES (?, ?, ?, ?)",
            (
                key_id,
                _today(),
                int(usage.get("prompt_tokens", 0) or 0),
                int(usage.get("completion_tokens", 0) or 0),
            ),
        )


def get_token_usage_today():
    with _conn() as c:
        row = c.execute(
            "SELECT COALESCE(SUM(prompt_tokens), 0) AS p, "
            "COALESCE(SUM(completion_tokens), 0) AS c "
            "FROM token_usage WHERE day = ?",
            (_today(),),
        ).fetchone()

        return {
            "prompt_tokens": row["p"],
            "completion_tokens": row["c"],
        }


def get_token_usage_for_key(key_id):
    with _conn() as c:
        row = c.execute(
            "SELECT COALESCE(SUM(prompt_tokens), 0) AS p, "
            "COALESCE(SUM(completion_tokens), 0) AS c "
            "FROM token_usage WHERE key_id = ?",
            (key_id,),
        ).fetchone()

        return {
            "prompt_tokens": row["p"],
            "completion_tokens": row["c"],
        }


# ---- transcripts ----

def insert_transcript(transcript_id, key_id, started, ended, segments):
    with _conn() as c:
        c.execute(
            "INSERT INTO transcripts "
            "(transcript_id, key_id, session_started, session_ended, "
            "uploaded_at, segments_json, segment_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                transcript_id,
                key_id,
                started,
                ended,
                datetime.now(timezone.utc).isoformat(),
                json.dumps(segments),
                len(segments),
            ),
        )


def upsert_transcript(session_id, key_id, started, ended, segments):
    """Create or replace a session by session_id (idempotent, retry-safe)."""

    with _conn() as c:
        existing = c.execute(
            "SELECT transcript_id FROM transcripts WHERE session_id = ?",
            (session_id,),
        ).fetchone()

        now = datetime.now(timezone.utc).isoformat()

        if existing:
            c.execute(
                "UPDATE transcripts SET session_ended=?, uploaded_at=?, "
                "segments_json=?, segment_count=? WHERE session_id=?",
                (
                    ended,
                    now,
                    json.dumps(segments),
                    len(segments),
                    session_id,
                ),
            )
            return existing["transcript_id"]

        tid = _uuid.uuid4().hex

        c.execute(
            "INSERT INTO transcripts (transcript_id, session_id, key_id, "
            "session_started, session_ended, uploaded_at, segments_json, "
            "segment_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tid,
                session_id,
                key_id,
                started,
                ended,
                now,
                json.dumps(segments),
                len(segments),
            ),
        )

        return tid


def get_transcript_by_session(session_id):
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM transcripts WHERE session_id = ?",
            (session_id,),
        ).fetchone()

        return dict(row) if row else None


def list_transcripts_for_key(key_id, limit=50):
    with _conn() as c:
        rows = c.execute(
            "SELECT transcript_id, session_started, session_ended, "
            "uploaded_at, segment_count "
            "FROM transcripts WHERE key_id = ? "
            "ORDER BY session_started DESC LIMIT ?",
            (key_id, limit),
        ).fetchall()

        return [dict(r) for r in rows]


def list_all_transcripts(limit=100):
    with _conn() as c:
        rows = c.execute(
            "SELECT transcript_id, key_id, session_started, "
            "uploaded_at, segment_count "
            "FROM transcripts ORDER BY session_started DESC LIMIT ?",
            (limit,),
        ).fetchall()

        return [dict(r) for r in rows]


def get_transcript(transcript_id):
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM transcripts WHERE transcript_id = ?",
            (transcript_id,),
        ).fetchone()

        if row is None:
            return None

        d = dict(row)
        d["segments"] = json.loads(d.pop("segments_json"))

        return d


# ---- settings ----

def get_setting(key, default=""):
    with _conn() as c:
        row = c.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        ).fetchone()

        return row["value"] if row else default


def set_setting(key, value):
    with _conn() as c:
        c.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )


def get_all_settings():
    with _conn() as c:
        return {
            r["key"]: r["value"]
            for r in c.execute(
                "SELECT key, value FROM settings"
            ).fetchall()
        }


# ---- provider usage tracking ----

def get_provider_usage(
    key_id: str,
    provider: str,
    day: str | None = None,
) -> dict | None:
    """Return the usage row for a specific key and provider."""

    d = day or _today()

    with _conn() as c:
        row = c.execute(
            "SELECT * FROM provider_usage "
            "WHERE key_id = ? AND provider = ? AND day = ?",
            (key_id, provider, d),
        ).fetchone()

        return dict(row) if row else None


def upsert_provider_usage(
    key_id: str,
    provider: str,
    model_id: str,
    add_requests: int = 1,
    add_tokens_in: int = 0,
    add_tokens_out: int = 0,
):
    """Increment provider usage counters for today."""

    d = _today()

    with _conn() as c:
        c.execute(
            "INSERT INTO provider_usage "
            "(key_id, provider, model_id, day, requests, tokens_in, tokens_out) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(key_id, day) DO UPDATE SET "
            "requests = requests + excluded.requests, "
            "tokens_in = tokens_in + excluded.tokens_in, "
            "tokens_out = tokens_out + excluded.tokens_out, "
            "provider = excluded.provider, "
            "model_id = excluded.model_id",
            (
                key_id,
                provider,
                model_id,
                d,
                add_requests,
                add_tokens_in,
                add_tokens_out,
            ),
        )


def suspend_key_for_today(key_id: str, provider: str):
    """Mark a provider key as suspended for today."""

    with _conn() as c:
        c.execute(
            "INSERT INTO provider_usage "
            "(key_id, provider, model_id, day, requests, tokens_in, tokens_out, "
            "suspended, suspended_at) "
            "VALUES (?, ?, '', ?, 0, 0, 0, 1, ?) "
            "ON CONFLICT(key_id, day) DO UPDATE SET "
            "suspended = 1, suspended_at = excluded.suspended_at",
            (
                key_id,
                provider,
                _today(),
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def is_key_suspended(
    key_id: str,
    provider: str,
    day: str | None = None,
) -> bool:
    """Check whether a provider key is suspended for the specified day."""

    row = get_provider_usage(key_id, provider, day)
    return bool(row and row.get("suspended"))


def reset_all_suspensions_for_today():
    """No action required: suspensions are scoped to individual days."""
    pass


def provider_usage_summary(day: str | None = None) -> list[dict]:
    """Return provider usage rows for the admin dashboard."""

    d = day or _today()

    with _conn() as c:
        rows = c.execute(
            "SELECT u.key_id, u.provider, u.model_id, u.requests, "
            "u.tokens_in, u.tokens_out, u.suspended, u.suspended_at, "
            "k.key_value, k.label, k.email "
            "FROM provider_usage u "
            "LEFT JOIN activation_keys k ON k.key_id = u.key_id "
            "WHERE u.day = ? "
            "ORDER BY u.provider, u.requests DESC",
            (d,),
        ).fetchall()

        return [dict(r) for r in rows]
