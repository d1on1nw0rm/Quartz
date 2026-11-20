from __future__ import annotations

from typing import Callable

from quartz.errors import PropertyTypeError

__all__ = [
    "MAX_NAME_BYTES", "RENAME_MODES", "RENAME_RESULTS",
    "truncate_utf8", "split_suffix", "unique_name", "sort_key", "plan_rename",
]

MAX_NAME_BYTES: int = 255
RENAME_MODES: tuple[str, ...] = ("NEVER", "ALWAYS", "SAME_ROOT")
RENAME_RESULTS: tuple[str, ...] = ("UNCHANGED", "UNCHANGED_COLLISION", "RENAMED_NO_COLLISION",
                                   "RENAMED_COLLISION_ADJUSTED", "RENAMED_COLLISION_FORCED")


def truncate_utf8(name: str, max_bytes: int = MAX_NAME_BYTES) -> str:
    data = name.encode("utf-8", "surrogatepass")
    if len(data) <= max_bytes:
        return name
    cut = data[:max_bytes]
    return cut.decode("utf-8", "ignore")


def split_suffix(name: str) -> tuple[str, int | None]:
    dot = name.rfind(".")
    if dot <= 0:
        return name, None
    digits = name[dot + 1:]
    if not digits or not all("0" <= ch <= "9" for ch in digits):
        return name, None
    return name[:dot], int(digits)


def unique_name(name: str, taken: Callable[[str], bool], *, default: str) -> str:
    candidate = truncate_utf8(name) if name else ""
    if not candidate:
        candidate = truncate_utf8(default)
    if not taken(candidate):
        return candidate
    base = split_suffix(candidate)[0]
    n = 1
    while True:
        suffix = f".{n:03d}"
        room = MAX_NAME_BYTES - len(suffix.encode("utf-8"))
        trial = truncate_utf8(base, room) + suffix
        if not taken(trial):
            return trial
        n += 1


def sort_key(name: str) -> str:
    return name.casefold()


def plan_rename(current: str, requested: str, taken: Callable[[str], bool], *, mode: str = "NEVER",
                default: str) -> tuple[str, str, str | None]:
    if mode not in RENAME_MODES:
        listing = ", ".join(repr(m) for m in RENAME_MODES)
        raise PropertyTypeError(f'enum "{mode}" not found in ({listing})')
    target = truncate_utf8(requested) or default
    if target == current:
        return "UNCHANGED", current, None
    if not taken(target):
        return "RENAMED_NO_COLLISION", target, None
    forced = mode == "ALWAYS" or (mode == "SAME_ROOT" and split_suffix(current)[0] == split_suffix(target)[0])
    if forced:
        other = unique_name(target, lambda n: taken(n) or n == target, default=default)
        return "RENAMED_COLLISION_FORCED", target, other
    new = unique_name(target, taken, default=default)
    if new == current:
        return "UNCHANGED_COLLISION", current, None
    return "RENAMED_COLLISION_ADJUSTED", new, None
