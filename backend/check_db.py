"""Inspect the local SQLite schema."""

import sqlite3

c = sqlite3.connect("data/assist.db")
tables = [r[0] for r in c.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
)]
print(f"{len(tables)} tables:")
for t in tables:
    cols = [r[1] for r in c.execute(f"PRAGMA table_info({t})")]
    print(f"  {t}  ({len(cols)} cols: {', '.join(cols[:8])}{'…' if len(cols) > 8 else ''})")

print()
if "provider_usage" in tables:
    print("✅ provider_usage EXISTS")
    count = c.execute("SELECT COUNT(*) FROM provider_usage").fetchone()[0]
    print(f"   rows: {count}")
else:
    print("❌ provider_usage MISSING — add the CREATE TABLE block to init_db()")
