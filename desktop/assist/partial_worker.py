"""Partial ASR worker for speculative question answers."""

import threading

import numpy as np
import webrtcvad

from .config import (
    PARTIAL_MIN_SPEECH_SEC,
    PARTIAL_POLL_MS,
    PARTIAL_WINDOW_SEC,
    STT_SR,
)
from .ring_buffer import get_ring
from .stt import _load_model


class PartialWorker(threading.Thread):
    def __init__(self, stop_event, on_partial, vad_mode: int = 2):
        super().__init__(daemon=True)
        self.stop_event = stop_event
        self.on_partial = on_partial
        self.vad = webrtcvad.Vad(vad_mode)
        self._last_read = 0

    def run(self):
        ring = get_ring()
        window_samples = int(PARTIAL_WINDOW_SEC * STT_SR)
        min_speech_samples = int(PARTIAL_MIN_SPEECH_SEC * STT_SR)
        self._last_read = ring.total_written
        model = _load_model()

        while not self.stop_event.wait(PARTIAL_POLL_MS / 1000):
            new_audio = ring.read_latest(int(0.5 * STT_SR))
            if len(new_audio) < 480:
                continue
            speech_frames = 0
            total_frames = 0
            for index in range(0, len(new_audio) - 479, 480):
                frame = new_audio[index:index + 480]
                pcm = np.clip(frame * 32768, -32768, 32767).astype(
                    np.int16
                ).tobytes()
                total_frames += 1
                speech_frames += int(self.vad.is_speech(pcm, STT_SR))
            if not total_frames or speech_frames / total_frames < 0.5:
                continue

            window = ring.read_latest(window_samples)
            if len(window) < min_speech_samples:
                continue
            try:
                text = model.recognize(window, sample_rate=STT_SR)
                if isinstance(text, list):
                    text = text[0] if text else ""
                text = str(text).strip()
                if text:
                    self.on_partial(text)
            except Exception as exc:
                print(f"[partial] transcribe error: {type(exc).__name__}: {exc}")
