from quartz.errors import LinkError, PropertyTypeError
from quartz.props import BoolProperty, EnumProperty, FloatVectorProperty
from quartz.rna import IDRef, PropCollection, builtin_struct
from quartz.types.blenddata import IDCollection
from quartz.types.id import ID, register_id_type

__all__ = [
    "Collection", "CollectionObjects", "CollectionChildren", "BlendDataCollections",
]

_COLOR_TAGS = ("NONE", "COLOR_01", "COLOR_02", "COLOR_03", "COLOR_04", "COLOR_05", "COLOR_06", "COLOR_07",
               "COLOR_08")
_VIS = {"dirty": "VISIBILITY"}


def _is_object(value) -> bool:
    return getattr(type(value), "q_id_type", "") == "OBJECT" and getattr(type(value), "_q_is_id", False)


def _check_live(value) -> None:
    if getattr(type(value), "_q_removed", False):
        value.name


class CollectionObjects(PropCollection):

    def __init__(self, coll: "Collection") -> None:
        super().__init__(owner=coll, path="objects")
        self._q_coll = coll

    def _q_items(self):
        return self._q_coll._q_objects

    def _q_key(self, item):
        return item._q_name

    def link(self, object) -> None:
        coll = self._q_coll
        _check_live(object)
        if not _is_object(object):
            raise PropertyTypeError(f"CollectionObjects.link(): error with argument 1, \"object\" - "
                                    f"expected a Object type, not {type(object).__name__}")
        if any(o is object for o in coll._q_objects):
            raise LinkError(f"Object '{object._q_name}' already in collection '{coll._q_name}'")
        coll._q_objects.append(object)
        coll.q_tag("HIERARCHY")
        object.q_tag("HIERARCHY")

    def unlink(self, object) -> None:
        coll = self._q_coll
        _check_live(object)
        if not _is_object(object):
            raise PropertyTypeError(f"CollectionObjects.unlink(): error with argument 1, \"object\" - "
                                    f"expected a Object type, not {type(object).__name__}")
        for i, o in enumerate(coll._q_objects):
            if o is object:
                del coll._q_objects[i]
                coll.q_tag("HIERARCHY")
                object.q_tag("HIERARCHY")
                return
        raise LinkError(f"Object '{object._q_name}' not in collection '{coll._q_name}'")


class CollectionChildren(PropCollection):

    def __init__(self, coll: "Collection") -> None:
        super().__init__(owner=coll, path="children")
        self._q_coll = coll

    def _q_items(self):
        return self._q_coll._q_children

    def _q_key(self, item):
        return item._q_name

    def link(self, child) -> None:
        coll = self._q_coll
        _check_live(child)
        if not isinstance(child, Collection):
            raise PropertyTypeError(f"CollectionChildren.link(): error with argument 1, \"child\" - "
                                    f"expected a Collection type, not {type(child).__name__}")
        if child._q_embedded_owner is not None:
            raise LinkError(f"Collection '{child._q_name}' is embedded in a scene and can not be linked")
        if any(c is child for c in coll._q_children):
            raise LinkError(f"Collection '{child._q_name}' already in collection '{coll._q_name}'")
        if child is coll or coll in child._q_descendants():
            raise LinkError(f"Collection '{child._q_name}' can not be linked into '{coll._q_name}': cycle detected")
        coll._q_children.append(child)
        coll.q_tag("HIERARCHY")
        child.q_tag("HIERARCHY")

    def unlink(self, child) -> None:
        coll = self._q_coll
        _check_live(child)
        if not isinstance(child, Collection):
            raise PropertyTypeError(f"CollectionChildren.unlink(): error with argument 1, \"child\" - "
                                    f"expected a Collection type, not {type(child).__name__}")
        for i, c in enumerate(coll._q_children):
            if c is child:
                del coll._q_children[i]
                coll.q_tag("HIERARCHY")
                child.q_tag("HIERARCHY")
                return
        raise LinkError(f"Collection '{child._q_name}' not in collection '{coll._q_name}'")


def _get_main(self):
    owner = self.__dict__.get("_q_embedded_owner")
    if owner is not None:
        return owner._q_main
    return self.__dict__.get("_q_main_store")


def _set_main(self, value):
    self.__dict__["_q_main_store"] = value


@builtin_struct
class Collection(ID):

    _q_strict_attrs = True
    _q_main = property(_get_main, _set_main)

    hide_select: BoolProperty(options=set(), meta=_VIS)
    hide_viewport: BoolProperty(options=set(), meta=_VIS)
    hide_render: BoolProperty(options=set(), meta=_VIS)
    color_tag: EnumProperty(items=[(t, t, "") for t in _COLOR_TAGS], default="COLOR_01")
    instance_offset: FloatVectorProperty(subtype="TRANSLATION", unit="LENGTH", size=3, soft_min=-10000.0,
                                         soft_max=10000.0, step=10.0, precision=5)

    @classmethod
    def _q_construct(cls, name: str):
        inst = super()._q_construct(name)
        object.__setattr__(inst, "_q_objects", [])
        object.__setattr__(inst, "_q_children", [])
        object.__setattr__(inst, "_q_objects_coll", CollectionObjects(inst))
        object.__setattr__(inst, "_q_children_coll", CollectionChildren(inst))
        return inst

    @property
    def objects(self) -> CollectionObjects:
        return self._q_objects_coll

    @property
    def children(self) -> CollectionChildren:
        return self._q_children_coll

    def _q_descendants(self) -> list:
        out: list = []
        seen: set[int] = set()

        def walk(c):
            for child in c._q_children:
                if id(child) not in seen:
                    seen.add(id(child))
                    out.append(child)
                    walk(child)
        walk(self)
        return out

    @property
    def all_objects(self) -> tuple:
        out: list = []
        seen: set[int] = set()
        seen_colls: set[int] = set()

        def walk(c):
            if id(c) in seen_colls:
                return
            seen_colls.add(id(c))
            for ob in c._q_objects:
                if id(ob) not in seen:
                    seen.add(id(ob))
                    out.append(ob)
            for child in c._q_children:
                walk(child)
        walk(self)
        return tuple(out)

    @property
    def children_recursive(self) -> list:
        return self._q_descendants()

    @property
    def users_dupli_group(self) -> tuple:
        main = self._q_main
        if main is None:
            return ()
        return tuple(ob for ob in main.objects if ob._p.get("instance_collection") is self)

    def _q_refs(self):
        yield from super()._q_refs()
        for ob in list(self._q_objects):
            yield IDRef(ob, self, "COLLECTION_OBJECT", True, "CLEAR", *_link_closures(self, "_q_objects", ob))
        for child in list(self._q_children):
            yield IDRef(child, self, "COLLECTION_CHILD", True, "CLEAR", *_link_closures(self, "_q_children", child))

    def _q_state_get(self) -> dict:
        state = super()._q_state_get()
        state["objects"] = list(self._q_objects)
        state["children"] = list(self._q_children)
        return state

    def _q_state_set(self, state: dict) -> None:
        super()._q_state_set(state)
        if "objects" in state:
            self._q_objects[:] = list(state["objects"])
        if "children" in state:
            self._q_children[:] = list(state["children"])


def _link_closures(coll: Collection, attr: str, target):
    def clear():
        items = getattr(coll, attr)
        for i, cur in enumerate(items):
            if cur is target:
                del items[i]
                break
        coll.q_tag("HIERARCHY")

    def remap(new):
        items = getattr(coll, attr)
        if any(cur is new for cur in items):
            for i, cur in enumerate(items):
                if cur is target:
                    del items[i]
                    break
        else:
            for i, cur in enumerate(items):
                if cur is target:
                    items[i] = new
                    break
        coll.q_tag("HIERARCHY")
    return clear, remap


class BlendDataCollections(IDCollection):

    def new(self, name: str) -> Collection:
        return super().new(name)

    def remove(self, collection: Collection, do_unlink: bool = True, do_id_user: bool = True,
               do_ui_user: bool = True) -> None:
        super().remove(collection, do_unlink, do_id_user, do_ui_user)


register_id_type(Collection, id_type="COLLECTION", collection="collections", default_name="Collection",
                 collection_cls=BlendDataCollections)
