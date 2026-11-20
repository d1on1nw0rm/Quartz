from __future__ import annotations

import itertools
import json
import math
import os

import numpy as np

from .. import __version__
from ..scene import EDITABLE_KIND, MODES, Mesh
from .bridge import _local_transform
from .model import Document, Node, compose, write_atomic
from .registry import FileFormat, FileFormatError, register

FORMAT_ID = "quartz"
VERSION = 1
EXTENSION = ".quartz"
LIMIT = 1e12


def _plain(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    raise FileFormatError(f"cannot store a value of type {type(value).__name__}")


def _json_checked(value, where: str):
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise FileFormatError(f"cannot store {where}: {value!r} is not a finite number")
        return float(value)
    if isinstance(value, (list, tuple)):
        return [_json_checked(v, where) for v in value]
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise FileFormatError(f"cannot store {where}: key {k!r} is not text")
            out[k] = _json_checked(v, where)
        return out
    raise FileFormatError(f"cannot store {where}: a value of type {type(value).__name__} is not JSON")


def _extras_to_json(extras, where: str) -> dict | None:
    if not extras:
        return None
    if not isinstance(extras, dict):
        raise FileFormatError(f"cannot store {where}: extras must be a dictionary")
    return _json_checked(extras, where)


def _mesh_to_json(mesh: Mesh) -> dict:
    polys = mesh.polygons
    sizes = np.fromiter((len(p) for p in polys), np.int64, len(polys))
    flat = np.fromiter(itertools.chain.from_iterable(polys), np.int64, int(sizes.sum()))
    loose = np.array(mesh.loose_edges, np.int64).reshape(-1)
    out = {
        "points": np.asarray(mesh.points, float).reshape(-1).tolist(),
        "polygon_sizes": sizes.tolist(),
        "polygon_indices": flat.tolist(),
        "loose_edges": loose.tolist(),
    }
    scales = mesh.point_scales
    if scales is not None:
        out["point_scales"] = np.asarray(scales, float).tolist()
    return out


def _node_to_json(node: Node, nodes: list[Node]) -> dict:
    position, rotation, scale = _local_transform(node, nodes)
    parametric = node.kind != EDITABLE_KIND and node.params is not None
    out = {
        "name": str(node.name),
        "kind": node.kind if parametric else EDITABLE_KIND,
        "parent": None if node.parent is None else int(node.parent),
        "enabled": bool(node.enabled),
        "position": [float(v) for v in position],
        "rotation": [float(v) for v in rotation],
        "scale": [float(v) for v in scale],
    }
    if parametric:
        out["params"] = dict(node.params)
    else:
        out["mesh"] = None if node.mesh is None else _mesh_to_json(node.mesh)
    extras = _extras_to_json(getattr(node, "extras", None), f"the extras of {node.name!r}")
    if extras is not None:
        out["extras"] = extras
    return out


def _selection(value, count: int) -> list[int]:
    if not isinstance(value, list):
        return []
    out: list[int] = []
    for i in value:
        if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < count and i not in out:
            out.append(int(i))
    return out if len(out) > 1 else []


def _payload(document: Document) -> dict:
    nodes = document.nodes
    meta = document.meta
    scene: dict = {"unit": "cm"}
    if "active" in meta:
        active = meta["active"]
        valid = isinstance(active, int) and not isinstance(active, bool) and 0 <= active < len(nodes)
        scene["active"] = int(active) if valid else None
    if isinstance(meta.get("selected"), bool):
        scene["selected"] = meta["selected"]
    chosen = _selection(meta.get("selection"), len(nodes))
    if chosen:
        scene["selection"] = chosen
    if isinstance(meta.get("mode"), str) and meta["mode"] in MODES:
        scene["mode"] = meta["mode"]
    scene["objects"] = [_node_to_json(n, nodes) for n in nodes]
    extras = _extras_to_json(meta.get("extras"), "the scene extras")
    if extras is not None:
        scene["extras"] = extras
    view = meta.get("view")
    return {
        "format": FORMAT_ID,
        "version": VERSION,
        "app": __version__,
        "scene": scene,
        "view": {} if view is None else view,
    }


def _encode(payload: dict) -> bytes:
    try:
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False,
                          default=_plain).encode("utf-8")
    except UnicodeEncodeError:
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=True,
                          default=_plain).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise FileFormatError(f"cannot store the project: {exc}") from exc


def save(path: str, document: Document, options: dict) -> None:
    write_atomic(path, _encode(_payload(document)))


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_index(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _vec3(value, default: tuple, fail, what: str) -> tuple:
    if value is None:
        return default
    if not isinstance(value, (list, tuple)) or len(value) != 3 or not all(_is_number(v) for v in value):
        fail(f"{what} must be three numbers")
    values = tuple(float(v) for v in value)
    if not all(math.isfinite(v) and abs(v) <= LIMIT for v in values):
        fail(f"{what} must be finite numbers no larger than {LIMIT:g}")
    return values


def _int_array(value, fail, what: str) -> np.ndarray:
    if not isinstance(value, list):
        fail(f"{what} must be a list")
    if not value:
        return np.zeros(0, np.int64)
    try:
        arr = np.array(value)
    except (TypeError, ValueError):
        fail(f"{what} must hold integers")
    if arr.ndim != 1 or arr.dtype.kind not in "iu":
        fail(f"{what} must hold integers")
    return arr.astype(np.int64, copy=False)


def _mesh_from_json(data, fail) -> Mesh:
    if not isinstance(data, dict):
        fail("mesh must be an object")
    raw = data.get("points", [])
    if not isinstance(raw, list):
        fail("mesh points must be a list")
    try:
        points = np.array(raw, dtype=float)
    except (TypeError, ValueError):
        fail("mesh points must be numbers")
    if points.size == 0:
        points = np.zeros((0, 3))
    if points.ndim != 1 and points.size:
        fail("mesh points must be a flat list")
    if points.size % 3:
        fail("mesh points must come in groups of three")
    points = points.reshape(-1, 3)
    if not np.isfinite(points).all():
        fail("mesh points must be finite numbers")
    count = len(points)
    sizes = _int_array(data.get("polygon_sizes", []), fail, "polygon_sizes")
    flat = _int_array(data.get("polygon_indices", []), fail, "polygon_indices")
    if len(sizes) and int(sizes.min()) < 3:
        fail("polygon_sizes must be at least 3 for every polygon")
    if int(sizes.sum()) != len(flat):
        fail("polygon_sizes does not match polygon_indices")
    if len(flat) and (int(flat.min()) < 0 or int(flat.max()) >= count):
        fail("a polygon uses a point that does not exist")
    loose = _int_array(data.get("loose_edges", []), fail, "loose_edges")
    if len(loose) % 2:
        fail("loose_edges must come in pairs")
    if len(loose) and (int(loose.min()) < 0 or int(loose.max()) >= count):
        fail("a loose edge uses a point that does not exist")
    ends = np.cumsum(sizes).tolist()
    starts = (np.cumsum(sizes) - sizes).tolist()
    items = flat.tolist()
    polygons = [tuple(items[a:b]) for a, b in zip(starts, ends)]
    scales = data.get("point_scales")
    if scales is not None:
        if not isinstance(scales, list) or len(scales) != count or not all(_is_number(v) for v in scales):
            fail("point_scales must hold one number per point")
        scales = np.array(scales, dtype=float)
        if not np.isfinite(scales).all() or float(np.abs(scales).max(initial=0.0)) > LIMIT:
            fail(f"point_scales must be finite numbers no larger than {LIMIT:g}")
    return Mesh(points, polygons, loose.reshape(-1, 2).tolist(), point_scales=scales)


def _world_matrices(locals_: list[np.ndarray], parents: list[int | None]) -> list[np.ndarray]:
    out: list[np.ndarray | None] = [None] * len(locals_)
    for i in range(len(locals_)):
        chain: list[int] = []
        seen: set[int] = set()
        j: int | None = i
        while j is not None and out[j] is None and j not in seen:
            seen.add(j)
            chain.append(j)
            j = parents[j]
        base = out[j] if j is not None and out[j] is not None else np.eye(4)
        for k in reversed(chain):
            base = base @ locals_[k]
            out[k] = base
    return out


def _parse_object(index: int, entry, count: int, warnings: list[str], specs: dict, name_of: str):
    def fail(message: str):
        raise FileFormatError(f"{name_of}: object {index}: {message}")

    if not isinstance(entry, dict):
        fail("must be an object")
    name = entry.get("name", "Object")
    if not isinstance(name, str):
        fail("name must be text")
    kind = entry.get("kind", EDITABLE_KIND)
    if not isinstance(kind, str):
        fail("kind must be text")
    parent = entry.get("parent")
    if parent is not None and (not _is_index(parent) or not 0 <= parent < count or parent == index):
        fail(f"invalid parent {parent!r}")
    position = _vec3(entry.get("position"), (0.0, 0.0, 0.0), fail, "position")
    rotation = _vec3(entry.get("rotation"), (0.0, 0.0, 0.0), fail, "rotation")
    scale = _vec3(entry.get("scale"), (1.0, 1.0, 1.0), fail, "scale")
    enabled = bool(entry.get("enabled", True))
    mesh = None
    params = None
    if kind == EDITABLE_KIND:
        if entry.get("mesh") is not None:
            mesh = _mesh_from_json(entry["mesh"], fail)
    elif kind not in specs:
        warnings.append(f"{name or 'Object'}: object type {kind!r} is not available in this build; "
                        f"loaded as an empty Null")
        kind = "null"
    else:
        raw = entry.get("params")
        if raw is not None and not isinstance(raw, dict):
            warnings.append(f"{name or 'Object'}: parameters of {kind!r} are invalid; defaults used")
            raw = None
        try:
            params = specs[kind].clamp(raw or {})
        except (TypeError, ValueError) as exc:
            warnings.append(f"{name or 'Object'}: parameters of {kind!r} are invalid ({exc}); defaults used")
            params = specs[kind].defaults()
    node = Node(name, mesh, np.eye(4), parent, kind, params, enabled, position, rotation, scale)
    extras = entry.get("extras")
    if extras is not None and not isinstance(extras, dict):
        warnings.append(f"{name or 'Object'}: extras are invalid and were ignored")
        extras = None
    if extras:
        node.extras = extras
    return node


def load(path: str) -> Document:
    name = os.path.basename(path)

    def fail(message: str):
        raise FileFormatError(f"{name}: {message}")

    with open(path, "rb") as handle:
        raw = handle.read()
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as exc:
        fail(f"not a Quartz project ({exc})")
    if not isinstance(data, dict):
        fail("not a Quartz project (the content is not an object)")
    if "format" not in data:
        fail("missing key 'format'")
    if data["format"] != FORMAT_ID:
        fail(f"not a Quartz project (format is {data['format']!r})")
    if "version" not in data:
        fail("missing key 'version'")
    version = data["version"]
    if not _is_index(version) or version < 1:
        fail(f"invalid version {version!r}")
    if version > VERSION:
        fail(f"this project was saved by a newer version of Quartz (file version {version}, "
             f"this build reads up to version {VERSION})")
    if "scene" not in data:
        fail("missing key 'scene'")
    scene = data["scene"]
    if not isinstance(scene, dict):
        fail("'scene' must be an object")
    if "objects" not in scene:
        fail("missing key 'objects' in 'scene'")
    entries = scene["objects"]
    if not isinstance(entries, list):
        fail("'objects' must be a list")

    from ..objects import registry as objects_registry
    specs = objects_registry.SPECS
    warnings: list[str] = []
    nodes = [_parse_object(i, e, len(entries), warnings, specs, name) for i, e in enumerate(entries)]
    for i in range(len(nodes)):
        seen = {i}
        j = nodes[i].parent
        while j is not None:
            if j in seen:
                fail(f"the hierarchy has a cycle at object {i} ({nodes[i].name!r})")
            seen.add(j)
            j = nodes[j].parent
    locals_ = [compose(n.position, n.rotation, n.scale) for n in nodes]
    worlds = _world_matrices(locals_, [n.parent for n in nodes])
    for node, world in zip(nodes, worlds):
        node.matrix = world

    app = data.get("app")
    meta: dict = {"unit": "cm", "up": "y", "handedness": "right", "source": "Quartz Studio",
                  "app": app if isinstance(app, str) else "", "version": version,
                  "warnings": warnings}
    if "active" in scene:
        active = scene["active"]
        if active is None or (_is_index(active) and 0 <= active < len(nodes)):
            meta["active"] = active
    if isinstance(scene.get("selected"), bool):
        meta["selected"] = scene["selected"]
    chosen = _selection(scene.get("selection"), len(nodes))
    if chosen:
        meta["selection"] = chosen
    elif scene.get("selection") is not None:
        warnings.append("the object selection is invalid and was ignored")
    if isinstance(scene.get("mode"), str) and scene["mode"] in MODES:
        meta["mode"] = scene["mode"]
    if "view" in data and data["view"] is not None:
        meta["view"] = data["view"]
    extras = scene.get("extras")
    if isinstance(extras, dict):
        if extras:
            meta["extras"] = extras
    elif extras is not None:
        warnings.append("scene extras are invalid and were ignored")
    return Document(nodes, meta)


register(FileFormat(FORMAT_ID, "Quartz Project", (EXTENSION,), load, save, "Quartz native project"))
