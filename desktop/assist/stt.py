
"""STT worker with local Q&A fast-path + LLM fallback."""

import queue
import sys
import threading
import time

import numpy as np

from .answer_bus import get_bus
from .config import PARAKEET_MODEL, QUESTION_COALESCE_SEC, STT_SR
from .question_patterns import detect as detect_question
from .qa_matcher import format_answer, match_question
from .transcript import TranscriptStore

_model = None
_model_lock = threading.Lock()


def _load_model():
    global _model

    if _model is None:
        with _model_lock:
            if _model is None:
                import onnx_asr

                print(f"[stt] loading {PARAKEET_MODEL}...")
                t0 = time.monotonic()

                _model = onnx_asr.load_model(PARAKEET_MODEL)

                print(
                    f"[stt] loaded in "
                    f"{time.monotonic() - t0:.1f}s"
                )

    return _model


def preload():
    """Preload the speech recognition model."""
    _load_model()


def _is_junk(text: str) -> bool:
    if not text:
        return True

    words = text.strip().split()

    if len(words) <= 1 and len(text.strip()) <= 3:
        return True

    return False


_pending = {
    "text": "",
    "context": "",
    "theme": "",
    "timer": None,
    "lock": threading.Lock(),
}


def _ends_cleanly(text: str) -> bool:
    t = text.rstrip()
    return bool(t) and t[-1] in "?!."


def _fire(on_question):
    """Process a coalesced question using local Q&A or LLM fallback."""

    with _pending["lock"]:
        q = _pending["text"]
        c = _pending["context"]

        _pending["text"] = ""
        _pending["context"] = ""
        _pending["theme"] = ""
        _pending["timer"] = None

    if not q:
        return

    # Fast path: local Q&A database
    profile = _get_profile()
    match = match_question(q, profile=profile)

    if match:
        answer = format_answer(match, profile)

        bus = get_bus()
        bus.push_question(q)

        for chunk in _chunk_text(answer, 24):
            bus.push_token(chunk)

        bus.push_done()

        print(f"[qa] DB match ({match['score']}): {q[:60]!r}")
        return

    # Slow path: LLM fallback
    print(f"[qa] no match, calling LLM: {q[:60]!r}")

    if on_question:
        try:
            on_question(q, c)
        except Exception as e:
            print(f"[q] handler error: {e}", file=sys.stderr)


def _chunk_text(text: str, size: int):
    """Yield text in chunks to simulate streaming tokens."""
    for i in range(0, len(text), size):
        yield text[i:i + size]


def _get_profile() -> dict:
    """Read user profile from auth cache if available."""

    try:
        from .auth import storage

        cfg = storage.load()
        return cfg.get("profile") or {}

    except Exception:
        return {}


def _queue_question(text: str, context: str, theme: str, on_question):
    """Combine partial questions before processing them."""

    with _pending["lock"]:
        if _pending["timer"] is not None:
            _pending["timer"].cancel()

            _pending["text"] += " " + text

            print(f"[q] coalesced: {_pending['text'][:100]}")

        else:
            _pending["text"] = text
            _pending["context"] = context
            _pending["theme"] = theme

        timer = threading.Timer(
            QUESTION_COALESCE_SEC,
            lambda: _fire(on_question)
        )

        timer.daemon = True
        _pending["timer"] = timer
        timer.start()


def transcribe_worker(stop_event, segment_q, store: TranscriptStore, on_question=None):
    """Transcribe queued audio and process detected questions."""

    from .config import MAX_SEGMENT_AGE_SEC

    while not stop_event.is_set() or not segment_q.empty():

        try:
            audio, enqueue_ts = segment_q.get(timeout=0.5)

        except queue.Empty:
            continue

        except Exception as e:
            print(f"[stt] queue error: {e}", file=sys.stderr)
            continue

        try:
            # Drop stale segments — prevent transcription backlog
            age = time.monotonic() - enqueue_ts

            if age > MAX_SEGMENT_AGE_SEC:
                print(
                    f"[stt] DROP stale segment ({age:.1f}s old)",
                    file=sys.stderr
                )
                continue

            # Convert stereo audio to mono
            if audio.ndim > 1:
                audio = audio.mean(axis=1)

            audio = audio.astype(np.float32)

            dur = len(audio) / STT_SR

            t0 = time.monotonic()

            # Speech recognition
            try:
                model = _load_model()

                text = model.recognize(
                    audio,
                    sample_rate=STT_SR
                )

                if isinstance(text, list):
                    text = text[0] if text else ""

                text = str(text).strip()

            except Exception as e:
                print(
                    f"[stt] recognize error: {e}",
                    file=sys.stderr
                )
                continue

            stt_ms = (time.monotonic() - t0) * 1000
            queue_wait_ms = (t0 - enqueue_ts) * 1000

            # Ignore empty or junk transcription
            if not text or _is_junk(text):
                continue

            # Save transcript
            store.add(dur, text)

            # Detect questions
            q_info = detect_question(text)
            q_mark = ""

            if q_info and on_question:

                q_mark = f"  ❓ [{q_info['theme']}]"

                if _ends_cleanly(q_info["question"]):

                    try:
                        q = q_info["question"]
                        c = store.context(3)

                        # Local Q&A database fast path
                        profile = _get_profile()
                        match = match_question(q, profile=profile)

                        if match:
                            answer = format_answer(
                                match,
                                profile
                            )

                            bus = get_bus()

                            bus.push_question(q)

                            for chunk in _chunk_text(answer, 24):
                                bus.push_token(chunk)

                            bus.push_done()

                            print(
                                f"[qa] DB match ({match['score']}): "
                                f"{q[:60]!r}"
                            )

                        else:
                            # LLM fallback
                            print(
                                f"[qa] no match, calling LLM: "
                                f"{q[:60]!r}"
                            )

                            on_question(q, c)

                    except Exception as e:
                        print(
                            f"[q] handler error: {e}",
                            file=sys.stderr
                        )

                else:
                    # Queue incomplete questions for coalescing
                    try:
                        _queue_question(
                            q_info["question"],
                            store.context(3),
                            q_info["theme"],
                            on_question,
                        )

                    except Exception as e:
                        print(
                            f"[q] queue error: {e}",
                            file=sys.stderr
                        )

            # Transcription output and performance metrics
            print(
                f"[{time.strftime('%H:%M:%S')}] "
                f"({dur:4.1f}s | "
                f"q {queue_wait_ms:4.0f}ms | "
                f"stt {stt_ms:5.0f}ms)"
                f"{q_mark}"
            )

            print(f"  {text}\n")

        except Exception as e:
            import traceback

            print(
                f"[stt] WORKER EXCEPTION: {e}",
                file=sys.stderr
            )

            traceback.print_exc()
            continue
