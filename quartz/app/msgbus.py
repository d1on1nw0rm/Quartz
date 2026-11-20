import sys
import traceback
from collections.abc import Callable
from typing import Any

_SUBS: list[dict[str, Any]] = []
_QUEUE: list[dict[str, Any]] = []
_QUEUE_SET: set[int] = set()


def _enqueue(sub: dict[str, Any]) -> None:
    sid = id(sub)
    if sid in _QUEUE_SET:
        return
    _QUEUE_SET.add(sid)
    _QUEUE.append(sub)


def subscribe_rna(*, key: object, owner: object, args: tuple, notify: Callable[..., None],
                  options: set[str] = frozenset()) -> None:
    _SUBS.append({
        "key": key,
        "owner": owner,
        "args": tuple(args),
        "notify": notify,
        "options": set(options),
    })


def publish_rna(*, key: object) -> None:
    for sub in _SUBS:
        if sub["key"] is key or sub["key"] == key:
            _enqueue(sub)


def _key_matches(sub_key: object, struct: object, ident: str) -> bool:
    if isinstance(sub_key, tuple) and len(sub_key) == 2:
        cls, name = sub_key
        if isinstance(cls, type) and isinstance(struct, cls) and name == ident:
            return True
    if isinstance(sub_key, type):
        if isinstance(struct, sub_key):
            return True
    if hasattr(sub_key, "_q_struct") and hasattr(sub_key, "_q_identifier"):
        try:
            if getattr(sub_key, "_q_struct") is struct and getattr(sub_key, "_q_identifier") == ident:
                return True
        except Exception:
            pass
    if sub_key is struct:
        return True
    return False


def notify_changed(struct: object, identifier: str) -> None:
    for sub in _SUBS:
        if _key_matches(sub["key"], struct, identifier):
            _enqueue(sub)


def flush() -> int:
    to_call = list(_QUEUE)
    _QUEUE.clear()
    _QUEUE_SET.clear()
    count = 0
    for sub in to_call:
        count += 1
        try:
            sub["notify"](*sub["args"])
        except Exception:
            traceback.print_exc(file=sys.stderr)
    return count


def pending() -> int:
    return len(_QUEUE)


def clear() -> None:
    _SUBS.clear()
    _QUEUE.clear()
    _QUEUE_SET.clear()


def clear_by_owner(owner: object) -> None:
    to_remove = [sub for sub in _SUBS if sub["owner"] is owner]
    for sub in to_remove:
        _SUBS.remove(sub)
    remaining_queue = []
    remaining_set = set()
    for sub in _QUEUE:
        if sub["owner"] is owner:
            continue
        remaining_queue.append(sub)
        remaining_set.add(id(sub))
    _QUEUE[:] = remaining_queue
    _QUEUE_SET.clear()
    _QUEUE_SET.update(remaining_set)


def snapshot() -> tuple:
    return (list(_SUBS), list(_QUEUE))


def restore(snap: tuple) -> None:
    _SUBS.clear()
    _QUEUE.clear()
    _QUEUE_SET.clear()
    if not snap:
        return
    subs, queue = snap
    for sub in subs:
        _SUBS.append(dict(sub))
    for sub in queue:
        _QUEUE.append(sub)
        _QUEUE_SET.add(id(sub))
