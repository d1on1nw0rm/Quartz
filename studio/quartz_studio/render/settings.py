from __future__ import annotations

import copy
from typing import Any

from .. import theme
from ..ext import store

__all__ = [
    "SETTINGS_KEY",
    "PRESETS",
    "AA_LEVELS",
    "FORMATS",
    "PASSES",
    "TONEMAPS",
    "BACKGROUNDS",
    "DEFAULT_LIGHTS",
    "BUCKET_ORDERS",
    "default_settings",
    "clean_settings",
    "get_settings",
    "set_settings",
    "update_settings",
    "resolution",
    "frame_list",
    "hex_to_rgb",
    "rgb_to_hex",
]

SETTINGS_KEY = "render"

PRESETS = {
    "640x360": (640, 360),
    "1280x720": (1280, 720),
    "1920x1080": (1920, 1080),
    "Custom": None,
}
AA_LEVELS = (1, 2, 4)
FORMATS = ("png", "jpg")
PASSES = ("beauty", "depth", "normal", "albedo", "ao")
TONEMAPS = ("standard", "filmic", "aces")
BACKGROUNDS = ("color", "gradient", "transparent")
DEFAULT_LIGHTS = ("auto", "on", "off")
BUCKET_ORDERS = ("spiral", "rows")
MAX_SIZE = 4096
MAX_TRANSPARENCY = 8


def hex_to_rgb(text: str) -> list[float]:
    t = str(text).lstrip("#")
    if len(t) != 6:
        return [0.0, 0.0, 0.0]
    return [int(t[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]


def rgb_to_hex(rgb) -> str:
    vals = [max(0, min(255, int(round(float(c) * 255.0)))) for c in list(rgb)[:3]]
    return "#" + "".join(f"{v:02x}" for v in vals)


def default_settings() -> dict:
    return {
        "preset": "640x360",
        "width": 640,
        "height": 360,
        "aa": 1,
        "output_path": "",
        "format": "png",
        "jpg_quality": 92,
        "auto_save": False,
        "save_passes": False,
        "passes": ["beauty", "depth", "normal", "albedo", "ao"],
        "camera": "",
        "camera_id": "",
        "animation": False,
        "frame_start": 0,
        "frame_end": 0,
        "frame_step": 1,
        "background": "gradient",
        "bg_color": hex_to_rgb(theme.VIEWPORT_BOTTOM),
        "bg_top": hex_to_rgb(theme.VIEWPORT_TOP),
        "bg_bottom": hex_to_rgb(theme.VIEWPORT_BOTTOM),
        "sky_color": [0.62, 0.68, 0.78],
        "ground_color": [0.22, 0.2, 0.19],
        "ambient": 0.25,
        "default_lights": "auto",
        "shadows": True,
        "shadow_map": 1024,
        "shadow_softness": 1.5,
        "ao": True,
        "ao_radius": 40.0,
        "ao_samples": 12,
        "ao_strength": 1.0,
        "tonemap": "filmic",
        "exposure": 0.0,
        "gamma": 2.2,
        "auto_phong": False,
        "phong_angle": 80.0,
        "backface_culling": False,
        "transparency_depth": 4,
        "bucket_size": 64,
        "bucket_order": "spiral",
        "seed": 1,
    }


def _num(value: Any, default: float, lo: float | None = None, hi: float | None = None) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return float(default)
    if v != v:
        return float(default)
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def _int(value: Any, default: int, lo: int | None = None, hi: int | None = None) -> int:
    return int(round(_num(value, default, lo, hi)))


def _color(value: Any, default: list) -> list[float]:
    if isinstance(value, str):
        return hex_to_rgb(value)
    try:
        vals = [float(v) for v in value][:3]
    except (TypeError, ValueError):
        return list(default)
    if len(vals) != 3:
        return list(default)
    return [max(0.0, min(1.0, v)) for v in vals]


def _choice(value: Any, choices, default):
    return value if value in choices else default


def clean_settings(values: dict | None) -> dict:
    base = default_settings()
    src = dict(values or {})
    out = dict(base)
    preset = _choice(src.get("preset", base["preset"]), PRESETS, base["preset"])
    out["preset"] = preset
    if PRESETS[preset] is not None:
        out["width"], out["height"] = PRESETS[preset]
    else:
        out["width"] = _int(src.get("width", base["width"]), base["width"], 16, MAX_SIZE)
        out["height"] = _int(src.get("height", base["height"]), base["height"], 16, MAX_SIZE)
    aa = _int(src.get("aa", base["aa"]), base["aa"])
    out["aa"] = aa if aa in AA_LEVELS else min(AA_LEVELS, key=lambda a: abs(a - aa))
    out["output_path"] = str(src.get("output_path", "") or "")
    out["format"] = _choice(str(src.get("format", base["format"])).lower(), FORMATS, base["format"])
    out["jpg_quality"] = _int(src.get("jpg_quality", base["jpg_quality"]), base["jpg_quality"], 1, 100)
    out["auto_save"] = bool(src.get("auto_save", base["auto_save"]))
    out["save_passes"] = bool(src.get("save_passes", base["save_passes"]))
    passes = src.get("passes", base["passes"])
    if isinstance(passes, (list, tuple, set)):
        chosen = [p for p in PASSES if p in passes]
    else:
        chosen = list(base["passes"])
    if "beauty" not in chosen:
        chosen.insert(0, "beauty")
    out["passes"] = chosen
    out["camera"] = str(src.get("camera", "") or "")
    out["camera_id"] = str(src.get("camera_id", "") or "") if out["camera"] else ""
    out["animation"] = bool(src.get("animation", base["animation"]))
    fs = _int(src.get("frame_start", base["frame_start"]), 0, -100000, 100000)
    fe = _int(src.get("frame_end", base["frame_end"]), 0, -100000, 100000)
    out["frame_start"] = fs
    out["frame_end"] = max(fs, fe)
    out["frame_step"] = _int(src.get("frame_step", 1), 1, 1, 10000)
    out["background"] = _choice(src.get("background", base["background"]), BACKGROUNDS, base["background"])
    for key in ("bg_color", "bg_top", "bg_bottom", "sky_color", "ground_color"):
        out[key] = _color(src.get(key, base[key]), base[key])
    out["ambient"] = _num(src.get("ambient", base["ambient"]), base["ambient"], 0.0, 10.0)
    out["default_lights"] = _choice(src.get("default_lights", base["default_lights"]), DEFAULT_LIGHTS,
                                    base["default_lights"])
    out["shadows"] = bool(src.get("shadows", base["shadows"]))
    sm = _int(src.get("shadow_map", base["shadow_map"]), base["shadow_map"], 64, 4096)
    out["shadow_map"] = sm
    out["shadow_softness"] = _num(src.get("shadow_softness", base["shadow_softness"]),
                                  base["shadow_softness"], 0.0, 8.0)
    out["ao"] = bool(src.get("ao", base["ao"]))
    out["ao_radius"] = _num(src.get("ao_radius", base["ao_radius"]), base["ao_radius"], 0.01, 1.0e5)
    out["ao_samples"] = _int(src.get("ao_samples", base["ao_samples"]), base["ao_samples"], 1, 64)
    out["ao_strength"] = _num(src.get("ao_strength", base["ao_strength"]), base["ao_strength"], 0.0, 4.0)
    out["tonemap"] = _choice(src.get("tonemap", base["tonemap"]), TONEMAPS, base["tonemap"])
    out["exposure"] = _num(src.get("exposure", base["exposure"]), 0.0, -16.0, 16.0)
    out["gamma"] = _num(src.get("gamma", base["gamma"]), 2.2, 0.1, 5.0)
    out["auto_phong"] = bool(src.get("auto_phong", base["auto_phong"]))
    out["phong_angle"] = _num(src.get("phong_angle", base["phong_angle"]), 80.0, 0.0, 180.0)
    out["backface_culling"] = bool(src.get("backface_culling", base["backface_culling"]))
    out["transparency_depth"] = _int(src.get("transparency_depth", base["transparency_depth"]),
                                     base["transparency_depth"], 0, MAX_TRANSPARENCY)
    out["bucket_size"] = _int(src.get("bucket_size", base["bucket_size"]), 64, 16, 512)
    out["bucket_order"] = _choice(src.get("bucket_order", base["bucket_order"]), BUCKET_ORDERS,
                                  base["bucket_order"])
    out["seed"] = _int(src.get("seed", base["seed"]), 1, 0, 2 ** 31 - 1)
    return out


def get_settings(scene) -> dict:
    raw = store.get_scene_data(scene, SETTINGS_KEY)
    return clean_settings(raw if isinstance(raw, dict) else None)


def set_settings(scene, values: dict) -> dict:
    clean = clean_settings(values)
    store.set_scene_data(scene, SETTINGS_KEY, copy.deepcopy(clean))
    return clean


def update_settings(scene, **values) -> dict:
    current = get_settings(scene)
    if "camera" in values and "camera_id" not in values and values["camera"] != current.get("camera"):
        current["camera_id"] = ""
    current.update(values)
    if "width" in values or "height" in values:
        if "preset" not in values:
            size = (int(current.get("width", 0)), int(current.get("height", 0)))
            match = [k for k, v in PRESETS.items() if v == size]
            current["preset"] = match[0] if match else "Custom"
    return set_settings(scene, current)


def resolution(settings: dict) -> tuple[int, int]:
    s = clean_settings(settings)
    return int(s["width"]), int(s["height"])


def frame_list(settings: dict) -> list[int]:
    s = clean_settings(settings)
    if not s["animation"]:
        return [s["frame_start"]]
    return list(range(s["frame_start"], s["frame_end"] + 1, s["frame_step"]))
