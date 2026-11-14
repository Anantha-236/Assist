"""SQLite storage for the Assist backend."""

import hashlib
import json
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from .config import DATABASE_PATH
from .features import merge_with_defaults


def _conn():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DATABASE_PATH)
    c.row_factory = sqlite3.Row
    return c


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


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
                profile_json TEXT,
                tier TEXT DEFAULT 'free',
                daily_limit INTEGER DEFAULT 200,
                email TEXT,
                role TEXT, experience TEXT, skills TEXT,
                company TEXT, target_role TEXT, target_company TEXT,
                industry TEXT, achievements TEXT, projects TEXT,
                target_salary TEXT, notice_period TEXT, answer_style TEXT,
                features_json TEXT,
                telegram_chat_id TEXT
            );
            CREATE TABLE IF NOT EXISTS usage (
                key_id TEXT NOT NULL,
                day TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (key_id, day)
            );
            CREATE TABLE IF NOT EXISTS transcripts (
                transcript_id TEXT PRIMARY KEY,
                session_id TEXT,
                key_id TEXT NOT NULL,
                session_started TEXT NOT NULL,
                session_ended TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                segments_json TEXT NOT NULL,
                segment_count INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_transcripts_key
                ON transcripts(key_id, session_started);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_transcripts_session
                ON transcripts(session_id);
            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_id TEXT NOT NULL,
                day TEXT NOT NULL,
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                api_key_id TEXT, provider TEXT, model TEXT
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
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                key_value TEXT NOT NULL,
                label TEXT,
                priority INTEGER DEFAULT 100,
                active INTEGER DEFAULT 1,
                failure_count INTEGER DEFAULT 0,
                last_used_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_api_keys_provider
                ON api_keys(provider, active, priority);
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
                remaining_requests INTEGER,
                remaining_tokens INTEGER,
                limit_requests INTEGER,
                limit_tokens INTEGER,
                reset_at TEXT,
                PRIMARY KEY (key_id, day)
            );
            CREATE INDEX IF NOT EXISTS idx_provider_usage_day
                ON provider_usage(day);
            CREATE TABLE IF NOT EXISTS interview_answers (
                id TEXT PRIMARY KEY,
                key_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                question_ts REAL NOT NULL,
                answer_ts REAL NOT NULL,
                metrics_json TEXT NOT NULL,
                review_json TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_answers_key
                ON interview_answers(key_id, created_at DESC);
            CREATE TABLE IF NOT EXISTS invites (
                token TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used INTEGER DEFAULT 0,
                chat_id TEXT
            );
        """)

        # migration: activation_keys
        cols = {r["name"] for r in c.execute("PRAGMA table_info(activation_keys)")}
        for col, typ, default in [
            ("tier", "TEXT", "'free'"),
            ("daily_limit", "INTEGER", "200"),
            ("email", "TEXT", "NULL"),
            ("role", "TEXT", "NULL"),
            ("experience", "TEXT", "NULL"),
            ("skills", "TEXT", "NULL"),
            ("company", "TEXT", "NULL"),
            ("target_role", "TEXT", "NULL"),
            ("target_company", "TEXT", "NULL"),
            ("industry", "TEXT", "NULL"),
            ("achievements", "TEXT", "NULL"),
            ("projects", "TEXT", "NULL"),
            ("target_salary", "TEXT", "NULL"),
            ("notice_period", "TEXT", "NULL"),
            ("answer_style", "TEXT", "NULL"),
            ("features_json", "TEXT", "NULL"),
            ("telegram_chat_id", "TEXT", "NULL"),
        ]:
            if col not in cols:
                c.execute(f"ALTER TABLE activation_keys ADD COLUMN {col} {typ} DEFAULT {default}")

        # migration: token_usage
        tcols = {r["name"] for r in c.execute("PRAGMA table_info(token_usage)")}
        for col, typ in [("api_key_id", "TEXT"), ("provider", "TEXT"), ("model", "TEXT")]:
            if col not in tcols:
                c.execute(f"ALTER TABLE token_usage ADD COLUMN {col} {typ}")

        # migration: transcripts
        trcols = {r["name"] for r in c.execute("PRAGMA table_info(transcripts)")}
        if "session_id" not in trcols:
            c.execute("ALTER TABLE transcripts ADD COLUMN session_id TEXT")
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_transcripts_session ON transcripts(session_id)")

        # migration: provider_usage
        pcols = {r["name"] for r in c.execute("PRAGMA table_info(provider_usage)")}
        for col, typ in [
            ("remaining_requests", "INTEGER"), ("remaining_tokens", "INTEGER"),
            ("limit_requests", "INTEGER"), ("limit_tokens", "INTEGER"), ("reset_at", "TEXT"),
        ]:
            if col not in pcols:
                c.execute(f"ALTER TABLE provider_usage ADD COLUMN {col} {typ}")

        _init_support_tables(c)


# ===== activation keys =====
def insert_key(key_id, key_value, label=None):
    with _conn() as c:
        c.execute(
            "INSERT INTO activation_keys (key_id, key_value, created_at, label) "
            "VALUES (?, ?, ?, ?)",
            (key_id, key_value, datetime.now(timezone.utc).isoformat(), label),
        )


def get_key_by_value(key_value):
    with _conn() as c:
        return c.execute("SELECT * FROM activation_keys WHERE key_value = ?",
                         (key_value,)).fetchone()


def get_key_by_id(key_id):
    with _conn() as c:
        return c.execute("SELECT * FROM activation_keys WHERE key_id = ?",
                         (key_id,)).fetchone()


def bind_key(key_id, fingerprint):
    with _conn() as c:
        c.execute(
            "UPDATE activation_keys SET device_fingerprint = ?, activated_at = ? "
            "WHERE key_id = ?",
            (fingerprint, datetime.now(timezone.utc).isoformat(), key_id))


def revoke_key(key_id):
    with _conn() as c:
        c.execute("UPDATE activation_keys SET revoked = 1 WHERE key_id = ?", (key_id,))


def set_profile(key_id, profile):
    with _conn() as c:
        c.execute("UPDATE activation_keys SET profile_json = ? WHERE key_id = ?",
                  (json.dumps(profile), key_id))


def get_profile(key_id):
    row = get_key_by_id(key_id)
    if row is None or not row["profile_json"]:
        return None
    try:
        return json.loads(row["profile_json"])
    except Exception:
        return None


def get_full_profile(key_id):
    row = get_key_by_id(key_id)
    if row is None:
        return None
    r = dict(row)
    profile = {}
    if r.get("profile_json"):
        try:
            profile = json.loads(r["profile_json"])
        except Exception:
            profile = {}
    for f in ("role", "experience", "skills", "company", "target_role",
              "target_company", "industry", "achievements", "projects",
              "target_salary", "notice_period", "answer_style", "email"):
        val = r.get(f)
        if val:
            profile[f] = val
    return profile or None


def set_key_limit(key_id, tier, daily_limit):
    with _conn() as c:
        c.execute("UPDATE activation_keys SET tier = ?, daily_limit = ? WHERE key_id = ?",
                  (tier, daily_limit, key_id))


def get_key_daily_limit(key_id, fallback):
    row = get_key_by_id(key_id)
    if row is None:
        return fallback
    try:
        return int(row["daily_limit"]) if row["daily_limit"] else fallback
    except (KeyError, TypeError, ValueError):
        return fallback


def set_key_email(key_id, email):
    with _conn() as c:
        c.execute("UPDATE activation_keys SET email = ? WHERE key_id = ?", (email, key_id))


def get_key_email(key_id):
    row = get_key_by_id(key_id)
    return row["email"] if row and "email" in row.keys() else None


def set_key_telegram_chat_id(key_id, chat_id):
    with _conn() as c:
        c.execute("UPDATE activation_keys SET telegram_chat_id = ? WHERE key_id = ?",
                  (str(chat_id), key_id))


def get_key_telegram_chat_id(key_id):
    row = get_key_by_id(key_id)
    return row["telegram_chat_id"] if row and "telegram_chat_id" in row.keys() else None


def get_key_by_telegram_chat_id(chat_id):
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM activation_keys WHERE telegram_chat_id = ? "
            "ORDER BY created_at DESC LIMIT 1", (str(chat_id),)).fetchone()
        return dict(row) if row else None


def find_chat_id_by_email(email):
    """Look up Telegram chat_id for any key with this email."""
    with _conn() as c:
        row = c.execute(
            "SELECT telegram_chat_id FROM activation_keys "
            "WHERE email = ? AND telegram_chat_id IS NOT NULL "
            "ORDER BY created_at DESC LIMIT 1",
            (email.strip().lower(),)).fetchone()
        return row["telegram_chat_id"] if row else None


def list_keys():
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM activation_keys ORDER BY created_at DESC").fetchall()]


def count_keys():
    with _conn() as c:
        return c.execute("SELECT COUNT(*) FROM activation_keys").fetchone()[0]


# ===== invites (Telegram onboarding) =====
def create_invite_row(token, email, ttl_hours=72):
    with _conn() as c:
        c.execute(
            "INSERT INTO invites (token, email, created_at, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (token, email, datetime.now(timezone.utc).isoformat(),
             (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat()))


def get_invite_row(token):
    with _conn() as c:
        row = c.execute("SELECT * FROM invites WHERE token = ?", (token,)).fetchone()
        return dict(row) if row else None


def update_invite_chat_id(token, chat_id):
    with _conn() as c:
        c.execute("UPDATE invites SET chat_id = ? WHERE token = ?", (str(chat_id), token))


def mark_invite_used(token):
    with _conn() as c:
        c.execute("UPDATE invites SET used = 1 WHERE token = ?", (token,))


# ===== features =====
def get_features(key_id):
    row = get_key_by_id(key_id)
    if row is None:
        return merge_with_defaults(None)
    raw = row["features_json"] if "features_json" in row.keys() else None
    if not raw:
        return merge_with_defaults(None)
    try:
        return merge_with_defaults(json.loads(raw))
    except Exception:
        return merge_with_defaults(None)


def set_features(key_id, features):
    from .features import DEFAULT_FEATURES
    clean = {k: bool(features.get(k, v)) for k, v in DEFAULT_FEATURES.items()}
    with _conn() as c:
        c.execute("UPDATE activation_keys SET features_json = ? WHERE key_id = ?",
                  (json.dumps(clean), key_id))


# ===== usage / quota =====
def get_today_usage(key_id):
    with _conn() as c:
        row = c.execute("SELECT count FROM usage WHERE key_id = ? AND day = ?",
                        (key_id, _today())).fetchone()
        return row["count"] if row else 0


def try_increment_usage(key_id, limit):
    with _conn() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT count FROM usage WHERE key_id = ? AND day = ?",
                        (key_id, _today())).fetchone()
        current = row["count"] if row else 0
        if current >= limit:
            return False
        c.execute(
            "INSERT INTO usage (key_id, day, count) VALUES (?, ?, 1) "
            "ON CONFLICT(key_id, day) DO UPDATE SET count = count + 1",
            (key_id, _today()))
        return True


def get_today_usage_all():
    with _conn() as c:
        rows = c.execute("SELECT key_id, count FROM usage WHERE day = ?",
                         (_today(),)).fetchall()
    return {"total": sum(r["count"] for r in rows),
            "by_key": {r["key_id"]: r["count"] for r in rows}}


def get_usage_history(key_id, days=30):
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT day, count FROM usage WHERE key_id = ? ORDER BY day DESC LIMIT ?",
            (key_id, days)).fetchall()]


def get_total_usage_for_key(key_id):
    with _conn() as c:
        row = c.execute("SELECT COALESCE(SUM(count), 0) AS total FROM usage WHERE key_id = ?",
                        (key_id,)).fetchone()
        return row["total"]


# ===== token usage =====
def record_token_usage(key_id, usage):
    with _conn() as c:
        c.execute(
            "INSERT INTO token_usage (key_id, day, prompt_tokens, completion_tokens) "
            "VALUES (?, ?, ?, ?)",
            (key_id, _today(),
             int(usage.get("prompt_tokens", 0) or 0),
             int(usage.get("completion_tokens", 0) or 0)))


def record_token_usage_full(key_id, prompt_tokens, completion_tokens,
                            api_key_id=None, provider=None, model=None):
    with _conn() as c:
        c.execute(
            "INSERT INTO token_usage "
            "(key_id, day, prompt_tokens, completion_tokens, api_key_id, provider, model) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (key_id, _today(), prompt_tokens, completion_tokens, api_key_id, provider, model))


def get_token_usage_today():
    with _conn() as c:
        row = c.execute(
            "SELECT COALESCE(SUM(prompt_tokens),0) AS p, "
            "COALESCE(SUM(completion_tokens),0) AS c "
            "FROM token_usage WHERE day = ?", (_today(),)).fetchone()
        return {"prompt_tokens": row["p"], "completion_tokens": row["c"]}


def get_token_usage_for_key(key_id):
    with _conn() as c:
        row = c.execute(
            "SELECT COALESCE(SUM(prompt_tokens),0) AS p, "
            "COALESCE(SUM(completion_tokens),0) AS c "
            "FROM token_usage WHERE key_id = ?", (key_id,)).fetchone()
        return {"prompt_tokens": row["p"], "completion_tokens": row["c"]}


def user_usage_summary(days=30):
    with _conn() as c:
        rows = c.execute(
            "SELECT u.key_id, SUM(u.prompt_tokens) AS prompt_tokens, "
            "SUM(u.completion_tokens) AS completion_tokens, COUNT(*) AS requests "
            "FROM token_usage u WHERE u.day >= date('now', ?) GROUP BY u.key_id",
            (f"-{days} days",)).fetchall()
        result = []
        for r in rows:
            key_row = get_key_by_id(r["key_id"])
            provider_split = c.execute(
                "SELECT provider, SUM(prompt_tokens) AS p, "
                "SUM(completion_tokens) AS c, COUNT(*) AS n "
                "FROM token_usage WHERE key_id = ? AND day >= date('now', ?) "
                "GROUP BY provider",
                (r["key_id"], f"-{days} days")).fetchall()
            result.append({
                "key_id": r["key_id"],
                "key_value": key_row["key_value"] if key_row else "?",
                "label": key_row["label"] if key_row else None,
                "email": key_row["email"] if key_row and "email" in key_row.keys() else None,
                "prompt_tokens": r["prompt_tokens"],
                "completion_tokens": r["completion_tokens"],
                "requests": r["requests"],
                "providers": {p["provider"]: {"prompt": p["p"], "completion": p["c"],
                                              "requests": p["n"]} for p in provider_split},
            })
        return result


def api_key_usage_summary(days=30):
    with _conn() as c:
        rows = c.execute(
            "SELECT api_key_id, provider, SUM(prompt_tokens) AS p, "
            "SUM(completion_tokens) AS c, COUNT(*) AS n "
            "FROM token_usage WHERE api_key_id IS NOT NULL AND day >= date('now', ?) "
            "GROUP BY api_key_id, provider", (f"-{days} days",)).fetchall()
        return [dict(r) for r in rows]


def get_pricing():
    defaults = {"groq_input_per_mtok": "0.05", "groq_output_per_mtok": "0.08",
                "openrouter_input_per_mtok": "0.10", "openrouter_output_per_mtok": "0.20"}
    return {k: float(get_setting(k, d)) for k, d in defaults.items()}


def set_pricing(provider, input_per_mtok, output_per_mtok):
    set_setting(f"{provider}_input_per_mtok", str(input_per_mtok))
    set_setting(f"{provider}_output_per_mtok", str(output_per_mtok))


# ===== transcripts =====
def insert_transcript(transcript_id, key_id, started, ended, segments):
    with _conn() as c:
        c.execute(
            "INSERT INTO transcripts (transcript_id, key_id, session_started, "
            "session_ended, uploaded_at, segments_json, segment_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (transcript_id, key_id, started, ended,
             datetime.now(timezone.utc).isoformat(),
             json.dumps(segments), len(segments)))


def upsert_transcript(session_id, key_id, started, ended, segments):
    with _conn() as c:
        existing = c.execute("SELECT transcript_id FROM transcripts WHERE session_id = ?",
                             (session_id,)).fetchone()
        now = datetime.now(timezone.utc).isoformat()
        if existing:
            c.execute(
                "UPDATE transcripts SET session_ended=?, uploaded_at=?, "
                "segments_json=?, segment_count=? WHERE session_id=?",
                (ended, now, json.dumps(segments), len(segments), session_id))
            return existing["transcript_id"]
        tid = uuid.uuid4().hex
        c.execute(
            "INSERT INTO transcripts (transcript_id, session_id, key_id, "
            "session_started, session_ended, uploaded_at, segments_json, segment_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (tid, session_id, key_id, started, ended, now,
             json.dumps(segments), len(segments)))
        return tid


def get_transcript_by_session(session_id):
    with _conn() as c:
        row = c.execute("SELECT * FROM transcripts WHERE session_id = ?",
                        (session_id,)).fetchone()
        return dict(row) if row else None


def list_transcripts_for_key(key_id, limit=50):
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT transcript_id, session_started, session_ended, "
            "uploaded_at, segment_count FROM transcripts WHERE key_id = ? "
            "ORDER BY session_started DESC LIMIT ?", (key_id, limit)).fetchall()]


def list_all_transcripts(limit=100):
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT transcript_id, key_id, session_started, uploaded_at, "
            "segment_count FROM transcripts ORDER BY session_started DESC LIMIT ?",
            (limit,)).fetchall()]


def get_transcript(transcript_id):
    with _conn() as c:
        row = c.execute("SELECT * FROM transcripts WHERE transcript_id = ?",
                        (transcript_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["segments"] = json.loads(d.pop("segments_json"))
        return d


# ===== settings =====
def get_setting(key, default=""):
    with _conn() as c:
        row = c.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key, value):
    with _conn() as c:
        c.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))


def get_all_settings():
    with _conn() as c:
        return {r["key"]: r["value"] for r in c.execute("SELECT key, value FROM settings")}


# ===== admin OTP (legacy) =====
def create_admin_otp(email, ttl_minutes=10):
    otp = str(secrets.randbelow(900_000) + 100_000)
    h = hashlib.sha256(otp.encode()).hexdigest()
    expires = (datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)).isoformat()
    with _conn() as c:
        c.execute("INSERT INTO admin_otps (email, otp_hash, expires_at) VALUES (?, ?, ?)",
                  (email, h, expires))
    return otp


def verify_admin_otp(email, otp):
    h = hashlib.sha256(otp.encode()).hexdigest()
    now_iso = datetime.now(timezone.utc).isoformat()
    with _conn() as c:
        row = c.execute(
            "SELECT id FROM admin_otps WHERE email = ? AND otp_hash = ? "
            "AND used = 0 AND expires_at > ?", (email, h, now_iso)).fetchone()
        if row:
            c.execute("UPDATE admin_otps SET used = 1 WHERE id = ?", (row["id"],))
            return True
    return False


# ===== TOTP =====
def get_totp_secret(email):
    with _conn() as c:
        row = c.execute("SELECT secret FROM admin_totp WHERE email = ?", (email,)).fetchone()
        return row["secret"] if row else None


def set_totp_secret(email, secret):
    with _conn() as c:
        c.execute(
            "INSERT INTO admin_totp (email, secret, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(email) DO UPDATE SET secret = excluded.secret",
            (email, secret, datetime.now(timezone.utc).isoformat()))


def clear_totp_secret(email):
    with _conn() as c:
        c.execute("DELETE FROM admin_totp WHERE email = ?", (email,))


# ===== API keys =====
def create_api_key(provider, key_value, label, priority=100):
    key_id = uuid.uuid4().hex[:12]
    with _conn() as c:
        c.execute(
            "INSERT INTO api_keys (id, provider, key_value, label, priority, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (key_id, provider, key_value, label, priority,
             datetime.now(timezone.utc).isoformat()))
    return key_id


def list_api_keys(provider=None):
    with _conn() as c:
        if provider:
            rows = c.execute(
                "SELECT * FROM api_keys WHERE provider = ? "
                "ORDER BY priority ASC, created_at ASC", (provider,)).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM api_keys ORDER BY provider, priority ASC").fetchall()
        return [dict(r) for r in rows]


def get_api_key(key_id):
    with _conn() as c:
        row = c.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,)).fetchone()
        return dict(row) if row else None


def set_api_key_active(key_id, active):
    with _conn() as c:
        c.execute("UPDATE api_keys SET active = ? WHERE id = ?",
                  (1 if active else 0, key_id))


def delete_api_key(key_id):
    with _conn() as c:
        c.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))


def set_api_key_priority(key_id, priority):
    with _conn() as c:
        c.execute("UPDATE api_keys SET priority = ? WHERE id = ?", (priority, key_id))


def get_active_keys(provider):
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM api_keys WHERE provider = ? AND active = 1 "
            "ORDER BY priority ASC, failure_count ASC, created_at ASC",
            (provider,)).fetchall()]


def mark_key_success(key_id):
    with _conn() as c:
        c.execute("UPDATE api_keys SET last_used_at = ?, failure_count = 0 WHERE id = ?",
                  (datetime.now(timezone.utc).isoformat(), key_id))


def mark_key_failure(key_id):
    with _conn() as c:
        c.execute("UPDATE api_keys SET failure_count = failure_count + 1 WHERE id = ?",
                  (key_id,))


# ===== provider usage =====
def get_provider_usage(key_id, provider, day=None):
    d = day or _today()
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM provider_usage WHERE key_id = ? AND day = ?",
            (key_id, d)).fetchone()
        return dict(row) if row else None


def upsert_provider_usage(key_id, provider, model_id,
                          add_requests=1, add_tokens_in=0, add_tokens_out=0):
    d = _today()
    with _conn() as c:
        c.execute(
            "INSERT INTO provider_usage (key_id, provider, model_id, day, "
            "requests, tokens_in, tokens_out) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(key_id, day) DO UPDATE SET "
            "requests = requests + excluded.requests, "
            "tokens_in = tokens_in + excluded.tokens_in, "
            "tokens_out = tokens_out + excluded.tokens_out",
            (key_id, provider, model_id, d, add_requests, add_tokens_in, add_tokens_out))


def update_live_quota(key_id, provider, headers):
    if not key_id:
        return
    try:
        rem_req = int(headers.get("x-ratelimit-remaining-requests", 0))
        rem_tok = int(headers.get("x-ratelimit-remaining-tokens", 0))
        lim_req = int(headers.get("x-ratelimit-limit-requests", 0))
        lim_tok = int(headers.get("x-ratelimit-limit-tokens", 0))
        reset = headers.get("x-ratelimit-reset-requests", "")
    except (ValueError, TypeError):
        return
    with _conn() as c:
        c.execute(
            "INSERT INTO provider_usage (key_id, provider, model_id, day, "
            "requests, tokens_in, tokens_out, remaining_requests, "
            "remaining_tokens, limit_requests, limit_tokens, reset_at) "
            "VALUES (?, ?, '', ?, 0, 0, 0, ?, ?, ?, ?, ?) "
            "ON CONFLICT(key_id, day) DO UPDATE SET "
            "remaining_requests = excluded.remaining_requests, "
            "remaining_tokens = excluded.remaining_tokens, "
            "limit_requests = excluded.limit_requests, "
            "limit_tokens = excluded.limit_tokens, "
            "reset_at = excluded.reset_at",
            (key_id, provider, _today(), rem_req, rem_tok, lim_req, lim_tok, reset))


def suspend_key_for_today(key_id, provider):
    with _conn() as c:
        c.execute(
            "INSERT INTO provider_usage (key_id, provider, model_id, day, "
            "requests, tokens_in, tokens_out, suspended, suspended_at) "
            "VALUES (?, ?, '', ?, 0, 0, 0, 1, ?) "
            "ON CONFLICT(key_id, day) DO UPDATE SET "
            "suspended = 1, suspended_at = excluded.suspended_at",
            (key_id, provider, _today(),
             datetime.now(timezone.utc).isoformat()))


def is_key_suspended(key_id, provider, day=None):
    row = get_provider_usage(key_id, provider, day)
    return bool(row and row.get("suspended"))


def provider_usage_summary(day=None):
    d = day or _today()
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT u.key_id, u.provider, u.model_id, u.requests, "
            "u.tokens_in, u.tokens_out, u.suspended, u.suspended_at, "
            "u.remaining_requests, u.remaining_tokens, u.limit_requests, "
            "u.limit_tokens, u.reset_at, k.key_value, k.label, k.email "
            "FROM provider_usage u LEFT JOIN activation_keys k ON k.key_id = u.key_id "
            "WHERE u.day = ? ORDER BY u.provider, u.requests DESC", (d,)).fetchall()]


# ===== interview answers =====
def insert_answer(key_id, session_id, question, answer,
                  question_ts, answer_ts, metrics):
    ans_id = uuid.uuid4().hex[:12]
    with _conn() as c:
        c.execute(
            "INSERT INTO interview_answers (id, key_id, session_id, question, "
            "answer, question_ts, answer_ts, metrics_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ans_id, key_id, session_id, question, answer, question_ts,
             answer_ts, json.dumps(metrics), datetime.now(timezone.utc).isoformat()))
    return ans_id


def get_answer(ans_id):
    with _conn() as c:
        row = c.execute("SELECT * FROM interview_answers WHERE id = ?", (ans_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["metrics"] = json.loads(d.pop("metrics_json"))
        if d.get("review_json"):
            d["review"] = json.loads(d["review_json"])
        return d


def list_answers_for_key(key_id, limit=50):
    with _conn() as c:
        rows = c.execute(
            "SELECT id, session_id, question, answer, metrics_json, "
            "review_json, created_at FROM interview_answers "
            "WHERE key_id = ? ORDER BY created_at DESC LIMIT ?",
            (key_id, limit)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["metrics"] = json.loads(d.pop("metrics_json"))
        d["review"] = json.loads(d.pop("review_json")) if d.get("review_json") else None
        out.append(d)
    return out


def save_answer_review(ans_id, review):
    with _conn() as c:
        c.execute("UPDATE interview_answers SET review_json = ? WHERE id = ?",
                  (json.dumps(review), ans_id))


# ===== support messaging =====
def _init_support_tables(connection=None):
    """Create the append-only support tables on first run."""
    if connection is None:
        with _conn() as c:
            _init_support_tables(c)
        return
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS admin_chats (
            chat_id TEXT PRIMARY KEY,
            admin_email TEXT,
            registered_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS support_messages (
            id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL,
            from_chat_id TEXT NOT NULL,
            from_key_id TEXT,
            to_chat_id TEXT NOT NULL,
            direction TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            read_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_support_thread
            ON support_messages(thread_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_support_unread
            ON support_messages(to_chat_id, read_at);
    """)


def register_admin_chat(chat_id: str, admin_email: str):
    with _conn() as c:
        c.execute(
            "INSERT INTO admin_chats (chat_id, admin_email, registered_at) "
            "VALUES (?, ?, ?) ON CONFLICT(chat_id) DO UPDATE SET "
            "admin_email = excluded.admin_email",
            (str(chat_id), admin_email, datetime.now(timezone.utc).isoformat()))


def is_admin_chat(chat_id: str) -> bool:
    with _conn() as c:
        row = c.execute("SELECT 1 FROM admin_chats WHERE chat_id = ?",
                        (str(chat_id),)).fetchone()
        return row is not None


def list_admin_chats() -> list[dict]:
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM admin_chats ORDER BY registered_at DESC").fetchall()]


def get_or_create_thread(from_chat_id: str) -> str:
    return str(from_chat_id)


def insert_support_message(
    thread_id: str, from_chat_id: str, to_chat_id: str,
    direction: str, text: str, from_key_id: str | None = None,
) -> str:
    msg_id = uuid.uuid4().hex[:12]
    with _conn() as c:
        c.execute(
            "INSERT INTO support_messages "
            "(id, thread_id, from_chat_id, from_key_id, to_chat_id, "
            "direction, text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (msg_id, thread_id, str(from_chat_id), from_key_id, str(to_chat_id),
             direction, text, datetime.now(timezone.utc).isoformat()))
    return msg_id


def list_thread_messages(thread_id: str, limit: int = 100) -> list[dict]:
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM support_messages WHERE thread_id = ? "
            "ORDER BY created_at ASC LIMIT ?", (thread_id, limit)).fetchall()]


def list_support_threads() -> list[dict]:
    with _conn() as c:
        rows = c.execute("""
            SELECT s.thread_id, MAX(s.created_at) AS last_at,
                (SELECT text FROM support_messages s2
                 WHERE s2.thread_id = s.thread_id
                 ORDER BY s2.created_at DESC LIMIT 1) AS last_text,
                (SELECT COUNT(*) FROM support_messages s3
                 WHERE s3.thread_id = s.thread_id
                   AND s3.direction = 'user_to_admin'
                   AND s3.read_at IS NULL) AS unread,
                (SELECT from_chat_id FROM support_messages s4
                 WHERE s4.thread_id = s.thread_id LIMIT 1) AS user_chat_id
            FROM support_messages s GROUP BY s.thread_id ORDER BY last_at DESC
        """).fetchall()
        return [dict(r) for r in rows]


def mark_thread_read(thread_id: str, admin_chat_id: str):
    with _conn() as c:
        c.execute(
            "UPDATE support_messages SET read_at = ? WHERE thread_id = ? "
            "AND read_at IS NULL AND (to_chat_id = ? OR "
            "(? = 'web' AND direction = 'user_to_admin'))",
            (datetime.now(timezone.utc).isoformat(), thread_id,
             str(admin_chat_id), str(admin_chat_id)))


def list_all_user_chat_ids() -> list[str]:
    with _conn() as c:
        rows = c.execute(
            "SELECT DISTINCT telegram_chat_id FROM activation_keys "
            "WHERE telegram_chat_id IS NOT NULL AND revoked = 0").fetchall()
        return [r["telegram_chat_id"] for r in rows]


def get_key_label_by_chat_id(chat_id: str) -> str | None:
    with _conn() as c:
        row = c.execute(
            "SELECT label FROM activation_keys WHERE telegram_chat_id = ? "
            "ORDER BY created_at DESC LIMIT 1", (str(chat_id),)).fetchone()
        return row["label"] if row else None