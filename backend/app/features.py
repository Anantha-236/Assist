"""Feature flag defaults + labels for per-user permissions."""

DEFAULT_FEATURES = {
    "qa_db": True,
    "llm": True,
    "code": True,
    "transcripts": True,
    "email_transcripts": False,
    "mic_capture": False,
    "per_process": True,
    "auto_answer": True,
    "save_answers": False,
}

FEATURE_LABELS = {
    "qa_db": "Local Q&A database answers",
    "llm": "LLM answers for unmatched questions (consumes API quota)",
    "code": "Code / programming answers",
    "transcripts": "Save and upload meeting transcripts",
    "email_transcripts": "Email transcript after each meeting",
    "mic_capture": "Capture your microphone (your own voice)",
    "per_process": "Per-process audio capture (meeting app only)",
    "auto_answer": "Auto-answer detected questions",
    "save_answers": "Save my interview answers for self-review (requires mic capture)",
}


def merge_with_defaults(features: dict | None) -> dict:
    out = dict(DEFAULT_FEATURES)
    if features:
        for k, v in features.items():
            if k in out:
                out[k] = bool(v)
    return out