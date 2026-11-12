"""Simulate usage until the 98% suspend threshold fires."""

import uuid

from app import db
from app.usage_tracker import check_and_track

key_id = "test-key-" + uuid.uuid4().hex[:8]
print(f"test key: {key_id}")

db.upsert_provider_usage(key_id, "groq", "llama-3.1-8b-instant", add_requests=0)

ok = check_and_track(key_id, "groq", "llama-3.1-8b-instant",
                     tokens_in=50, tokens_out=30)
print(f"first call ok: {ok}")

suspended_at = None
for i in range(14500):
    ok = check_and_track(key_id, "groq", "llama-3.1-8b-instant",
                         tokens_in=50, tokens_out=30)
    if not ok:
        suspended_at = i + 2
        break

print(f"suspended after: {suspended_at} calls")
print(f"is_key_suspended: {db.is_key_suspended(key_id, 'groq')}")
print(f"expected: 14400 × 0.98 = 14112")

# clean up
with db._conn() as c:
    c.execute("DELETE FROM provider_usage WHERE key_id LIKE 'test-key-%'")
print("cleaned up")