"""Inspect what sinary-winaudio 0.1.0 actually exposes."""

import inspect

import winaudio

print("=" * 70)
print("MODULE-LEVEL ATTRIBUTES")
print("=" * 70)
for name in dir(winaudio):
    if name.startswith("_"):
        continue
    obj = getattr(winaudio, name)
    if inspect.isclass(obj):
        print(f"  CLASS   {name}")
    elif inspect.isfunction(obj) or inspect.ismethod(obj):
        try:
            sig = inspect.signature(obj)
            print(f"  FUNC    {name}{sig}")
        except (ValueError, TypeError):
            print(f"  FUNC    {name}(...)")
    else:
        print(f"  VALUE   {name} = {obj!r}")

print()
print("=" * 70)
print("SESSIONS (list_sessions)")
print("=" * 70)

if hasattr(winaudio, "list_sessions"):
    try:
        sessions = winaudio.list_sessions()
        print(f"Found {len(sessions)} session(s)")
        for i, s in enumerate(sessions):
            print(f"\n  Session {i}:")
            for attr in (
                "pid",
                "name",
                "host_app_name",
                "state",
                "session_id",
                "process_id",
            ):
                if hasattr(s, attr):
                    print(f"    {attr} = {getattr(s, attr)!r}")
            extra = [
                a
                for a in dir(s)
                if not a.startswith("_")
                and a
                not in (
                    "pid",
                    "name",
                    "host_app_name",
                    "state",
                    "session_id",
                    "process_id",
                )
                and not callable(getattr(s, a))
            ]
            if extra:
                print(f"    other attrs: {extra}")
    except Exception as e:
        print(f"  list_sessions() raised: {type(e).__name__}: {e}")
else:
    print("  winaudio has no 'list_sessions' method!")
    print("  Look at the CLASS list above to find the right entry point.")

print()
print("=" * 70)
print("CAPTURE CLASS SIGNATURE")
print("=" * 70)

if hasattr(winaudio, "Capture"):
    try:
        sig = inspect.signature(winaudio.Capture.__init__)
        print(f"  Capture.__init__{sig}")
    except (ValueError, TypeError):
        print("  Could not introspect Capture.__init__")

    try:
        members = [m for m in dir(winaudio.Capture) if not m.startswith("_")]
        print(f"  Capture members: {members}")
    except Exception:
        pass
else:
    print("  winaudio has no 'Capture' class!")
