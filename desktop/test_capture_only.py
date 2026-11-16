"""Test audio capture in isolation - no STT, no UI, no LLM."""

import queue
import threading
import time

import numpy as np

from assist.audio import capture_loop
from assist.config import CAPTURE_MODE

stop_event = threading.Event()
reload_flag = threading.Event()
audio_q = queue.Queue(maxsize=200)

print(f"[test] starting capture (CAPTURE_MODE={CAPTURE_MODE!r})")
threading.Thread(
    target=capture_loop,
    args=(stop_event, reload_flag, audio_q),
    daemon=True,
).start()

print("[test] capturing for 10 seconds...\n")
t0 = time.time()
chunks = 0
total_samples = 0
peak_rms = 0.0

while time.time() - t0 < 10:
    try:
        chunk = audio_q.get(timeout=0.5)
        chunks += 1
        total_samples += len(chunk)
        rms = float(np.sqrt(np.mean(chunk ** 2)))
        peak_rms = max(peak_rms, rms)
        if chunks <= 5 or chunks % 50 == 0:
            print(f"[test] chunk {chunks}: {len(chunk)} samples, rms={rms:.4f}")
    except queue.Empty:
        continue

stop_event.set()
time.sleep(0.2)

print(
    f"\n[test] RESULT: {chunks} chunks, {total_samples} samples "
    f"({total_samples / 16000:.1f}s of audio), peak RMS={peak_rms:.4f}"
)

if chunks == 0:
    print("[test] FAILED - no audio captured")
elif peak_rms < 0.001:
    print("[test] PARTIAL - chunks received but silent (RMS near 0)")
else:
    print(f"[test] OK - audio capture works ({chunks / 10:.1f} chunks/sec)")
