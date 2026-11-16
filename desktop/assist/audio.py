"""Audio capture with watchdog + mode dispatch."""

import queue
import sys
import threading
import time
from enum import Enum

from .config import (
    BLOCK_FRAMES,
    CAPTURE_MODE,
    CAPTURE_SR,
    DEVICE_POLL_SEC,
    ENABLE_MIC_CAPTURE,
    MIC_DEVICE,
    MIC_GAIN,
    STT_SR,
)

# watchdog: if no audio for this many seconds, restart the recorder
WATCHDOG_SILENT_SEC = 60.0
# if this many consecutive empty reads, restart
WATCHDOG_MAX_EMPTY = 30


class CaptureMode(Enum):
    PER_PROCESS = "per_process"
    SYSTEM_LOOPBACK = "system_loopback"


def _try_winaudio():
    try:
        import winaudio

        return winaudio
    except ImportError:
        return None


def _stream_winaudio_capture(cap, stop_event, reload_flag, audio_q):
    reader = getattr(cap, "read_frame", None)
    if reader is None:
        raise RuntimeError("winaudio Capture has no read_frame method")

    import soxr

    while not stop_event.is_set() and not reload_flag.is_set():
        chunk = reader(100)
        if chunk is None:
            time.sleep(0.01)
            continue
        if isinstance(chunk, bytes):
            data = np.frombuffer(chunk, dtype=np.int16)
            if data.size % 2:
                data = data[:-1]
            data = data.reshape(-1, 2)
        else:
            data = np.asarray(chunk)
        if data.size == 0:
            continue
        if data.dtype == np.int16:
            data = data.astype(np.float32) / 32768.0
        else:
            data = data.astype(np.float32)
        try:
            audio_q.put_nowait(data)
        except queue.Full:
            pass
        mono = data.mean(axis=1) if data.ndim > 1 else data
        if CAPTURE_SR != STT_SR:
            mono = soxr.resample(mono, CAPTURE_SR, STT_SR)
        from .ring_buffer import get_ring

        get_ring().write(np.asarray(mono, dtype=np.float32))


def _capture_per_process(stop_event, reload_flag, audio_q, target_pid=None):
    winaudio = _try_winaudio()
    if winaudio is None:
        print("[capture] winaudio not installed; falling back")
        _capture_system_loopback(stop_event, reload_flag, audio_q)
        return

    while not stop_event.is_set():
        if reload_flag.is_set():
            reload_flag.clear()
        pid = target_pid or find_meeting_pid()
        if pid is None:
            print("[capture] no meeting process found; retrying in 2s")
            if stop_event.wait(2.0):
                return
            continue
        try:
            session = next(
                (item for item in winaudio.list_sessions() if item.pid == pid),
                None,
            )
            kwargs = {"name": session.name} if session and session.name else {"pid": pid}
            with winaudio.Capture(
                **kwargs, sample_rate=CAPTURE_SR, channels=2
            ) as capture:
                print(f"[capture] per-process -> PID {pid}")
                _stream_winaudio_capture(
                    capture, stop_event, reload_flag, audio_q
                )
        except Exception as exc:
            if stop_event.is_set():
                return
            print(
                f"[capture] per-process error: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            if stop_event.wait(1.0):
                return


def _try_pac():
    try:
        from process_audio_capture import ProcessAudioCapture
        if not ProcessAudioCapture.is_supported():
            return None
        return ProcessAudioCapture
    except Exception as e:
        print(f"[capture] process-audio-capture not usable: {e}")
        return None


def _try_proctap():
    try:
        from proctap import ProcessAudioTap
        return ProcessAudioTap
    except Exception:
        return None


def _capture_pac(stop_event, reload_flag, audio_q, pid, PAC):
    print(f"[capture] per-process (PAC) → PID {pid}")

    def on_level(level_db):
        pass

    try:
        with PAC(pid=pid, output_path=None, level_callback=on_level) as cap:
            cap.start()
            while not stop_event.is_set() and not reload_flag.is_set():
                time.sleep(0.2)
    except Exception as e:
        print(f"[capture] PAC error: {e}; falling back", file=sys.stderr)
        _capture_system_loopback(stop_event, reload_flag, audio_q)


def _capture_proctap(stop_event, reload_flag, audio_q, pid, Tap):
    import asyncio

    import numpy as np

    print(f"[capture] per-process (proc-tap) → PID {pid}")

    async def _run():
        tap = Tap(pid=pid)
        tap.start()
        try:
            async for chunk in tap.stream():
                if stop_event.is_set() or reload_flag.is_set():
                    break
                try:
                    audio_q.put_nowait(np.asarray(chunk, dtype=np.float32))
                except queue.Full:
                    pass
        finally:
            tap.stop()

    try:
        asyncio.run(_run())
    except Exception as e:
        print(f"[capture] proc-tap error: {e}; falling back", file=sys.stderr)
        _capture_system_loopback(stop_event, reload_flag, audio_q)


def _capture_system_loopback(stop_event, reload_flag, audio_q):
    """Loopback with watchdog: reopen recorder if it goes silent."""
    import numpy as np
    import soundcard as sc

    while not stop_event.is_set():
        if reload_flag.is_set():
            reload_flag.clear()
        try:
            speaker = sc.default_speaker()
            mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)
            print(f"[capture] system loopback → {speaker.name}")

            empty_streak = 0
            last_audio = time.time()

            with mic.recorder(samplerate=CAPTURE_SR, blocksize=BLOCK_FRAMES) as rec:
                while not stop_event.is_set() and not reload_flag.is_set():
                    try:
                        data = rec.record(numframes=BLOCK_FRAMES)
                    except Exception as e:
                        if stop_event.is_set():
                            break
                        err = str(e)
                        if (
                            "0x88890004" in err
                            or "0xe000020b" in err.lower()
                            or "invalidated" in err.lower()
                            or "AUDCLNT_E_DEVICE_INVALIDATED" in err
                        ):
                            print("[capture] endpoint invalidated, reopening",
                                  file=sys.stderr)
                            reload_flag.set()
                            break
                        print(f"[capture] record error: {e}", file=sys.stderr)
                        empty_streak += 1
                        if empty_streak > WATCHDOG_MAX_EMPTY:
                            print("[capture] too many errors, reopening", file=sys.stderr)
                            break
                        time.sleep(0.1)
                        continue

                    if data is None or len(data) == 0:
                        empty_streak += 1
                        silent_for = time.time() - last_audio
                        if (empty_streak > WATCHDOG_MAX_EMPTY
                                or silent_for > WATCHDOG_SILENT_SEC):
                            print(
                                f"[capture] watchdog fired "
                                f"(empty={empty_streak}, silent={silent_for:.0f}s) — reopening",
                                file=sys.stderr,
                            )
                            break
                        time.sleep(0.05)
                        continue

                    empty_streak = 0
                    last_audio = time.time()

                    # compute RMS to detect silence vs noise
                    try:
                        mono = data.mean(axis=1) if data.ndim > 1 else data
                        if np.sqrt(np.mean(mono ** 2)) > 0.001:
                            last_audio = time.time()
                    except Exception:
                        pass

                    try:
                        audio_q.put_nowait(data.copy())
                    except queue.Full:
                        pass

                    try:
                        import soxr

                        mono = data.mean(axis=1) if data.ndim > 1 else data
                        mono16 = soxr.resample(
                            mono, CAPTURE_SR, STT_SR
                        ).astype(np.float32)
                        from .ring_buffer import get_ring

                        get_ring().write(mono16)
                    except Exception as exc:
                        print(
                            f"[capture] ring buffer write failed: "
                            f"{type(exc).__name__}"
                        )
        except Exception as e:
            if stop_event.is_set():
                break
            print(f"[capture] device error: {e}", file=sys.stderr)
            time.sleep(1.0)


def mic_capture_loop(stop_event, audio_q):
    if not ENABLE_MIC_CAPTURE:
        return

    import soundcard as sc

    try:
        if MIC_DEVICE is None:
            mic = sc.default_microphone()
        else:
            mic = sc.get_microphone(MIC_DEVICE)
        print(f"[mic] recording from {mic.name}")
    except Exception as e:
        print(f"[mic] unavailable: {e}", file=sys.stderr)
        return

    time.sleep(0.5)

    while not stop_event.is_set():
        try:
            with mic.recorder(
                samplerate=CAPTURE_SR, blocksize=BLOCK_FRAMES
            ) as rec:
                empty_streak = 0
                while not stop_event.is_set():
                    try:
                        data = rec.record(numframes=BLOCK_FRAMES)
                    except Exception as e:
                        if stop_event.is_set():
                            break
                        print(f"[mic] record error: {e}", file=sys.stderr)
                        time.sleep(0.5)
                        break
                    if data is None or len(data) == 0:
                        empty_streak += 1
                        if empty_streak > WATCHDOG_MAX_EMPTY:
                            print("[mic] reopening", file=sys.stderr)
                            break
                        continue
                    empty_streak = 0
                    if MIC_GAIN != 1.0:
                        data = (data * MIC_GAIN).astype("float32")
                    try:
                        audio_q.put_nowait(data.copy())
                    except queue.Full:
                        pass
        except Exception as e:
            if stop_event.is_set():
                break
            print(f"[mic] error: {e}", file=sys.stderr)
            time.sleep(1.0)


def find_meeting_pid(name_hint: str | None = None) -> int | None:
    try:
        import psutil
    except ImportError:
        return None

    targets = ("zoom", "teams", "ms-teams", "meet", "webex", "gotomeeting",
               "slack", "discord")

    candidates: list[int] = []
    for p in psutil.process_iter(["pid", "name"]):
        n = (p.info.get("name") or "").lower()
        if name_hint:
            if name_hint.lower() in n:
                candidates.append(p.info["pid"])
        elif any(t in n for t in targets):
            candidates.append(p.info["pid"])

    if not candidates:
        return None

    try:
        from pycaw.pycaw import AudioUtilities
        audio_pids = set()
        for s in AudioUtilities.GetAllSessions():
            if s.Process:
                audio_pids.add(s.Process.pid)
        live = [p for p in candidates if p in audio_pids]
        if live:
            return live[0]
    except Exception:
        pass

    return candidates[0]


def capture_loop(stop_event, reload_flag, audio_q, pid: int | None = None):
    print(f"[capture] CAPTURE_MODE = {CAPTURE_MODE!r}")

    if CAPTURE_MODE == "system_loopback":
        _capture_system_loopback(stop_event, reload_flag, audio_q)
        return

    if pid is None:
        pid = find_meeting_pid()

    if CAPTURE_MODE == "per_process" and _try_winaudio() is not None:
        _capture_per_process(stop_event, reload_flag, audio_q, pid)
        return

    if CAPTURE_MODE in ("per_process", "auto"):
        PAC = _try_pac()
        if PAC and pid is not None:
            _capture_pac(stop_event, reload_flag, audio_q, pid, PAC)
            return
        Tap = _try_proctap()
        if Tap and pid is not None:
            _capture_proctap(stop_event, reload_flag, audio_q, pid, Tap)
            return

    print("[capture] falling back to system loopback")
    _capture_system_loopback(stop_event, reload_flag, audio_q)


def device_watcher(stop_event, reload_flag):
    import soundcard as sc

    try:
        last = sc.default_speaker().name
    except Exception:
        last = None
    while not stop_event.is_set():
        time.sleep(DEVICE_POLL_SEC)
        try:
            now = sc.default_speaker().name
        except Exception:
            continue
        if now != last:
            print(f"[device] default speaker changed: {last} -> {now}")
            last = now
            reload_flag.set()