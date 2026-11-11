
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
        """)

        # ---- Migrate activation_keys columns ----

        cols = {r["name"] for r in c.execute(
            "PRAGMA table_info(activation_keys)"
        ).fetchall()}

        if "tier" not in cols:
            c.execute(
                "ALTER TABLE activation_keys ADD COLUMN tier TEXT DEFAULT 'free'"
            )

        if "daily_limit" not in cols:
            c.execute(
                "ALTER TABLE activation_keys ADD COLUMN daily_limit INTEGER DEFAULT 200"
            )

        # ---- Migrate transcript session_id ----

        tcols = {r["name"] for r in c.execute(
            "PRAGMA table_info(transcripts)"
        ).fetchall()}

        if "session_id" not in tcols:
            c.execute(
                "ALTER TABLE transcripts ADD COLUMN session_id TEXT"
            )
            c.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_transcripts_session "
                "ON transcripts(session_id)"
            )

        # ---- Migrate activation_keys email ----

        kcols = {r["name"] for r in c.execute(
            "PRAGMA table_info(activation_keys)"
        ).fetchall()}

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
            "SELECT * FROM activation_keys WHERE key_value = ?", (key_value,)
        ).fetchone()


def get_key_by_id(key_id):
    with _conn() as c:
        return c.execute(
            "SELECT * FROM activation_keys WHERE key_id = ?", (key_id,)
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
        return [dict(r) for r in c.execute(
            "SELECT * FROM activation_keys ORDER BY created_at DESC"
        ).fetchall()]


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
        return [dict(r) for r in c.execute(
            "SELECT day, count FROM usage WHERE key_id = ? "
            "ORDER BY day DESC LIMIT ?",
            (key_id, days),
        ).fetchall()]


def get_total_usage_for_key(key_id):
    with _conn() as c:
        row = c.execute(
            "SELECT COALESCE(SUM(count), 0) AS total FROM usage WHERE key_id = ?",
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
            " uploaded_at, segments_json, segment_count) "
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
            " session_started, session_ended, uploaded_at, segments_json, segment_count) "
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
            "       uploaded_at, segment_count "
            "FROM transcripts WHERE key_id = ? "
            "ORDER BY session_started DESC LIMIT ?",
            (key_id, limit),
        ).fetchall()

        return [dict(r) for r in rows]


def list_all_transcripts(limit=100):
    with _conn() as c:
        rows = c.execute(
            "SELECT transcript_id, key_id, session_started, "
            "       uploaded_at, segment_count "
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
