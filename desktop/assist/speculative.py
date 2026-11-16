"""Speculative question engine triggered by partial transcripts."""

import threading
import time


QUESTION_TRIGGERS = (
    "tell me about", "tell us about", "introduce yourself",
    "walk me through", "describe", "explain", "talk about",
    "write a program", "write code", "write a function", "implement",
    "how do you", "how would you", "what is", "what are",
    "why do you", "why are you", "can you", "could you",
    "would you", "give me an example",
)
MIN_WORDS = 4
MIN_SECONDS_BETWEEN_FIRES = 1.5


class SpeculativeEngine:
    def __init__(self, on_question, on_cancel=None):
        self.on_question = on_question
        self.on_cancel = on_cancel or (lambda question: None)
        self._lock = threading.Lock()
        self._last_fired = ""
        self._last_fired_at = 0.0
        self._in_flight = False

    def on_partial(self, partial_text: str, context: str = ""):
        if not partial_text:
            return
        text = partial_text.strip().lower()
        if len(text.split()) < MIN_WORDS or not self._looks_like_question(text):
            return
        with self._lock:
            if (
                self._in_flight
                or text == self._last_fired
                or time.monotonic() - self._last_fired_at
                < MIN_SECONDS_BETWEEN_FIRES
            ):
                return
            self._last_fired = text
            self._last_fired_at = time.monotonic()
            self._in_flight = True
        threading.Thread(
            target=self._fire, args=(partial_text, context), daemon=True
        ).start()

    def on_final(self, final_text: str, context: str = ""):
        with self._lock:
            last = self._last_fired
            self._in_flight = False
        if not final_text:
            return
        if not last:
            self.on_question(final_text, context)
            return
        partial_words = set(last.split())
        final_words = set(final_text.lower().split())
        overlap = len(partial_words & final_words) / len(partial_words)
        if overlap >= 0.75:
            with self._lock:
                self._last_fired = ""
            return
        try:
            self.on_cancel(last)
        except Exception as exc:
            print(f"[spec] cancel error: {type(exc).__name__}: {exc}")
        finally:
            with self._lock:
                self._last_fired = ""
        self.on_question(final_text, context)

    def _looks_like_question(self, text: str) -> bool:
        return text.endswith("?") or any(trigger in text for trigger in QUESTION_TRIGGERS)

    def _fire(self, question: str, context: str):
        try:
            self.on_question(question, context)
        except Exception as exc:
            print(f"[spec] fire error: {type(exc).__name__}: {exc}")
        finally:
            with self._lock:
                self._in_flight = False
