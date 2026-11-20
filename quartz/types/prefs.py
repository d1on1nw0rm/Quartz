from __future__ import annotations

import quartz.app
from quartz import registry
from quartz.app import paths as app_paths
from quartz.app import settings as app_settings
from quartz.app import translations
from quartz.errors import LinkError
from quartz.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, IntVectorProperty, PointerProperty, \
    StringProperty
from quartz.rna.annotations import iter_properties
from quartz.rna.collections import PropCollection
from quartz.rna.struct import Struct, builtin_struct

__all__ = [
    "Preferences", "Addons", "Addon", "AddonPreferences", "PreferencesEdit", "PreferencesView",
    "PreferencesFilePaths", "PreferencesExtensions", "UserExtensionRepo", "PreferencesSystem",
    "PreferencesInput", "PreferencesExperimental", "PreferencesKeymap",
]

_ACTIVE_SECTIONS: tuple[str, ...] = (
    "INTERFACE", "VIEWPORT", "LIGHTS", "EDITING", "ANIMATION", "EXTENSIONS", "ADDONS", "THEMES", "ASSETS",
    "INPUT", "NAVIGATION", "KEYMAP", "SYSTEM", "SAVE_LOAD", "FILE_PATHS", "DEVELOPER_TOOLS", "EXPERIMENTAL",
)


def _items(ids):
    return [(i, i.replace("_", " ").title(), "") for i in ids]


class _EmptyCollection(PropCollection):

    def _q_items(self):
        return ()


def _empty_member(self, attr: str, path: str) -> PropCollection:
    coll = self.__dict__.get(attr)
    if coll is None:
        coll = _EmptyCollection(owner=self, path=path)
        object.__setattr__(self, attr, coll)
    return coll


@builtin_struct
class AddonPreferences(Struct):
    _q_registrable = True

    @property
    def layout(self):
        return getattr(self, "_q_layout", None)


@builtin_struct
class Addon(Struct):
    _q_strict_attrs = True

    module: StringProperty(name="Module", maxlen=128, options=set())

    @property
    def preferences(self) -> AddonPreferences | None:
        chosen = None
        for klass in registry.iter_classes(AddonPreferences):
            if getattr(klass, "bl_idname", None) == self.module:
                chosen = klass
        if chosen is None:
            return None
        cached = self.__dict__.get("_q_prefs")
        if cached is not None and cached[0] is chosen:
            return cached[1]
        inst = chosen._q_new_child(owner=self, path="preferences")
        object.__setattr__(self, "_q_prefs", (chosen, inst))
        return inst


class Addons(PropCollection):

    def __init__(self, *, owner: object = None, path: str = "addons") -> None:
        super().__init__(owner=owner, path=path)
        self._items: list[Addon] = []

    def _q_items(self):
        return tuple(self._items)

    def _q_key(self, item):
        return item.module

    def new(self) -> Addon:
        addon = Addon._q_new_child(owner=self._owner, path=f"addons[{len(self._items)}]")
        self._items.append(addon)
        return addon

    def remove(self, addon: Addon) -> None:
        for i, item in enumerate(self._items):
            if item is addon:
                del self._items[i]
                for j, rest in enumerate(self._items):
                    rest._q_set_owner(self._owner, f"addons[{j}]")
                return
        raise LinkError(f"Addon '{getattr(addon, 'module', addon)}' not found in preferences")

    def _q_clear(self) -> None:
        for item in self._items:
            item.__dict__.pop("_q_prefs", None)
        self._items.clear()


def _get_undo_steps(self) -> int:
    return int(app_settings.settings.undo_steps)


def _set_undo_steps(self, value: int) -> None:
    app_settings.settings.undo_steps = int(value)


@builtin_struct
class PreferencesEdit(Struct):
    _q_strict_attrs = True

    use_global_undo: BoolProperty(name="Global Undo", default=True)
    undo_steps: IntProperty(name="Undo Steps", min=0, max=256, default=32,
                            meta={"virtual_get": _get_undo_steps, "virtual_set": _set_undo_steps})
    undo_memory_limit: IntProperty(name="Undo Memory Size", min=0, max=2147483647, default=0)


def _language_items(self, context):
    return [("DEFAULT", "Automatic (Automatic)", "")] + [(loc, loc, "") for loc in translations.locales]


def _get_language(self) -> str:
    return translations.locale


def _set_language(self, value: str) -> None:
    translations.set_locale("en_US" if value == "DEFAULT" else value)


@builtin_struct
class PreferencesView(Struct):
    _q_strict_attrs = True

    ui_scale: FloatProperty(name="Resolution Scale", default=1.0, min=0.25, max=4.0)
    show_developer_ui: BoolProperty(name="Developer Extras", default=False)
    show_tooltips: BoolProperty(name="Tooltips", default=True)
    language: EnumProperty(items=_language_items, name="Language",
                           meta={"virtual_get": _get_language, "virtual_set": _set_language})


@builtin_struct
class PreferencesFilePaths(Struct):
    _q_strict_attrs = True

    temporary_directory: StringProperty(name="Temporary Directory", subtype="DIR_PATH", options=set(),
                                        meta={"virtual_get": lambda self: str(app_paths.temp_dir())})

    @property
    def script_directories(self) -> PropCollection:
        return _empty_member(self, "_q_script_dirs", "script_directories")

    @property
    def asset_libraries(self) -> PropCollection:
        return _empty_member(self, "_q_asset_libs", "asset_libraries")


@builtin_struct
class UserExtensionRepo(Struct):
    _q_strict_attrs = True

    name: StringProperty(name="Name", options=set(), meta={"virtual_get": lambda self: self._q_module})
    module: StringProperty(name="Module", options=set(), meta={"virtual_get": lambda self: self._q_module})
    directory: StringProperty(name="Directory", subtype="DIR_PATH", options=set(),
                              meta={"virtual_get": lambda self: self._q_directory})
    enabled: BoolProperty(name="Enabled", meta={"virtual_get": lambda self: True})
    source: EnumProperty(items=[("USER", "User", ""), ("SYSTEM", "System", "")], name="Source",
                         meta={"virtual_get": lambda self: "SYSTEM" if self._q_module == "system" else "USER"})
    use_remote_url: BoolProperty(name="Use Remote", meta={"virtual_get": lambda self: False})


class _Repos(PropCollection):

    def __init__(self, *, owner: object, path: str) -> None:
        super().__init__(owner=owner, path=path)
        self._cache: dict[str, UserExtensionRepo] = {}

    def _q_items(self):
        out = []
        for i, (module, directory) in enumerate(app_paths.extension_repos().items()):
            repo = self._cache.get(module)
            if repo is None:
                repo = UserExtensionRepo._q_new_child(owner=self._owner, path=f"repos[{i}]")
                object.__setattr__(repo, "_q_module", module)
                self._cache[module] = repo
            object.__setattr__(repo, "_q_directory", str(directory))
            out.append(repo)
        return tuple(out)

    def _q_key(self, item):
        return item._q_module


@builtin_struct
class PreferencesExtensions(Struct):
    _q_strict_attrs = True

    @property
    def repos(self) -> PropCollection:
        coll = self.__dict__.get("_q_repos")
        if coll is None:
            coll = _Repos(owner=self, path="repos")
            object.__setattr__(self, "_q_repos", coll)
        return coll


@builtin_struct
class PreferencesSystem(Struct):
    _q_strict_attrs = True


@builtin_struct
class PreferencesInput(Struct):
    _q_strict_attrs = True


@builtin_struct
class PreferencesExperimental(Struct):
    _q_strict_attrs = True


@builtin_struct
class PreferencesKeymap(Struct):
    _q_strict_attrs = True


def _get_version(self):
    return tuple(quartz.app.version)


@builtin_struct
class Preferences(Struct):
    _q_strict_attrs = True

    active_section: EnumProperty(items=_items(_ACTIVE_SECTIONS), name="Active Section", default="INTERFACE")
    app_template: StringProperty(name="Application Template", maxlen=64, options=set())
    use_recent_searches: BoolProperty(name="Recent Searches", default=True)
    show_hidden_ids: BoolProperty(name="Show Hidden IDs", default=False)
    view: PointerProperty(type=PreferencesView, name="View & Controls", options=set())
    edit: PointerProperty(type=PreferencesEdit, name="Edit Methods", options=set())
    inputs: PointerProperty(type=PreferencesInput, name="Inputs", options=set())
    keymap: PointerProperty(type=PreferencesKeymap, name="Keymap", options=set())
    filepaths: PointerProperty(type=PreferencesFilePaths, name="File Paths", options=set())
    extensions: PointerProperty(type=PreferencesExtensions, name="Extensions", options=set())
    system: PointerProperty(type=PreferencesSystem, name="System & OpenGL", options=set())
    experimental: PointerProperty(type=PreferencesExperimental, name="Experimental", options=set())
    version: IntVectorProperty(name="Version", subtype="XYZ", size=3, min=0, meta={"virtual_get": _get_version})
    use_preferences_save: BoolProperty(name="Auto-Save Preferences", default=False)
    is_dirty: BoolProperty(name="Dirty", default=False)

    @property
    def addons(self) -> Addons:
        coll = self.__dict__.get("_q_addons")
        if coll is None:
            coll = Addons(owner=self, path="addons")
            object.__setattr__(self, "_q_addons", coll)
        return coll

    @property
    def themes(self) -> PropCollection:
        return _empty_member(self, "_q_themes", "themes")

    @property
    def ui_styles(self) -> PropCollection:
        return _empty_member(self, "_q_ui_styles", "ui_styles")

    @property
    def autoexec_paths(self) -> PropCollection:
        return _empty_member(self, "_q_autoexec_paths", "autoexec_paths")

    def q_reset(self) -> None:
        _reset_struct(self)
        self.addons._q_clear()


def _reset_struct(inst: Struct) -> None:
    for pdef in list(iter_properties(type(inst))):
        ident = pdef.identifier
        if pdef.kind == "POINTER" and not pdef.is_id_pointer:
            child = inst._p.get(ident)
            if isinstance(child, Struct):
                _reset_struct(child)
            continue
        if pdef.kind == "COLLECTION":
            continue
        inst.property_unset(ident)


registry.register_base(AddonPreferences, kind="GENERIC", required=(), rna_name=lambda cls: cls.__name__,
                       callbacks={})
