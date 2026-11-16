"""Thread-safe circular audio buffer for parallel audio readers."""

import threading

import numpy as np


class RingBuffer:
    def __init__(self, capacity_samples: int = 16000 * 30):
        self._buf = np.zeros(capacity_samples, dtype=np.float32)
        self._write_pos = 0
        self._total_written = 0
        self._capacity = capacity_samples
        self._lock = threading.Lock()

    def write(self, samples: np.ndarray):
        samples = np.asarray(samples, dtype=np.float32)
        if len(samples) == 0:
            return
        with self._lock:
            if len(samples) >= self._capacity:
                self._buf[:] = samples[-self._capacity:]
                self._write_pos = 0
                self._total_written += len(samples)
                return
            end = self._write_pos + len(samples)
            if end <= self._capacity:
                self._buf[self._write_pos:end] = samples
            else:
                head = self._capacity - self._write_pos
                self._buf[self._write_pos:] = samples[:head]
                self._buf[:end - self._capacity] = samples[head:]
            self._write_pos = end % self._capacity
            self._total_written += len(samples)

    def read_latest(self, n_samples: int) -> np.ndarray:
        with self._lock:
            n = min(n_samples, self._capacity, self._total_written)
            if n == 0:
                return np.zeros(0, dtype=np.float32)
            start = (self._write_pos - n) % self._capacity
            if start + n <= self._capacity:
                return self._buf[start:start + n].copy()
            head = self._capacity - start
            return np.concatenate([self._buf[start:], self._buf[:n - head]])

    @property
    def total_written(self) -> int:
        with self._lock:
            return self._total_written


_ring: RingBuffer | None = None


def get_ring() -> RingBuffer:
    global _ring
    if _ring is None:
        _ring = RingBuffer()
    return _ring
