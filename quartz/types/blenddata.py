from bisect import bisect_right
from typing import Iterable, Iterator

import quartz.app as _app
import quartz.types as _types
from quartz.errors import LinkError, NotImplementedInQuartz, PropertyTypeError, RemovedStructError
from quartz.props import BoolProperty, IntVectorProperty, StringProperty
from quartz.rna import PropCollection, Struct, builtin_struct, hooks
from quartz.types.id import (DIRTY_CHANNELS, ID, IDTypeInfo, _api_prefix, _q_owner_id, dirty_clock, dirty_tick,
                             id_type_info)
from quartz.types.naming import sort_key, unique_name

__all__ = [
    "COLLECTION_NAMES", "IMPLEMENTED", "IDCollection", "PhantomIDCollection", "BlendData",
]

COLLECTION_NAMES: dict[str, str] = {
    "cameras": "BlendDataCameras", "scenes": "BlendDataScenes", "objects": "BlendDataObjects",
    "materials": "BlendDataMaterials", "node_groups": "BlendDataNodeTrees", "meshes": "BlendDataMeshes",
    "lights": "BlendDataLights", "libraries": "BlendDataLibraries", "screens": "BlendDataScreens",
    "window_managers": "BlendDataWindowManagers", "images": "BlendDataImages", "lattices": "BlendDataLattices",
    "curves": "BlendDataCurves", "metaballs": "BlendDataMetaBalls", "fonts": "BlendDataFonts",
    "textures": "BlendDataTextures", "brushes": "BlendDataBrushes", "worlds": "BlendDataWorlds",
    "collections": "BlendDataCollections", "shape_keys": "BlendDataShapeKeys", "texts": "BlendDataTexts",
    "speakers": "BlendDataSpeakers", "sounds": "BlendDataSounds", "armatures": "BlendDataArmatures",
    "actions": "BlendDataActions", "particles": "BlendDataParticles", "palettes": "BlendDataPalettes",
    "annotations": "BlendDataAnnotations", "grease_pencils": "BlendDataGreasePencilsV3",
    "movieclips": "BlendDataMovieClips", "masks": "BlendDataMasks", "linestyles": "BlendDataLineStyles",
    "cache_files": "BlendDataCacheFiles", "paint_curves": "BlendDataPaintCurves",
    "workspaces": "BlendDataWorkSpaces", "lightprobes": "BlendDataProbes", "hair_curves": "BlendDataHairCurves",
    "pointclouds": "BlendDataPointClouds", "volumes": "BlendDataVolumes", "all_ids": "IDs",
}

IMPLEMENTED: frozenset[str] = frozenset({
    "objects", "meshes", "materials", "cameras", "lights", "collections", "scenes", "worlds", "images", "texts",
    "window_managers", "screens", "workspaces",
})

_PURGE_KEEP = frozenset({"SCENE", "WINDOWMANAGER", "SCREEN", "WORKSPACE"})


def _is_removed(obj: object) -> bool:
    return bool(getattr(type(obj), "_q_removed", False))


def _raise_removed(obj: object) -> None:
    obj.name


class IDCollection(PropCollection):

    def __init__(self, main: "BlendData", info: IDTypeInfo) -> None:
        super().__init__(owner=main, path=info.collection)
        self._q_main = main
        self.q_info = info
        self._q_list: list = []

    def _q_items(self):
        return self._q_list

    def _q_key(self, item):
        return item._q_name

    def __repr__(self) -> str:
        return f"<bpy_collection[{len(self._q_list)}], {COLLECTION_NAMES.get(self.q_info.collection, type(self).__name__)}>"

    def _q_taken(self, name: str, exclude: object = None) -> bool:
        return any(i._q_name == name for i in self._q_list if i is not exclude)

    def _q_by_name(self, name: str, exclude: object = None):
        for item in self._q_list:
            if item is not exclude and item._q_name == name:
                return item
        return None

    def _q_insert_sorted(self, item) -> None:
        keys = [sort_key(i._q_name) for i in self._q_list]
        self._q_list.insert(bisect_right(keys, sort_key(item._q_name)), item)

    def _q_reposition(self, item) -> None:
        for i, cur in enumerate(self._q_list):
            if cur is item:
                del self._q_list[i]
                break
        self._q_insert_sorted(item)

    def new(self, name: str):
        if not isinstance(name, str):
            raise PropertyTypeError(f"{type(self).__name__}.new(): error with argument 1, \"name\" - "
                                    f"expected a string type, not {type(name).__name__}")
        info = self.q_info
        new_id = info.cls._q_construct(unique_name(name, lambda n: self._q_taken(n), default=info.default_name))
        self._q_link(new_id)
        new_id.q_tag(*DIRTY_CHANNELS)
        return new_id

    def remove(self, id, do_unlink: bool = True, do_id_user: bool = True, do_ui_user: bool = True) -> None:
        if _is_removed(id):
            _raise_removed(id)
        info = self.q_info
        if not isinstance(id, info.cls):
            raise PropertyTypeError(f"{type(self).__name__}.remove(): error with argument 1 - expected a "
                                    f"{info.cls.bl_rna.identifier} type, not {type(id).__name__}")
        if not any(i is id for i in self._q_list):
            raise LinkError(f"{type(self).__name__}.remove(): ID '{id._q_name}' is not in "
                            f"{_api_prefix()}.data.{info.collection}")
        if not do_unlink and id.users > 0:
            raise LinkError(f"{type(self).__name__}.remove(): ID '{id._q_name}' must have zero users to be removed, "
                            f"found {id.users}")
        self._q_main._q_remove_ids([id], cascade=True)

    def tag(self, value: bool) -> None:
        pdef = ID.__dict__["tag"]
        flag = bool(value)
        for item in self._q_list:
            pdef.write_raw(item, flag)

    def _q_link(self, id) -> None:
        self._q_insert_sorted(id)
        id._q_main = self._q_main

    def _q_unlink(self, id) -> None:
        for i, cur in enumerate(self._q_list):
            if cur is id:
                del self._q_list[i]
                return


class PhantomIDCollection(PropCollection):

    def __init__(self, main: "BlendData", attr: str) -> None:
        super().__init__(owner=main, path=attr)
        self._q_attr = attr

    def _q_items(self):
        return ()

    def __repr__(self) -> str:
        return f"<bpy_collection[0], {COLLECTION_NAMES[self._q_attr]}>"

    def _q_ni(self, method: str):
        return NotImplementedInQuartz(f"{_api_prefix()}.data.{self._q_attr}.{method}")

    def new(self, *args, **kwargs):
        raise self._q_ni("new")

    def remove(self, *args, **kwargs):
        raise self._q_ni("remove")

    def load(self, *args, **kwargs):
        raise self._q_ni("load")

    def tag(self, value: bool) -> None:
        return None


class _AllIDs(PropCollection):

    def __init__(self, main: "BlendData") -> None:
        super().__init__(owner=main, path="all_ids")
        self._q_main = main

    def _q_items(self):
        return list(self._q_main.q_iter_ids())

    def _q_key(self, item):
        return item._q_name

    def __repr__(self) -> str:
        return f"<bpy_collection[{len(self)}], IDs>"


def _get_filepath(self):
    return self._q_filepath


def _get_is_dirty(self):
    return dirty_clock() > self._q_clean_stamp


def _get_is_saved(self):
    return self._q_filepath != ""


@builtin_struct(identifier="BlendData")
class BlendData(Struct):

    _q_strict_attrs = True

    filepath: StringProperty(subtype="FILE_PATH", maxlen=1024, meta={"virtual_get": _get_filepath})
    is_dirty: BoolProperty(meta={"virtual_get": _get_is_dirty})
    is_saved: BoolProperty(meta={"virtual_get": _get_is_saved})
    use_autopack: BoolProperty()
    version: IntVectorProperty(subtype="XYZ", size=3, min=0, meta={"readonly": True})

    def __init__(self) -> None:
        _types.load_builtin_types()
        colls: dict[str, object] = {}
        for attr in COLLECTION_NAMES:
            if attr == "all_ids":
                colls[attr] = _AllIDs(self)
                continue
            info = id_type_info(attr)
            if info is not None and info.collection == attr:
                colls[attr] = (info.collection_cls or IDCollection)(self, info)
            else:
                colls[attr] = PhantomIDCollection(self, attr)
        self._q_colls = colls
        self._q_filepath = ""
        self._q_clean_stamp = dirty_clock()
        type(self).__dict__["version"].write_raw(self, _version_array(None))

    def batch_remove(self, ids: Iterable) -> None:
        ids = list(ids)
        for item in ids:
            if _is_removed(item):
                _raise_removed(item)
        for item in ids:
            coll = self.q_collection_for(item)
            if coll is None or not any(i is item for i in coll._q_list):
                raise LinkError(f"BlendData.batch_remove(): ID '{item._q_name}' is not in {_api_prefix()}.data")
        self._q_remove_ids(ids, cascade=True)

    def orphans_purge(self, do_local_ids: bool = True, do_linked_ids: bool = True, do_recursive: bool = False) -> int:
        if not do_local_ids:
            return 0
        total = 0
        while True:
            orphans = [x for x in self.q_iter_ids()
                       if type(x).q_id_type not in _PURGE_KEEP and x.users == 0]
            if not orphans:
                break
            self._q_remove_ids(orphans, cascade=False)
            total += len(orphans)
            if not do_recursive:
                break
        return total

    def user_map(self, subset: Iterable | None = None, key_types: set | None = None,
                 value_types: set | None = None) -> dict:
        keys = list(subset) if subset is not None else list(self.q_iter_ids())
        if key_types is not None:
            keys = [k for k in keys if type(k).q_id_type in key_types]
        result = {k: set() for k in keys}
        for user in self.q_iter_ids():
            for ref in user._q_refs():
                if ref.target not in result:
                    continue
                owner = _q_owner_id(ref.owner)
                if owner is None:
                    continue
                if value_types is not None and type(owner).q_id_type not in value_types:
                    continue
                result[ref.target].add(owner)
        return result

    def temp_data(self, filepath: str | None = None):
        raise NotImplementedInQuartz("BlendData.temp_data")

    def file_path_map(self, *a, **k):
        raise NotImplementedInQuartz("BlendData.file_path_map")

    def file_path_foreach(self, *a, **k):
        raise NotImplementedInQuartz("BlendData.file_path_foreach")

    def pack_linked_ids_hierarchy(self, root_id):
        raise NotImplementedInQuartz("BlendData.pack_linked_ids_hierarchy")

    def q_iter_ids(self, *, include_embedded: bool = False) -> Iterator:
        for attr in COLLECTION_NAMES:
            if attr not in IMPLEMENTED:
                continue
            coll = self._q_colls.get(attr)
            if not isinstance(coll, IDCollection):
                continue
            for item in list(coll._q_list):
                yield item
                if include_embedded:
                    master = item.__dict__.get("_q_master")
                    if master is not None:
                        yield master

    def q_collection_for(self, key):
        if isinstance(key, (type, str)):
            info = id_type_info(key)
        else:
            info = id_type_info(type(key))
        if info is None:
            return None
        coll = self._q_colls.get(info.collection)
        return coll if isinstance(coll, IDCollection) else None

    def q_refs_to(self, id) -> list:
        return [ref for x in self.q_iter_ids() for ref in x._q_refs() if ref.target is id]

    def q_users_of(self, id) -> int:
        return sum(1 for ref in self.q_refs_to(id) if ref.counts_user)

    def q_clear(self, *, keep: Iterable = ()) -> None:
        keep_ids = {id(k) for k in keep}
        removed = [x for x in self.q_iter_ids() if id(x) not in keep_ids]
        removed_ids = {id(x) for x in removed}
        for x in removed:
            coll = self.q_collection_for(x)
            if coll is not None:
                coll._q_unlink(x)
            x._q_main = None
        for x in self.q_iter_ids():
            for ref in list(x._q_refs()):
                if id(ref.target) in removed_ids:
                    ref.clear()
        for x in removed:
            master = x.__dict__.get("_q_master")
            x._q_tombstone()
            if master is not None:
                master._q_tombstone()

    def q_set_filepath(self, path: str) -> None:
        self._q_filepath = str(path)

    def q_mark_clean(self) -> None:
        self._q_clean_stamp = dirty_clock()

    def q_set_version(self, version=None) -> None:
        type(self).__dict__["version"].write_raw(self, _version_array(version))

    def _q_remove_ids(self, roots: list, *, cascade: bool) -> None:
        doomed: list = []
        doomed_ids: set[int] = set()

        def add(x):
            if id(x) not in doomed_ids:
                doomed_ids.add(id(x))
                doomed.append(x)
        for r in roots:
            add(r)
        if cascade:
            i = 0
            while i < len(doomed):
                for ref in self.q_refs_to(doomed[i]):
                    if ref.on_remove == "DELETE_OWNER":
                        owner = _q_owner_id(ref.owner)
                        if owner is not None:
                            add(owner)
                i += 1
        for x in doomed:
            for ref in self.q_refs_to(x):
                owner = _q_owner_id(ref.owner)
                if owner is not None and id(owner) in doomed_ids:
                    continue
                ref.clear()
        for x in doomed:
            coll = self.q_collection_for(x)
            if coll is not None:
                coll._q_unlink(x)
            master = x.__dict__.get("_q_master")
            x._q_main = None
            x._q_tombstone()
            if master is not None:
                master._q_tombstone()
        dirty_tick()


def _version_array(version):
    import numpy as np
    vals = tuple(_app.version) if version is None else tuple(int(v) for v in version)
    return np.array(vals, dtype=np.int32)


def _make_collection_getter(attr: str):
    def getter(self):
        coll = self._q_colls[attr]
        if isinstance(coll, PhantomIDCollection):
            hooks.note_missing(f"bpy.data.{attr}")
        return coll
    getter.__name__ = attr
    return property(getter)


for _attr in COLLECTION_NAMES:
    type.__setattr__(BlendData, _attr, _make_collection_getter(_attr))
del _attr
