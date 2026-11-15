
"""LLM provider — calls the Assist backend, which proxies OpenRouter/Groq."""

import json
import threading
import time

import httpx

from .answer_bus import get_bus
from .auth import storage
from .config import BACKEND_URL

_inflight = {"q": None, "lock": threading.Lock()}


def _token() -> str | None:
    return storage.load().get("token")


def answer_async(question: str, context: str = ""):
    from .pause_state import is_paused

    if is_paused():
        print(f"[llm] paused, skipping: {question[:60]!r}")
        return

    bus = get_bus()

    with _inflight["lock"]:
        if _inflight["q"] is not None:
            print(f"[llm] skipping (inflight): {question[:60]!r}")
            return
        _inflight["q"] = question

    bus.push_question(question, context)

    token = _token()
    if not token:
        with _inflight["lock"]:
            _inflight["q"] = None
        bus.push_error("not authenticated")
        bus.push_done()
        return

    print(f"[llm] POST /answer  q={question[:60]!r}")

    def _run():
        last_beat = time.time()
        try:
            # 30s connect timeout for cold starts; 20s read timeout
            # ensures hanging streams still break.
            timeout = httpx.Timeout(45.0, connect=30.0, read=20.0)

            with httpx.stream(
                "POST",
                f"{BACKEND_URL}/answer",
                json={"question": question, "context": context},
                headers={"Authorization": f"Bearer {token}"},
                timeout=timeout,
            ) as r:
                print(f"[llm] status={r.status_code}")

                if r.status_code != 200:
                    body = b"".join(r.iter_bytes())
                    print(f"[llm] ERROR HTTP {r.status_code}: {body[:200]!r}")
                    bus.push_error(f"HTTP {r.status_code}")
                    return

                n_deltas = 0
                n_errors = 0

                for line in r.iter_lines():
                    if not line.startswith("data: "):
                        continue

                    data = line[6:].strip()

                    if data == "[DONE]":
                        print(
                            f"[llm] DONE (deltas={n_deltas}, errors={n_errors})"
                        )
                        break

                    try:
                        j = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    if "delta" in j:
                        n_deltas += 1
                        bus.push_token(j["delta"])

                    elif "error" in j:
                        n_errors += 1
                        print(f"[llm] SERVER ERROR: {j['error']}")
                        bus.push_error(j["error"])

                    now = time.time()
                    if now - last_beat > 5.0:
                        last_beat = now
                        print(f"[llm] heartbeat (deltas={n_deltas})")

                if n_deltas == 0 and n_errors == 0:
                    print("[llm] WARNING: no tokens received")
                    bus.push_error("no answer returned")

        except httpx.ReadTimeout:
            print("[llm] READ TIMEOUT (20s)")
            bus.push_error("timeout — model stalled")

        except httpx.TimeoutException:
            print("[llm] TIMEOUT")
            bus.push_error("timeout")

        except Exception as e:
            print(f"[llm] EXCEPTION {type(e).__name__}: {e}")
            bus.push_error(f"{type(e).__name__}")

        finally:
            bus.push_done()
            with _inflight["lock"]:
                _inflight["q"] = None

    threading.Thread(target=_run, daemon=True).start()
