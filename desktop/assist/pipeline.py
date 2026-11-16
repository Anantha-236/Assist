
"""Wire the pipeline: capture → segmenter → stt worker → transcript → LLM."""

import queue
import threading
import time

import webrtcvad

from .answer_bus import get_bus
from .audio import capture_loop, device_watcher, find_meeting_pid
from .config import TRANSCRIPTS_DIR, VAD_MODE
from .llm import answer_async
from .meeting_watcher import MeetingWatcher
from .partial_worker import PartialWorker
from .segmenter import Segmenter
from .speculative import SpeculativeEngine
from .stt import preload as preload_stt, transcribe_worker
from .transcript import TranscriptStore


def run_pipeline(pid: int | None = None):
    if pid is None:
        pid = find_meeting_pid()
        if pid:
            print(f"[init] auto-detected meeting app PID {pid}")

    session = time.strftime("%Y%m%d_%H%M%S")
    store = TranscriptStore(TRANSCRIPTS_DIR / f"session_{session}.jsonl")
    print(f"[init] transcript -> {store.path}")

    audio_q: "queue.Queue" = queue.Queue(maxsize=100)
    segment_q: "queue.Queue" = queue.Queue(maxsize=2)
    stop_event = threading.Event()
    reload_flag = threading.Event()

    vad = webrtcvad.Vad(VAD_MODE)

    # Inform the user about the initial AI model download.
    print("[init] First run downloads the AI model (~600 MB). This may take 5-10 minutes.")
    print("[init] Subsequent launches are instant — the model is cached locally.")

    preload_stt()

    bus = get_bus()
    speculative = SpeculativeEngine(
        on_question=answer_async,
        on_cancel=lambda question: print(
            f"[spec] cancelled answer for: {question[:60]!r}"
        ),
    )

    def on_meeting_start(label: str, pid: int):
        bus.push_status(f"● {label} — listening")

    def on_meeting_stop():
        bus.push_status("○ Waiting for a meeting…")

    threading.Thread(
        target=capture_loop,
        args=(stop_event, reload_flag, audio_q, pid),
        daemon=True,
    ).start()
    threading.Thread(
        target=device_watcher, args=(stop_event, reload_flag), daemon=True
    ).start()
    threading.Thread(
        target=transcribe_worker,
        args=(stop_event, segment_q, store, speculative.on_final),
        daemon=True,
    ).start()

    partial = PartialWorker(
        stop_event, on_partial=speculative.on_partial, vad_mode=VAD_MODE
    )
    partial.start()
    print("[init] partial worker started")

    watcher = MeetingWatcher(on_meeting_start, on_meeting_stop, stop_event)
    watcher.start()

    print("[init] ready.")
    seg = Segmenter(audio_q, segment_q, vad)

    try:
        seg.run(stop_event, reload_flag)
    except KeyboardInterrupt:
        print("\n[stop] shutting down")
    finally:
        stop_event.set()
        time.sleep(0.3)
        store.close()
        tid = store.upload_to_backend()
        if tid:
            print(f"[transcript] final upload -> {tid}")
        store.email_to_user()
