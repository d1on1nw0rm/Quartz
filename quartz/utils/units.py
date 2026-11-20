from __future__ import annotations

import math
import re

__all__ = ["categories", "systems", "to_string", "to_value"]


class _Names:
    __slots__ = ("_names",)

    def __init__(self, names: tuple[str, ...]) -> None:
        object.__setattr__(self, "_names", names)

    def __getattr__(self, name: str) -> str:
        if name in self._names:
            return name
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"'{name}' is read-only")

    def __delattr__(self, name: str) -> None:
        raise AttributeError(f"'{name}' is read-only")

    def __iter__(self):
        return iter(self._names)

    def __contains__(self, name: object) -> bool:
        return name in self._names

    def __len__(self) -> int:
        return len(self._names)

    def __dir__(self):
        return list(self._names)

    def __repr__(self) -> str:
        return f"<units {', '.join(self._names)}>"


systems = _Names(("NONE", "METRIC", "IMPERIAL"))
categories = _Names((
    "NONE", "LENGTH", "AREA", "VOLUME", "MASS", "ROTATION", "TIME", "TIME_ABSOLUTE", "VELOCITY", "ACCELERATION",
    "CAMERA", "POWER", "TEMPERATURE", "WAVELENGTH", "COLOR_TEMPERATURE", "FREQUENCY",
))

_UNITS: dict[tuple[str, str], tuple[tuple[str, float, str], ...]] = {
    ("METRIC", "LENGTH"): (("km", 1e3, "km"), ("m", 1.0, "m"), ("cm", 1e-2, "cm"), ("mm", 1e-3, "mm"),
                           ("µm", 1e-6, "um")),
    ("IMPERIAL", "LENGTH"): (("mi", 1609.344, "mi"), ("ft", 0.3048, "ft"), ("in", 0.0254, "in"),
                             ("thou", 2.54e-5, "thou")),
    ("METRIC", "MASS"): (("t", 1e3, "t"), ("kg", 1.0, "kg"), ("g", 1e-3, "g"), ("mg", 1e-6, "mg")),
    ("IMPERIAL", "MASS"): (("lb", 0.45359237, "lb"), ("oz", 0.028349523125, "oz")),
    ("METRIC", "AREA"): (("m²", 1.0, "m2"),),
    ("METRIC", "VOLUME"): (("m³", 1.0, "m3"),),
}
_ROTATION = (("°", math.pi / 180.0, "deg"),)
_TIME = (("s", 1.0, "s"), ("ms", 1e-3, "ms"))
_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_TERM = re.compile(rf"\s*({_NUMBER})\s*([^\s\d+\-.][^\s+\-]*)?")


def _check(unit_system: str, unit_category: str) -> None:
    if unit_system not in systems:
        raise ValueError(f"unknown unit system {unit_system!r}")
    if unit_category not in categories:
        raise ValueError(f"unknown unit category {unit_category!r}")


def _units(unit_system: str, unit_category: str) -> tuple[tuple[str, float, str], ...]:
    if unit_system == "NONE":
        return ()
    if unit_category == "ROTATION":
        return _ROTATION
    if unit_category == "TIME":
        return _TIME
    return _UNITS.get((unit_system, unit_category), ())


def _fmt(value: float, precision: int) -> str:
    text = f"{value:.{max(int(precision), 0)}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("-0", ""):
        text = "0"
    return text


def _pick(units: tuple[tuple[str, float, str], ...], value: float) -> int:
    if value == 0:
        return min(range(len(units)), key=lambda i: abs(math.log(units[i][1])))
    magnitude = abs(value)
    for i, (_sym, factor, _ascii) in enumerate(units):
        if magnitude >= factor * (1.0 - 1e-12):
            return i
    return len(units) - 1


def to_string(unit_system: str, unit_category: str, value: float, precision: int = 3, split_unit: bool = False,
              compatible_unit: bool = False) -> str:
    _check(unit_system, unit_category)
    value = float(value)
    units = _units(unit_system, unit_category)
    if not units:
        return _fmt(value, precision)

    def symbol(i: int) -> str:
        return units[i][2] if compatible_unit else units[i][0]

    idx = _pick(units, value)
    factor = units[idx][1]
    scaled = value / factor
    if not split_unit or idx + 1 >= len(units):
        return f"{_fmt(scaled, precision)} {symbol(idx)}"
    whole = math.trunc(scaled)
    rest = value - whole * factor
    next_factor = units[idx + 1][1]
    rest_text = _fmt(rest / next_factor, precision)
    head = f"{whole} {symbol(idx)}"
    if rest_text == "0":
        return head
    return f"{head} {rest_text} {symbol(idx + 1)}"


def _factor_of(units: tuple[tuple[str, float, str], ...], name: str) -> float | None:
    for sym, factor, ascii_sym in units:
        if name in (sym, ascii_sym):
            return factor
    return None


def to_value(unit_system: str, unit_category: str, str_input: str, str_ref_unit: str | None = None) -> float:
    _check(unit_system, unit_category)
    units = _units(unit_system, unit_category)
    text = str_input if isinstance(str_input, str) else ""
    ref_factor = 1.0
    if str_ref_unit:
        found = _factor_of(units, str_ref_unit)
        if found is None:
            raise ValueError(f"could not convert {str_input!r}: unknown reference unit {str_ref_unit!r}")
        ref_factor = found
    total = 0.0
    pos = 0
    terms = 0
    stripped = text.rstrip()
    while pos < len(stripped):
        match = _TERM.match(stripped, pos)
        if match is None or match.end() == pos:
            raise ValueError(f"could not convert {str_input!r} to a value")
        number, unit = match.group(1), match.group(2)
        if unit:
            factor = _factor_of(units, unit)
            if factor is None:
                raise ValueError(f"could not convert {str_input!r}: unknown unit {unit!r}")
        else:
            factor = ref_factor
        total += float(number) * factor
        terms += 1
        pos = match.end()
    if terms == 0:
        raise ValueError(f"could not convert {str_input!r} to a value")
    return total
