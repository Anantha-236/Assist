"""Fast 98% test: hit the boundary condition exactly."""

import uuid

from app import db
from app.usage_tracker import check_and_track

key_id = "test-key-" + uuid.uuid4().hex[:8]
print(f"test key: {key_id}")

# ---- Phase 1: verify calls below threshold still work ----
db.upsert_provider_usage(
    key_id, "groq", "llama-3.1-8b-instant",
    add_requests=13_968,
    add_tokens_in=100_000,
    add_tokens_out=100_000,
)
print(f"\nSeeded: 13,968 requests (97.0%)")

ok = check_and_track(key_id, "groq", "llama-3.1-8b-instant", tokens_in=10, tokens_out=10)
print(f"  call 13,969 → ok={ok}  (below threshold, expect True)")

# ---- Phase 2: bring counter to 14,111 (one below 14,112) ----
# Currently at 13,969. Need +142 to reach 14,111.
db.upsert_provider_usage(
    key_id, "groq", "llama-3.1-8b-instant",
    add_requests=142,
    add_tokens_in=0,
    add_tokens_out=0,
)
row = db.get_provider_usage(key_id, "groq")
print(f"\nSeeded to: {row['requests']} requests ({row['requests']/14400*100:.2f}%)")
print(f"  threshold: 14,400 × 0.98 = 14,112")
print(f"  one more call → 14,112 → should SUSPEND")

# ---- Phase 3: one call crosses the boundary ----
ok = check_and_track(key_id, "groq", "llama-3.1-8b-instant", tokens_in=10, tokens_out=10)
print(f"\n  call 14,112 → ok={ok}  (expect False)")
print(f"  is_suspended: {db.is_key_suspended(key_id, 'groq')}  (expect True)")

# ---- Cleanup ----
with db._conn() as c:
    c.execute("DELETE FROM provider_usage WHERE key_id LIKE 'test-key-%'")
print("\ncleaned up")