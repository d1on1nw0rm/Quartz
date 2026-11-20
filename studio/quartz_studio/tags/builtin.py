from __future__ import annotations

import numpy as np

from ..ext import store
from .core import (MODE_FOR_TYPE, find_tags, restore_selection, selection_items,
                   store_selection, tag_at, update_tag, write_extra, write_hooks)
from .mathutil import (AIM_AXES, blend_rotation, decompose, look_rotation, orthonormal,
                       rotation_matrix)
from .registry import TagAction, TagParam, TagSpec, register_tag
from .runtime import MAX_SCALE_AMPLITUDE, base_transform, vibrate_offsets
from .shading import (PROJECTION_LABELS, PROJECTIONS, SHADING_MODES, SIDES, fit_projection,
                      generate_uvw, projection_label)

__all__ = ["CONSTRAINT_MODES", "PYTHON_TEMPLATE", "IK_SOLVERS", "IK_KEY", "normalize_weights",
           "migrate_material", "ik_record", "sync_ik", "set_point_weights", "SPEC_IDS"]

CONSTRAINT_MODES = ("Parent", "Position", "Rotation", "Aim")
PYTHON_PRIORITIES = ("Initial", "Animation", "Expressions", "Dynamics", "Generators")
PYTHON_TEMPLATE = "def main(op, frame):\n    pass\n"


def _vec(key, label, default, kind_unit="", group="Tag", minimum=None, maximum=None, step=1.0):
    return TagParam(key, label, "vector", list(default), minimum=minimum, maximum=maximum,
                    step=step, unit=kind_unit, group=group)


def migrate_material(tag: dict) -> None:
    if "offset" not in tag and ("offset_u" in tag or "offset_v" in tag):
        tag["offset"] = [float(tag.get("offset_u", 0.0)) / 100.0, float(tag.get("offset_v", 0.0)) / 100.0]
    if "tiling" not in tag and ("tiles_u" in tag or "tiles_v" in tag):
        tag["tiling"] = [float(tag.get("tiles_u", 1.0)), float(tag.get("tiles_v", 1.0))]
    for key in ("offset_u", "offset_v", "tiles_u", "tiles_v"):
        tag.pop(key, None)


def _material_create(scene, obj, tag) -> None:
    if obj is None or not len(obj.mesh.points):
        return
    lo, hi = obj.mesh.bounds()
    tag["proj_offset"] = [float(x) for x in (lo + hi) / 2.0]
    tag["proj_size"] = [float(x) for x in np.maximum((hi - lo) / 2.0, 1e-3)]


def _reset_projection(scene, obj, index):
    return update_tag(obj, index, proj_offset=[0.0, 0.0, 0.0], proj_rotation=[0.0, 0.0, 0.0],
                      proj_size=[100.0, 100.0, 100.0], offset=[0.0, 0.0], tiling=[1.0, 1.0])


def _material_summary(obj, tag) -> str:
    from .shading import material_polygons
    mat = tag.get("material") or "no material"
    return (f"{mat}, {projection_label(tag.get('projection', 'uvw'))}, "
            f"{len(material_polygons(obj, tag))} polygons")


MATERIAL = register_tag(TagSpec(
    id="material", label="Material", category="Rendering Tags", icon="material", menu_order=0,
    params=(
        TagParam("material", "Material", "text", "", group="Tag"),
        TagParam("selection", "Selection", "tag_ref", "", ref_type="polygon_selection", group="Tag"),
        TagParam("projection", "Projection", "choice", "uvw", choices=PROJECTIONS,
                 labels=PROJECTION_LABELS, group="Tag"),
        TagParam("side", "Side", "choice", "Both", choices=SIDES, group="Tag"),
        _vec("offset", "Offset", (0.0, 0.0), "", "Tiling", step=0.01),
        _vec("tiling", "Tiles", (1.0, 1.0), "", "Tiling", minimum=0.001, step=0.1),
        _vec("proj_offset", "Center", (0.0, 0.0, 0.0), "cm", "Projection"),
        _vec("proj_rotation", "Rotation", (0.0, 0.0, 0.0), "deg", "Projection"),
        _vec("proj_size", "Size", (100.0, 100.0, 100.0), "cm", "Projection", minimum=0.001),
    ),
    actions=(
        TagAction("fit", "Fit to Object", fit_projection),
        TagAction("generate_uvw", "Generate UVW", generate_uvw),
        TagAction("reset_projection", "Reset Projection", _reset_projection),
    ),
    on_create=_material_create,
    migrate=migrate_material,
    summary=_material_summary,
    description="Assigns a material and the projection that maps it onto the object",
))


COMPOSITING = register_tag(TagSpec(
    id="compositing", label="Compositing", category="Rendering Tags", icon="render_settings",
    unique=True, menu_order=1,
    params=(
        TagParam("cast_shadows", "Cast Shadows", "bool", True, group="Tag"),
        TagParam("receive_shadows", "Receive Shadows", "bool", True, group="Tag"),
        TagParam("self_shadowing", "Self Shadowing", "bool", True, group="Tag"),
        TagParam("seen_by_camera", "Seen by Camera", "bool", True, group="Visibility"),
        TagParam("seen_by_rays", "Seen by Rays", "bool", True, group="Visibility"),
        TagParam("seen_by_gi", "Seen by GI", "bool", True, group="Visibility"),
        TagParam("seen_by_transparency", "Seen by Transparency", "bool", True, group="Visibility"),
        TagParam("holdout", "Holdout", "bool", False, group="Visibility"),
    ),
    summary=lambda obj, tag: ", ".join(
        label for key, label in (("cast_shadows", "casts"), ("receive_shadows", "receives"),
                                 ("seen_by_camera", "camera"), ("seen_by_rays", "rays"))
        if tag.get(key)) or "hidden from render",
    description="Controls how the object takes part in rendering",
))


DISPLAY = register_tag(TagSpec(
    id="display", label="Display", category="Rendering Tags", icon="eye", unique=True, menu_order=2,
    params=(
        TagParam("use_shading", "Use Shading Mode", "bool", False, group="Tag"),
        TagParam("shading_mode", "Shading Mode", "choice", SHADING_MODES[0], choices=SHADING_MODES,
                 group="Tag"),
        TagParam("use_visibility", "Use Visibility", "bool", True, group="Tag"),
        TagParam("visibility", "Visibility", "percent", 100.0, minimum=0.0, maximum=100.0, group="Tag"),
        TagParam("affect_children", "Affect Children", "bool", True, group="Tag"),
        TagParam("backface_culling", "Backface Culling", "bool", False, group="Viewport"),
        TagParam("textures", "Textures", "bool", True, group="Viewport"),
        TagParam("xray", "X-Ray", "bool", False, group="Viewport"),
    ),
    summary=lambda obj, tag: (f"{tag.get('visibility', 100.0):.0f}% visible"
                              + (f", {tag.get('shading_mode')}" if tag.get("use_shading") else "")),
    description="Overrides how the object is drawn in the viewport",
))


def _look_at_camera(ctx, obj, tag, state) -> None:
    cam = ctx.camera()
    if cam is None:
        return
    wp = state.world_position()
    fwd = cam - wp
    if tag.get("rotate_h_only", False):
        fwd = np.array([fwd[0], 0.0, fwd[2]])
    axis = tag.get("aim_axis", "+Z")
    r = look_rotation(fwd, (0.0, 1.0, 0.0), axis)
    if r is not None:
        state.set_world_rotation(r, aim_axis=axis)


LOOK_AT_CAMERA = register_tag(TagSpec(
    id="look_at_camera", label="Look At Camera", category="Rendering Tags", icon="camera",
    runtime=True, menu_order=3,
    params=(
        TagParam("rotate_h_only", "Rotate Heading Only", "bool", False, group="Tag"),
        TagParam("aim_axis", "Aim Axis", "choice", "+Z", choices=AIM_AXES, group="Tag"),
    ),
    evaluate=_look_at_camera,
    description="Turns the object so its aim axis faces the camera",
))


def _phong_summary(obj, tag) -> str:
    n = len(tag.get("edge_breaks", []))
    limit = f"{tag.get('angle', 80.0):.0f} deg limit" if tag.get("angle_limit", True) else "no limit"
    return f"{limit}, {n} edge breaks"


def _selected_edges(scene, obj) -> set:
    if scene is None or scene.active is not obj:
        return set()
    edges = set(obj.mesh.edges)
    return {tuple(e) for e in scene.selected_edges if tuple(e) in edges}


def _break_selected(scene, obj, index):
    tag = tag_at(obj, index)
    cur = {tuple(e) for e in tag.get("edge_breaks", [])}
    new = sorted(cur | _selected_edges(scene, obj))
    update_tag(obj, index, edge_breaks=[list(e) for e in new])
    return len(new)


def _unbreak_selected(scene, obj, index):
    tag = tag_at(obj, index)
    cur = {tuple(e) for e in tag.get("edge_breaks", [])}
    new = sorted(cur - _selected_edges(scene, obj))
    update_tag(obj, index, edge_breaks=[list(e) for e in new])
    return len(new)


def _clear_breaks(scene, obj, index):
    update_tag(obj, index, edge_breaks=[])
    return 0


def _select_breaks(scene, obj, index):
    tag = tag_at(obj, index)
    edges = set(obj.mesh.edges)
    items = {tuple(sorted((int(e[0]), int(e[1])))) for e in tag.get("edge_breaks", [])} & edges
    if scene.active is not obj:
        scene.set_active(obj)
    scene.set_mode("edges")
    scene.selected_edges.clear()
    scene.selected_edges.update(items)
    scene.selectionChanged.emit()
    return len(items)


PHONG = register_tag(TagSpec(
    id="phong", label="Phong", category="Modeling Tags", icon="sphere", unique=True, menu_order=0,
    params=(
        TagParam("angle_limit", "Angle Limit", "bool", True, group="Tag"),
        TagParam("angle", "Phong Angle", "angle", 80.0, minimum=0.0, maximum=180.0, group="Tag"),
        TagParam("use_edge_breaks", "Use Edge Breaks", "bool", True, group="Tag"),
        TagParam("edge_breaks", "Edge Breaks", "data", []),
    ),
    actions=(
        TagAction("break_selected", "Break Selected Edges", _break_selected),
        TagAction("unbreak_selected", "Unbreak Selected", _unbreak_selected),
        TagAction("select_breaks", "Select Breaks", _select_breaks),
        TagAction("clear_breaks", "Clear Breaks", _clear_breaks),
    ),
    summary=_phong_summary,
    description="Smooths shading across edges whose angle is under the limit",
))


def _sel_set(scene, obj, index):
    return store_selection(scene, obj, index)


def _sel_restore(scene, obj, index):
    return restore_selection(scene, obj, index, "replace")


def _sel_add(scene, obj, index):
    return restore_selection(scene, obj, index, "add")


def _sel_remove(scene, obj, index):
    return restore_selection(scene, obj, index, "remove")


def _sel_clear(scene, obj, index):
    update_tag(obj, index, selection=[])
    return 0


_SEL_ACTIONS = (
    TagAction("set", "Set Selection", _sel_set),
    TagAction("restore", "Restore Selection", _sel_restore),
    TagAction("select", "Select", _sel_add),
    TagAction("deselect", "Deselect", _sel_remove),
    TagAction("clear", "Clear", _sel_clear),
)

_SEL_NOUN = {"points": "points", "edges": "edges", "polygons": "polygons"}

for _order, (_id, _label, _icon) in enumerate((
        ("point_selection", "Point Selection", "mode_points"),
        ("edge_selection", "Edge Selection", "mode_edges"),
        ("polygon_selection", "Polygon Selection", "mode_polygons"))):
    register_tag(TagSpec(
        id=_id, label=_label, category="Modeling Tags", icon=_icon, menu_order=1 + _order,
        params=(TagParam("selection", "Selection", "data", []),),
        actions=_SEL_ACTIONS,
        summary=lambda obj, tag: f"{len(selection_items(obj, tag))} "
                                 f"{_SEL_NOUN[MODE_FOR_TYPE[tag['type']]]}",
        description=f"Stores a named {_label.lower()} that can be restored later",
    ))


def _uvw_summary(obj, tag) -> str:
    data = tag.get("uvw") or []
    ok = len(data) == len(obj.mesh.polygons)
    return f"{len(data)} polygons" + ("" if ok or not data else ", out of date")


def _uvw_clear(scene, obj, index):
    update_tag(obj, index, uvw=[])
    return 0


UVW = register_tag(TagSpec(
    id="uvw", label="UVW", category="Modeling Tags", icon="four_side", unique=True, menu_order=4,
    params=(TagParam("uvw", "Coordinates", "data", []),),
    actions=(TagAction("clear", "Clear Coordinates", _uvw_clear),),
    summary=_uvw_summary,
    description="Holds per-polygon texture coordinates",
))


def _vibrate(ctx, obj, tag, state) -> None:
    off = vibrate_offsets(tag, ctx.time)
    state.position = state.position + off["position"]
    if np.any(off["rotation"]):
        state.rotation = state.rotation @ rotation_matrix(off["rotation"])
    state.scale = state.scale * off["scale"]


VIBRATE = register_tag(TagSpec(
    id="vibrate", label="Vibrate", category="Animation Tags", icon="random_field", runtime=True,
    menu_order=0,
    params=(
        TagParam("enable_position", "Enable Position", "bool", True, group="Position"),
        _vec("position_amplitude", "Amplitude", (10.0, 10.0, 10.0), "cm", "Position", minimum=0.0),
        TagParam("enable_rotation", "Enable Rotation", "bool", False, group="Rotation"),
        _vec("rotation_amplitude", "Amplitude", (10.0, 10.0, 10.0), "deg", "Rotation", minimum=0.0),
        TagParam("enable_scale", "Enable Scale", "bool", False, group="Scale"),
        TagParam("uniform_scale", "Uniform", "bool", True, group="Scale"),
        _vec("scale_amplitude", "Amplitude", (0.1, 0.1, 0.1), "", "Scale", minimum=0.0,
             maximum=MAX_SCALE_AMPLITUDE, step=0.01),
        TagParam("frequency", "Frequency", "float", 2.0, minimum=0.0, step=0.1, unit="Hz", group="Tag"),
        _vec("seed", "Seed", (1.0, 2.0, 3.0), "", "Tag", step=1.0),
        TagParam("regular", "Regular Pulse", "bool", False, group="Tag"),
    ),
    evaluate=_vibrate,
    description="Shakes position, rotation and scale with seeded noise",
))


def _target(ctx, obj, tag, state) -> None:
    target = ctx.object(tag.get("target", ""))
    if target is None or target is obj:
        return
    wp = state.world_position()
    up = np.array([0.0, 1.0, 0.0])
    up_obj = ctx.object(tag.get("up_vector", ""))
    if up_obj is not None and up_obj is not obj:
        cand = up_obj.world_position() - wp
        if np.linalg.norm(cand) > 1e-9:
            up = cand
    axis = tag.get("aim_axis", "+Z")
    r = look_rotation(target.world_position() - wp, up, axis)
    if r is not None:
        state.set_world_rotation(r, aim_axis=axis)


TARGET = register_tag(TagSpec(
    id="target", label="Target", category="Animation Tags", icon="target", runtime=True,
    menu_order=1,
    params=(
        TagParam("target", "Target Object", "object", "", group="Tag"),
        TagParam("up_vector", "Up Vector", "object", "", group="Tag"),
        TagParam("aim_axis", "Aim Axis", "choice", "+Z", choices=AIM_AXES, group="Tag"),
    ),
    evaluate=_target,
    summary=lambda obj, tag: f"aims at {tag.get('target') or 'nothing'}",
    description="Keeps the object's aim axis pointed at another object",
))


_AXES = ("lock_x", "lock_y", "lock_z")
_CHANNELS = (("lock_position", "position"), ("lock_rotation", "rotation"), ("lock_scale", "scale"))


def _capture(base: dict) -> dict:
    return {k: [float(x) for x in np.asarray(base[k], float)] for k in ("position", "rotation", "scale")}


def _protection(ctx, obj, tag, base) -> None:
    frozen = tag.get("frozen")
    if not isinstance(frozen, dict) or not all(k in frozen for k in ("position", "rotation", "scale")):
        frozen = _capture(base)
        tag["frozen"] = frozen
    mask = np.array([bool(tag.get(a, True)) for a in _AXES])
    for flag, ch in _CHANNELS:
        if tag.get(flag, True):
            vals = np.asarray(base[ch], float).copy()
            vals[mask] = np.asarray(frozen[ch], float)[mask]
            base[ch] = vals


def _protection_create(scene, obj, tag) -> None:
    if obj is not None:
        tag["frozen"] = _capture(base_transform(obj))


def _freeze(scene, obj, index):
    update_tag(obj, index, frozen=_capture(base_transform(obj)))
    return True


PROTECTION = register_tag(TagSpec(
    id="protection", label="Protection", category="Animation Tags", icon="lock", runtime=True,
    unique=True, menu_order=2,
    params=(
        TagParam("lock_position", "Lock Position", "bool", True, group="Tag"),
        TagParam("lock_rotation", "Lock Rotation", "bool", True, group="Tag"),
        TagParam("lock_scale", "Lock Scale", "bool", True, group="Tag"),
        TagParam("lock_x", "X Axis", "bool", True, group="Axes"),
        TagParam("lock_y", "Y Axis", "bool", True, group="Axes"),
        TagParam("lock_z", "Z Axis", "bool", True, group="Axes"),
        TagParam("frozen", "Frozen", "data", None),
    ),
    actions=(TagAction("freeze", "Freeze Current", _freeze),),
    evaluate=_protection,
    on_create=_protection_create,
    captured=("frozen",),
    recapture=True,
    summary=lambda obj, tag: "locks " + (", ".join(
        n for f, n in (("lock_position", "P"), ("lock_rotation", "R"), ("lock_scale", "S"))
        if tag.get(f)) or "nothing"),
    extra={"stage": "base"},
    description="Stops position, rotation or scale from being changed",
))


PYTHON = register_tag(TagSpec(
    id="python", label="Python", category="Programming Tags", icon="python", menu_order=0,
    params=(
        TagParam("priority", "Priority", "choice", "Expressions", choices=PYTHON_PRIORITIES,
                 group="Tag"),
        TagParam("code", "Code", "code", PYTHON_TEMPLATE, group="Code"),
    ),
    summary=lambda obj, tag: f"{len((tag.get('code') or '').splitlines())} lines",
    description="Python code run by the scripting system every frame",
))


RIGID_BODY = register_tag(TagSpec(
    id="rigid_body", label="Rigid Body", category="Simulation Tags", icon="cube", unique=True,
    menu_order=0,
    params=(
        TagParam("dynamic", "Dynamic", "bool", True, group="Dynamics"),
        TagParam("mass", "Mass", "float", 1.0, minimum=0.0, step=0.1, unit="kg", group="Dynamics"),
        TagParam("bounce", "Bounce", "percent", 50.0, minimum=0.0, maximum=100.0, group="Collision"),
        TagParam("friction", "Friction", "percent", 30.0, minimum=0.0, maximum=100.0, group="Collision"),
        TagParam("shape", "Shape", "choice", "Automatic",
                 choices=("Automatic", "Box", "Sphere", "Convex Hull", "Static Mesh"), group="Collision"),
    ),
    description="Marks the object as a rigid body for the simulation system",
))

COLLIDER_BODY = register_tag(TagSpec(
    id="collider_body", label="Collider Body", category="Simulation Tags", icon="floor", unique=True,
    menu_order=1,
    params=(
        TagParam("bounce", "Bounce", "percent", 50.0, minimum=0.0, maximum=100.0, group="Collision"),
        TagParam("friction", "Friction", "percent", 30.0, minimum=0.0, maximum=100.0, group="Collision"),
        TagParam("shape", "Shape", "choice", "Static Mesh",
                 choices=("Automatic", "Box", "Sphere", "Convex Hull", "Static Mesh"), group="Collision"),
    ),
    description="Marks the object as a static collider for the simulation system",
))

SOFT_BODY = register_tag(TagSpec(
    id="soft_body", label="Soft Body", category="Simulation Tags", icon="metaball", unique=True,
    menu_order=2,
    params=(
        TagParam("mass", "Mass", "float", 1.0, minimum=0.0, step=0.1, unit="kg", group="Dynamics"),
        TagParam("stiffness", "Stiffness", "percent", 20.0, minimum=0.0, maximum=100.0, group="Springs"),
        TagParam("damping", "Damping", "percent", 20.0, minimum=0.0, maximum=100.0, group="Springs"),
        TagParam("pressure", "Pressure", "float", 0.0, minimum=0.0, step=0.1, group="Springs"),
    ),
    description="Marks the object as a soft body for the simulation system",
))


def _offset_key(tag: dict) -> list:
    return [tag.get("mode", "Parent"), tag.get("target", "")]


def _constraint(ctx, obj, tag, state) -> None:
    target = ctx.object(tag.get("target", ""))
    if target is None or target is obj:
        return
    mode = tag.get("mode", "Parent")
    strength = max(0.0, min(100.0, float(tag.get("strength", 100.0)))) / 100.0
    tw = target.world_matrix()
    trot = orthonormal(tw[:3, :3])
    tpos = tw[:3, 3].copy()
    world = state.world_matrix()
    wrot = state.world_rotation()
    wpos = world[:3, 3].copy()
    keep = bool(tag.get("maintain_offset", True))
    offset = tag.get("offset")
    if keep and (not isinstance(offset, dict) or offset.get("key") != _offset_key(tag)):
        if mode == "Parent":
            value = np.linalg.solve(tw, world)
        elif mode == "Position":
            value = wpos - tpos
        elif mode == "Rotation":
            value = trot.T @ wrot
        else:
            aim = look_rotation(tpos - wpos, _up(ctx, obj, tag, wpos), tag.get("aim_axis", "+Z"))
            value = np.eye(3) if aim is None else aim.T @ wrot
        offset = {"key": _offset_key(tag), "value": np.asarray(value, float).tolist()}
        tag["offset"] = offset
    off = np.asarray(offset["value"], float) if keep and isinstance(offset, dict) else None
    if mode == "Parent":
        desired = tw @ (off if off is not None and off.shape == (4, 4) else state.local_matrix())
        p0, r0, s0 = decompose(world)
        p1, r1, s1 = decompose(desired)
        blended = np.eye(4)
        blended[:3, :3] = blend_rotation(r0, r1, strength) @ np.diag(s0 + (s1 - s0) * strength)
        blended[:3, 3] = p0 + (p1 - p0) * strength
        state.set_world_matrix(blended)
    elif mode == "Position":
        desired = tpos + (off if off is not None and off.shape == (3,) else 0.0)
        mask = np.array([bool(tag.get(k, True)) for k in ("axis_x", "axis_y", "axis_z")])
        goal = np.where(mask, desired, wpos)
        state.set_world_position(wpos + (goal - wpos) * strength)
    elif mode == "Rotation":
        desired = trot @ (off if off is not None and off.shape == (3, 3) else np.eye(3))
        state.set_world_rotation(blend_rotation(wrot, desired, strength))
    else:
        aim = look_rotation(tpos - wpos, _up(ctx, obj, tag, wpos), tag.get("aim_axis", "+Z"))
        if aim is None:
            return
        desired = aim @ (off if off is not None and off.shape == (3, 3) else np.eye(3))
        exact = off is None or np.allclose(off, np.eye(3), atol=1e-9)
        state.set_world_rotation(blend_rotation(wrot, desired, strength),
                                 aim_axis=tag.get("aim_axis", "+Z") if exact and strength >= 1.0 else None)


def _up(ctx, obj, tag, wpos) -> np.ndarray:
    up_obj = ctx.object(tag.get("up_vector", ""))
    if up_obj is not None and up_obj is not obj:
        cand = up_obj.world_position() - wpos
        if np.linalg.norm(cand) > 1e-9:
            return cand
    return np.array([0.0, 1.0, 0.0])


def _set_offset(scene, obj, index):
    update_tag(obj, index, offset=None, maintain_offset=True)
    return True


def _clear_offset(scene, obj, index):
    update_tag(obj, index, offset=None, maintain_offset=False)
    return True


CONSTRAINT = register_tag(TagSpec(
    id="constraint", label="Constraint", category="Character Tags", icon="connect", runtime=True,
    menu_order=0,
    params=(
        TagParam("mode", "Mode", "choice", "Parent", choices=CONSTRAINT_MODES, group="Tag"),
        TagParam("target", "Target", "object", "", group="Tag"),
        TagParam("strength", "Strength", "percent", 100.0, minimum=0.0, maximum=100.0, group="Tag"),
        TagParam("maintain_offset", "Maintain Offset", "bool", True, group="Tag"),
        TagParam("axis_x", "X", "bool", True, group="Position Axes"),
        TagParam("axis_y", "Y", "bool", True, group="Position Axes"),
        TagParam("axis_z", "Z", "bool", True, group="Position Axes"),
        TagParam("aim_axis", "Aim Axis", "choice", "+Z", choices=AIM_AXES, group="Aim"),
        TagParam("up_vector", "Up Vector", "object", "", group="Aim"),
        TagParam("offset", "Offset", "data", None),
    ),
    actions=(
        TagAction("set_offset", "Set Offset", _set_offset),
        TagAction("clear_offset", "Clear Offset", _clear_offset),
    ),
    evaluate=_constraint,
    captured=("offset",),
    summary=lambda obj, tag: f"{tag.get('mode')} to {tag.get('target') or 'nothing'}, "
                             f"{tag.get('strength', 100.0):.0f}%",
    description="Ties the object's transform to a target object",
))


IK_KEY = "ik"
IK_SOLVERS = ("Auto", "Two Bone", "CCD")
_IK_FIELDS = ("end", "goal", "pole")


def _ik_key() -> str:
    try:
        from ..rig import data as rig_data
    except Exception:
        return IK_KEY
    return getattr(rig_data, "IK_KEY", IK_KEY)


def _ik_create(scene, obj, tag) -> None:
    if obj is None:
        return
    cur = store.object_extras(obj).get(_ik_key())
    if not isinstance(cur, dict):
        return
    cur = store.from_json(cur)
    for key in _IK_FIELDS:
        if isinstance(cur.get(key), str):
            tag[key] = cur[key]
    solver = str(cur.get("solver", "Auto"))
    tag["solver"] = solver if solver in IK_SOLVERS else "Auto"
    for src, dst, scale in (("blend", "strength", 100.0), ("tolerance", "tolerance", 1.0),
                            ("twist", "twist", 1.0)):
        try:
            tag[dst] = float(cur[src]) * scale
        except (KeyError, TypeError, ValueError):
            pass
    try:
        tag["iterations"] = int(cur["iterations"])
    except (KeyError, TypeError, ValueError):
        pass
    if "match_goal_rotation" in cur:
        tag["match_goal_rotation"] = bool(cur["match_goal_rotation"])


def ik_record(tag: dict, current: dict | None = None) -> dict:
    out = dict(current) if isinstance(current, dict) else {}
    for key in _IK_FIELDS:
        out[key] = str(tag.get(key, "") or "")
    out["solver"] = str(tag.get("solver", "Auto"))
    out["blend"] = max(0.0, min(1.0, float(tag.get("strength", 100.0)) / 100.0))
    out["iterations"] = int(max(1, int(tag.get("iterations", 24))))
    out["tolerance"] = float(max(1e-6, float(tag.get("tolerance", 0.01))))
    out["match_goal_rotation"] = bool(tag.get("match_goal_rotation", False))
    out["twist"] = float(tag.get("twist", 0.0))
    out["enabled"] = bool(tag.get("enabled", True))
    out["source"] = "tags"
    return out


def sync_ik(scene, obj) -> bool:
    key = _ik_key()
    extras = store.object_extras(obj)
    raw = extras.get(key)
    cur = store.from_json(raw) if isinstance(raw, dict) else None
    found = find_tags(obj, "ik")
    if not found:
        if isinstance(cur, dict) and cur.get("source") == "tags":
            write_extra(obj, key, None, scene=scene, quiet=scene is None)
            return True
        return False
    new = ik_record(found[0][1], cur)
    if cur is not None and store.to_json(new) == store.to_json(cur):
        return False
    write_extra(obj, key, new, scene=scene, quiet=scene is None)
    return True


if sync_ik not in write_hooks():
    write_hooks().append(sync_ik)


def _ik_summary(obj, tag) -> str:
    text = f"{tag.get('solver')} to {tag.get('goal') or 'no goal'}"
    if getattr(obj, "kind", "") != "joint":
        text += ", start is not a joint"
    return text


IK = register_tag(TagSpec(
    id="ik", label="IK", category="Character Tags", icon="joint", menu_order=1, unique=True,
    params=(
        TagParam("solver", "Solver", "choice", "Auto", choices=IK_SOLVERS, group="Tag"),
        TagParam("end", "End", "object", "", ref_type="joint", group="Tag"),
        TagParam("goal", "Goal", "object", "", group="Tag"),
        TagParam("pole", "Pole Vector", "object", "", group="Tag"),
        TagParam("strength", "Strength", "percent", 100.0, minimum=0.0, maximum=100.0, group="Tag"),
        TagParam("twist", "Twist", "angle", 0.0, group="Tag"),
        TagParam("match_goal_rotation", "Match Goal Rotation", "bool", False, group="Tag"),
        TagParam("iterations", "Iterations", "int", 24, minimum=1, maximum=500, group="Solver"),
        TagParam("tolerance", "Tolerance", "distance", 0.01, minimum=0.000001, step=0.01,
                 group="Solver"),
    ),
    on_create=_ik_create,
    summary=_ik_summary,
    description="Inverse kinematics chain solved by the rig system",
))


def normalize_weights(weights: dict, point_count: int | None = None) -> dict:
    names = list(weights)
    if not names:
        return {}
    n = point_count if point_count is not None else max(len(weights[k]) for k in names)
    mat = np.zeros((len(names), n))
    for r, k in enumerate(names):
        w = np.asarray(weights[k], float)[:n]
        mat[r, :len(w)] = np.clip(w, 0.0, None)
    total = mat.sum(axis=0)
    ok = total > 1e-12
    mat[:, ok] = mat[:, ok] / total[ok]
    return {k: mat[r].tolist() for r, k in enumerate(names)}


def set_point_weights(weights: dict, joint: str, indices, value: float, point_count: int,
                      normalize: bool = True) -> dict:
    n = int(point_count)
    names = list(weights)
    if joint not in names:
        names.append(joint)
    mat = np.zeros((len(names), n))
    for r, k in enumerate(names):
        w = np.clip(np.asarray(weights.get(k, []), float).reshape(-1)[:n], 0.0, None)
        mat[r, :len(w)] = w
    row = names.index(joint)
    idx = np.array(sorted({int(i) for i in indices if 0 <= int(i) < n}), int)
    v = max(0.0, min(1.0, float(value)))
    if len(idx):
        if normalize:
            others = np.delete(np.arange(len(names)), row)
            if len(others):
                sub = mat[np.ix_(others, idx)]
                total = sub.sum(axis=0)
                ok = total > 1e-12
                scale = np.zeros(len(idx))
                scale[ok] = (1.0 - v) / total[ok]
                mat[np.ix_(others, idx)] = sub * scale
        mat[row, idx] = v
    return {k: mat[r].tolist() for r, k in enumerate(names)}


def _normalize(scene, obj, index):
    tag = tag_at(obj, index)
    out = normalize_weights(tag.get("weights") or {}, len(obj.mesh.points))
    update_tag(obj, index, weights=out)
    return len(out)


def _target_points(scene, obj) -> list[int]:
    if scene is None or scene.active is not obj or scene.mode == "model":
        return []
    return list(scene.affected_points())


def _assign_weights(scene, obj, index):
    tag = tag_at(obj, index)
    joint = str(tag.get("joint") or "")
    if not joint:
        return 0
    points = _target_points(scene, obj)
    if not points:
        return 0
    out = set_point_weights(tag.get("weights") or {}, joint, points,
                            float(tag.get("value", 100.0)) / 100.0, len(obj.mesh.points),
                            bool(tag.get("auto_normalize", True)))
    update_tag(obj, index, weights=out)
    return len(points)


def _remove_joint(scene, obj, index):
    tag = tag_at(obj, index)
    joint = str(tag.get("joint") or "")
    weights = dict(tag.get("weights") or {})
    if joint not in weights:
        return 0
    weights.pop(joint)
    if tag.get("auto_normalize", True):
        weights = normalize_weights(weights, len(obj.mesh.points))
    update_tag(obj, index, weights=weights)
    return 1


def _select_weighted(scene, obj, index):
    tag = tag_at(obj, index)
    joint = str(tag.get("joint") or "")
    w = np.asarray((tag.get("weights") or {}).get(joint, []), float).reshape(-1)
    n = len(obj.mesh.points)
    items = {int(i) for i in np.nonzero(w[:n] > 1e-6)[0]}
    if scene.active is not obj:
        scene.set_active(obj)
    scene.set_mode("points")
    scene.selected_points.clear()
    scene.selected_points.update(items)
    scene.selectionChanged.emit()
    return len(items)


def _weight_summary(obj, tag) -> str:
    weights = tag.get("weights") or {}
    joint = str(tag.get("joint") or "")
    text = f"{len(weights)} joints"
    if joint in weights:
        w = np.asarray(weights[joint], float).reshape(-1)
        text += f", {int(np.count_nonzero(w > 1e-6))} points on {joint}"
    return text


WEIGHT = register_tag(TagSpec(
    id="weight", label="Weight", category="Character Tags", icon="weight", unique=True, menu_order=2,
    params=(
        TagParam("auto_normalize", "Auto Normalize", "bool", True, group="Tag"),
        TagParam("joint", "Joint", "object", "", ref_type="joint", group="Paint"),
        TagParam("value", "Weight", "percent", 100.0, minimum=0.0, maximum=100.0, group="Paint"),
        TagParam("weights", "Weights", "data", {}),
    ),
    actions=(
        TagAction("assign", "Set Selected Points", _assign_weights),
        TagAction("select", "Select Weighted Points", _select_weighted),
        TagAction("remove_joint", "Remove Joint", _remove_joint),
        TagAction("normalize", "Normalize Weights", _normalize),
    ),
    summary=_weight_summary,
    extra={"name_keyed": ("weights",)},
    description="Holds per-point joint weights used by skinning",
))

SKIN = register_tag(TagSpec(
    id="skin", label="Skin", category="Character Tags", icon="figure", unique=True, menu_order=3,
    params=(
        TagParam("skin_type", "Type", "choice", "Linear",
                 choices=("Linear", "Spherical", "Dual Quaternion"), group="Tag"),
        TagParam("strength", "Strength", "percent", 100.0, minimum=0.0, maximum=100.0, group="Tag"),
    ),
    summary=lambda obj, tag: f"{tag.get('skin_type')}, {tag.get('strength', 100.0):.0f}%",
    description="Deforms the mesh with its joints using the weight tag",
))

SPEC_IDS = ("material", "compositing", "display", "look_at_camera", "phong", "point_selection",
            "edge_selection", "polygon_selection", "uvw", "vibrate", "target", "protection",
            "python", "rigid_body", "collider_body", "soft_body", "constraint", "ik", "weight",
            "skin")
