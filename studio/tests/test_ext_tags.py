from __future__ import annotations

import json
import math
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtWidgets import QApplication, QMenu

from quartz_studio import tags
from quartz_studio.ext import store
from quartz_studio.scene import Mesh, SceneObject, reset_scene, rotation_matrix
from quartz_studio.tags import core, mathutil, registry, runtime, shading
from quartz_studio.tags.builtin import SPEC_IDS, normalize_weights

_APP = QApplication.instance() or QApplication([sys.argv[0]])


def _fresh():
    scene = reset_scene()
    return scene, scene.objects[0]


def _add(scene, name, mesh=None, pos=(0.0, 0.0, 0.0)):
    obj = scene.add_object(name, mesh if mesh is not None else Mesh.cube(100.0))
    obj.position = np.asarray(pos, float)
    return obj


def _aim(obj, axis=(0.0, 0.0, 1.0)):
    return obj.world_linear() @ np.asarray(axis, float) / np.linalg.norm(obj.world_linear()[:, 2])


def _pump(n=3):
    from PySide6.QtCore import QCoreApplication, QEvent
    for _ in range(n):
        _APP.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_registry_has_all_types_in_all_categories():
    assert set(SPEC_IDS) <= set(tags.tag_ids())
    cats = [c for c, _s in tags.specs_by_category()]
    assert cats == list(registry.CATEGORIES)
    for spec in tags.tag_specs():
        tag = tags.make_tag(spec.id)
        assert tag["type"] == spec.id and tag["enabled"] is True and tag["name"] == spec.label
        json.dumps(store.to_json(tag))
        if spec.runtime:
            assert spec.evaluate is not None


def test_param_clamping_rules():
    vis = tags.get_tag_spec("display").param("visibility")
    assert vis.clamp(150) == 100.0 and vis.clamp(-3) == 0.0
    proj = tags.get_tag_spec("material").param("projection")
    assert proj.clamp("Spherical") == "spherical" and proj.clamp("Bogus") == "uvw"
    assert proj.clamp("cubic") == "cubic" and proj.clamp("Shrink Wrapping") == "shrinkwrap"
    assert proj.choice_label("frontal") == "Frontal"
    vec = tags.get_tag_spec("vibrate").param("position_amplitude")
    assert vec.clamp((1, 2, 3)) == [1.0, 2.0, 3.0]
    assert vec.clamp((-1, 2, 3)) == [0.0, 2.0, 3.0]
    try:
        vec.clamp((1, 2))
    except ValueError:
        pass
    else:
        raise AssertionError("short vector accepted")
    assert tags.get_tag_spec("target").param("target").clamp(None) == ""


def test_registry_rejects_bad_specs():
    try:
        registry.TagSpec(id="x", label="X", category="Nope")
    except ValueError:
        pass
    else:
        raise AssertionError("bad category accepted")
    try:
        registry.TagSpec(id="x", label="X", category="Modeling Tags",
                         params=(registry.TagParam("name", "Name", "text", ""),))
    except ValueError:
        pass
    else:
        raise AssertionError("reserved key accepted")
    try:
        registry.TagSpec(id="x", label="X", category="Modeling Tags", runtime=True)
    except ValueError:
        pass
    else:
        raise AssertionError("runtime tag without hook accepted")
    try:
        tags.register_tag(registry.TagSpec(id="phong", label="P", category="Modeling Tags"))
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate registration accepted")


def test_add_remove_move_duplicate_rename():
    scene, cube = _fresh()
    a = tags.add_tag(cube, "material")
    b = tags.add_tag(cube, "material")
    c = tags.add_tag(cube, "python")
    names = [t["name"] for t in tags.tags_of(cube)]
    assert (a, b, c) == (0, 1, 2)
    assert names == ["Material", "Material.1", "Python"]
    assert tags.move_tag(cube, 2, 0)
    assert [t["type"] for t in tags.tags_of(cube)] == ["python", "material", "material"]
    assert not tags.move_tag(cube, 0, 0)
    d = tags.duplicate_tag(cube, 1)
    assert d == 2 and tags.tags_of(cube)[2]["name"] == "Material.2"
    assert tags.rename_tag(cube, 2, "Material") == "Material.2"
    assert tags.rename_tag(cube, 2, "Wood") == "Wood"
    gone = tags.remove_tag(cube, 0)
    assert gone["type"] == "python" and len(tags.tags_of(cube)) == 3
    assert tags.remove_tag(cube, 9) is None
    assert tags.add_tag(cube, "python", index=0) == 0


def test_unique_tags_are_not_doubled():
    scene, cube = _fresh()
    i = tags.add_tag(cube, "phong")
    j = tags.add_tag(cube, "phong")
    assert i == j and len(tags.tags_of(cube)) == 1
    assert tags.duplicate_tag(cube, 0) is None


def test_update_tag_clamps_and_rejects_unknown():
    scene, cube = _fresh()
    i = tags.add_tag(cube, "display")
    tag = tags.update_tag(cube, i, visibility=250.0, shading_mode="Lines", use_shading=1)
    assert tag["visibility"] == 100.0 and tag["shading_mode"] == "Lines" and tag["use_shading"] is True
    try:
        tags.update_tag(cube, i, nope=1)
    except KeyError:
        pass
    else:
        raise AssertionError("unknown key accepted")
    tags.set_tag_enabled(cube, i, False)
    assert tags.find_tags(cube, "display", enabled_only=True) == []
    assert len(tags.find_tags(cube, "display")) == 1


def test_stored_tags_are_copies():
    scene, cube = _fresh()
    tags.add_tag(cube, "phong")
    copy = tags.get_tags(cube)
    copy[0]["angle"] = 5.0
    assert tags.tags_of(cube)[0]["angle"] == 80.0
    assert store.get_object(cube, "tags") == tags.tags_of(cube)
    assert store.get_object(cube, "tags") is not tags.tags_of(cube)


def test_copy_tags_respects_unique():
    scene, cube = _fresh()
    other = _add(scene, "Other")
    tags.add_tag(cube, "phong")
    tags.add_tag(cube, "material")
    tags.add_tag(other, "phong")
    tags.add_tag(other, "material")
    added = tags.copy_tags(cube, other)
    assert added == 1
    assert [t["name"] for t in tags.tags_of(other)] == ["Phong", "Material", "Material.1"]
    tags.clear_tags(other)
    assert tags.tags_of(other) == []


def test_serialize_roundtrip():
    scene, cube = _fresh()
    tags.add_tag(cube, "vibrate", seed=[4, 5, 6])
    tags.add_tag(cube, "polygon_selection")
    tags.update_tag(cube, 1, selection=[0, 2])
    data = json.loads(json.dumps(tags.serialize_tags(cube)))
    other = _add(scene, "Copy")
    tags.deserialize_tags(other, data)
    assert tags.tags_of(other) == tags.tags_of(cube)


def test_current_tag_tracking():
    scene, cube = _fresh()
    tags.add_tag(cube, "phong")
    tags.add_tag(cube, "python")
    tags.set_current_tag(scene, cube, 1)
    assert tags.current_tag(scene) == (cube, 1)
    tags.remove_tag(cube, 1)
    assert tags.current_tag(scene) == (cube, None)
    tags.set_current_tag(scene, None, None)
    assert tags.current_tag(scene) == (None, None)


def test_polygon_selection_store_and_restore():
    scene, cube = _fresh()
    scene.set_active(cube)
    scene.set_mode("polygons")
    scene.select_components([1, 3])
    i = tags.add_tag(cube, "polygon_selection")
    assert tags.store_selection(scene, cube, i) == 2
    assert tags.tags_of(cube)[i]["selection"] == [1, 3]
    scene.select_components([0])
    scene.set_mode("model")
    assert tags.restore_selection(scene, cube, i) == 2
    assert scene.mode == "polygons" and scene.selected_polygons == {1, 3}
    scene.select_components([5])
    tags.restore_selection(scene, cube, i, "add")
    assert scene.selected_polygons == {1, 3, 5}
    tags.restore_selection(scene, cube, i, "remove")
    assert scene.selected_polygons == {5}
    assert "2 polygons" in tags.tag_summary(cube, i)


def test_edge_and_point_selection_filter_invalid():
    scene, cube = _fresh()
    scene.set_active(cube)
    scene.set_mode("edges")
    e = list(cube.mesh.edges[:2])
    scene.select_components(e)
    i = tags.add_tag(cube, "edge_selection")
    tags.store_selection(scene, cube, i)
    stored = tags.tags_of(cube)[i]["selection"]
    assert sorted(tuple(x) for x in stored) == sorted(e)
    j = tags.add_tag(cube, "point_selection")
    tags.update_tag(cube, j, selection=[0, 7, 99])
    assert tags.selection_items(cube, tags.tags_of(cube)[j]) == [0, 7]
    tags.update_tag(cube, i, selection=[[0, 6], list(e[0])])
    assert tags.selection_items(cube, tags.tags_of(cube)[i]) == [tuple(sorted(e[0]))]


def test_new_selection_tag_uses_scene_mode():
    scene, cube = _fresh()
    scene.set_active(cube)
    scene.set_mode("points")
    scene.select_components([2, 4, 6])
    i = tags.new_selection_tag(scene)
    tag = tags.tags_of(cube)[i]
    assert tag["type"] == "point_selection" and tag["selection"] == [2, 4, 6]
    scene.set_mode("model")
    assert tags.new_selection_tag(scene) is None


def test_selection_actions_through_run_action():
    scene, cube = _fresh()
    scene.set_active(cube)
    scene.set_mode("polygons")
    scene.select_components([0, 1, 2])
    i = tags.add_tag(cube, "polygon_selection")
    assert tags.run_action(scene, cube, i, "set") == 3
    scene.select_components([])
    tags.run_action(scene, cube, i, "restore")
    assert scene.selected_polygons == {0, 1, 2}
    tags.run_action(scene, cube, i, "clear")
    assert tags.tags_of(cube)[i]["selection"] == []
    try:
        tags.run_action(scene, cube, i, "nope")
    except KeyError:
        pass
    else:
        raise AssertionError("unknown action accepted")


def test_phong_cube_limits():
    cube = Mesh.cube(200.0)
    face = cube.polygon_normals()
    sharp = tags.phong_normals(cube, True, 80.0)
    for k, n in enumerate(sharp):
        assert np.allclose(n, face[k])
    smooth = tags.phong_normals(cube, True, 100.0)
    for k, poly in enumerate(cube.polygons):
        for c, v in enumerate(poly):
            expect = cube.points[v] / np.linalg.norm(cube.points[v])
            assert np.allclose(smooth[k][c], expect, atol=1e-9)
    free = tags.phong_normals(cube, False, 0.0)
    assert np.allclose(free[0], smooth[0])


def _hinge(angle_deg):
    a = math.radians(angle_deg)
    pts = [(0, 0, 0), (100, 0, 0), (100, 0, 100), (0, 0, 100),
           (100 + 100 * math.cos(a), 100 * math.sin(a), 0), (100 + 100 * math.cos(a), 100 * math.sin(a), 100)]
    return Mesh(pts, [(0, 3, 2, 1), (1, 2, 5, 4)])


def test_phong_hinge_and_edge_breaks():
    mesh = _hinge(30.0)
    face = mesh.polygon_normals()
    sm = tags.phong_normals(mesh, True, 40.0)
    mid = (face[0] + face[1]) / np.linalg.norm(face[0] + face[1])
    c0 = mesh.polygons[0].index(1)
    c1 = mesh.polygons[1].index(1)
    assert np.allclose(sm[0][c0], mid) and np.allclose(sm[1][c1], mid)
    assert np.allclose(sm[0][mesh.polygons[0].index(0)], face[0])
    hard = tags.phong_normals(mesh, True, 20.0)
    assert np.allclose(hard[0][c0], face[0])
    broken = tags.phong_normals(mesh, True, 40.0, breaks=[(2, 1)])
    assert np.allclose(broken[0][c0], face[0]) and np.allclose(broken[1][c1], face[1])


def test_phong_tag_actions_and_object_normals():
    scene, cube = _fresh()
    flat = tags.object_normals(cube)
    assert np.allclose(flat[0], cube.mesh.polygon_normals()[0])
    i = tags.add_tag(cube, "phong", angle=100.0)
    assert not np.allclose(tags.object_normals(cube)[0], flat[0])
    scene.set_active(cube)
    scene.set_mode("edges")
    scene.select_components(cube.mesh.edges)
    assert tags.run_action(scene, cube, i, "break_selected") == 12
    assert np.allclose(tags.object_normals(cube)[0], flat[0])
    tags.update_tag(cube, i, use_edge_breaks=False)
    assert not np.allclose(tags.object_normals(cube)[0], flat[0])
    tags.update_tag(cube, i, use_edge_breaks=True)
    scene.select_components(cube.mesh.edges[:4])
    assert tags.run_action(scene, cube, i, "unbreak_selected") == 8
    scene.select_components([])
    assert tags.run_action(scene, cube, i, "select_breaks") == 8
    assert len(scene.selected_edges) == 8
    assert tags.run_action(scene, cube, i, "clear_breaks") == 0
    assert "0 edge breaks" in tags.tag_summary(cube, i)


def test_display_state_hierarchy():
    scene, cube = _fresh()
    child = _add(scene, "Child")
    scene.set_parent(child, cube)
    assert tags.display_state(scene, child)["visibility"] == 1.0
    tags.add_tag(cube, "display", visibility=50.0, use_shading=True, shading_mode="Wireframe")
    tags.add_tag(child, "display", visibility=50.0, backface_culling=True)
    st = tags.display_state(scene, child)
    assert abs(st["visibility"] - 0.25) < 1e-12
    assert st["shading"] == "Wireframe" and st["backface_culling"] is True and st["tag"]
    tags.update_tag(cube, 0, affect_children=False)
    assert tags.display_state(scene, child)["shading"] == ""
    tags.update_tag(child, 0, use_visibility=False)
    assert abs(tags.display_state(scene, child)["visibility"] - 0.5) < 1e-12


def test_compositing_flags_and_inheritance():
    scene, cube = _fresh()
    child = _add(scene, "Child")
    scene.set_parent(child, cube)
    flags = tags.compositing_flags(child)
    assert flags["cast_shadows"] and not flags["holdout"]
    tags.add_tag(cube, "compositing", cast_shadows=False, seen_by_camera=False)
    flags = tags.compositing_flags(child)
    assert not flags["cast_shadows"] and not flags["seen_by_camera"] and flags["receive_shadows"]
    tags.add_tag(child, "compositing")
    assert tags.compositing_flags(child)["cast_shadows"]
    assert "receives" in tags.tag_summary(cube, 0)


def test_material_flat_projection_fit():
    scene, cube = _fresh()
    i = tags.add_tag(cube, "material", projection="Flat")
    tag = tags.tags_of(cube)[i]
    assert np.allclose(tag["proj_size"], [100.0, 100.0, 100.0])
    uvs = tags.projection_uvs(cube, tag)
    for poly, uv in zip(cube.mesh.polygons, uvs):
        pts = cube.mesh.points[list(poly)]
        assert np.allclose(uv[:, 0], 0.5 + 0.5 * pts[:, 0] / 100.0)
        assert np.allclose(uv[:, 1], 0.5 + 0.5 * pts[:, 1] / 100.0)
    tags.update_tag(cube, i, tiling=[2.0, 3.0], offset=[0.1, -0.2])
    tiled = tags.projection_uvs(cube, tags.tags_of(cube)[i])
    assert np.allclose(tiled[0][:, 0], uvs[0][:, 0] * 2.0 + 0.1)
    assert np.allclose(tiled[0][:, 1], uvs[0][:, 1] * 3.0 - 0.2)
    tags.run_action(scene, cube, i, "reset_projection")
    assert tags.tags_of(cube)[i]["tiling"] == [1.0, 1.0]
    assert tags.tags_of(cube)[i]["offset"] == [0.0, 0.0]


def test_material_projection_rotation_and_fit_action():
    scene, cube = _fresh()
    cube.mesh.points += np.array([50.0, 0.0, 0.0])
    i = tags.add_tag(cube, "material", projection="Flat")
    tags.update_tag(cube, i, proj_offset=[0, 0, 0], proj_size=[10, 10, 10])
    assert tags.run_action(scene, cube, i, "fit")
    tag = tags.tags_of(cube)[i]
    assert np.allclose(tag["proj_offset"], [50.0, 0.0, 0.0])
    tags.update_tag(cube, i, proj_rotation=[0.0, 0.0, 90.0])
    tag = tags.tags_of(cube)[i]
    uv = tags.projection_uvs(cube, tag)
    poly = cube.mesh.polygons[0]
    q = (cube.mesh.points[list(poly)] - np.array([50.0, 0, 0])) @ rotation_matrix([0, 0, 90]) / 100.0
    assert np.allclose(uv[0][:, 0], 0.5 + 0.5 * q[:, 0])


def _sphere_mesh():
    pts = [(0, 0, 100), (100, 0, 0), (0, 100, 0), (0, -100, 0), (-100, 0, 0), (0, 0, -100)]
    return Mesh(pts, [(0, 1, 2), (0, 3, 1), (5, 2, 4), (5, 4, 3)])


def test_spherical_cylindrical_shrink_values():
    scene, _ = _fresh()
    obj = _add(scene, "Ball", _sphere_mesh())
    i = tags.add_tag(obj, "material", projection="Spherical")
    tags.update_tag(obj, i, proj_offset=[0, 0, 0], proj_size=[100, 100, 100])
    uv = tags.projection_uvs(obj, tags.tags_of(obj)[i])
    p0 = obj.mesh.polygons[0]
    assert np.allclose(uv[0][p0.index(0)], [0.5, 0.5])
    assert np.isclose(uv[0][p0.index(2)][1], 1.0)
    assert np.isclose(uv[0][p0.index(1)][0], 0.75)
    tags.update_tag(obj, i, projection="Cylindrical")
    uv = tags.projection_uvs(obj, tags.tags_of(obj)[i])
    assert np.isclose(uv[0][p0.index(2)][1], 1.0) and np.isclose(uv[0][p0.index(0)][1], 0.5)
    tags.update_tag(obj, i, projection="Shrink Wrapping")
    uv = tags.projection_uvs(obj, tags.tags_of(obj)[i])
    assert np.allclose(uv[0][p0.index(2)], [0.5, 0.5])
    p1 = obj.mesh.polygons[1]
    south = uv[1][p1.index(3)]
    assert np.isclose(np.linalg.norm(south - 0.5), 0.5)
    assert np.isclose(np.linalg.norm(uv[0][p0.index(0)] - 0.5), 0.25)


def test_spherical_seam_is_continuous():
    scene, _ = _fresh()
    pts = [(-10, 0, -100), (10, 0, -100), (10, 20, -100), (-10, 20, -100)]
    obj = _add(scene, "Seam", Mesh(pts, [(0, 1, 2, 3)]))
    i = tags.add_tag(obj, "material", projection="Cylindrical")
    tags.update_tag(obj, i, proj_offset=[0, 0, 0], proj_size=[100, 100, 100])
    uv = tags.projection_uvs(obj, tags.tags_of(obj)[i])[0]
    assert uv[:, 0].max() - uv[:, 0].min() < 0.1


def test_cubic_and_frontal_projection():
    scene, cube = _fresh()
    i = tags.add_tag(cube, "material", projection="Cubic")
    uv = tags.projection_uvs(cube, tags.tags_of(cube)[i])
    for face in uv:
        assert np.allclose(sorted(set(np.round(face[:, 0], 9))), [0.0, 1.0])
        assert np.allclose(sorted(set(np.round(face[:, 1], 9))), [0.0, 1.0])
    tags.update_tag(cube, i, projection="Frontal")
    no_cam = tags.projection_uvs(cube, tags.tags_of(cube)[i])
    tags.update_tag(cube, i, projection="Flat")
    flat = tags.projection_uvs(cube, tags.tags_of(cube)[i])
    assert all(np.allclose(a, b) for a, b in zip(no_cam, flat))
    tags.update_tag(cube, i, projection="Frontal")
    front = tags.projection_uvs(cube, tags.tags_of(cube)[i], camera_position=(0, 0, 1000))
    k = int(np.argmax(cube.mesh.polygon_normals()[:, 2]))
    face = front[k]
    assert np.isclose(face[:, 0].mean(), 0.5) and np.isclose(face[:, 1].mean(), 0.5)
    far = 1000.0 - 100.0
    assert np.isclose(face[:, 0].max(), 0.5 + 0.5 * (100.0 / far) * 1000.0 / 100.0)


def test_generate_uvw_and_uvw_mapping():
    scene, cube = _fresh()
    i = tags.add_tag(cube, "material", projection="Spherical")
    expected = tags.projection_uvs(cube, tags.tags_of(cube)[i], tiled=False)
    j = tags.run_action(scene, cube, i, "generate_uvw")
    found = tags.find_tags(cube, "uvw")
    assert len(found) == 1 and found[0][0] == j
    mat_index = tags.find_tags(cube, "material")[0][0]
    assert tags.tags_of(cube)[mat_index]["projection"] == "uvw"
    got = tags.projection_uvs(cube, tags.tags_of(cube)[mat_index])
    assert all(np.allclose(a, b) for a, b in zip(got, expected))
    assert "6 polygons" == tags.tag_summary(cube, j)
    tags.run_action(scene, cube, j, "clear")
    assert tags.uvw_coordinates(cube) is None


def test_material_assignments_with_selection():
    scene, cube = _fresh()
    tags.add_tag(cube, "polygon_selection", name="Top")
    tags.update_tag(cube, 0, selection=[4])
    a = tags.add_tag(cube, "material", material="Base")
    b = tags.add_tag(cube, "material", material="Paint", selection="Top")
    assign = tags.material_assignments(cube)
    assert assign == [a, a, a, a, b, a]
    tags.update_tag(cube, b, selection="Missing")
    assert tags.material_polygons(cube, tags.tags_of(cube)[b]) == set()
    tags.set_tag_enabled(cube, a, False)
    assert tags.material_assignments(cube) == [None] * 6
    assert shading.material_side_visible({"side": "Front"}, True)
    assert not shading.material_side_visible({"side": "Front"}, False)
    assert shading.material_side_visible({"side": "Back"}, False)
    assert shading.material_side_visible({"side": "Both"}, False)


def test_math_euler_roundtrip_and_look_rotation():
    rng = np.random.default_rng(7)
    for _ in range(50):
        e = rng.uniform(-170, 170, 3)
        e[1] = rng.uniform(-80, 80)
        r = rotation_matrix(e)
        back = mathutil.euler_from_matrix(r, reference=e)
        assert np.allclose(back, e, atol=1e-7)
        assert np.allclose(rotation_matrix(mathutil.euler_from_matrix(r)), r, atol=1e-9)
    f = np.array([1.0, 2.0, -0.5])
    fn = f / np.linalg.norm(f)
    cols = {"+Z": (2, 1), "-Z": (2, -1), "+X": (0, 1), "-X": (0, -1), "+Y": (1, 1), "-Y": (1, -1)}
    for axis, (col, sign) in cols.items():
        r = mathutil.look_rotation(f, (0, 1, 0), axis)
        assert np.allclose(r.T @ r, np.eye(3)) and np.isclose(np.linalg.det(r), 1.0)
        assert np.allclose(sign * r[:, col], fn)
    assert mathutil.look_rotation((0, 0, 0)) is None
    up = mathutil.look_rotation((0, 5, 0), (0, 1, 0))
    assert np.allclose(up[:, 2], [0, 1, 0])


def test_math_slerp_and_decompose():
    r0 = np.eye(3)
    r1 = rotation_matrix([0, 90, 0])
    half = mathutil.blend_rotation(r0, r1, 0.5)
    assert np.allclose(half, rotation_matrix([0, 45, 0]), atol=1e-9)
    m = mathutil.compose([1, 2, 3], rotation_matrix([10, 20, 30]), [2, 3, 4])
    p, r, s = mathutil.decompose(m)
    assert np.allclose(p, [1, 2, 3]) and np.allclose(s, [2, 3, 4])
    assert np.allclose(r, rotation_matrix([10, 20, 30]))
    vals = [mathutil.smooth_noise(t * 0.1, 3) for t in range(100)]
    assert all(-1.0 <= v <= 1.0 for v in vals)
    assert mathutil.smooth_noise(2.0, 3) == mathutil.hash_unit(2, 3)


def test_target_tag_aims_and_keeps_base():
    scene, cube = _fresh()
    goal = _add(scene, "Goal", pos=(100.0, 0.0, 0.0))
    cube.rotation = np.array([0.0, 0.0, 15.0])
    tags.add_tag(cube, "target", target="Goal")
    changed = tags.evaluate_tags(scene)
    assert cube in changed
    assert np.allclose(cube.world_linear()[:, 2], [1.0, 0.0, 0.0], atol=1e-9)
    base = tags.base_transform(cube)
    assert np.allclose(base["rotation"], [0.0, 0.0, 15.0])
    assert tags.evaluate_tags(scene) == []
    goal.position = np.array([0.0, 0.0, -100.0])
    tags.evaluate_tags(scene)
    assert np.allclose(cube.world_linear()[:, 2], [0.0, 0.0, -1.0], atol=1e-9)
    tags.remove_tag(cube, 0)
    tags.evaluate_tags(scene)
    assert np.allclose(cube.rotation, [0.0, 0.0, 15.0])
    assert runtime.BASE_KEY not in store.object_extras(cube)


def test_target_with_rotated_parent_and_up_vector():
    scene, cube = _fresh()
    holder = _add(scene, "Holder", pos=(10.0, 0.0, 0.0))
    holder.rotation = np.array([0.0, 40.0, 0.0])
    scene.set_parent(cube, holder)
    _add(scene, "Goal", pos=(10.0, 0.0, 200.0))
    _add(scene, "Up", pos=(10.0, 0.0, 0.0))
    cube.position = np.array([0.0, 0.0, 0.0])
    holder.position = np.array([10.0, 0.0, 0.0])
    tags.add_tag(cube, "target", target="Goal", aim_axis="-Z")
    tags.evaluate_tags(scene)
    wl = cube.world_matrix()[:3, :3]
    assert np.allclose(-wl[:, 2] / np.linalg.norm(wl[:, 2]), [0.0, 0.0, 1.0], atol=1e-9)
    scene.objects[-1].position = np.array([110.0, 0.0, 0.0])
    tags.update_tag(cube, 0, up_vector="Up")
    tags.evaluate_tags(scene)
    wl = cube.world_matrix()[:3, :3]
    assert np.allclose(wl[:, 1] / np.linalg.norm(wl[:, 1]), [1.0, 0.0, 0.0], atol=1e-9)


def test_user_edit_becomes_new_base():
    scene, cube = _fresh()
    _add(scene, "Goal", pos=(0.0, 0.0, 300.0))
    tags.add_tag(cube, "target", target="Goal")
    tags.evaluate_tags(scene)
    cube.position = np.array([300.0, 0.0, 0.0])
    tags.evaluate_tags(scene)
    assert np.allclose(tags.base_transform(cube)["position"], [300.0, 0.0, 0.0])
    d = np.array([-300.0, 0.0, 300.0]) / math.sqrt(2 * 300.0 ** 2)
    assert np.allclose(cube.world_linear()[:, 2], d, atol=1e-9)


def test_look_at_camera_with_argument_and_scene_data():
    scene, cube = _fresh()
    cube.position = np.array([0.0, 0.0, 0.0])
    tags.add_tag(cube, "look_at_camera")
    assert tags.evaluate_tags(scene) == []
    tags.evaluate_tags(scene, camera_position=(0.0, 0.0, -500.0))
    assert np.allclose(cube.world_linear()[:, 2], [0.0, 0.0, -1.0], atol=1e-9)
    tags.update_tag(cube, 0, rotate_h_only=True)
    tags.evaluate_tags(scene, camera_position=(500.0, 500.0, 0.0))
    z = cube.world_linear()[:, 2]
    assert np.allclose(z, [1.0, 0.0, 0.0], atol=1e-9)
    store.set_scene_data(scene, "camera_position", [0.0, 800.0, 1.0])
    tags.update_tag(cube, 0, rotate_h_only=False)
    tags.evaluate_tags(scene)
    assert cube.world_linear()[:, 2][1] > 0.99


def test_look_at_camera_finds_camera_object():
    scene, cube = _fresh()
    cam = SceneObject("Cam", Mesh.empty(), "camera")
    cam.position = np.array([0.0, 0.0, 400.0])
    scene.objects.append(cam)
    assert np.allclose(tags.find_camera_position(scene), [0.0, 0.0, 400.0])
    tags.add_tag(cube, "look_at_camera")
    tags.evaluate_tags(scene)
    assert np.allclose(cube.world_linear()[:, 2], [0.0, 0.0, 1.0], atol=1e-9)
    scene.objects.remove(cam)


def test_vibrate_is_deterministic_bounded_and_seeded():
    scene, cube = _fresh()
    tags.add_tag(cube, "vibrate", position_amplitude=[10.0, 20.0, 0.0], frequency=3.0)
    tag = tags.tags_of(cube)[0]
    a = tags.vibrate_offsets(tag, 1.25)
    b = tags.vibrate_offsets(tag, 1.25)
    assert np.allclose(a["position"], b["position"])
    assert a["position"][2] == 0.0
    samples = np.array([tags.vibrate_offsets(tag, t / 30.0)["position"] for t in range(300)])
    assert np.all(np.abs(samples[:, 0]) <= 10.0 + 1e-9) and np.all(np.abs(samples[:, 1]) <= 20.0 + 1e-9)
    assert np.std(samples[:, 0]) > 0.5
    assert not np.allclose(samples[:, 0] / 10.0, samples[:, 1] / 20.0)
    other = dict(tag, seed=[9.0, 2.0, 3.0])
    assert not np.isclose(tags.vibrate_offsets(other, 1.25)["position"][0], a["position"][0])
    assert np.isclose(tags.vibrate_offsets(other, 1.25)["position"][1], a["position"][1])
    reg = dict(tag, regular=True)
    p0 = tags.vibrate_offsets(reg, 0.2)["position"]
    p1 = tags.vibrate_offsets(reg, 0.2 + 1.0 / 3.0)["position"]
    assert np.allclose(p0, p1, atol=1e-9)
    tags.evaluate_tags(scene, frame=37)
    off = tags.vibrate_offsets(tag, 37 / 30.0)["position"]
    assert np.allclose(cube.position, off)
    tags.evaluate_tags(scene, frame=0)
    assert np.allclose(tags.base_transform(cube)["position"], [0.0, 0.0, 0.0])


def test_vibrate_rotation_and_scale():
    scene, cube = _fresh()
    tags.add_tag(cube, "vibrate", enable_position=False, enable_rotation=True,
                 rotation_amplitude=[0.0, 30.0, 0.0], enable_scale=True, scale_amplitude=[0.5, 0, 0])
    tags.evaluate_tags(scene, frame=11)
    off = tags.vibrate_offsets(tags.tags_of(cube)[0], 11 / 30.0)
    assert np.allclose(cube.rotation, off["rotation"], atol=1e-7)
    assert np.allclose(cube.scale, off["scale"]) and np.allclose(cube.scale, cube.scale[0])
    assert np.allclose(cube.position, 0.0)


def test_protection_locks_channels_and_axes():
    scene, cube = _fresh()
    cube.position = np.array([5.0, 6.0, 7.0])
    tags.add_tag(cube, "protection")
    cube.position = np.array([50.0, 60.0, 70.0])
    cube.scale = np.array([2.0, 2.0, 2.0])
    tags.evaluate_tags(scene)
    assert np.allclose(cube.position, [5.0, 6.0, 7.0]) and np.allclose(cube.scale, 1.0)
    tags.update_tag(cube, 0, lock_y=False, lock_z=False, lock_scale=False)
    cube.position = np.array([50.0, 60.0, 70.0])
    cube.scale = np.array([3.0, 3.0, 3.0])
    tags.evaluate_tags(scene)
    assert np.allclose(cube.position, [5.0, 60.0, 70.0]) and np.allclose(cube.scale, 3.0)
    tags.run_action(scene, cube, 0, "freeze")
    tags.update_tag(cube, 0, lock_y=True, lock_z=True)
    cube.position = np.array([0.0, 0.0, 0.0])
    tags.evaluate_tags(scene)
    assert np.allclose(cube.position, [5.0, 60.0, 70.0])
    tags.set_tag_enabled(cube, 0, False)
    cube.position = np.array([1.0, 1.0, 1.0])
    tags.evaluate_tags(scene)
    assert np.allclose(cube.position, [1.0, 1.0, 1.0])


def test_protection_does_not_block_tag_results():
    scene, cube = _fresh()
    _add(scene, "Goal", pos=(100.0, 0.0, 0.0))
    tags.add_tag(cube, "protection")
    tags.add_tag(cube, "target", target="Goal")
    tags.evaluate_tags(scene)
    assert np.allclose(cube.world_linear()[:, 2], [1.0, 0.0, 0.0], atol=1e-9)


def test_constraint_parent_follows_with_offset_and_strength():
    scene, cube = _fresh()
    driver = _add(scene, "Driver", pos=(100.0, 0.0, 0.0))
    cube.position = np.array([150.0, 0.0, 0.0])
    tags.add_tag(cube, "constraint", mode="Parent", target="Driver")
    tags.evaluate_tags(scene)
    assert np.allclose(cube.position, [150.0, 0.0, 0.0])
    driver.position = np.array([100.0, 100.0, 0.0])
    driver.rotation = np.array([0.0, 90.0, 0.0])
    tags.evaluate_tags(scene)
    rest = np.array([50.0, 0.0, 0.0, 1.0])
    assert np.allclose(cube.world_position(), (driver.world_matrix() @ rest)[:3], atol=1e-9)
    assert np.allclose(cube.world_linear(), rotation_matrix([0, 90, 0]), atol=1e-9)
    tags.update_tag(cube, 0, strength=50.0)
    tags.evaluate_tags(scene)
    full = (driver.world_matrix() @ rest)[:3]
    assert np.allclose(cube.world_position(), (np.array([150.0, 0, 0]) + full) / 2.0, atol=1e-9)
    assert np.allclose(cube.world_linear(), rotation_matrix([0, 45, 0]), atol=1e-9)
    assert "50%" in tags.tag_summary(cube, 0)


def test_constraint_parent_without_offset_acts_like_child():
    scene, cube = _fresh()
    driver = _add(scene, "Driver", pos=(0.0, 100.0, 0.0))
    cube.position = np.array([10.0, 0.0, 0.0])
    tags.add_tag(cube, "constraint", mode="Parent", target="Driver", maintain_offset=False)
    tags.evaluate_tags(scene)
    assert np.allclose(cube.world_position(), [10.0, 100.0, 0.0])


def test_constraint_position_rotation_aim_modes():
    scene, cube = _fresh()
    driver = _add(scene, "Driver", pos=(100.0, 200.0, 300.0))
    driver.rotation = np.array([0.0, 0.0, 30.0])
    tags.add_tag(cube, "constraint", mode="Position", target="Driver", maintain_offset=False,
                 axis_y=False)
    tags.evaluate_tags(scene)
    assert np.allclose(cube.position, [100.0, 0.0, 300.0])
    tags.update_tag(cube, 0, mode="Rotation")
    tags.evaluate_tags(scene)
    assert np.allclose(cube.position, 0.0) and np.allclose(cube.rotation, [0.0, 0.0, 30.0])
    tags.update_tag(cube, 0, mode="Aim", aim_axis="+X")
    tags.evaluate_tags(scene)
    d = np.array([100.0, 200.0, 300.0]) / np.linalg.norm([100.0, 200.0, 300.0])
    assert np.allclose(cube.world_linear()[:, 0], d, atol=1e-9)
    tags.update_tag(cube, 0, mode="Position", maintain_offset=True, axis_y=True)
    cube.position = np.array([0.0, 0.0, 0.0])
    tags.evaluate_tags(scene)
    assert np.allclose(cube.position, 0.0)
    driver.position = np.array([110.0, 200.0, 300.0])
    tags.evaluate_tags(scene)
    assert np.allclose(cube.position, [10.0, 0.0, 0.0])
    tags.run_action(scene, cube, 0, "clear_offset")
    tags.evaluate_tags(scene)
    assert np.allclose(cube.position, [110.0, 200.0, 300.0])
    tags.run_action(scene, cube, 0, "set_offset")
    assert tags.tags_of(cube)[0]["maintain_offset"] and tags.tags_of(cube)[0]["offset"] is None


def test_dependency_order_chains_targets():
    scene, cube = _fresh()
    a = _add(scene, "A", pos=(0.0, 0.0, 0.0))
    b = _add(scene, "B", pos=(0.0, 0.0, 0.0))
    tags.add_tag(cube, "constraint", mode="Position", target="A", maintain_offset=False)
    tags.add_tag(a, "constraint", mode="Position", target="B", maintain_offset=False)
    b.position = np.array([7.0, 8.0, 9.0])
    order = runtime.dependency_order(scene)
    assert order.index(b) < order.index(a) < order.index(cube)
    tags.evaluate_tags(scene)
    assert np.allclose(cube.position, [7.0, 8.0, 9.0]) and np.allclose(a.position, [7.0, 8.0, 9.0])
    tags.add_tag(b, "constraint", mode="Position", target="Cube", maintain_offset=False)
    assert len(runtime.dependency_order(scene)) == len(scene.objects)


def test_reset_runtime_restores_base():
    scene, cube = _fresh()
    tags.add_tag(cube, "vibrate")
    tags.evaluate_tags(scene, frame=20)
    assert not np.allclose(cube.position, 0.0)
    assert tags.reset_runtime(scene) == 1
    assert np.allclose(cube.position, 0.0)
    assert runtime.BASE_KEY not in store.object_extras(cube)


def test_marker_tags_store_values():
    scene, cube = _fresh()
    p = tags.add_tag(cube, "python")
    assert "def main" in tags.tags_of(cube)[p]["code"]
    tags.update_tag(cube, p, code="print(1)\nprint(2)\n", priority="Generators")
    assert tags.tag_summary(cube, p) == "2 lines"
    k = tags.add_tag(cube, "ik", goal="Cube", solver="CCD")
    assert tags.tags_of(cube)[k]["solver"] == "CCD"
    w = tags.add_tag(cube, "weight")
    tags.update_tag(cube, w, weights={"J1": [1.0, 3.0, 0.0], "J2": [1.0, 1.0, 0.0]})
    tags.run_action(scene, cube, w, "normalize")
    ws = tags.tags_of(cube)[w]["weights"]
    assert np.allclose(ws["J1"][:3], [0.5, 0.75, 0.0]) and np.allclose(ws["J2"][:3], [0.5, 0.25, 0.0])
    assert len(ws["J1"]) == 8
    assert normalize_weights({}) == {}
    s = tags.add_tag(cube, "skin", skin_type="Dual Quaternion")
    assert "Dual Quaternion" in tags.tag_summary(cube, s)
    for tid in ("rigid_body", "collider_body", "soft_body"):
        i = tags.add_tag(cube, tid)
        assert tags.tags_of(cube)[i]["type"] == tid


def test_tag_edits_are_undoable_and_selection_is_not():
    scene, cube = _fresh()
    if not hasattr(scene, "set_object_extra"):
        return
    scene.clear_history()
    tags.set_current_tag(scene, cube, None)
    assert not scene.can_undo()
    tags.add_tag(cube, "phong")
    tags.update_tag(cube, 0, angle=33.0)
    assert scene.can_undo()
    scene.undo()
    assert tags.tags_of(scene.objects[0])[0]["angle"] == 80.0
    scene.undo()
    assert tags.tags_of(scene.objects[0]) == []
    scene.redo()
    scene.redo()
    assert tags.tags_of(scene.objects[0])[0]["angle"] == 33.0


def test_runtime_captures_persist_without_undo_steps():
    scene, cube = _fresh()
    _add(scene, "Driver", pos=(10.0, 0.0, 0.0))
    tags.add_tag(cube, "constraint", mode="Position", target="Driver")
    if hasattr(scene, "clear_history"):
        scene.clear_history()
    tags.evaluate_tags(scene)
    off = tags.tags_of(cube)[0]["offset"]
    assert off is not None and np.allclose(off["value"], [-10.0, 0.0, 0.0])
    assert not scene.can_undo()
    json.dumps(store.to_json(store.object_extras(cube)))


def test_commands_add_to_active_object():
    scene, cube = _fresh()
    cmds = tags.commands()
    paths = [p for p, _fn in cmds]
    assert all(p[0] == "Tags" for p in paths)
    labels = {p[-1] for p in paths}
    for spec in tags.tag_specs():
        assert spec.label in labels
    by = {p: fn for p, fn in cmds}
    by[("Tags", "Modeling Tags", "Phong")]()
    by[("Tags", "Rendering Tags", "Material")](False)
    assert [t["type"] for t in tags.tags_of(cube)] == ["phong", "material"]
    assert tags.current_tag(scene) == (cube, 1)
    scene.set_mode("polygons")
    scene.select_components([0])
    by[("Tags", "Set Selection")]()
    assert tags.tags_of(cube)[-1]["type"] == "polygon_selection"
    child = _add(scene, "Kid")
    scene.set_parent(child, cube)
    scene.set_active(cube)
    assert by[("Tags", "Copy Tags to Children")]() == 3
    by[("Tags", "Animation Tags", "Vibrate")]()
    store.set_scene_data(scene, "frame", 15)
    assert cube in by[("Tags", "Evaluate Runtime Tags")]()
    assert by[("Tags", "Reset Runtime Transforms")]() == 1
    by[("Tags", "Remove All Tags")]()
    assert tags.tags_of(cube) == []
    scene.set_active(None)
    assert by[("Tags", "Modeling Tags", "Phong")]() is None


def test_docks_and_pages():
    scene, cube = _fresh()
    ds = tags.docks()
    assert [d[0] for d in ds] == ["Tags", "Tag Attributes"]
    assert all(d[2] in ("left", "right", "bottom") for d in ds)
    for title, factory, _area in ds:
        w = factory()
        assert w.scene is scene
        w.deleteLater()
    titles = {d[0] for d in ds}
    for name, docks in tags.pages():
        assert name and set(docks) <= titles
    _pump()


def _panel_pair(scene):
    from quartz_studio.tags.widgets import TagAttributes, TagsPanel
    panel = TagsPanel(scene)
    attrs = TagAttributes(scene, panel=panel)
    panel.resize(320, 384)
    attrs.resize(320, 448)
    panel.show()
    attrs.show()
    _pump()
    return panel, attrs


def test_tags_panel_drives_list_and_buttons():
    scene, cube = _fresh()
    scene.set_active(cube)
    panel, attrs = _panel_pair(scene)
    assert panel.list.count() == 0 and not panel.empty_label.isHidden()
    cats = [a.text() for a in panel.add_menu.actions()]
    assert cats == list(registry.CATEGORIES)
    sub = panel.add_menu.actions()[1].menu()
    phong_act = next(a for a in sub.actions() if a.text() == "Phong")
    phong_act.trigger()
    assert tags.tags_of(cube)[0]["type"] == "phong"
    panel.add_tag("material")
    panel.add_tag("python")
    assert panel.list.count() == 3 and panel.current_index() == 2
    assert attrs._type == "python"
    panel.up_button.click()
    assert [t["type"] for t in tags.tags_of(cube)] == ["phong", "python", "material"]
    assert panel.current_index() == 1
    panel.down_button.click()
    assert [t["type"] for t in tags.tags_of(cube)] == ["phong", "material", "python"]
    panel.select_index(1)
    assert attrs._type == "material"
    panel.duplicate_button.click()
    assert tags.tags_of(cube)[2]["name"] == "Material.1"
    panel.select_index(0)
    assert not panel.duplicate_button.isEnabled()
    assert not panel.up_button.isEnabled()
    panel.rows[0].toggle.click()
    assert tags.tags_of(cube)[0]["enabled"] is False
    assert panel.rows[0].toggle.isChecked() is False
    panel.select_index(3)
    panel.remove_button.click()
    assert len(tags.tags_of(cube)) == 3 and panel.current_index() == 2
    menu = panel.context_menu()
    texts = [a.text() for a in menu.actions()]
    assert "Remove" in texts and "Add Tag" in texts
    assert panel.count_label.text() == "3 tags"
    other = _add(scene, "Other")
    scene.set_active(other)
    _pump()
    assert panel.list.count() == 0 and panel.object_label.text() == "Other"
    assert attrs.tag() is None
    panel.deleteLater()
    attrs.deleteLater()
    _pump()


def test_tags_panel_runtime_footer():
    scene, cube = _fresh()
    scene.set_active(cube)
    panel, attrs = _panel_pair(scene)
    panel.add_tag("vibrate")
    panel.frame_spin.setValue(12)
    assert panel.frame() == 12.0
    panel.evaluate_button.click()
    off = tags.vibrate_offsets(tags.tags_of(cube)[0], 12 / 30.0)["position"]
    assert np.allclose(cube.position, off)
    panel.reset_button.click()
    assert np.allclose(cube.position, 0.0)
    panel.set_live(True)
    assert panel.is_live()
    assert np.allclose(cube.position, off)
    panel.frame_spin.setValue(40)
    off40 = tags.vibrate_offsets(tags.tags_of(cube)[0], 40 / 30.0)["position"]
    assert np.allclose(cube.position, off40)
    tags.update_tag(cube, 0, position_amplitude=[0.0, 0.0, 0.0])
    assert np.allclose(cube.position, 0.0)
    scene.changed.emit()
    panel.reset_button.click()
    assert not panel.is_live()
    panel.deleteLater()
    attrs.deleteLater()
    _pump()


def test_tag_attributes_builds_every_tag_type():
    scene, cube = _fresh()
    scene.set_active(cube)
    _add(scene, "Goal")
    scene.set_active(cube)
    panel, attrs = _panel_pair(scene)
    for spec in tags.tag_specs():
        index = panel.add_tag(spec.id)
        assert attrs.obj is cube and attrs.index == index and attrs._type == spec.id
        visible = [p.key for p in spec.params if p.visible]
        assert list(attrs.editors) == visible
        assert set(attrs.action_buttons) == {a.key for a in spec.actions}
        tag = tags.tags_of(cube)[index]
        for key, editor in attrs.editors.items():
            value = editor.value()
            if editor.param.kind == "vector":
                assert np.allclose(value, tag[key])
            else:
                assert value == tag[key], (spec.id, key, value, tag[key])
    panel.deleteLater()
    attrs.deleteLater()
    _pump()


def test_tag_attributes_edits_reach_the_store():
    scene, cube = _fresh()
    scene.set_active(cube)
    _add(scene, "Goal", pos=(0.0, 0.0, 100.0))
    scene.set_active(cube)
    panel, attrs = _panel_pair(scene)
    panel.add_tag("polygon_selection")
    tags.rename_tag(cube, 0, "Top")
    i = panel.add_tag("material")
    ed = attrs.editors
    ed["tiling"].widgets[0].setValue(4.0)
    assert tags.tags_of(cube)[i]["tiling"] == [4.0, 1.0]
    combo = ed["projection"].widgets[0]
    assert combo.itemText(combo.findData("cubic")) == "Cubic"
    combo.setCurrentIndex(combo.findData("cubic"))
    combo.activated.emit(combo.currentIndex())
    assert tags.tags_of(cube)[i]["projection"] == "cubic"
    ed["proj_size"].widgets[1].setValue(25.0)
    assert np.allclose(tags.tags_of(cube)[i]["proj_size"][1], 25.0)
    sel = ed["selection"].widgets[0]
    assert sel.findData("Top") >= 0
    sel.setCurrentIndex(sel.findData("Top"))
    sel.activated.emit(sel.currentIndex())
    assert tags.tags_of(cube)[i]["selection"] == "Top"
    ed["material"].widgets[0].setText("Steel")
    ed["material"].widgets[0].editingFinished.emit()
    assert tags.tags_of(cube)[i]["material"] == "Steel"
    attrs.name_edit.setText("Metal")
    attrs.name_edit.editingFinished.emit()
    assert tags.tags_of(cube)[i]["name"] == "Metal"
    attrs.enabled_box.setChecked(False)
    assert tags.tags_of(cube)[i]["enabled"] is False
    attrs.action_buttons["reset_projection"].click()
    assert tags.tags_of(cube)[i]["tiling"] == [1.0, 1.0]
    assert attrs.editors["tiling"].value() == [1.0, 1.0]
    t = panel.add_tag("target")
    tcombo = attrs.editors["target"].widgets[0]
    assert tcombo.findData("Goal") >= 0 and tcombo.findData("Cube") < 0
    tcombo.setCurrentIndex(tcombo.findData("Goal"))
    tcombo.activated.emit(tcombo.currentIndex())
    assert tags.tags_of(cube)[t]["target"] == "Goal"
    _add(scene, "Late")
    scene.set_active(cube)
    _pump()
    assert attrs.editors["target"].widgets[0].findData("Late") >= 0
    p = panel.add_tag("python")
    code = attrs.editors["code"]
    code.widgets[0].setPlainText("x = 1\n")
    code.commit()
    assert tags.tags_of(cube)[p]["code"] == "x = 1\n"
    tags.update_tag(cube, p, code="y = 2\n")
    assert code.widgets[0].toPlainText() == "y = 2\n"
    panel.deleteLater()
    attrs.deleteLater()
    _pump()


def test_tag_attributes_action_buttons_run():
    scene, cube = _fresh()
    scene.set_active(cube)
    panel, attrs = _panel_pair(scene)
    scene.set_mode("polygons")
    scene.select_components([2, 3])
    panel.add_tag("polygon_selection")
    attrs.action_buttons["set"].click()
    assert tags.tags_of(cube)[0]["selection"] == [2, 3]
    assert "2 polygons" in attrs.summary_label.text()
    scene.select_components([])
    attrs.action_buttons["restore"].click()
    assert scene.selected_polygons == {2, 3}
    panel.add_tag("phong")
    attrs.editors["angle"].widgets[0].setValue(120.0)
    assert tags.tags_of(cube)[1]["angle"] == 120.0
    assert panel.run_action("clear_breaks") == 0
    panel.deleteLater()
    attrs.deleteLater()
    _pump()


def test_widgets_follow_object_removal():
    scene, cube = _fresh()
    other = _add(scene, "Other")
    scene.set_active(other)
    panel, attrs = _panel_pair(scene)
    panel.add_tag("display")
    assert attrs.obj is other
    scene.remove_object(other)
    _pump()
    assert attrs.obj is None or attrs.obj in scene.objects
    assert panel._obj is None or panel._obj in scene.objects
    panel.deleteLater()
    attrs.deleteLater()
    _pump()
    before = len(store._LISTENERS)
    from quartz_studio.tags.widgets import TagsPanel
    w = TagsPanel(scene)
    assert len(store._LISTENERS) == before + 1
    w.deleteLater()
    _pump()
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert len(store._LISTENERS) == before


def test_chip_and_toggle_paint():
    from PySide6.QtGui import QImage, QPainter
    from quartz_studio.tags.widgets import EnableToggle, TagChip
    for tid in tags.tag_ids():
        chip = TagChip(tid)
        img = QImage(24, 24, QImage.Format.Format_ARGB32)
        img.fill(0)
        chip.render(img)
        assert any(img.pixel(x, y) != 0 for x in range(24) for y in range(24))
        chip.deleteLater()
    t = EnableToggle(None, True)
    img = QImage(32, 16, QImage.Format.Format_ARGB32)
    img.fill(0)
    t.render(img)
    on = img.pixel(4, 8)
    t.setChecked(False)
    img.fill(0)
    t.render(img)
    assert img.pixel(4, 8) != on
    t.deleteLater()
    _pump()


def test_review_foreign_material_tags_stay_byte_identical():
    from quartz_studio.materials import tags as mtags
    scene, cube = _fresh()
    mtags.add_material_tag(cube, "mat1", projection="spherical", tiling=(2, 3))
    store.object_extras(cube)["tags"].append({"type": "custom_thing", "x": [1, 2], "keep": "me"})
    before = json.dumps(store.object_extras(cube)["tags"], sort_keys=True)
    i = tags.add_tag(cube, "phong")
    tags.update_tag(cube, i, angle=40.0)
    tags.add_tag(cube, "vibrate")
    tags.move_tag(cube, 3, 0)
    after = [t for t in store.object_extras(cube)["tags"] if t.get("type") in ("material", "custom_thing")]
    assert json.dumps(after, sort_keys=True) == before
    assert mtags.material_tags(cube)[0]["projection"] == "spherical"
    assert mtags.material_tags(cube)[0]["tiling"] == [2.0, 3.0]


def test_review_material_schema_is_shared_with_materials_package():
    from quartz_studio.materials import tags as mtags
    scene, cube = _fresh()
    i = tags.add_tag(cube, "material", material="m7", projection="Cubic", tiling=[2.0, 3.0],
                     offset=[0.25, -0.5])
    tag = tags.tags_of(cube)[i]
    assert tag["projection"] == "cubic" and tag["tiling"] == [2.0, 3.0] and tag["offset"] == [0.25, -0.5]
    assert not any(k in tag for k in ("tiles_u", "tiles_v", "offset_u", "offset_v"))
    mt = mtags.material_tags(cube)[0]
    assert mt["material"] == "m7" and mt["projection"] in mtags.PROJECTIONS
    u, v = mtags.object_uvs(cube, mt)
    assert len(u) == len(cube.mesh.points) and np.all(np.isfinite(u))
    mtags.set_tag_field(cube, 0, "projection", "spherical")
    mtags.set_tag_field(cube, 0, "tiling", (4.0, 1.0))
    tag = tags.tags_of(cube)[i]
    assert tag["projection"] == "spherical" and tags.shading.tag_tiling(tag).tolist() == [4.0, 1.0]
    raw = tags.projection_uvs(cube, tag, tiled=False)
    tiled = tags.projection_uvs(cube, tag)
    assert np.allclose(tiled[0][:, 0], raw[0][:, 0] * 4.0 + 0.25)
    mtags.add_material_tag(cube, "m8", projection="flat")
    j = tags.find_tags(cube, "material")[1][0]
    tags.update_tag(cube, j, side="Front")
    t2 = tags.tags_of(cube)[j]
    assert t2["projection"] == "flat" and t2["material"] == "m8" and t2["side"] == "Front"
    assert mtags.material_tags(cube)[1]["tiling"] == [1.0, 1.0]
    assert all(a == j for a in tags.material_assignments(cube, front=True))
    assert all(a == i for a in tags.material_assignments(cube, front=False))


def test_review_legacy_material_tags_migrate_on_write():
    scene, cube = _fresh()
    legacy = {"type": "material", "name": "Old", "enabled": True, "projection": "Spherical",
              "offset_u": 10.0, "offset_v": -20.0, "tiles_u": 2.0, "tiles_v": 3.0}
    assert np.allclose(tags.shading.tag_tiling(legacy), [2.0, 3.0])
    assert np.allclose(tags.shading.tag_offset(legacy), [0.1, -0.2])
    tags.set_tags(cube, [legacy])
    tag = tags.tags_of(cube)[0]
    assert tag["projection"] == "spherical"
    assert np.allclose(tag["tiling"], [2.0, 3.0]) and np.allclose(tag["offset"], [0.1, -0.2])
    assert "tiles_u" not in tag and "offset_u" not in tag
    assert legacy["tiles_u"] == 2.0


def test_review_copy_tags_does_not_carry_captured_state():
    scene, parent = _fresh()
    parent.position = np.array([500.0, 0.0, 0.0])
    child = _add(scene, "Kid")
    child.parent = parent
    child.position = np.array([-500.0, 0.0, 0.0])
    other = _add(scene, "Driver", pos=(0.0, 300.0, 0.0))
    tags.add_tag(parent, "protection")
    tags.add_tag(parent, "constraint", mode="Position", target="Driver")
    tags.evaluate_tags(scene)
    assert tags.tags_of(parent)[1]["offset"] is not None
    scene.set_active(parent)
    by = {p: fn for p, fn in tags.commands()}
    if hasattr(scene, "clear_history"):
        scene.clear_history()
    by[("Tags", "Copy Tags to Children")]()
    if hasattr(scene, "clear_history"):
        assert len(scene._undo) == 1
    kid_tags = tags.tags_of(child)
    prot = [t for t in kid_tags if t["type"] == "protection"][0]
    cons = [t for t in kid_tags if t["type"] == "constraint"][0]
    assert np.allclose(prot["frozen"]["position"], [-500.0, 0.0, 0.0])
    assert cons["offset"] is None
    tags.update_tag(child, 1, enabled=False)
    tags.evaluate_tags(scene)
    assert np.allclose(child.position, [-500.0, 0.0, 0.0])
    assert np.allclose(child.world_position(), [0.0, 0.0, 0.0])
    assert other.name == "Driver"


def test_review_object_references_follow_renames():
    scene, cube = _fresh()
    target = _add(scene, "T", pos=(0.0, 0.0, 300.0))
    scene.set_active(cube)
    tags.add_tag(cube, "constraint", mode="Position", target="T", maintain_offset=False)
    tags.evaluate_tags(scene)
    assert np.allclose(cube.position, [0.0, 0.0, 300.0])
    scene.rename_object(target, "T2")
    assert tags.tags_of(cube)[0]["target"] == "T2"
    target.position = np.array([50.0, 0.0, 0.0])
    tags.evaluate_tags(scene)
    assert np.allclose(cube.position, [50.0, 0.0, 0.0])
    if hasattr(scene, "set_object_extra"):
        scene.undo()
        assert scene.objects[1].name == "T" and tags.tags_of(scene.objects[0])[0]["target"] == "T"


def test_review_rename_updates_weight_keys_and_selection_refs():
    scene, cube = _fresh()
    joint = _add(scene, "J1")
    w = tags.add_tag(cube, "weight")
    tags.update_tag(cube, w, weights={"J1": [1.0] * 8}, joint="J1")
    s = tags.add_tag(cube, "polygon_selection", name="Top")
    m = tags.add_tag(cube, "material", selection="Top")
    scene.rename_object(joint, "Shoulder")
    tag = tags.tags_of(cube)[w]
    assert "Shoulder" in tag["weights"] and "J1" not in tag["weights"] and tag["joint"] == "Shoulder"
    tags.rename_tag(cube, s, "Roof")
    assert tags.tags_of(cube)[m]["selection"] == "Roof"


def test_review_object_combo_shows_missing_and_renamed_targets():
    scene, cube = _fresh()
    b = _add(scene, "B")
    scene.set_active(cube)
    panel, attrs = _panel_pair(scene)
    t = panel.add_tag("target")
    tags.update_tag(cube, t, target="B")
    _pump()
    combo = attrs.editors["target"].widgets[0]
    assert combo.currentData() == "B"
    scene.rename_object(b, "Bee")
    _pump()
    combo = attrs.editors["target"].widgets[0]
    assert tags.tags_of(cube)[t]["target"] == "Bee"
    assert combo.currentData() == "Bee" and not attrs.editors["target"].is_missing()
    tags.update_tag(cube, t, target="Ghost")
    _pump()
    combo = attrs.editors["target"].widgets[0]
    assert combo.currentText() == "Ghost (missing)" and attrs.editors["target"].is_missing()
    _add(scene, "Late")
    scene.set_active(cube)
    _pump()
    combo = attrs.editors["target"].widgets[0]
    assert combo.currentText() == "Ghost (missing)" and combo.findData("Late") >= 0
    panel.deleteLater()
    attrs.deleteLater()
    _pump()


def test_review_scrubbing_coalesces_undo_steps():
    scene, cube = _fresh()
    if not hasattr(scene, "set_object_extra"):
        return
    scene.set_active(cube)
    panel, attrs = _panel_pair(scene)
    panel.add_tag("vibrate")
    _pump()
    core.end_coalescing()
    n0 = len(scene._undo)
    spin = attrs.editors["frequency"].widgets[0]
    for k in range(20):
        spin.setValue(3.0 + k * 0.1)
    assert len(scene._undo) == n0 + 1
    assert abs(tags.tags_of(cube)[0]["frequency"] - 4.9) < 1e-9
    vec = attrs.editors["position_amplitude"].widgets[1]
    for k in range(10):
        vec.setValue(20.0 + k)
    assert len(scene._undo) == n0 + 2
    core.end_coalescing()
    spin.setValue(7.0)
    assert len(scene._undo) == n0 + 3
    scene.undo()
    scene.undo()
    scene.undo()
    _pump()
    assert tags.tags_of(scene.objects[0])[0]["frequency"] == 2.0
    i = tags.add_tag(scene.objects[0], "material", projection="Spherical")
    n1 = len(scene._undo)
    tags.run_action(scene, scene.objects[0], i, "generate_uvw")
    assert len(scene._undo) == n1 + 1
    panel.deleteLater()
    attrs.deleteLater()
    _pump()


def test_review_dock_attributes_survive_undo():
    scene, cube = _fresh()
    if not hasattr(scene, "set_object_extra"):
        return
    scene.set_active(cube)
    factories = {title: factory for title, factory, _a in tags.docks()}
    panel = factories["Tags"]()
    attrs = factories["Tag Attributes"]()
    panel.show()
    attrs.show()
    _pump()
    panel.add_tag("vibrate")
    _pump()
    assert attrs.obj is cube and attrs.index == 0
    core.end_coalescing()
    attrs.editors["frequency"].widgets[0].setValue(5.0)
    core.end_coalescing()
    scene.undo()
    _pump()
    new_cube = scene.objects[0]
    assert new_cube is not cube
    assert attrs.obj is new_cube and attrs.index == 0 and attrs.editors
    assert attrs.editors["frequency"].value() == 2.0
    scene.redo()
    _pump()
    assert attrs.obj is scene.objects[0] and attrs.editors["frequency"].value() == 5.0
    panel.deleteLater()
    attrs.deleteLater()
    _pump()


def test_review_code_edits_survive_quick_tag_switch():
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QFocusEvent
    scene, cube = _fresh()
    scene.set_active(cube)
    panel, attrs = _panel_pair(scene)
    panel.add_tag("vibrate")
    p = panel.add_tag("python")
    _pump()
    attrs.editors["code"].widgets[0].setPlainText("print('hi')")
    assert attrs.editors["code"].has_pending()
    panel.select_index(0)
    _pump()
    assert tags.tags_of(cube)[p]["code"] == "print('hi')"
    assert attrs.index == 0
    panel.select_index(p)
    _pump()
    editor = attrs.editors["code"]
    editor.widgets[0].setPlainText("x = 2\n")
    _APP.sendEvent(editor.widgets[0], QFocusEvent(QEvent.Type.FocusOut))
    assert not editor.has_pending()
    assert tags.tags_of(cube)[p]["code"] == "x = 2\n"
    panel.deleteLater()
    attrs.deleteLater()
    _pump()


def test_review_remove_all_keeps_object_in_attributes():
    scene, cube = _fresh()
    scene.set_active(cube)
    panel, attrs = _panel_pair(scene)
    from quartz_studio.tags.widgets import TagAttributes
    lone = TagAttributes(scene)
    by = {p: fn for p, fn in tags.commands()}
    by[("Tags", "Animation Tags", "Vibrate")]()
    _pump()
    assert lone.obj is cube and lone.index == 0
    by[("Tags", "Remove All Tags")]()
    _pump()
    for w in (attrs, lone):
        assert w.obj is cube and w.index is None
        assert w.empty_label.text() == "Select a tag to edit it"
    assert tags.current_tag(scene) == (cube, None)
    for w in (panel, attrs, lone):
        w.deleteLater()
    _pump()


def test_review_aim_is_exact_under_sheared_parent():
    scene, cube = _fresh()
    parent = _add(scene, "P")
    parent.rotation = np.array([0.0, 45.0, 0.0])
    parent.scale = np.array([2.0, 1.0, 1.0])
    child = _add(scene, "C")
    child.parent = parent
    child.position = np.array([0.0, 200.0, 0.0])
    b = _add(scene, "B", pos=(300.0, 100.0, -200.0))
    tags.add_tag(child, "target", target="B")
    tags.evaluate_tags(scene)
    d = b.world_position() - child.world_position()
    aim = child.world_linear() @ np.array([0.0, 0.0, 1.0])
    assert float(np.dot(aim / np.linalg.norm(aim), d / np.linalg.norm(d))) > 0.999999
    tags.update_tag(child, 0, aim_axis="-X")
    tags.evaluate_tags(scene)
    aim = child.world_linear() @ np.array([-1.0, 0.0, 0.0])
    assert float(np.dot(aim / np.linalg.norm(aim), d / np.linalg.norm(d))) > 0.999999
    tags.clear_tags(child)
    tags.add_tag(child, "look_at_camera")
    cam = np.array([-400.0, 50.0, 600.0])
    tags.evaluate_tags(scene, camera_position=cam)
    d = cam - child.world_position()
    aim = child.world_linear() @ np.array([0.0, 0.0, 1.0])
    assert float(np.dot(aim / np.linalg.norm(aim), d / np.linalg.norm(d))) > 0.999999
    tags.clear_tags(child)
    tags.add_tag(child, "constraint", mode="Aim", target="B", maintain_offset=False)
    tags.evaluate_tags(scene)
    d = b.world_position() - child.world_position()
    aim = child.world_linear() @ np.array([0.0, 0.0, 1.0])
    assert float(np.dot(aim / np.linalg.norm(aim), d / np.linalg.norm(d))) > 0.999999


def test_review_vibrate_scale_never_flips():
    scene, cube = _fresh()
    i = tags.add_tag(cube, "vibrate", enable_position=False, enable_scale=True)
    tags.update_tag(cube, i, scale_amplitude=[2.0, 2.0, 2.0], uniform_scale=False)
    assert tags.tags_of(cube)[i]["scale_amplitude"] == [runtime.MAX_SCALE_AMPLITUDE] * 3
    low = np.inf
    for f in range(60):
        tags.evaluate_tags(scene, f)
        low = min(low, float(np.min(cube.scale)))
    assert low > 0.0


def _grid(n):
    xs, ys = np.meshgrid(np.arange(n + 1), np.arange(n + 1))
    pts = np.column_stack([xs.ravel() * 10.0, np.sin(xs.ravel() * 0.3) * 20.0, ys.ravel() * 10.0])
    polys = [(j * (n + 1) + i, j * (n + 1) + i + 1, (j + 1) * (n + 1) + i + 1, (j + 1) * (n + 1) + i)
             for j in range(n) for i in range(n)]
    return Mesh(pts, polys)


def test_review_shading_is_fast_on_medium_meshes():
    import time
    scene, _cube = _fresh()
    obj = scene.add_object("Grid", _grid(100))
    t0 = time.perf_counter()
    normals = tags.phong_normals(obj.mesh)
    t1 = time.perf_counter()
    assert len(normals) == 10000 and t1 - t0 < 0.5
    i = tags.add_tag(obj, "material", projection="Spherical")
    t0 = time.perf_counter()
    uvs = tags.projection_uvs(obj, tags.tags_of(obj)[i])
    t1 = time.perf_counter()
    assert len(uvs) == 10000 and t1 - t0 < 0.5
    t0 = time.perf_counter()
    tags.generate_uvw(scene, obj, i)
    t1 = time.perf_counter()
    assert t1 - t0 < 1.5
    got = tags.projection_uvs(obj, tags.tags_of(obj)[i], tiled=False)
    assert all(np.allclose(a, b) for a, b in zip(got[:50], uvs[:50]))
    small = scene.add_object("Small", _grid(3))
    ref = tags.phong_normals(small.mesh, angle_limit=False)
    assert all(np.allclose(np.linalg.norm(n, axis=1), 1.0) for n in ref)


def test_review_ik_tag_feeds_the_rig_package():
    from quartz_studio.rig import data as rig_data
    from quartz_studio.rig import ik as rig_ik
    from quartz_studio.rig import joints as rig_joints
    scene, _cube = _fresh()
    chain = rig_joints.create_chain(scene, [(0.0, 0.0, 0.0), (0.0, 100.0, 0.0), (0.0, 200.0, 0.0)],
                                    name="Arm")
    goal = _add(scene, "Goal", pos=(120.0, 80.0, 0.0))
    start = chain[0]
    k = tags.add_tag(start, "ik", end=chain[-1].name, goal="Goal", strength=50.0, solver="CCD")
    found = rig_ik.ik_tags(scene)
    assert len(found) == 1 and found[0][0] is start
    rec = found[0][1]
    assert rec["goal"] == "Goal" and rec["end"] == chain[-1].name and rec["solver"] == "CCD"
    assert abs(rec["blend"] - 0.5) < 1e-9
    tags.update_tag(start, k, strength=100.0, solver="Two Bone")
    assert rig_ik.ik_tag(start)["blend"] == 1.0 and rig_ik.ik_tag(start)["solver"] == "Two Bone"
    rig_ik.solve_ik(scene, start)
    assert np.linalg.norm(chain[-1].world_position() - goal.world_position()) < 1.0
    tags.set_tag_enabled(start, k, False)
    assert rig_ik.ik_tag(start)["enabled"] is False
    tags.remove_tag(start, k)
    assert rig_data.IK_KEY not in store.object_extras(start)
    other = chain[1]
    store.object_extras(other)[rig_data.IK_KEY] = {"end": chain[-1].name, "goal": "Goal", "blend": 0.25,
                                                   "solver": "CCD", "iterations": 9}
    k2 = tags.add_tag(other, "ik")
    t = tags.tags_of(other)[k2]
    assert t["goal"] == "Goal" and abs(t["strength"] - 25.0) < 1e-9 and t["iterations"] == 9
    tags.remove_tag(other, k2)
    assert rig_data.IK_KEY not in store.object_extras(other)
    store.object_extras(chain[2])[rig_data.IK_KEY] = {"end": "x"}
    tags.add_tag(chain[2], "phong")
    assert store.object_extras(chain[2])[rig_data.IK_KEY] == {"end": "x"}


def test_review_weight_tag_can_be_edited():
    from quartz_studio.tags.builtin import set_point_weights
    out = set_point_weights({"A": [1.0, 1.0, 1.0]}, "B", [0, 2], 0.6, 3)
    assert np.allclose(out["A"], [0.4, 1.0, 0.4]) and np.allclose(out["B"], [0.6, 0.0, 0.6])
    raw = set_point_weights({"A": [1.0, 1.0]}, "A", [1], 0.3, 2, normalize=False)
    assert np.allclose(raw["A"], [1.0, 0.3])
    scene, cube = _fresh()
    j1 = _add(scene, "J1")
    j1.kind = "joint"
    scene.set_active(cube)
    panel, attrs = _panel_pair(scene)
    w = panel.add_tag("weight")
    _pump()
    combo = attrs.editors["joint"].widgets[0]
    assert combo.findData("J1") >= 0 and combo.findData("Cube") < 0
    combo.setCurrentIndex(combo.findData("J1"))
    combo.activated.emit(combo.currentIndex())
    attrs.editors["value"].widgets[0].setValue(60.0)
    scene.set_mode("points")
    scene.selected_points.update({0, 1})
    assert attrs.run_action("assign") == 2
    ws = tags.tags_of(cube)[w]["weights"]
    assert np.allclose(ws["J1"][:3], [0.6, 0.6, 0.0]) and len(ws["J1"]) == 8
    scene.selected_points.clear()
    attrs.run_action("select")
    assert scene.selected_points == {0, 1}
    assert "2 points on J1" in tags.tag_summary(cube, w)
    attrs.run_action("remove_joint")
    assert tags.tags_of(cube)[w]["weights"] == {}
    panel.deleteLater()
    attrs.deleteLater()
    _pump()


def test_review_non_global_scene_records_undo():
    from quartz_studio.scene import Scene
    from quartz_studio.tags.widgets import TagsPanel
    s3 = Scene()
    if not hasattr(s3, "set_object_extra"):
        return
    obj = s3.objects[0]
    tags.add_tag(obj, "phong", scene=s3)
    assert len(s3._undo) == 1
    tags.update_tag(obj, 0, angle=20.0)
    assert len(s3._undo) == 2
    s3.undo()
    assert tags.tags_of(s3.objects[0])[0]["angle"] == 80.0
    s4 = Scene()
    panel = TagsPanel(s4)
    panel.add_tag("vibrate")
    assert len(s4._undo) == 1
    s4.undo()
    _pump()
    assert tags.tags_of(s4.objects[0]) == []
    panel.deleteLater()
    _pump()


def test_panel_inline_rename_drag_reorder_and_frame_sync():
    scene, cube = _fresh()
    scene.set_active(cube)
    panel, attrs = _panel_pair(scene)
    for tid in ("phong", "vibrate", "display"):
        panel.add_tag(tid)
    _pump()
    panel.select_index(1)
    assert panel.rename_current()
    row = panel.rows[1]
    assert row.is_renaming()
    row.name_edit.setText("Shaker")
    row.name_edit.editingFinished.emit()
    _pump()
    assert tags.tags_of(cube)[1]["name"] == "Shaker"
    assert attrs.name_edit.text() == "Shaker"
    panel.rows[0].start_rename()
    panel.rows[0].cancel_rename()
    assert not panel.rows[0].is_renaming() and tags.tags_of(cube)[0]["name"] == "Phong"
    assert panel.drop_move(0, 2)
    _pump()
    assert [t["type"] for t in tags.tags_of(cube)] == ["vibrate", "display", "phong"]
    assert panel.list.currentRow() == 2 and attrs.index == 2 and attrs._type == "phong"
    assert panel.drop_move(2, 0)
    _pump()
    assert [t["type"] for t in tags.tags_of(cube)] == ["phong", "vibrate", "display"]
    assert len(panel.rows) == 3 and panel.rows[0].name.text() == "Phong"
    panel.set_live(True)
    store.set_scene_data(scene, "frame", 12)
    _pump()
    assert panel.frame() == 12.0
    off = tags.vibrate_offsets(tags.tags_of(cube)[1], 12 / 30.0)["position"]
    assert np.allclose(cube.position, off)
    panel.set_live(False)
    panel.deleteLater()
    attrs.deleteLater()
    _pump()


def _run_as_script() -> int:
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    tests.sort(key=lambda item: item[1].__code__.co_firstlineno)
    failures = 0
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}".encode("ascii", "replace").decode())
        else:
            print(f"ok   {name}")
    print(f"{len(tests) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run_as_script())
