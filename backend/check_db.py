"""Inspect the local SQLite schema."""

import sqlite3

c = sqlite3.connect("data/assist.db")
tables = [r[0] for r in c.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
)]
print(f"{len(tables)} tables:")
for t in tables:
    print(f"  {t}")

print()
if "provider_usage" in tables:
    count = c.execute("SELECT COUNT(*) FROM provider_usage").fetchone()[0]
    print(f"✅ provider_usage EXISTS ({count} rows)")
else:
    print("❌ provider_usage MISSING")