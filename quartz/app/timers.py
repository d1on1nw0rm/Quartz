import sys
import time
import traceback
from collections.abc import Callable

_TIMERS: list[dict] = []
_SEQ: int = 0


def register(function: Callable, *, first_interval: float = 0.0, persistent: bool = False) -> None:
    global _SEQ
    for t in _TIMERS:
        if t["function"] is function:
            t["deadline"] = time.monotonic() + float(first_interval)
            t["first_interval"] = float(first_interval)
            t["persistent"] = bool(persistent)
            t["ran"] = False
            return
    _SEQ += 1
    _TIMERS.append({
        "function": function,
        "deadline": time.monotonic() + float(first_interval),
        "first_interval": float(first_interval),
        "persistent": bool(persistent),
        "seq": _SEQ,
        "ran": False,
    })


def unregister(function: Callable) -> None:
    for i, t in enumerate(_TIMERS):
        if t["function"] is function:
            del _TIMERS[i]
            return
    raise ValueError("Error: function is not registered")


def is_registered(function: Callable) -> bool:
    return any(t["function"] is function for t in _TIMERS)


def pump(*, now: float | None = None, max_calls: int = 1000) -> int:
    if now is None:
        now = time.monotonic()
    for t in _TIMERS:
        t["ran"] = False
    calls = 0
    while calls < max_calls:
        candidates = [t for t in _TIMERS if not t["ran"] and t["deadline"] <= now]
        if not candidates:
            break
        candidates.sort(key=lambda t: (t["deadline"], t["seq"]))
        t = candidates[0]
        t["ran"] = True
        try:
            result = t["function"]()
        except Exception:
            traceback.print_exc(file=sys.stderr)
            result = None
            try:
                _TIMERS.remove(t)
            except ValueError:
                pass
            calls += 1
            continue
        if result is None:
            try:
                _TIMERS.remove(t)
            except ValueError:
                pass
        else:
            t["deadline"] = now + float(result)
        calls += 1
    for t in _TIMERS:
        t["ran"] = False
    return calls


def clear(*, keep_persistent: bool = False) -> None:
    if keep_persistent:
        _TIMERS[:] = [t for t in _TIMERS if t["persistent"]]
    else:
        _TIMERS.clear()


def snapshot() -> list:
    return [
        {
            "function": t["function"],
            "deadline": t["deadline"],
            "first_interval": t["first_interval"],
            "persistent": t["persistent"],
            "seq": t["seq"],
        }
        for t in _TIMERS
    ]


def restore(snap: list) -> None:
    _TIMERS.clear()
    for item in snap:
        _TIMERS.append({
            "function": item["function"],
            "deadline": item["deadline"],
            "first_interval": item["first_interval"],
            "persistent": item["persistent"],
            "seq": item["seq"],
            "ran": False,
        })
