import os
from collections.abc import Mapping

locale: str = "en_US"
locales: tuple[str, ...] = ("en_US",)

_CONTEXT_VALUES: dict[str, str | None] = {
    "amount": "Amount",
    "color": "Color",
    "constraint": "Constraint",
    "countable": "Countable",
    "default": "*",
    "default_real": None,
    "editor_filebrowser": "File browser",
    "editor_preferences": "Preferences",
    "editor_python_console": "Python console",
    "editor_view3d": "View3D",
    "id_action": "Action",
    "id_armature": "Armature",
    "id_brush": "Brush",
    "id_cachefile": "CacheFile",
    "id_camera": "Camera",
    "id_collection": "Collection",
    "id_curve": "Curve",
    "id_curves": "Curves",
    "id_fs_linestyle": "FreestyleLineStyle",
    "id_gpencil": "GPencil",
    "id_id": "ID",
    "id_image": "Image",
    "id_lattice": "Lattice",
    "id_library": "Library",
    "id_light": "Light",
    "id_lightprobe": "LightProbe",
    "id_mask": "Mask",
    "id_material": "Material",
    "id_mesh": "Mesh",
    "id_metaball": "Metaball",
    "id_movieclip": "MovieClip",
    "id_nodetree": "NodeTree",
    "id_object": "Object",
    "id_paintcurve": "PaintCurve",
    "id_palette": "Palette",
    "id_particlesettings": "ParticleSettings",
    "id_pointcloud": "PointCloud",
    "id_scene": "Scene",
    "id_screen": "Screen",
    "id_sequence": "Sequence",
    "id_shapekey": "Key",
    "id_simulation": "Simulation",
    "id_sound": "Sound",
    "id_speaker": "Speaker",
    "id_text": "Text",
    "id_texture": "Texture",
    "id_vfont": "VFont",
    "id_volume": "Volume",
    "id_windowmanager": "WindowManager",
    "id_workspace": "WorkSpace",
    "id_world": "World",
    "modifier": "Modifier",
    "navigation": "Navigation",
    "no_translation": "Do not translate",
    "operator_default": "Operator",
    "plural": "Plural",
    "render_layer": "Render Layer",
    "time": "Time",
    "ui_events_keymaps": "UI_Events_KeyMaps",
    "unit": "Unit",
}

assert len(_CONTEXT_VALUES) == 60, len(_CONTEXT_VALUES)


class TranslationContexts:
    __slots__ = ("_m",)

    def __init__(self, mapping: dict[str, str | None]) -> None:
        self._m = dict(mapping)

    def __getattr__(self, name: str) -> object:
        if name == "_m":
            raise AttributeError
        if name in self._m:
            return self._m[name]
        raise AttributeError(f"TranslationContexts has no attribute {name!r}")

    def __iter__(self):
        return iter(self._m.values())

    def __contains__(self, name: object) -> bool:
        return name in self._m

    def __repr__(self) -> str:
        return f"TranslationContexts({len(self._m)})"


contexts: TranslationContexts = TranslationContexts(_CONTEXT_VALUES)

contexts_C_to_py: dict[str, str] = {
    f"BLT_I18NCONTEXT_{field.upper()}": field for field in _CONTEXT_VALUES
}

_REGISTRY: dict[str, Mapping] = {}


def _lookup(key: tuple[str, str]) -> str | None:
    for mod in _REGISTRY.values():
        if not isinstance(mod, Mapping):
            continue
        locale_map = mod.get(locale)
        if isinstance(locale_map, Mapping) and key in locale_map:
            return locale_map[key]
    return None


def pgettext(msgid: str, msgctxt: str | None = None) -> str:
    if locale == "en_US":
        return msgid
    primary_ctx = msgctxt if msgctxt is not None else "*"
    found = _lookup((primary_ctx, msgid))
    if found is None and msgctxt is not None:
        found = _lookup(("*", msgid))
    return msgid if found is None else found


def pgettext_iface(msgid: str, msgctxt: str | None = None) -> str:
    return pgettext(msgid, msgctxt)


def pgettext_tip(msgid: str, msgctxt: str | None = None) -> str:
    return pgettext(msgid, msgctxt)


def pgettext_rpt(msgid: str, msgctxt: str | None = None) -> str:
    return pgettext(msgid, msgctxt)


def pgettext_data(msgid: str, msgctxt: str | None = None) -> str:
    return pgettext(msgid, msgctxt)


def pgettext_n(msgid: str, msgctxt: str | None = None) -> str:
    return msgid


def register(module_name: str, translations_dict) -> None:
    _REGISTRY[module_name] = translations_dict


def unregister(module_name: str) -> None:
    _REGISTRY.pop(module_name, None)


def locale_explode(locale: str) -> tuple:
    if not locale:
        return (None, None, None, None, None)
    base, sep, variant = locale.partition("@")
    if "_" in base:
        lang, country = base.split("_", 1)
    else:
        lang = base
        country = None
    language_country = base if base else None
    language_variant = f"{lang}@{variant}" if variant else None
    v = variant if variant else None
    return (lang or None, country, v, language_country, language_variant)


def set_locale(name: str) -> None:
    global locale
    locale = name
