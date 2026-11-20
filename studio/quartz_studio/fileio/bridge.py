from __future__ import annotations

import copy

import numpy as np

from ..scene import EDITABLE_KIND, MODES, Mesh, Scene, SceneObject
from .model import Document, Node, decompose
from .registry import FileFormatError

__all__ = [
    "document_from_scene",
    "full_document_from_scene",
    "add_document_to_scene",
    "replace_scene",
]


def _meta() -> dict:
    return {"unit": "cm", "up": "y", "handedness": "right", "source": "Quartz Studio"}


def _has_geometry(mesh: Mesh) -> bool:
    return len(mesh.points) > 0 and bool(mesh.polygons or mesh.loose_edges)


def _copy(mesh: Mesh, scales: bool = True) -> Mesh:
    return Mesh(mesh.points.copy(), list(mesh.polygons), list(mesh.loose_edges),
                point_scales=mesh.point_scales if scales else None)


def document_from_scene(scene: Scene, selected_only: bool = False) -> Document:
    objects = scene.render_objects()
    if selected_only:
        keep = set()
        for chosen in scene.selected_objects():
            keep |= {id(chosen)} | {id(d) for d in scene.descendants(chosen)}
        objects = [o for o in objects if id(o) in keep]
    nodes = [Node(o.name, _copy(o.mesh, scales=False), o.world_matrix(), None)
             for o in objects if _has_geometry(o.mesh)]
    return Document(nodes, _meta())


def full_document_from_scene(scene: Scene, view: dict | None = None) -> Document:
    index = {id(o): i for i, o in enumerate(scene.objects)}
    nodes = []
    for o in scene.objects:
        editable = o.kind == EDITABLE_KIND
        nodes.append(Node(
            o.name,
            _copy(o.mesh) if editable else None,
            o.world_matrix(),
            index[id(o.parent)] if o.parent is not None else None,
            o.kind,
            dict(o.params) if not editable else None,
            o.enabled,
            tuple(float(v) for v in o.position),
            tuple(float(v) for v in o.rotation),
            tuple(float(v) for v in o.scale),
        ))
        if o.extras:
            nodes[-1].extras = copy.deepcopy(o.extras)
    meta = _meta()
    meta["active"] = index[id(scene.active)] if scene.active in scene.objects else None
    meta["selected"] = bool(scene.object_selected)
    chosen = scene.selected_objects()
    if len(chosen) > 1:
        meta["selection"] = [index[id(o)] for o in chosen]
    meta["mode"] = scene.mode
    if view is not None:
        meta["view"] = view
    if scene.extras:
        meta["extras"] = copy.deepcopy(scene.extras)
    return Document(nodes, meta)


def _local_transform(node: Node, nodes: list[Node]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    given = (node.position, node.rotation, node.scale)
    if all(v is not None for v in given):
        return tuple(np.array(v, float) for v in given)
    local = np.array(node.matrix, float)
    if node.parent is not None:
        try:
            local = np.linalg.inv(nodes[node.parent].matrix) @ local
        except np.linalg.LinAlgError:
            pass
    solved = decompose(local)
    return tuple(np.array(g, float) if g is not None else s for g, s in zip(given, solved))


def _make_object(node: Node) -> SceneObject:
    from ..objects import registry as objects_registry
    spec = objects_registry.SPECS.get(node.kind) if node.kind != EDITABLE_KIND else None
    name = node.name or "Object"
    if spec is not None and node.params is not None:
        try:
            params = spec.clamp(dict(node.params))
        except (TypeError, ValueError):
            params = spec.defaults()
        return SceneObject(name, Mesh.empty(), spec.id, params)
    if node.mesh is None:
        null = objects_registry.SPECS.get("null")
        if null is not None:
            return SceneObject(name, Mesh.empty(), null.id, null.defaults())
        return SceneObject(name, Mesh.empty())
    return SceneObject(name, _copy(node.mesh))


def _build(document: Document) -> tuple[list[SceneObject], list[int | None]]:
    nodes = document.nodes
    parents: list[int | None] = []
    objs: list[SceneObject] = []
    for node in nodes:
        p = node.parent
        if p is not None and (not isinstance(p, (int, np.integer)) or not 0 <= p < len(nodes)):
            raise FileFormatError(f"{node.name or 'Object'}: invalid parent index {p!r}")
        parents.append(None if p is None else int(p))
        obj = _make_object(node)
        position, rotation, scale = _local_transform(node, nodes)
        obj.position, obj.rotation, obj.scale = position, rotation, scale
        obj.enabled = bool(node.enabled)
        extras = getattr(node, "extras", None)
        if isinstance(extras, dict):
            obj.extras = copy.deepcopy(extras)
        objs.append(obj)
    return objs, parents


def add_document_to_scene(scene: Scene, document: Document) -> list[SceneObject]:
    objs, parents = _build(document)
    try:
        return scene.insert_objects(objs, parents, activate=True)
    except ValueError as exc:
        raise FileFormatError(str(exc)) from exc


def replace_scene(scene: Scene, document: Document) -> None:
    objs, parents = _build(document)
    try:
        scene.insert_objects(objs, parents, activate=False, replace=True)
    except ValueError as exc:
        raise FileFormatError(str(exc)) from exc
    meta = document.meta
    active = meta.get("active")
    selected = meta.get("selected")
    selected = True if not isinstance(selected, bool) else selected
    if isinstance(active, int) and not isinstance(active, bool) and 0 <= active < len(objs):
        scene.set_active(objs[active], select=selected)
    elif "active" in meta and active is None:
        scene.set_active(None)
    elif objs:
        scene.set_active(objs[0], select=selected)
    chosen = meta.get("selection")
    if selected and scene.active is not None and isinstance(chosen, list):
        picked = [objs[i] for i in chosen
                  if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(objs)]
        if len(picked) > 1:
            scene.select_objects(picked + [scene.active], "replace", active=scene.active)
    mode = meta.get("mode")
    if isinstance(mode, str) and mode in MODES:
        scene.set_mode(mode)
    extras = meta.get("extras")
    if isinstance(extras, dict):
        scene.extras = copy.deepcopy(extras)
    scene.clear_history()
