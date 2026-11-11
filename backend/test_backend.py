"""Test the full /answer endpoint end-to-end."""

import json
import os
from pathlib import Path

import httpx

cfg_path = Path(os.environ["APPDATA"]) / "Assist" / "config.json"
token = json.loads(cfg_path.read_text())["token"]

print("POST /answer ...")
with httpx.stream(
    "POST",
    "http://127.0.0.1:8000/answer",
    json={"question": "Say OK", "context": ""},
    headers={"Authorization": f"Bearer {token}"},
    timeout=60.0,
) as r:
    print("status:", r.status_code)
    n = 0
    for line in r.iter_lines():
        if not line.startswith("data: "):
            continue
        d = line[6:].strip()
        if d == "[DONE]":
            print(f"[DONE] {n} tokens received")
            break
        try:
            j = json.loads(d)
        except Exception:
            print("  bad line:", d[:80])
            continue
        if "delta" in j:
            n += 1
            if n <= 10:
                print(f"  + {j['delta']!r}")
        elif "error" in j:
            print("  ERROR:", j["error"])