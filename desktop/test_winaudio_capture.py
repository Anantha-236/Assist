"""Probe the exact sinary-winaudio 0.1.0 Capture API."""

import inspect
import time

import winaudio


def try_construct(pid: int):
    patterns = [
        ("Capture(pid=...)", lambda: winaudio.Capture(pid=pid)),
        ("Capture(target_pid=...)", lambda: winaudio.Capture(target_pid=pid)),
        ("Capture(positional)", lambda: winaudio.Capture(pid)),
        ("Capture() + .target_pid", lambda: _deferred(pid)),
    ]
    for name, constructor in patterns:
        try:
            capture = constructor()
            print(f"  OK {name} works")
            return capture, name
        except Exception as exc:
            print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    return None, None


def _deferred(pid):
    capture = winaudio.Capture()
    capture.target_pid = pid
    return capture


def main():
    print("=" * 70)
    print("STEP 1: List sessions")
    print("=" * 70)
    sessions = winaudio.list_sessions()
    for session in sessions:
        print(
            f"  pid={session.pid:<8} state={session.state:<10} "
            f"name={session.name!r}"
        )

    active = [session for session in sessions if session.state == "Active"]
    print(f"\nActive sessions: {[session.name for session in active]}")
    if not active:
        print("\nNo active sessions found. Play audio and re-run.")
        return

    target = active[0]
    print(f"\nWill capture from: {target.name} (pid={target.pid})")
    print("\n" + "=" * 70)
    print("STEP 2: Try construction patterns")
    print("=" * 70)
    capture, pattern_name = try_construct(target.pid)
    if capture is None:
        print("\nNo construction pattern worked.")
        print(f"Capture.__init__ = {inspect.signature(winaudio.Capture.__init__)}")
        return

    print(f"Selected: {pattern_name}")
    print("\n" + "=" * 70)
    print("STEP 3: Test read_frame()")
    print("=" * 70)
    try:
        start = time.time()
        for index in range(10):
            try:
                frame = capture.read_frame(100)
            except TypeError:
                frame = capture.read_frame()
            elapsed_ms = (time.time() - start) * 1000
            if frame is None:
                print(f"  frame {index}: None ({elapsed_ms:.1f}ms)")
            elif isinstance(frame, bytes):
                print(f"  frame {index}: bytes len={len(frame)} ({elapsed_ms:.1f}ms)")
            else:
                print(
                    f"  frame {index}: {type(frame).__name__} "
                    f"repr={repr(frame)[:60]} ({elapsed_ms:.1f}ms)"
                )
    except Exception as exc:
        print(f"  read_frame() raised: {type(exc).__name__}: {exc}")

    try:
        capture.stop()
        print("\n  capture.stop() called successfully")
    except Exception as exc:
        print(f"  stop() raised: {type(exc).__name__}: {exc}")

    print("\n" + "=" * 70)
    print("STEP 4: Inspect record_to_wav signature")
    print("=" * 70)
    try:
        print(f"  record_to_wav{inspect.signature(capture.record_to_wav)}")
    except Exception as exc:
        print(f"  Cannot inspect: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
