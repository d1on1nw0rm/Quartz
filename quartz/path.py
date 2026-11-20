import os
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

_PROVIDER: Callable[[], str] = lambda: ""


def set_blend_filepath_provider(fn: Callable[[], str] | None) -> None:
    global _PROVIDER
    if fn is None:
        _PROVIDER = lambda: ""
    else:
        _PROVIDER = fn


def blend_filepath() -> str:
    try:
        return _PROVIDER() or ""
    except Exception:
        return ""


def abspath(path: str, *, start: str | None = None, library: object = None) -> str:
    if not isinstance(path, str):
        path = str(path)
    if not path.startswith("//"):
        return path
    rest = path[2:]
    if start is not None:
        base = start
    else:
        base = os.path.dirname(blend_filepath())
    if not base:
        return rest
    return os.path.join(base, rest)


def relpath(path: str, *, start: str | None = None) -> str:
    if not isinstance(path, str):
        path = str(path)
    if path.startswith("//"):
        return path
    if start is not None:
        base = start
    else:
        base = os.path.dirname(blend_filepath())
    if not base:
        return path
    try:
        rel = os.path.relpath(path, base)
    except ValueError:
        return path
    return "//" + rel.replace(os.sep, "/")


def basename(path: str) -> str:
    if not isinstance(path, str):
        path = str(path)
    p = path
    if p.startswith("//"):
        p = p[2:]
    return os.path.basename(p)


def clean_name(name: str, *, replace: str = "_") -> str:
    out = []
    for ch in str(name):
        if ("A" <= ch <= "Z") or ("a" <= ch <= "z") or ("0" <= ch <= "9") or ch in "_-":
            out.append(ch)
        else:
            out.append(replace)
    return "".join(out)


def display_name(name: str, *, has_ext: bool = True, title_case: bool = True) -> str:
    s = str(name)
    if has_ext:
        s = os.path.splitext(s)[0]
    s = s.replace("_", " ")
    if title_case and s != "" and s == s.lower():
        s = s.title()
    return s


def display_name_from_filepath(name: str) -> str:
    base = os.path.basename(str(name))
    return os.path.splitext(base)[0]


def display_name_to_filepath(name: str) -> str:
    s = str(name)
    for ch in "\\/:*?\"<>|":
        s = s.replace(ch, "_")
    return s


def ensure_ext(filepath: str, ext: str, *, case_sensitive: bool = False) -> str:
    fp = str(filepath)
    e = str(ext)
    if case_sensitive:
        if fp.endswith(e):
            return fp
    else:
        if fp.lower().endswith(e.lower()):
            return fp
    return fp + e


def is_subdir(path: str, directory: str) -> bool:
    p = os.path.normpath(str(path)).replace("\\", "/")
    d = os.path.normpath(str(directory)).replace("\\", "/")
    p_parts = [x for x in p.split("/") if x != ""]
    d_parts = [x for x in d.split("/") if x != ""]
    if len(p_parts) < len(d_parts):
        return False
    return p_parts[: len(d_parts)] == d_parts


def module_names(path: str, *, recursive: bool = False, package: str = "") -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    base = str(path)
    if not os.path.isdir(base):
        return result

    def walk(cur: str, pkg_prefix: str) -> None:
        try:
            entries = sorted(os.listdir(cur))
        except OSError:
            return
        for name in entries:
            if name.startswith("."):
                continue
            if name == "__pycache__":
                continue
            full = os.path.join(cur, name)
            if os.path.isfile(full) and name.endswith(".py") and name != "__init__.py":
                modname = name[:-3]
                if pkg_prefix:
                    modname = f"{pkg_prefix}.{modname}"
                if package and not pkg_prefix:
                    modname = f"{package}.{modname}"
                result.append((modname, full))
            elif os.path.isdir(full) and os.path.isfile(os.path.join(full, "__init__.py")):
                modname = name
                if pkg_prefix:
                    modname = f"{pkg_prefix}.{modname}"
                if package and not pkg_prefix:
                    modname = f"{package}.{modname}"
                result.append((modname, os.path.join(full, "__init__.py")))
                if recursive:
                    walk(full, modname)

    walk(base, "")
    result.sort(key=lambda x: x[0])
    return result


def native_pathsep(path: str) -> str:
    return str(path).replace("/", os.sep)


def reduce_dirs(dirs: Iterable[str]) -> list[str]:
    items = [str(d) for d in dirs]
    norm = [os.path.normpath(d).replace("\\", "/") for d in items]

    def is_sub(a: str, b: str) -> bool:
        return is_subdir(a, b) and os.path.normpath(a).replace("\\", "/") != os.path.normpath(b).replace("\\", "/")

    result = []
    for i, d in enumerate(items):
        ni = norm[i]
        skip = False
        for j, other in enumerate(items):
            if i == j:
                continue
            nj = norm[j]
            if ni == nj and j < i:
                skip = True
                break
            if ni != nj and is_sub(ni, nj):
                skip = True
                break
        if not skip:
            result.append(d)
    return result


def resolve_ncase(path: str) -> str:
    p = str(path)
    if not os.path.exists(p):
        return p
    drive, tail = os.path.splitdrive(p)
    is_abs = os.path.isabs(p)
    parts = [x for x in tail.replace("\\", "/").split("/") if x not in ("", ".")]
    if is_abs:
        current = drive + (os.sep if drive else os.sep)
    else:
        current = ""
    out: list[str] = []
    if drive:
        out.append(drive)
    for part in parts:
        if part == "..":
            out.append(part)
            current = os.path.join(current, part) if current not in ("", None) else part
            continue
        actual = part
        scan_dir = current if current not in ("", None) else "."
        try:
            for entry in os.scandir(scan_dir):
                if entry.name.casefold() == part.casefold():
                    actual = entry.name
                    break
        except OSError:
            pass
        out.append(actual)
        current = os.path.join(current, actual) if current not in ("", None) else actual
    if is_abs:
        if drive:
            if len(out) > 1:
                return drive + os.sep + os.path.join(*out[1:])
            return drive + os.sep
        return os.sep + os.path.join(*out)
    return os.path.join(*out) if out else ""


def is_autoexec(filepath: str) -> bool:
    return False


extensions_image: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".bmp", ".tga", ".tif", ".tiff", ".exr", ".hdr",
    ".webp", ".dds", ".psd", ".svg",
})
extensions_movie: frozenset[str] = frozenset({
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".ogv", ".mpg", ".mpeg", ".m4v",
})
extensions_audio: frozenset[str] = frozenset({
    ".wav", ".mp3", ".ogg", ".flac", ".aac", ".m4a",
})
