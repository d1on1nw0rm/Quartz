from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import copy
import json
import math
import tempfile

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

APP = QApplication.instance() or QApplication([])

from quartz_studio.ext import store
import quartz_studio.materials.menus as commands
from quartz_studio.materials import colorutil, convert, evaluate, hub, model, nodes as N, noise, preview
from quartz_studio.materials import ramp, tags, textures
from quartz_studio.materials.editor import MaterialEditor
from quartz_studio.materials.manager import MATERIAL_MIME, MaterialManager
from quartz_studio.materials.node_editor import LinkItem, NodeEditor
from quartz_studio.materials.params import Param, coerce
from quartz_studio.materials.ui_common import ColorButton, FloatField, ParamForm, RampEditor, VecField
from quartz_studio.scene import Mesh, SceneObject, reset_scene

TMP = tempfile.mkdtemp(prefix="qs_materials_")


def _close(a, b, tol=1e-6) -> bool:
    return bool(np.allclose(np.asarray(a, float), np.asarray(b, float), atol=tol))


def _ctx(u, v, **kw):
    return evaluate.make_context(np.atleast_1d(u), np.atleast_1d(v), **kw)


def _const_tex(color) -> dict:
    return textures.new_texture("checker", color1=color, color2=color)


def _write_image(name: str, alpha: int = 255) -> str:
    img = QImage(2, 2, QImage.Format.Format_RGBA8888)
    img.setPixelColor(0, 0, QColor(255, 0, 0, alpha))
    img.setPixelColor(1, 0, QColor(0, 255, 0, alpha))
    img.setPixelColor(0, 1, QColor(0, 0, 255, alpha))
    img.setPixelColor(1, 1, QColor(255, 255, 255, alpha))
    path = os.path.join(TMP, name)
    assert img.save(path)
    textures.clear_image_cache()
    return path


def _pump(n: int = 3) -> None:
    for _ in range(n):
        APP.processEvents()


def _mouse(widget, kind, pos: QPoint, button=Qt.MouseButton.LeftButton, buttons=None,
           modifiers=Qt.KeyboardModifier.NoModifier) -> None:
    if buttons is None:
        buttons = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseButtonRelease else button
    local = QPointF(pos)
    glob = QPointF(widget.mapToGlobal(pos))
    ev = QMouseEvent(kind, local, glob, button if kind != QEvent.Type.MouseMove else Qt.MouseButton.NoButton,
                     buttons, modifiers)
    QApplication.sendEvent(widget, ev)


def test_color_conversions_roundtrip():
    c = np.random.default_rng(1).random((50, 3))
    assert _close(colorutil.linear_to_srgb(colorutil.srgb_to_linear(c)), c, 1e-9)
    assert _close(colorutil.hsv_to_rgb(colorutil.rgb_to_hsv(c)), c, 1e-9)
    assert abs(float(colorutil.srgb_to_linear(0.5)) - 0.21404114) < 1e-6
    assert colorutil.to_hex([1.0, 0.5, 0.0]) == "#ff8000"
    assert _close(colorutil.from_hex("#ff8000"), [1.0, 128 / 255, 0.0])
    assert _close(colorutil.from_hex("f80"), [1.0, 136 / 255, 0.0])
    assert abs(float(colorutil.luminance([1.0, 1.0, 1.0])) - 1.0) < 1e-9
    assert _close(colorutil.rgb_to_hsv(np.array([[0.0, 1.0, 0.0]])), [[1 / 3, 1.0, 1.0]])


def test_noise_deterministic_and_bounded():
    p = np.random.default_rng(2).random((500, 3)) * 10
    for kind in noise.NOISE_TYPES:
        a = noise.fractal(p, kind, 4, 0.5, 2.0, 0.0, 3)
        b = noise.fractal(p, kind, 4, 0.5, 2.0, 0.0, 3)
        c = noise.fractal(p, kind, 4, 0.5, 2.0, 0.0, 4)
        assert np.array_equal(a, b), kind
        assert not np.array_equal(a, c), kind
        assert a.min() >= 0.0 and a.max() <= 1.0, kind
        assert a.std() > 0.01, kind
    lattice = np.array([[1.0, 2.0, 3.0], [-4.0, 0.0, 7.0]])
    assert _close(noise.perlin_noise(lattice), [0.0, 0.0])
    assert _close(noise.value_noise(lattice, 5), noise.rand01([1, -4], [2, 0], [3, 7], 5))
    d = noise.fractal(p, "fbm", 3, 0.5, 2.0, 1.0, 0)
    assert not np.array_equal(d, noise.fractal(p, "fbm", 3, 0.5, 2.0, 0.0, 0))


def test_noise_continuity():
    p = np.array([[0.31, 0.47, 0.2]])
    e = np.array([[1e-5, 0.0, 0.0]])
    assert abs(float(noise.perlin_noise(p + e)[0] - noise.perlin_noise(p)[0])) < 1e-3
    assert abs(float(noise.value_noise(p + e)[0] - noise.value_noise(p)[0])) < 1e-3


def test_voronoi_features():
    p = np.random.default_rng(3).random((300, 3)) * 5
    res = noise.voronoi(p, 1.0, "euclidean", 0, 3)
    assert np.all(res["f1"] <= res["f2"] + 1e-12)
    again = noise.voronoi(res["position"], 1.0, "euclidean", 0, 3)
    assert np.all(again["f1"] < 1e-9)
    man = noise.voronoi(p, 1.0, "manhattan", 0, 3)
    che = noise.voronoi(p, 1.0, "chebyshev", 0, 3)
    assert np.all(man["f1"] >= res["f1"] - 1e-9)
    assert np.all(che["f1"] <= res["f1"] + 1e-9)
    grid = noise.voronoi(p, 0.0, "euclidean", 0, 3)
    assert _close(grid["position"], np.floor(p) + 0.5)
    flat = noise.voronoi(p, 1.0, "euclidean", 0, 2)
    assert np.all(flat["position"][:, 2] == 0.0)


def test_ramp_evaluation():
    stops = [[0.0, [0, 0, 0, 1]], [0.5, [1, 0, 0, 1]], [1.0, [1, 1, 1, 0]]]
    out = ramp.evaluate_ramp(stops, [0.0, 0.25, 0.5, 0.75, 1.0, -1.0, 2.0])
    assert _close(out[1], [0.5, 0, 0, 1])
    assert _close(out[3], [1, 0.5, 0.5, 0.5])
    assert _close(out[5], out[0]) and _close(out[6], out[4])
    const = ramp.evaluate_ramp(stops, [0.49, 0.51], "constant")
    assert _close(const, [[0, 0, 0, 1], [1, 0, 0, 1]])
    ease = ramp.evaluate_ramp(stops, [0.125], "ease")
    assert _close(ease[0, 0], 0.15625)
    more = ramp.add_stop(stops, 0.75)
    assert len(more) == 4 and _close(more[2][1], [1, 0.5, 0.5, 0.5])
    assert len(ramp.remove_stop(more, 0)) == 3
    assert len(ramp.remove_stop([[0.3, [1, 1, 1]]], 0)) == 1
    assert ramp.normalize_ramp([[0.9, [1, 1, 1]], [0.1, [0, 0, 0]]])[0][0] == 0.1


def test_param_coercion():
    p = Param("r", "R", "float", 0.5, 0.0, 1.0)
    assert coerce(p, 3.0) == 1.0 and coerce(p, -1) == 0.0 and coerce(p, None) == 0.5
    assert coerce(Param("i", "I", "int", 0, 0, 10), 4.6) == 5
    try:
        coerce(Param("e", "E", "enum", "a", options=("a", "b")), "z")
    except ValueError:
        pass
    else:
        raise AssertionError("enum accepted a bad option")
    assert coerce(Param("c", "C", "color", [0, 0, 0]), (1, 2, 3, 4)) == [1.0, 2.0, 3.0]
    assert coerce(Param("r", "R", "ramp", None), [[0.7, [1, 1, 1]], [0.2, [0, 0, 0]]])[0] == [0.2, [0.0, 0.0, 0.0, 1.0]]


def test_checker_and_gradient_textures():
    tex = textures.new_texture("checker", color1=[1, 0, 0], color2=[0, 0, 1], scale=10)
    col, fac = textures.sample_texture(tex, _ctx([0.05, 0.15, 0.15], [0.05, 0.05, 0.15]))
    assert _close(col, [[1, 0, 0], [0, 0, 1], [1, 0, 0]])
    tex3 = textures.new_texture("checker", color1=[1, 1, 1], color2=[0, 0, 0], scale=1, space="object")
    col, _ = textures.sample_texture(tex3, _ctx([0, 0], [0, 0], pos=[[50, 50, 50], [50, 50, 150]]))
    assert _close(col, [[1, 1, 1], [0, 0, 0]])
    tiled = textures.new_texture("checker", color1=[1, 1, 1], color2=[0, 0, 0], scale=1, tiling=[2, 1])
    col, _ = textures.sample_texture(tiled, _ctx([0.75], [0.25]))
    assert _close(col, [[0, 0, 0]])
    u = np.array([1.0, 0.5, 0.0, 0.5, 0.2])
    v = np.array([0.5, 0.5, 0.5, 0.5, 0.4])
    assert _close(textures.gradient_value(u, v, "radial")[0], 0.5)
    assert _close(textures.gradient_value(u, v, "spherical")[1], 1.0)
    assert _close(textures.gradient_value(u, v, "box")[[1, 2]], [1.0, 0.0])
    assert _close(textures.gradient_value(u, v, "quadratic")[1], 0.25)
    assert _close(textures.gradient_value(u, v, "easing")[1], 0.5)
    assert _close(textures.gradient_value(u, v, "diagonal")[4], 0.3)
    assert _close(textures.gradient_value(np.array([1.25]), np.array([0.0]), "linear", True), [0.25])
    g = textures.new_texture("gradient")
    col, fac = textures.sample_texture(g, _ctx([0.25], [0.9]))
    assert _close(col, [[0.25, 0.25, 0.25]]) and _close(fac, [0.25])


def test_brick_and_voronoi_textures():
    mask, rnd = textures.brick_pattern(np.array([0.125, 0.125, 0.0, 0.0]),
                                       np.array([0.0625, 0.125, 0.0625, 0.1875]),
                                       4.0, 8.0, 0.1, 0.0, 0.5, 0)
    assert _close(mask, [0.0, 1.0, 1.0, 0.0])
    assert np.all((rnd >= 0) & (rnd <= 1))
    tex = textures.new_texture("brick", color1=[1, 0, 0], color2=[1, 0, 0], mortar_color=[0, 1, 0], smooth=0.0)
    col, _ = textures.sample_texture(tex, _ctx([0.125, 0.125], [0.0625, 0.125]))
    assert _close(col, [[1, 0, 0], [0, 1, 0]])
    vt = textures.new_texture("voronoi", feature="f1")
    vt2 = textures.new_texture("voronoi", feature="f2")
    c1, f1 = textures.sample_texture(vt, _ctx(np.linspace(0, 1, 64), np.linspace(1, 0, 64)))
    c2, f2 = textures.sample_texture(vt2, _ctx(np.linspace(0, 1, 64), np.linspace(1, 0, 64)))
    assert np.all(f2 >= f1 - 1e-9)
    cells = textures.new_texture("voronoi", coloring="cells")
    cc, _ = textures.sample_texture(cells, _ctx([0.1, 0.1001], [0.1, 0.1]))
    assert _close(cc[0], cc[1])


def test_noise_texture_contrast_and_mapping():
    base = textures.new_texture("noise", color1=[0, 0, 0], color2=[1, 1, 1])
    hard = textures.new_texture("noise", color1=[0, 0, 0], color2=[1, 1, 1], contrast=4.0)
    ctx = _ctx(np.linspace(0, 1, 200), np.linspace(0, 1, 200) ** 2)
    _, a = textures.sample_texture(base, ctx)
    _, b = textures.sample_texture(hard, ctx)
    assert b.std() > a.std()
    assert _close(b, np.clip((a - 0.5) * 4 + 0.5, 0, 1), 1e-9)


def test_image_texture_sampling():
    path = _write_image("quad.png", 128)
    img = textures.load_image(path)
    assert img.shape == (2, 2, 4)
    tex = textures.new_texture("image", path=path, interpolation="closest")
    col, fac = textures.sample_texture(tex, _ctx([0.25, 0.75, 0.25, 0.75], [0.75, 0.75, 0.25, 0.25]))
    assert _close(col, [[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 1]], 1e-6)
    lin = textures.new_texture("image", path=path, use_alpha=True)
    col, fac = textures.sample_texture(lin, _ctx([0.5], [0.5]))
    assert _close(col, [[0.5, 0.5, 0.5]], 1e-6)
    assert _close(fac, [128 / 255], 1e-6)
    clip = textures.new_texture("image", path=path, extension="clip")
    col, _ = textures.sample_texture(clip, _ctx([1.5], [0.5]))
    assert _close(col, [[0, 0, 0]])
    mirror = textures.new_texture("image", path=path, interpolation="closest", extension="mirror")
    col, _ = textures.sample_texture(mirror, _ctx([1.25], [0.75]))
    assert _close(col, [[0, 1, 0]])
    rep = textures.new_texture("image", path=path, interpolation="closest")
    col, _ = textures.sample_texture(rep, _ctx([1.25], [0.75]))
    assert _close(col, [[1, 0, 0]])
    missing = textures.new_texture("image", path=os.path.join(TMP, "nope.png"))
    col, _ = textures.sample_texture(missing, _ctx([0.5], [0.5]))
    assert _close(col, [textures.MISSING_COLOR])
    assert textures.load_image(path) is img


def test_texture_params_validation():
    tex = textures.new_texture("noise", scale=8, noise_type="ridged")
    assert tex["scale"] == 8.0 and tex["noise_type"] == "ridged"
    try:
        textures.set_texture_param(tex, "nonsense", 1)
    except KeyError:
        pass
    else:
        raise AssertionError("unknown texture param accepted")
    for kind in textures.TEXTURE_TYPES:
        t = textures.new_texture(kind)
        assert "tiling" in t and "offset" in t
        col, fac = textures.sample_texture(t, _ctx(np.linspace(0, 1, 16), np.linspace(0, 1, 16)))
        assert col.shape == (16, 3) and fac.shape == (16,)


def test_material_library_crud():
    s = reset_scene()
    a = model.create_material(s, "pbr")
    b = model.create_material(s, "pbr")
    assert a["name"] == "Mat" and b["name"] == "Mat.1"
    assert model.active_material_id(s) == b["id"]
    assert len(model.materials(s)) == 2
    assert store.get_scene_data(s, "materials")[0]["id"] == a["id"]
    assert model.rename_material(s, a["id"], "Mat.1") == "Mat.2"
    assert model.rename_material(s, a["id"], "Steel") == "Steel"
    d = model.duplicate_material(s, a["id"])
    assert d["name"] == "Steel.1" and d["id"] != a["id"]
    assert [m["id"] for m in model.materials(s)] == [a["id"], d["id"], b["id"]]
    assert model.active_material_id(s) == d["id"]
    assert model.delete_material(s, d["id"])
    assert model.active_material_id(s) == b["id"]
    assert not model.delete_material(s, "missing")
    n = model.create_material(s, "node", name="Graph")
    assert n["type"] == "node" and N.output_node(n["graph"]) is not None
    json.dumps(store.to_json(model.materials(s)))


def test_material_channel_editing():
    mat = model.new_material()
    assert set(mat["channels"]) == set(model.CHANNEL_KEYS)
    model.set_channel(mat, "roughness", "value", 2.0)
    assert mat["channels"]["roughness"]["value"] == 1.0
    model.set_channel(mat, "base_color", "enabled", False)
    assert mat["channels"]["base_color"]["enabled"] is True
    model.set_channel(mat, "emission", "enabled", True)
    assert mat["channels"]["emission"]["enabled"] is True
    model.set_channel_texture(mat, "base_color", "checker")
    model.set_texture_value(mat, "base_color", "tiling", [3, 2])
    model.set_channel_texture(mat, "base_color", "noise")
    assert mat["channels"]["base_color"]["texture"]["type"] == "noise"
    assert mat["channels"]["base_color"]["texture"]["tiling"] == [3.0, 2.0]
    model.set_channel_texture(mat, "bump", "gradient")
    assert mat["channels"]["bump"]["enabled"] is True
    model.set_channel_texture(mat, "base_color", None)
    assert mat["channels"]["base_color"]["texture"] is None
    model.set_channel_texture(mat, "ior", textures.new_texture("checker", color1=[1, 1, 1], color2=[0, 0, 0],
                                                               scale=2))
    assert mat["channels"]["ior"]["texture"]["type"] == "checker"
    res = evaluate.evaluate_material(mat, np.array([0.1, 0.6]), np.array([0.1, 0.1]))
    assert _close(res["ior"], [2.5, 1.0])
    model.set_channel(mat, "ior", "mix", 0.5)
    res = evaluate.evaluate_material(mat, np.array([0.1, 0.6]), np.array([0.1, 0.1]))
    assert _close(res["ior"], [(1.45 + 2.5) / 2, (1.45 + 1.0) / 2])
    graph = convert.pbr_to_graph(mat)
    node_res = evaluate.evaluate_material({"type": "node", "graph": graph}, np.array([0.1, 0.6]),
                                          np.array([0.1, 0.1]))
    assert _close(node_res["ior"], res["ior"], 1e-9)
    try:
        model.set_channel_texture(mat, "nope", "checker")
    except KeyError:
        pass
    else:
        raise AssertionError("unknown channel accepted a texture")
    try:
        model.set_channel(mat, "normal", "value", 1)
    except KeyError:
        pass
    else:
        raise AssertionError("normal channel accepted a value")
    other = copy.deepcopy(mat)
    other["name"] = "Renamed"
    assert model.material_signature(other) == model.material_signature(mat)


def test_presets_all_build():
    for key in model.PRESETS:
        mat = model.preset_material(key)
        res = evaluate.evaluate_material(mat, np.linspace(0, 1, 8), np.linspace(0, 1, 8))
        assert res["base_color"].shape == (8, 3)
    glass = model.preset_material("glass")
    assert evaluate.evaluate_material(glass, 0.5, 0.5)["transmission"] == 1.0


def test_library_save_load_roundtrip():
    s = reset_scene()
    m = model.create_material(s, preset="bricks")
    model.create_material(s, "node")
    path = os.path.join(TMP, "lib.qmat.json")
    assert model.save_library(s, path) == 2
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["format"] == "quartz-materials" and len(data["materials"]) == 2
    s2 = reset_scene()
    loaded = model.load_library(s2, path)
    assert [x["id"] for x in loaded][0] == m["id"]
    assert model.material_signature(model.find_material(s2, m["id"])) == model.material_signature(m)
    again = model.load_library(s2, path)
    assert again[0]["id"] != m["id"] and again[0]["name"] == "Bricks.1"
    assert model.save_library(s2, path, ids=[m["id"]]) == 1


def test_material_tags_format_and_update():
    s = reset_scene()
    obj = s.objects[0]
    m1 = model.create_material(s)
    m2 = model.create_material(s)
    tag = tags.apply_material(obj, m1["id"])
    assert tag == {"type": "material", "material": m1["id"], "projection": "uvw", "offset": [0.0, 0.0],
                   "tiling": [1.0, 1.0], "selection": ""}
    tags.apply_material(obj, m2["id"], tiling=[2, 3])
    assert len(tags.material_tags(obj)) == 1
    assert tags.material_tags(obj)[0]["material"] == m2["id"]
    assert tags.material_tags(obj)[0]["tiling"] == [2.0, 3.0]
    tags.apply_material(obj, m1["id"], selection="top")
    assert len(tags.material_tags(obj)) == 2
    tags.add_material_tag(obj, m1["id"], projection="cubic")
    assert len(tags.material_tags(obj)) == 3
    tags.set_tag_field(obj, 2, "offset", [0.5, 0.25])
    assert tags.material_tags(obj)[2]["offset"] == [0.5, 0.25]
    try:
        tags.set_tag_field(obj, 0, "projection", "bogus")
    except ValueError:
        pass
    else:
        raise AssertionError("bad projection accepted")
    assert tags.remove_tag(obj, 2) and len(tags.material_tags(obj)) == 2
    store.set_object(obj, "tags", tags.object_tags(obj) + [{"type": "phong", "angle": 40}])
    assert tags.remove_material_tags(obj, m1["id"]) == 1
    assert [t["type"] for t in tags.object_tags(obj)] == ["material", "phong"]
    assert tags.objects_using(s, m2["id"]) == [obj]
    model.delete_material(s, m2["id"])
    assert tags.material_tags(obj) == [] and tags.object_tags(obj) == [{"type": "phong", "angle": 40}]


def test_effective_material_resolution():
    s = reset_scene()
    cube = s.objects[0]
    child = SceneObject("Child", Mesh.cube(50.0))
    s.objects.append(child)
    child.parent = cube
    red = model.create_material(s, name="Red")
    blue = model.create_material(s, name="Blue")
    assert tags.effective_material_id(s, cube) is None
    tags.apply_material(cube, red["id"])
    assert tags.effective_material_id(s, child) == red["id"]
    store.set_object(cube, "selections", {"top": [4], "sides": {"type": "polygons", "indices": [0, 1]}})
    tags.apply_material(cube, blue["id"], selection="top")
    ids = tags.polygon_material_ids(s, cube)
    assert ids == [red["id"], red["id"], red["id"], red["id"], blue["id"], red["id"]]
    assert tags.effective_material_id(s, cube, 4) == blue["id"]
    assert tags.effective_material_id(s, cube, 3) == red["id"]
    tags.apply_material(cube, blue["id"], selection="sides")
    assert tags.polygon_material_ids(s, cube)[:2] == [blue["id"], blue["id"]]
    assert tags.polygon_material_ids(s, child) == [red["id"]] * 6
    tags.apply_material(child, blue["id"])
    assert tags.effective_material_id(s, child) == blue["id"]
    s.active = cube
    s.object_selected = True
    assert tags.assign_to_selected(s, red["id"]) == 1
    assert tags.remove_from_selected(s) == 3


def test_uv_projections():
    pts = np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [0.5, 0.25, 1.0], [-1.0, -1.0, 0.0]])
    bounds = ([-1, -1, -1], [1, 1, 1])
    u, v = tags.project_uv("spherical", pts[:2], bounds=bounds)
    assert _close(u[0], 0.5) and _close(v, [0.5, 1.0])
    u, v = tags.project_uv("cubic", pts[2:3], normals=[[0, 0, 1]], bounds=bounds)
    assert _close([u[0], v[0]], [0.75, 0.625])
    u, v = tags.project_uv("cubic", np.array([[0.5, 1.0, 0.5]]), normals=[[0, 1, 0]], bounds=bounds)
    assert _close([u[0], v[0]], [0.75, 0.25])
    u, v = tags.project_uv("flat", pts[3:4], bounds=bounds)
    assert _close([u[0], v[0]], [0.0, 0.0])
    u, v = tags.project_uv("cylindrical", np.array([[1.0, 0.5, 0.0]]), bounds=bounds)
    assert _close([u[0], v[0]], [0.75, 0.75])
    tu, tv = tags.tag_uv({"tiling": [2, 3], "offset": [0.5, 0.25]}, [0.5], [0.5])
    assert _close([tu[0], tv[0]], [1.5, 1.75])
    obj = SceneObject("Plane", Mesh([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], [(0, 1, 2, 3)]))
    store.set_object(obj, "uvw", [[0, 0], [1, 0], [1, 1], [0, 1]])
    u, v = tags.object_uvs(obj, {"projection": "uvw", "tiling": [2, 2], "offset": [0, 0]})
    assert _close(u, [0, 2, 2, 0]) and _close(v, [0, 0, 2, 2])
    cube = SceneObject("Cube", Mesh.cube(2.0))
    u, v = tags.object_uvs(cube, {"projection": "cubic"})
    assert u.shape == (8,) and np.all((u >= 0) & (u <= 1))


def test_evaluate_pbr_defaults_and_channels():
    mat = model.new_material()
    res = evaluate.evaluate_material(mat, 0.3, 0.6)
    assert _close(res["base_color"], [0.6038273] * 3, 1e-6)
    assert res["metallic"] == 0.0 and res["roughness"] == 0.5 and res["alpha"] == 1.0
    assert _close(res["normal"], [0, 0, 1]) and _close(res["emission"], [0, 0, 0])
    raw = evaluate.evaluate_material(mat, 0.3, 0.6, linear=False)
    assert _close(raw["base_color"], [0.8, 0.8, 0.8])
    model.set_channel(mat, "emission", "value", [1.0, 0.5, 0.0])
    model.set_channel(mat, "emission", "strength", 3.0)
    assert _close(evaluate.evaluate_material(mat, 0, 0, linear=False)["emission"], [0, 0, 0])
    model.set_channel(mat, "emission", "enabled", True)
    assert _close(evaluate.evaluate_material(mat, 0, 0, linear=False)["emission"], [3.0, 1.5, 0.0])
    model.set_channel(mat, "metallic", "value", 0.2)
    model.set_channel_texture(mat, "metallic", _const_tex([1.0, 1.0, 1.0]))
    model.set_channel(mat, "metallic", "mix", 0.5)
    assert _close(evaluate.evaluate_material(mat, 0.1, 0.1)["metallic"], 0.6)
    model.set_channel_texture(mat, "alpha", _const_tex([0.25, 0.25, 0.25]))
    assert _close(evaluate.evaluate_material(mat, 0.1, 0.1)["alpha"], 0.25)
    model.set_channel(mat, "alpha", "enabled", False)
    assert evaluate.evaluate_material(mat, 0.1, 0.1)["alpha"] == 1.0
    model.set_channel(mat, "clearcoat", "enabled", True)
    model.set_channel(mat, "clearcoat", "roughness", 0.4)
    res = evaluate.evaluate_material(mat, 0.1, 0.1)
    assert res["clearcoat"] == 1.0 and _close(res["clearcoat_roughness"], 0.4)
    many = evaluate.evaluate_material(mat, np.zeros(7), np.zeros(7))
    assert many["base_color"].shape == (7, 3) and many["roughness"].shape == (7,)


def test_evaluate_normal_map_bump_displacement():
    mat = model.new_material()
    model.set_channel_texture(mat, "normal", _const_tex([0.5, 0.5, 1.0]))
    assert _close(evaluate.evaluate_material(mat, 0.2, 0.2)["normal"], [0, 0, 1])
    s = math.sqrt(0.5)
    model.set_channel_texture(mat, "normal", _const_tex([0.5 + 0.5 * s, 0.5, 0.5 + 0.5 * s]))
    assert _close(evaluate.evaluate_material(mat, 0.2, 0.2)["normal"], [s, 0, s], 1e-6)
    model.set_channel(mat, "normal", "flip_green", True)
    model.set_channel_texture(mat, "normal", _const_tex([0.5, 0.5 + 0.5 * s, 0.5 + 0.5 * s]))
    assert _close(evaluate.evaluate_material(mat, 0.2, 0.2)["normal"], [0, -s, s], 1e-6)
    model.set_channel(mat, "normal", "enabled", False)
    model.set_channel_texture(mat, "bump", textures.new_texture("gradient"))
    model.set_channel(mat, "bump", "strength", 10.0)
    model.set_channel(mat, "bump", "distance", 0.1)
    assert _close(evaluate.evaluate_material(mat, 0.3, 0.4)["normal"], [-s, 0, s], 1e-6)
    model.set_channel(mat, "bump", "invert", True)
    assert _close(evaluate.evaluate_material(mat, 0.3, 0.4)["normal"], [s, 0, s], 1e-6)
    model.set_channel_texture(mat, "bump", _const_tex([0.7, 0.7, 0.7]))
    assert _close(evaluate.evaluate_material(mat, 0.3, 0.4)["normal"], [0, 0, 1])
    model.set_channel_texture(mat, "displacement", textures.new_texture("gradient"))
    model.set_channel(mat, "displacement", "height", 2.0)
    assert _close(evaluate.evaluate_material(mat, 0.75, 0.1)["displacement"], 0.5)
    tilted = evaluate.evaluate_material(model.new_material(), 0.1, 0.1, normal=[0, 1, 0])
    assert _close(tilted["normal"], [0, 1, 0])


def test_display_color():
    mat = model.new_material()
    model.set_channel(mat, "base_color", "value", [0.2, 0.4, 0.6])
    assert _close(evaluate.display_color(mat), [0.2, 0.4, 0.6])
    chk = model.preset_material("checker")
    assert _close(evaluate.display_color(chk), [0.5, 0.5, 0.5], 1e-9)
    assert evaluate.display_color(None) == [0.8, 0.8, 0.8]


def test_graph_editing_operations():
    g = N.new_graph()
    bsdf, out = g["nodes"][0], g["nodes"][1]
    assert bsdf["type"] == "principled" and out["type"] == "output"
    assert N.link_into(g, out["id"], "surface")["from"] == [bsdf["id"], "bsdf"]
    chk = N.add_node(g, "checker", (10, 20))
    assert chk["id"] == "n3" and chk["pos"] == [10.0, 20.0]
    assert chk["inputs"]["scale"] == 5.0 and "vector" not in chk["inputs"]
    ok, why = N.can_connect(g, chk["id"], "color", out["id"], "surface")
    assert not ok and "shader" in why
    N.connect(g, chk["id"], "color", bsdf["id"], "base_color")
    N.connect(g, chk["id"], "fac", bsdf["id"], "base_color")
    assert len([l for l in g["links"] if l["to"] == [bsdf["id"], "base_color"]]) == 1
    math_a = N.add_node(g, "math")
    math_b = N.add_node(g, "math")
    N.connect(g, math_a["id"], "value", math_b["id"], "a")
    try:
        N.connect(g, math_b["id"], "value", math_a["id"], "a")
    except ValueError as exc:
        assert "cycle" in str(exc)
    else:
        raise AssertionError("cycle accepted")
    try:
        N.connect(g, math_a["id"], "value", math_a["id"], "b")
    except ValueError:
        pass
    else:
        raise AssertionError("self link accepted")
    assert N.upstream(g, math_b["id"]) == {math_a["id"]}
    N.set_node_input(g, math_a["id"], "a", 3)
    N.set_node_prop(g, math_a["id"], "op", "power")
    try:
        N.set_node_prop(g, math_a["id"], "op", "nope")
    except ValueError:
        pass
    else:
        raise AssertionError("bad op accepted")
    N.set_node_input(g, chk["id"], "scale", -5)
    assert N.find_node(g, chk["id"])["inputs"]["scale"] == 0.0
    dup = N.duplicate_node(g, math_a["id"])
    assert dup["props"]["op"] == "power" and dup["id"] != math_a["id"]
    assert N.disconnect(g, math_b["id"], "a") and not N.disconnect(g, math_b["id"], "a")
    assert N.remove_node(g, chk["id"])
    assert N.link_into(g, bsdf["id"], "base_color") is None
    g["links"].append({"from": ["zz", "x"], "to": [bsdf["id"], "metallic"]})
    g["links"].append({"from": [math_a["id"], "nope"], "to": [bsdf["id"], "metallic"]})
    assert N.prune_graph(g) == 2
    N.move_node(g, math_a["id"], (5, 6))
    assert N.find_node(g, math_a["id"])["pos"] == [5.0, 6.0]
    assert "Texture" in N.node_types_by_category()


def test_arrange_graph_layers():
    g = N.new_graph()
    chk = N.add_node(g, "checker")
    ramp_node = N.add_node(g, "color_ramp")
    N.connect(g, chk["id"], "fac", ramp_node["id"], "fac")
    N.connect(g, ramp_node["id"], "color", "n1", "base_color")
    pos = N.arrange_graph(g)
    xs = {k: v[0] for k, v in pos.items()}
    assert xs["n2"] > xs["n1"] > xs[ramp_node["id"]] > xs[chk["id"]]
    assert xs["n2"] == 0.0


def _eval_node(type_id: str, inputs: dict | None = None, props: dict | None = None, out: str = "color",
               u=None, v=None, **ctx_kw):
    g = {"nodes": [], "links": [], "next_id": 1}
    node = N.add_node(g, type_id, **(props or {}))
    for k, val in (inputs or {}).items():
        N.set_node_input(g, node["id"], k, val)
    u = np.array([0.25]) if u is None else np.asarray(u, float)
    v = np.array([0.5]) if v is None else np.asarray(v, float)
    ctx = evaluate.make_context(u, v, **ctx_kw)
    return N.GraphEvaluator(g).output(node["id"], out, ctx)


def test_math_node_operations():
    expected = {"add": 5, "subtract": 1, "multiply": 6, "divide": 1.5, "power": 9, "minimum": 2,
                "maximum": 3, "modulo": 1, "absolute": 3, "less_than": 0, "greater_than": 1}
    for op, want in expected.items():
        got = _eval_node("math", {"a": 3, "b": 2}, {"op": op}, "value")
        assert _close(got, [want]), op
    assert _close(_eval_node("math", {"a": 3, "b": 0}, {"op": "divide"}, "value"), [0.0])
    assert _close(_eval_node("math", {"a": -8, "b": 0.5}, {"op": "power"}, "value"), [0.0])
    assert _close(_eval_node("math", {"a": 3, "b": 2}, {"op": "add", "clamp": True}, "value"), [1.0])


def test_color_nodes():
    a, b = [0.25, 0.25, 0.25], [0.5, 0.5, 0.5]
    expected = {"mix": 0.5, "add": 0.75, "multiply": 0.125, "subtract": -0.25, "screen": 0.625,
                "overlay": 0.25, "darken": 0.25, "lighten": 0.5, "difference": 0.25, "divide": 0.5}
    for mode, want in expected.items():
        got = _eval_node("mix_color", {"fac": 1.0, "color1": a, "color2": b}, {"blend": mode})
        assert _close(got, [[want] * 3]), mode
    half = _eval_node("mix_color", {"fac": 0.5, "color1": [0, 0, 0], "color2": [1, 1, 1]})
    assert _close(half, [[0.5] * 3])
    clamp = _eval_node("mix_color", {"fac": 1, "color1": a, "color2": b}, {"blend": "subtract", "clamp": True})
    assert _close(clamp, [[0, 0, 0]])
    assert _close(_eval_node("invert", {"color": [0.2, 0.4, 1.0]}), [[0.8, 0.6, 0.0]])
    assert _close(_eval_node("invert", {"color": [0.2, 0.4, 1.0], "fac": 0.5}), [[0.5, 0.5, 0.5]])
    shifted = _eval_node("hue_saturation", {"color": [1, 0, 0], "hue": 0.5 + 1 / 3})
    assert _close(shifted, [[0, 1, 0]], 1e-9)
    gray = _eval_node("hue_saturation", {"color": [1, 0, 0], "saturation": 0.0})
    assert _close(gray, [[1, 1, 1]])
    dark = _eval_node("hue_saturation", {"color": [1, 0.5, 0], "value": 0.5})
    assert _close(dark, [[0.5, 0.25, 0]])
    assert _close(_eval_node("rgb", props={"color": [0.1, 0.2, 0.3]}), [[0.1, 0.2, 0.3]])
    assert _close(_eval_node("value", props={"value": 4.5}, out="value"), [4.5])
    stops = [[0.0, [1, 0, 0, 1]], [1.0, [0, 0, 1, 0]]]
    assert _close(_eval_node("color_ramp", {"fac": 0.25}, {"stops": stops}), [[0.75, 0, 0.25]])
    assert _close(_eval_node("color_ramp", {"fac": 0.25}, {"stops": stops}, "alpha"), [0.75])
    assert _close(_eval_node("separate_rgb", {"color": [0.1, 0.2, 0.3]}, out="g"), [0.2])
    assert _close(_eval_node("combine_rgb", {"r": 0.1, "g": 0.2, "b": 0.3}), [[0.1, 0.2, 0.3]])


def test_vector_and_input_nodes():
    s = math.sqrt(0.5)
    assert _close(_eval_node("fresnel", {"ior": 1.5}, out="fac"), [0.04])
    grazing = _eval_node("fresnel", {"ior": 1.5}, out="fac", view=[1, 0, 0])
    assert _close(grazing, [1.0])
    mid = _eval_node("fresnel", {"ior": 1.5}, out="fac", view=[s, 0, s])
    assert 0.04 < float(mid[0]) < 1.0
    flat = _eval_node("normal_map", {"color": [0.5, 0.5, 1.0]}, out="normal")
    assert _close(flat, [[0, 0, 1]])
    tilt = _eval_node("normal_map", {"color": [0.5 + 0.5 * s, 0.5, 0.5 + 0.5 * s]}, out="normal")
    assert _close(tilt, [[s, 0, s]], 1e-6)
    half = _eval_node("normal_map", {"color": [0.5 + 0.5 * s, 0.5, 0.5 + 0.5 * s], "strength": 0.0}, out="normal")
    assert _close(half, [[0, 0, 1]])
    obj = _eval_node("normal_map", {"color": [1.0, 0.5, 0.5]}, {"space": "object"}, out="normal")
    assert _close(obj, [[1, 0, 0]])
    tc = _eval_node("texcoord", out="uv", u=[0.2], v=[0.7])
    assert _close(tc, [[0.2, 0.7, 0.0]])
    pos = _eval_node("texcoord", out="object", pos=[[100, 200, 300]])
    assert _close(pos, [[1, 2, 3]])
    mp = _eval_node("mapping", {"scale": [2, 3, 1], "location": [0.5, 0, 0]}, out="vector", u=[0.25], v=[0.5])
    assert _close(mp, [[1.0, 1.5, 0.0]])
    rot = _eval_node("mapping", {}, {"rotation": 90.0}, out="vector", u=[1.0], v=[0.0])
    assert _close(rot, [[0.0, 1.0, 0.0]], 1e-9)


def test_texture_nodes():
    chk = _eval_node("checker", {"scale": 10, "color1": [1, 0, 0], "color2": [0, 0, 1]},
                     u=[0.05, 0.15], v=[0.05, 0.05])
    assert _close(chk, [[1, 0, 0], [0, 0, 1]])
    nf = _eval_node("noise", {"scale": 3}, out="fac", u=np.linspace(0, 1, 50), v=np.zeros(50))
    assert nf.shape == (50,) and np.all((nf >= 0) & (nf <= 1)) and nf.std() > 0
    expect = noise.fractal(np.stack([np.linspace(0, 1, 50), np.zeros(50), np.zeros(50)], 1) * 3, "fbm", 2, 0.5)
    assert _close(nf, expect)
    gr = _eval_node("gradient", {}, {"gradient_type": "vertical"}, out="fac", u=[0.1], v=[0.8])
    assert _close(gr, [0.8])
    vd = _eval_node("voronoi", {"randomness": 0.0, "scale": 1.0}, {}, out="distance", u=[0.5], v=[0.5])
    assert _close(vd, [0.0])
    vp = _eval_node("voronoi", {"randomness": 0.0, "scale": 1.0}, {}, out="position", u=[0.3], v=[0.6])
    assert _close(vp, [[0.5, 0.5, 0.0]])
    br = _eval_node("brick", {"scale": 4, "mortar_size": 0.1}, {"rows_ratio": 2.0, "mortar_smooth": 0.0},
                    out="fac", u=[0.125, 0.125], v=[0.0625, 0.125])
    assert _close(br, [0.0, 1.0])
    path = _write_image("node.png")
    img = _eval_node("image_texture", props={"path": path, "interpolation": "closest"}, u=[0.75], v=[0.25])
    assert _close(img, [[1, 1, 1]])
    missing = _eval_node("image_texture", props={"path": ""}, u=[0.5], v=[0.5])
    assert _close(missing, [textures.MISSING_COLOR])


def test_graph_evaluation_links_and_conversion():
    g = N.new_graph()
    rgb = N.add_node(g, "rgb", color=[0.2, 0.4, 0.6])
    val = N.add_node(g, "value", value=0.3)
    N.connect(g, rgb["id"], "color", "n1", "base_color")
    N.connect(g, rgb["id"], "color", "n1", "roughness")
    N.connect(g, val["id"], "value", "n1", "emission")
    mat = {"type": "node", "graph": g}
    res = evaluate.evaluate_material(mat, 0.5, 0.5, linear=False)
    assert _close(res["base_color"], [0.2, 0.4, 0.6])
    assert _close(res["roughness"], 0.2 * 0.2126 + 0.4 * 0.7152 + 0.6 * 0.0722)
    assert _close(res["emission"], [0.3, 0.3, 0.3])
    tc = N.add_node(g, "texcoord")
    N.connect(g, tc["id"], "object", "n1", "metallic")
    res = evaluate.evaluate_material(mat, 0.5, 0.5, pos=[30.0, 60.0, 90.0])
    assert _close(res["metallic"], 0.6)
    N.disconnect(g, "n2", "surface")
    res = evaluate.evaluate_material(mat, 0.5, 0.5, linear=False)
    assert _close(res["base_color"], [0.8, 0.8, 0.8])
    disp = N.add_node(g, "value", value=0.75)
    N.connect(g, disp["id"], "value", "n2", "displacement")
    assert _close(evaluate.evaluate_material(mat, 0, 0)["displacement"], 0.75)
    g2 = N.new_graph()
    a = N.add_node(g2, "math")
    b = N.add_node(g2, "math")
    g2["links"].append({"from": [a["id"], "value"], "to": [b["id"], "a"]})
    g2["links"].append({"from": [b["id"], "value"], "to": [a["id"], "a"]})
    N.connect(g2, b["id"], "value", "n1", "metallic")
    res = evaluate.evaluate_material({"type": "node", "graph": g2}, 0, 0)
    assert np.isfinite(res["metallic"])


def test_mix_shader_and_bump_nodes():
    g = N.new_graph()
    second = N.add_node(g, "principled")
    N.set_node_input(g, second["id"], "base_color", [0.0, 0.0, 1.0])
    N.set_node_input(g, "n1", "base_color", [1.0, 0.0, 0.0])
    mix = N.add_node(g, "mix_shader")
    N.set_node_input(g, mix["id"], "fac", 0.25)
    N.connect(g, "n1", "bsdf", mix["id"], "shader1")
    N.connect(g, second["id"], "bsdf", mix["id"], "shader2")
    N.connect(g, mix["id"], "shader", "n2", "surface")
    res = evaluate.evaluate_material({"type": "node", "graph": g}, 0, 0, linear=False)
    assert _close(res["base_color"], [0.75, 0.0, 0.25])
    g = N.new_graph()
    grad = N.add_node(g, "gradient")
    bump = N.add_node(g, "bump")
    N.set_node_input(g, bump["id"], "strength", 10)
    N.set_node_input(g, bump["id"], "distance", 0.1)
    N.connect(g, grad["id"], "fac", bump["id"], "height")
    N.connect(g, bump["id"], "normal", "n1", "normal")
    s = math.sqrt(0.5)
    res = evaluate.evaluate_material({"type": "node", "graph": g}, 0.3, 0.4)
    assert _close(res["normal"], [-s, 0, s], 1e-6)
    N.set_node_prop(g, bump["id"], "invert", True)
    res = evaluate.evaluate_material({"type": "node", "graph": g}, 0.3, 0.4)
    assert _close(res["normal"], [s, 0, s], 1e-6)


def _random_material(rng) -> dict:
    mat = model.new_material()
    kinds = list(textures.TEXTURE_TYPES)
    path = _write_image("conv.png")
    for key in ("base_color", "metallic", "roughness", "alpha", "emission", "bump", "displacement", "normal"):
        kind = kinds[int(rng.integers(len(kinds)))]
        extra = {"path": path} if kind == "image" else {}
        tex = textures.new_texture(kind, **extra)
        if kind != "gradient" and kind != "brick" and kind != "image" and rng.random() < 0.5:
            tex["space"] = "object"
        tex["tiling"] = [float(rng.uniform(0.5, 3)), float(rng.uniform(0.5, 3))]
        tex["offset"] = [float(rng.uniform(-1, 1)), float(rng.uniform(-1, 1))]
        if kind == "noise":
            tex["contrast"] = float(rng.uniform(0.5, 3))
        if kind == "voronoi" and rng.random() < 0.5:
            tex["coloring"] = "cells"
        model.set_channel_texture(mat, key, tex)
        if "mix" in mat["channels"][key]:
            mat["channels"][key]["mix"] = float(rng.choice([1.0, 0.5]))
    model.set_channel(mat, "emission", "strength", 2.0)
    model.set_channel(mat, "clearcoat", "enabled", True)
    model.set_channel(mat, "sheen", "enabled", True)
    model.set_channel(mat, "sheen", "tint", [0.3, 0.6, 0.9])
    return mat


def test_pbr_to_node_conversion_matches():
    rng = np.random.default_rng(7)
    u = rng.random(300)
    v = rng.random(300)
    pos = rng.random((300, 3)) * 2 - 1
    nrm = rng.normal(size=(300, 3))
    for key in model.PRESETS:
        mat = model.preset_material(key)
        graph = convert.pbr_to_graph(mat)
        a = evaluate.evaluate_material(mat, u, v, pos, nrm)
        b = evaluate.evaluate_material({"type": "node", "graph": graph}, u, v, pos, nrm)
        for k in evaluate.OUTPUT_KEYS:
            assert _close(a[k], b[k], 1e-9), (key, k)
    for trial in range(6):
        mat = _random_material(rng)
        graph = convert.pbr_to_graph(mat)
        a = evaluate.evaluate_material(mat, u, v, pos, nrm)
        b = evaluate.evaluate_material({"type": "node", "graph": graph}, u, v, pos, nrm)
        for k in evaluate.OUTPUT_KEYS:
            assert _close(a[k], b[k], 1e-7), (trial, k, float(np.max(np.abs(np.asarray(a[k]) - np.asarray(b[k])))))


def test_convert_to_nodes_in_library():
    s = reset_scene()
    m = model.create_material(s, preset="marble")
    out = convert.convert_to_nodes(s, m["id"])
    assert out["type"] == "node" and model.find_material(s, m["id"])["type"] == "node"
    assert convert.convert_to_nodes(s, m["id"]) == model.find_material(s, m["id"])


def test_preview_rendering():
    arr = preview.render_preview_array(model.new_material(), 32)
    assert arr.shape == (32, 32, 4) and arr.dtype == np.uint8
    assert np.all(arr[..., 3] == 255)
    bg = preview.render_preview_array(None, 32, "plane")
    assert not np.array_equal(arr[16, 16], arr[0, 0])
    emissive = model.preset_material("emissive")
    lit = preview.render_preview_array(emissive, 32)
    assert lit[16, 16, :3].astype(int).sum() > arr[16, 16, :3].astype(int).sum()
    for shape in preview.SHAPES:
        out = preview.render_preview_array(model.preset_material("checker"), 24, shape)
        assert out.shape == (24, 24, 4)
        assert np.array_equal(out[0, 0], bg[0, 0]) or shape == "plane"
    alpha = preview.render_preview_array(model.new_material(), 16, background=False)
    assert alpha[0, 0, 3] == 0 and alpha[8, 8, 3] == 255
    mat = model.new_material()
    model.set_channel(mat, "alpha", "enabled", True)
    model.set_channel(mat, "alpha", "value", 0.0)
    ghost = preview.render_preview_array(mat, 32)
    other = copy.deepcopy(mat)
    model.set_channel(other, "base_color", "value", [1, 0, 0])
    assert np.array_equal(ghost, preview.render_preview_array(other, 32))
    assert not np.array_equal(ghost, arr)
    img = preview.render_preview(model.new_material(), 40)
    assert img.width() == 40 and img.height() == 40
    preview.clear_thumbnail_cache()
    t1 = preview.thumbnail(mat, 32)
    t2 = preview.thumbnail(copy.deepcopy(mat), 32)
    assert t1 is t2
    mat2 = copy.deepcopy(mat)
    mat2["preview"] = "cube"
    assert preview.thumbnail(mat2, 32) is not t1


def test_ggx_and_env_brdf_sanity():
    n = np.array([[0.0, 0.0, 1.0]])
    v = np.array([[0.0, 0.0, 1.0]])
    l = np.array([[0.0, 0.0, 1.0]])
    smooth, _ = preview.ggx_specular(n, v, l, np.array([0.1]), np.full((1, 3), 0.04))
    rough, _ = preview.ggx_specular(n, v, l, np.array([0.9]), np.full((1, 3), 0.04))
    assert smooth[0, 0] > rough[0, 0] > 0
    _, f = preview.ggx_specular(n, v, l, np.array([0.5]), np.full((1, 3), 0.04))
    assert _close(f, [[0.04] * 3])
    e = preview.env_brdf(np.full((3, 3), 0.04), np.array([0.0, 0.5, 1.0]), np.array([1.0, 1.0, 1.0]))
    assert np.all(e > 0) and np.all(e < 1)
    assert _close(preview.tonemap(np.array([0.0])), [0.0]) and preview.tonemap(np.array([100.0]))[0] > 0.98


def test_hub_notifications():
    s = reset_scene()
    seen = []
    hub.hub().changed.connect(lambda owner, key: seen.append((owner, key)))
    m = model.create_material(s)
    assert (s, "materials") in seen and (s, "active_material") in seen
    seen.clear()
    tags.apply_material(s.objects[0], m["id"])
    assert (s.objects[0], "tags") in seen
    seen.clear()
    store.set_scene_data(s, "unrelated", 1)
    assert seen == []


def test_commands_docks_pages():
    s = reset_scene()
    cmds = commands.commands()
    paths = [p for p, _ in cmds]
    assert ("Materials", "New PBR Material") in paths and ("Tags", "Material") not in paths
    assert all(isinstance(p, tuple) and callable(fn) for p, fn in cmds)
    lookup = dict(cmds)
    lookup[("Materials", "New PBR Material")]()
    lookup[("Materials", "New Node Material")]()
    lookup[("Materials", "Presets", "Gold")]()
    assert [m["name"] for m in model.materials(s)] == ["Mat", "Mat.1", "Gold"]
    assert lookup[("Materials", "Apply to Selected")]() == 1
    assert tags.material_tags(s.objects[0])[0]["material"] == model.active_material_id(s)
    assert lookup[("Materials", "Apply to Selected")]() == 1
    assert len(tags.material_tags(s.objects[0])) == 1
    assert commands.add_tag_to_selected() == 1
    assert len(tags.material_tags(s.objects[0])) == 1
    assert lookup[("Materials", "Remove from Selected")]() == 1
    dup = lookup[("Materials", "Duplicate Active")]()
    assert dup["name"] == "Gold.1"
    assert lookup[("Materials", "Convert Active to Nodes")]()["type"] == "node"
    assert lookup[("Materials", "Delete Active")]()
    assert lookup[("Materials", "Delete Unused")]() == 3
    assert model.materials(s) == []
    docks = commands.docks()
    assert [d[0] for d in docks] == ["Material Manager", "Material Editor", "Node Editor"]
    assert all(d[2] in ("left", "right", "bottom") for d in docks)
    assert commands.pages() == [("Materials", ["Material Manager", "Material Editor", "Node Editor"])]
    assert commands.key_actions()[0][1] == "Ctrl+Shift+M"
    for title, factory, _area in docks:
        w = factory()
        assert w.scene is s if hasattr(w, "scene") and not callable(w.scene) else True
        w.deleteLater()
    _pump()


def test_ui_common_widgets():
    ff = FloatField(0.5, 0.0, 2.0, 0.01, soft_max=1.0)
    got = []
    ff.valueChanged.connect(got.append)
    ff.slider.setValue(ff.STEPS)
    assert _close(ff.value(), 1.0) and got and _close(got[-1], 1.0)
    ff.spin.setValue(2.0)
    assert ff.slider.value() == ff.STEPS and _close(got[-1], 2.0)
    ff.set_value(0.25)
    assert _close(got[-1], 2.0) and ff.slider.value() == 250
    cb = ColorButton((0.1, 0.2, 0.3))
    colors = []
    cb.colorChanged.connect(colors.append)
    cb.set_color([1, 0, 0], emit=True)
    assert colors == [[1.0, 0.0, 0.0]] and cb.toolTip() == "#ff0000"
    vf = VecField((1, 2))
    vals = []
    vf.valueChanged.connect(vals.append)
    vf.spins[1].setValue(5)
    assert vals[-1] == [1.0, 5.0]
    re = RampEditor()
    ramps = []
    re.rampChanged.connect(ramps.append)
    re.add_at(0.5)
    assert len(ramps[-1]) == 3 and _close(ramps[-1][1][1], [0.5, 0.5, 0.5, 1.0])
    re.color.set_color([1, 0, 0], emit=True)
    assert _close(ramps[-1][re.bar.current][1][:3], [1, 0, 0])
    re.move_stop(re.bar.current, 0.9)
    assert _close(ramps[-1][1][0], 0.9) and _close(ramps[-1][1][1][:3], [1, 0, 0])
    re.alpha.setValue(0.5)
    assert _close(ramps[-1][1][1][3], 0.5)
    re.remove_current()
    assert len(ramps[-1]) == 2
    re.resize(256, 64)
    re.show()
    _pump()
    x = int(re.bar.x_of(0.5))
    QTest.mouseDClick(re.bar, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(x, 8))
    assert len(ramps[-1]) == 3
    params = textures.texture_params("noise") + (Param("ramp", "Ramp", "ramp", ramp.DEFAULT_RAMP),
                                                  Param("path", "Path", "path", ""))
    form = ParamForm(params, textures.new_texture("noise"))
    changes = []
    form.changed.connect(lambda k, v: changes.append((k, v)))
    form.editors["noise_type"].setCurrentIndex(form.editors["noise_type"].findData("ridged"))
    form.editors["seed"].setValue(7)
    form.editors["space"].setCurrentIndex(1)
    form.editors["tiling"].spins[0].setValue(3)
    form.editors["path"].set_path("x.png", emit=True)
    form.set_value("scale", 9.0)
    assert ("noise_type", "ridged") in changes and ("seed", 7) in changes and ("space", "object") in changes
    assert ("tiling", [3.0, 1.0]) in changes and ("path", "x.png") in changes and ("scale", 9.0) in changes
    n = len(changes)
    form.set_values(textures.new_texture("noise", scale=2))
    assert len(changes) == n and _close(form.value("scale"), 2.0)
    for w in (ff, cb, vf, re, form):
        w.deleteLater()
    _pump()


def test_material_manager_widget():
    s = reset_scene()
    mgr = MaterialManager(s)
    mgr.resize(640, 320)
    mgr.show()
    _pump()
    assert mgr.list.count() == 0 and not mgr.apply_button.isEnabled()
    a = mgr.create("pbr")
    b = mgr.create(preset="gold")
    _pump()
    assert mgr.list.count() == 2 and mgr.item_for(b["id"]).isSelected()
    assert not mgr.item_for(a["id"]).icon().isNull()
    assert mgr.apply_button.isEnabled()
    extra = mgr.create("pbr")
    _pump()
    assert mgr.list.count() == 3
    while model.find_material(s, extra["id"]) is not None and s.can_undo():
        s.undo()
    _pump()
    assert model.find_material(s, extra["id"]) is None and mgr.list.count() == 2
    assert mgr.item_for(extra["id"]) is None
    model.set_active_material(s, b["id"])
    mgr.select(a["id"])
    assert model.active_material_id(s) == a["id"]
    mgr.item_for(a["id"]).setText("Copper")
    assert model.find_material(s, a["id"])["name"] == "Copper"
    model.rename_material(s, b["id"], "Shiny")
    assert mgr.item_for(b["id"]).text() == "Shiny"
    assert mgr.apply_to_selected() == 1
    assert tags.material_tags(s.objects[0])[0]["material"] == a["id"]
    assert "Used by 1" in mgr.item_for(a["id"]).toolTip()
    mgr.search.setText("shi")
    assert mgr.item_for(a["id"]).isHidden() and not mgr.item_for(b["id"]).isHidden()
    mgr.search.setText("")
    mgr.select(a["id"])
    dups = mgr.duplicate_selected()
    assert len(dups) == 1 and mgr.list.count() == 3 and model.active_material_id(s) == dups[0]["id"]
    data = mgr.list.mimeData([mgr.item_for(a["id"])])
    assert bytes(data.data(MATERIAL_MIME)).decode() == a["id"] and data.text() == f"material:{a['id']}"
    mgr.select(b["id"])
    assert mgr.convert_selected() == 1 and model.find_material(s, b["id"])["type"] == "node"
    assert mgr.select_user() is None
    mgr.select(a["id"])
    assert mgr.select_user() is s.objects[0]
    path = os.path.join(TMP, "mgr.qmat.json")
    assert mgr.save_library(path) == 3
    img = _write_image("brick.png")
    made = mgr.import_files([img, path, os.path.join(TMP, "ignored.txt")])
    assert len(made) == 4 and made[0]["name"] == "brick"
    assert made[0]["channels"]["base_color"]["texture"]["path"] == img
    assert mgr.list.count() == 7
    mgr.select(made[0]["id"])
    assert mgr.delete_selected() == 1 and mgr.list.count() == 6
    assert mgr.remove_from_selected() == 1
    assert mgr.delete_unused() == 6 and mgr.list.count() == 0
    actions = [a.text() for a in mgr.create_menu.actions()]
    assert "New PBR Material" in actions and "New Node Material" in actions
    next(act for act in mgr.create_menu.actions() if act.text() == "New Node Material").trigger()
    assert mgr.list.count() == 1 and model.materials(s)[0]["type"] == "node"
    preset_menu = next(act for act in mgr.create_menu.actions() if act.text() == "Presets").menu()
    next(act for act in preset_menu.actions() if act.text() == "Glass").trigger()
    assert model.materials(s)[-1]["name"] == "Glass"
    mgr.act_duplicate.trigger()
    assert mgr.list.count() == 3
    mgr.act_delete.trigger()
    assert mgr.list.count() == 2
    mgr.deleteLater()
    _pump()


def test_material_editor_widget():
    s = reset_scene()
    m = model.create_material(s, "pbr")
    ed = MaterialEditor(s)
    ed.resize(480, 640)
    ed.show()
    _pump()
    assert ed.material_id == m["id"] and ed.stack.currentIndex() == 1
    assert ed.preview.pixmap() is not None and not ed.preview.pixmap().isNull()
    ed.select_channel("roughness")
    page = ed.channel_page()
    assert page.key == "roughness"
    page.form.editors["value"].set_value(0.8, emit=True)
    assert model.find_material(s, m["id"])["channels"]["roughness"]["value"] == 0.8
    page.texture_combo.setCurrentIndex(page.texture_combo.findData("noise"))
    tex = model.find_material(s, m["id"])["channels"]["roughness"]["texture"]
    assert tex["type"] == "noise"
    page = ed.channel_page()
    assert page.texture_form is not None and page.form.rows["mix"].isVisibleTo(page)
    page.texture_form.set_value("scale", 12.0)
    assert model.find_material(s, m["id"])["channels"]["roughness"]["texture"]["scale"] == 12.0
    page.form.set_value("mix", 0.5)
    assert model.find_material(s, m["id"])["channels"]["roughness"]["mix"] == 0.5
    ed.select_channel("emission")
    page = ed.channel_page()
    page.enabled_box.setChecked(True)
    assert model.find_material(s, m["id"])["channels"]["emission"]["enabled"] is True
    item = next(ed.channel_list.item(i) for i in range(ed.channel_list.count())
                if ed.channel_list.item(i).data(Qt.ItemDataRole.UserRole) == "emission")
    assert item.checkState() == Qt.CheckState.Checked
    item.setCheckState(Qt.CheckState.Unchecked)
    assert model.find_material(s, m["id"])["channels"]["emission"]["enabled"] is False
    page = ed.channel_page()
    page.form.editors["strength"].set_value(5.0, emit=True)
    page.form.editors["value"].set_color([0, 1, 0], emit=True)
    ch = model.find_material(s, m["id"])["channels"]["emission"]
    assert ch["strength"] == 5.0 and ch["value"] == [0.0, 1.0, 0.0]
    ed.select_channel("base_color")
    ed.channel_page().texture_combo.setCurrentIndex(ed.channel_page().texture_combo.findData("gradient"))
    ramp_editor = ed.channel_page().texture_form.editors["ramp"]
    ramp_editor.add_at(0.5)
    assert len(model.find_material(s, m["id"])["channels"]["base_color"]["texture"]["ramp"]) == 3
    assert ed.rename("Painted") == "Painted"
    assert model.find_material(s, m["id"])["name"] == "Painted"
    ed.set_preview_shape("cube")
    assert model.find_material(s, m["id"])["preview"] == "cube"
    assert ed.apply_to_selected() == 1
    model.set_channel(mat := copy.deepcopy(model.find_material(s, m["id"])), "metallic", "value", 0.9)
    model.update_material(s, mat)
    ed.select_channel("metallic")
    assert _close(ed.channel_page().form.value("value"), 0.9)
    ed.action_button.click()
    assert model.find_material(s, m["id"])["type"] == "node" and ed.stack.currentIndex() == 2
    form = ed.node_form()
    assert form is not None and not form.rows["base_color"].isEnabled()
    form.editors["metallic"].set_value(0.3, emit=True)
    g = model.find_material(s, m["id"])["graph"]
    principled = next(n for n in g["nodes"] if n["type"] == "principled")
    assert principled["inputs"]["metallic"] == 0.3
    window = ed.open_node_editor()
    assert window is not None and window.material_id == m["id"] and window.isVisible()
    requested = []
    ed.openNodeEditorRequested.connect(requested.append)
    assert ed.open_node_editor() is None and requested == [m["id"]]
    other = model.create_material(s, "pbr")
    _pump()
    assert ed.material_id == other["id"] and ed.stack.currentIndex() == 1
    model.delete_material(s, other["id"])
    model.delete_material(s, m["id"])
    _pump()
    assert ed.material_id is None and ed.stack.currentIndex() == 0
    ed.new_button.click()
    assert len(model.materials(s)) == 1 and ed.material_id == model.materials(s)[0]["id"]
    window.close()
    window.deleteLater()
    ed.deleteLater()
    _pump()


def _socket_view_pos(editor: NodeEditor, nid: str, name: str, output: bool) -> QPoint:
    sock = editor.items[nid].socket(name, output)
    return editor.view.mapFromScene(sock.scenePos())


def test_node_editor_widget():
    s = reset_scene()
    m = model.create_material(s, "node")
    ne = NodeEditor(s)
    ne.resize(1024, 640)
    ne.show()
    _pump()
    assert ne.stack.currentIndex() == 1 and set(ne.items) == {"n1", "n2"} and len(ne.links) == 1
    chk = ne.add_node("checker", (-480, -96))
    assert chk == "n3" and N.find_node(model.find_material(s, m["id"])["graph"], chk) is not None
    ne.frame_all()
    _pump()
    viewport = ne.view.viewport()
    a = _socket_view_pos(ne, chk, "color", True)
    b = _socket_view_pos(ne, "n1", "base_color", False)
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a)
    QTest.mouseMove(viewport, (a + b) / 2)
    QTest.mouseMove(viewport, b)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b)
    g = model.find_material(s, m["id"])["graph"]
    assert N.link_into(g, "n1", "base_color")["from"] == [chk, "color"]
    assert ("n1", "base_color") in ne.links and isinstance(ne.links[("n1", "base_color")], LinkItem)
    res = evaluate.evaluate_material(model.find_material(s, m["id"]), [0.05, 0.25], [0.05, 0.05], linear=False)
    assert _close(res["base_color"], [[0.8] * 3, [0.2] * 3])
    b = _socket_view_pos(ne, "n1", "base_color", False)
    empty = QPoint(4, 4)
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b)
    QTest.mouseMove(viewport, empty)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, empty)
    assert N.link_into(model.find_material(s, m["id"])["graph"], "n1", "base_color") is None
    b = _socket_view_pos(ne, "n1", "base_color", False)
    a = _socket_view_pos(ne, chk, "fac", True)
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b)
    QTest.mouseMove(viewport, a)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a)
    assert N.link_into(model.find_material(s, m["id"])["graph"], "n1", "base_color")["from"] == [chk, "fac"]
    out_sock = _socket_view_pos(ne, chk, "color", True)
    surf = _socket_view_pos(ne, "n2", "surface", False)
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, out_sock)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, surf)
    assert N.link_into(model.find_material(s, m["id"])["graph"], "n2", "surface")["from"] == ["n1", "bsdf"]
    item = ne.items[chk]
    header = ne.view.mapFromScene(item.mapToScene(QPointF(N.NODE_WIDTH / 2, 8)))
    target = header + QPoint(48, 24)
    _mouse(viewport, QEvent.Type.MouseButtonPress, header)
    _mouse(viewport, QEvent.Type.MouseMove, header + QPoint(24, 12), buttons=Qt.MouseButton.LeftButton)
    _mouse(viewport, QEvent.Type.MouseMove, target, buttons=Qt.MouseButton.LeftButton)
    _mouse(viewport, QEvent.Type.MouseButtonRelease, target)
    moved = N.find_node(model.find_material(s, m["id"])["graph"], chk)["pos"]
    assert moved != [-480.0, -96.0]
    assert _close(moved, [item.pos().x(), item.pos().y()])
    assert ne.selected_node_ids() == [chk]
    form = ne.node_form()
    assert form is not None and "scale" in form.editors
    form.editors["scale"].set_value(20.0, emit=True)
    assert N.find_node(model.find_material(s, m["id"])["graph"], chk)["inputs"]["scale"] == 20.0
    mid = ne.add_node("math")
    ne.select_nodes([mid])
    ne.node_form().set_value("op", "multiply")
    assert N.find_node(model.find_material(s, m["id"])["graph"], mid)["props"]["op"] == "multiply"
    assert ne.connect_sockets(mid, "value", "n1", "roughness")
    assert not ne.connect_sockets(mid, "value", "n2", "surface")
    ne.select_nodes([mid])
    dup = ne.duplicate_selected()
    assert len(dup) == 1 and N.find_node(model.find_material(s, m["id"])["graph"], dup[0])["props"]["op"] == "multiply"
    ne.select_nodes(dup)
    ne.view.setFocus()
    QTest.keyClick(ne.view, Qt.Key.Key_Delete)
    assert N.find_node(model.find_material(s, m["id"])["graph"], dup[0]) is None
    ne.select_nodes(["n2"])
    assert ne.delete_selected() == 0 and "n2" in ne.items
    link = ne.links[("n1", "roughness")]
    ne.gscene.clearSelection()
    link.setSelected(True)
    assert ne.delete_selected() == 1
    assert N.link_into(model.find_material(s, m["id"])["graph"], "n1", "roughness") is None
    assert ne.remove_node(mid)
    ne.arrange()
    g = model.find_material(s, m["id"])["graph"]
    assert N.find_node(g, "n2")["pos"][0] > N.find_node(g, "n1")["pos"][0] > N.find_node(g, chk)["pos"][0]
    z0 = ne.view.zoom()
    center = QPointF(viewport.rect().center())
    wheel = QWheelEvent(center, QPointF(viewport.mapToGlobal(center.toPoint())), QPoint(0, 0), QPoint(0, 240),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(viewport, wheel)
    assert ne.view.zoom() > z0
    ne.view.set_zoom(100)
    assert _close(ne.view.zoom(), 4.0)
    ne.view.set_zoom(1.0)
    before = ne.view.mapToScene(viewport.rect().center())
    p0 = viewport.rect().center()
    _mouse(viewport, QEvent.Type.MouseButtonPress, p0, Qt.MouseButton.MiddleButton)
    _mouse(viewport, QEvent.Type.MouseMove, p0 + QPoint(64, 32), Qt.MouseButton.MiddleButton,
           buttons=Qt.MouseButton.MiddleButton)
    _mouse(viewport, QEvent.Type.MouseButtonRelease, p0 + QPoint(64, 32), Qt.MouseButton.MiddleButton)
    after = ne.view.mapToScene(viewport.rect().center())
    assert abs((before - after).x() - 64) < 2 and abs((before - after).y() - 32) < 2
    ne.frame_all()
    rect = ne.view.mapToScene(viewport.rect()).boundingRect()
    for it in ne.items.values():
        assert rect.contains(it.sceneBoundingRect())
    add_types = [act.text() for sub in ne.add_menu.actions() if sub.menu() for act in sub.menu().actions()]
    assert "Principled BSDF" in add_types and "Voronoi Texture" in add_types and len(add_types) == len(N.NODE_TYPES)
    count = len(ne.items)
    tex_menu = next(a.menu() for a in ne.add_menu.actions() if a.text() == "Texture")
    next(a for a in tex_menu.actions() if a.text() == "Noise Texture").trigger()
    assert len(ne.items) == count + 1
    p = model.create_material(s, preset="checker")
    _pump()
    assert ne.material_id == p["id"] and ne.stack.currentIndex() == 0 and ne.convert_button.isVisible()
    ne.convert_button.click()
    assert model.find_material(s, p["id"])["type"] == "node" and ne.stack.currentIndex() == 1
    assert len(ne.items) >= 3
    ne.material_combo.setCurrentIndex(ne.material_combo.findData(m["id"]))
    ne.material_combo.activated.emit(ne.material_combo.currentIndex())
    assert model.active_material_id(s) == m["id"] and ne.material_id == m["id"]
    mat = copy.deepcopy(model.find_material(s, m["id"]))
    N.add_node(mat["graph"], "rgb")
    model.update_material(s, mat)
    assert len(ne.items) == len(mat["graph"]["nodes"])
    ne.new_button.click()
    assert model.find_material(s, model.active_material_id(s))["type"] == "node"
    ne.deleteLater()
    _pump()


def _flush_deletes() -> None:
    from PySide6.QtCore import QCoreApplication
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    _pump()


def test_regression_emission_strength_is_linear():
    m = model.preset_material("emissive")
    color = np.array([0.37, 0.9, 0.78])
    got = evaluate.evaluate_material(m, 0.5, 0.5)["emission"]
    assert _close(got, colorutil.srgb_to_linear(color) * 4.0, 1e-9), got
    model.set_channel(m, "emission", "strength", 100.0)
    got = evaluate.evaluate_material(m, 0.5, 0.5)["emission"]
    assert _close(got, colorutil.srgb_to_linear(color) * 100.0, 1e-9), got
    assert got[1] < 100.0
    raw = evaluate.evaluate_material(m, 0.5, 0.5, linear=False)["emission"]
    assert _close(raw, color * 100.0, 1e-9)
    graph = convert.pbr_to_graph(m)
    node = evaluate.evaluate_material({"type": "node", "graph": graph}, 0.5, 0.5)["emission"]
    assert _close(node, got, 1e-9)
    g = {"nodes": [], "links": [], "next_id": 1}
    p1 = N.add_node(g, "principled")
    p2 = N.add_node(g, "principled")
    mix = N.add_node(g, "mix_shader")
    out = N.add_node(g, "output")
    N.set_node_input(g, p1["id"], "emission", [1.0, 0.0, 0.0])
    N.set_node_input(g, p1["id"], "emission_strength", 2.0)
    N.set_node_input(g, p2["id"], "emission", [0.0, 0.5, 0.0])
    N.set_node_input(g, p2["id"], "emission_strength", 1.0)
    N.set_node_input(g, mix["id"], "fac", 0.25)
    N.connect(g, p1["id"], "bsdf", mix["id"], "shader1")
    N.connect(g, p2["id"], "bsdf", mix["id"], "shader2")
    N.connect(g, mix["id"], "shader", out["id"], "surface")
    res = evaluate.evaluate_material({"type": "node", "graph": g}, 0.5, 0.5)["emission"]
    want = 0.75 * colorutil.srgb_to_linear([1.0, 0.0, 0.0]) * 2.0 + 0.25 * colorutil.srgb_to_linear([0.0, 0.5, 0.0])
    assert _close(res, want, 1e-9), res
    assert "_emission_linear" not in evaluate.evaluate_material(m, 0.5, 0.5)
    arr = preview.render_preview_array(model.preset_material("emissive"), 16, "sphere")
    assert arr.shape == (16, 16, 4)


def test_regression_editor_controls_survive_edits():
    import shiboken6
    s = reset_scene()
    m = model.create_material(s, "pbr")
    ed = MaterialEditor(s)
    ed.resize(480, 640)
    ed.show()
    _pump()
    ed.select_channel("metallic")
    page = ed.channel_page()
    field = page.form.editors["value"]
    slider = field.slider
    for k in range(1, 9):
        slider.setValue(k * 50)
        _flush_deletes()
        assert shiboken6.isValid(slider) and ed.channel_page() is page
    assert _close(model.find_material(s, m["id"])["channels"]["metallic"]["value"], 0.4)
    slider.resize(256, 24)
    s.clear_history()
    y = slider.height() // 2
    x0 = int(round(0.4 * slider.width()))
    _mouse(slider, QEvent.Type.MouseButtonPress, QPoint(x0, y))
    assert slider.isSliderDown()
    for x in range(x0 + 8, x0 + 128, 8):
        _mouse(slider, QEvent.Type.MouseMove, QPoint(x, y), buttons=Qt.MouseButton.LeftButton)
        _flush_deletes()
        assert shiboken6.isValid(slider) and ed.channel_page() is page
    _mouse(slider, QEvent.Type.MouseButtonRelease, QPoint(x0 + 120, y))
    _flush_deletes()
    dragged = model.find_material(s, m["id"])["channels"]["metallic"]["value"]
    assert len(s._undo) == 1, len(s._undo)
    s.undo()
    _pump()
    assert dragged > 0.4 and _close(model.find_material(s, m["id"])["channels"]["metallic"]["value"], 0.4)
    page = ed.channel_page()
    field = page.form.editors["value"]
    slider = field.slider
    spin = field.spin
    spin.setFocus()
    QTest.keyClick(spin, Qt.Key.Key_Up)
    _flush_deletes()
    assert shiboken6.isValid(spin) and ed.channel_page() is page
    assert _close(model.find_material(s, m["id"])["channels"]["metallic"]["value"], 0.41)
    ed.select_channel("base_color")
    page = ed.channel_page()
    page.texture_combo.setCurrentIndex(page.texture_combo.findData("checker"))
    _flush_deletes()
    page = ed.channel_page()
    scale = page.texture_form.editors["scale"]
    scale.set_value(3.0, emit=True)
    _flush_deletes()
    assert shiboken6.isValid(scale.slider) and ed.channel_page() is page
    assert model.find_material(s, m["id"])["channels"]["base_color"]["texture"]["scale"] == 3.0
    mat = copy.deepcopy(model.find_material(s, m["id"]))
    mat["channels"]["roughness"]["value"] = 0.9
    model.update_material(s, mat)
    _flush_deletes()
    assert ed.channel_page() is not page
    ed.deleteLater()
    _pump()


def test_regression_slider_drag_is_one_undo_step():
    s = reset_scene()
    m = model.create_material(s, "pbr")
    ed = MaterialEditor(s)
    ed.show()
    _pump()
    ed.select_channel("roughness")
    s.clear_history()
    for k in range(40):
        ed.channel_page().form.editors["value"].slider.setValue(100 + k * 10)
    assert len(s._undo) == 1, len(s._undo)
    assert _close(model.find_material(s, m["id"])["channels"]["roughness"]["value"], 0.49)
    ed.select_channel("metallic")
    ed.channel_page().form.editors["value"].slider.setValue(300)
    ed.channel_page().form.editors["value"].slider.setValue(350)
    assert len(s._undo) == 2
    s.undo()
    _pump()
    assert model.find_material(s, m["id"])["channels"]["metallic"]["value"] == 0.0
    assert _close(model.find_material(s, m["id"])["channels"]["roughness"]["value"], 0.49)
    s.undo()
    _pump()
    assert model.find_material(s, m["id"])["channels"]["roughness"]["value"] == 0.5
    s.redo()
    assert _close(model.find_material(s, m["id"])["channels"]["roughness"]["value"], 0.49)
    s.clear_history()
    saved = model.COALESCE_SECONDS
    model.COALESCE_SECONDS = -1.0
    try:
        for k in range(3):
            ed.select_channel("roughness")
            ed.channel_page().form.editors["value"].slider.setValue(700 + k * 10)
    finally:
        model.COALESCE_SECONDS = saved
    assert len(s._undo) == 3
    s.clear_history()
    mat = copy.deepcopy(model.find_material(s, m["id"]))
    for k in range(5):
        mat["channels"]["specular"]["value"] = 0.1 * k
        model.update_material(s, mat)
    assert len(s._undo) == 5
    ed.deleteLater()
    nm = model.create_material(s, "node")
    ne = NodeEditor(s)
    ne.show()
    _pump()
    bsdf = next(n["id"] for n in model.find_material(s, nm["id"])["graph"]["nodes"] if n["type"] == "principled")
    s.clear_history()
    for k in range(10):
        ne.set_node_input(bsdf, "roughness", 0.05 * k)
    assert len(s._undo) == 1
    s.undo()
    g = model.find_material(s, nm["id"])["graph"]
    assert N.find_node(g, bsdf)["inputs"]["roughness"] == 0.5
    ne.deleteLater()
    _pump()


def test_regression_multi_step_operations_group_undo():
    s = reset_scene()
    cube = s.objects[0]
    s.clear_history()
    n0 = len(model.materials(s))
    m = model.create_material(s, "pbr")
    assert len(s._undo) == 1
    s.undo()
    assert len(model.materials(s)) == n0 and model.active_material_id(s) is None
    s.redo()
    assert model.find_material(s, m["id"]) is not None and model.active_material_id(s) == m["id"]
    s.clear_history()
    cube = s.objects[0]
    other = model.create_material(s, preset="gold", activate=False)
    tags.apply_material(cube, m["id"])
    assert len(s._undo) == 2
    s.clear_history()
    assert model.delete_material(s, m["id"])
    assert len(s._undo) == 1 and tags.material_tags(cube) == []
    assert model.active_material_id(s) == other["id"]
    s.undo()
    cube = s.objects[0]
    assert model.find_material(s, m["id"]) is not None
    assert tags.material_tags(cube)[0]["material"] == m["id"]
    assert model.active_material_id(s) == m["id"]
    s.clear_history()
    dup = model.duplicate_material(s, m["id"])
    assert len(s._undo) == 1 and model.active_material_id(s) == dup["id"]
    s.undo()
    assert model.find_material(s, dup["id"]) is None and model.active_material_id(s) == m["id"]
    path = os.path.join(TMP, "group_lib.json")
    model.save_library(s, path)
    s.clear_history()
    loaded = model.load_library(s, path)
    assert len(loaded) == 2 and len(s._undo) == 1
    s.undo()
    assert all(model.find_material(s, x["id"]) is None for x in loaded)
    s.clear_history()
    assert model.delete_unused(s) == 1
    assert len(s._undo) == 1
    s.clear_history()
    assert model.find_material(s, other["id"]) is None
    assert tags.remove_from_selected(s) == 1
    assert len(s._undo) == 1
    s.clear_history()
    assert tags.assign_to_selected(s, m["id"]) == 1
    assert len(s._undo) == 1
    mgr = MaterialManager(s)
    mgr.select(m["id"])
    s.clear_history()
    mgr.duplicate_selected()
    assert len(s._undo) == 1
    mgr.deleteLater()
    _pump()


def test_regression_tag_resolution_matches_tags_package():
    import quartz_studio.tags.core as TC
    from quartz_studio.tags import shading
    s = reset_scene()
    cube = s.objects[0]
    gold = model.create_material(s, preset="gold")["id"]
    plastic = model.create_material(s, preset="plastic")["id"]
    tags.apply_material(cube, gold)
    i = TC.add_tag(cube, "polygon_selection", name="Top")
    TC.update_tag(cube, i, selection=[0, 1])
    tags.add_material_tag(cube, plastic, selection="Top")
    ids = tags.polygon_material_ids(s, cube)
    all_tags = TC.tags_of(cube)
    assign = shading.material_assignments(cube)
    assert ids == [all_tags[a]["material"] if a is not None else None for a in assign]
    assert ids == [plastic, plastic, gold, gold, gold, gold]
    assert tags.polygon_selection(cube, "Top") == {0, 1}
    assert tags.effective_material_id(s, cube, polygon=1) == plastic
    assert tags.effective_material_id(s, cube, polygon=4) == gold
    TC.update_tag(cube, 0, enabled=False)
    ids = tags.polygon_material_ids(s, cube)
    assign = shading.material_assignments(cube)
    assert ids == [TC.tags_of(cube)[a]["material"] if a is not None else None for a in assign]
    assert ids == [plastic, plastic, None, None, None, None]
    assert tags.effective_material_id(s, cube) is None
    tags.add_material_tag(cube, plastic, selection="Top")
    tags.apply_material(cube, gold, selection="Top")
    assert len(tags.material_tags(cube)) == 3
    assert tags.polygon_material_ids(s, cube) == [gold, gold, None, None, None, None]
    tags.apply_material(cube, gold)
    assert len(tags.material_tags(cube)) == 4
    ids = tags.polygon_material_ids(s, cube)
    assign = shading.material_assignments(cube)
    assert ids == [TC.tags_of(cube)[a]["material"] if a is not None else None for a in assign]
    assert ids == [gold] * 6
    tags.set_tag_field(cube, 0, "enabled", True)
    assert tags.material_tags(cube)[0]["enabled"] is True
    child = SceneObject("Child", Mesh(np.zeros((3, 3)), [(0, 1, 2)]))
    child.parent = cube
    assert tags.effective_material_id(s, child) == gold
    TC.update_tag(cube, len(TC.tags_of(cube)) - 1, enabled=False)
    TC.update_tag(cube, 0, enabled=False)
    assert tags.effective_material_id(s, child) is None
    j = TC.add_tag(cube, "material", material="Plastic")
    assert tags.resolve_material_ref(s, "Plastic") == plastic
    assert tags.resolve_material_ref(s, "Nope") is None and tags.resolve_material_ref(s, None) is None
    assert tags.effective_material_id(s, child) == plastic
    assert tags.polygon_material_ids(s, cube)[3] == plastic
    TC.update_tag(cube, j, enabled=False)
    assert tags.effective_material_id(s, child) is None


def test_regression_node_editor_keeps_view_on_external_edit():
    from quartz_studio.materials.node_editor import SOCKET_R
    s = reset_scene()
    m = model.create_material(s, "node")
    ne = NodeEditor(s)
    ne.resize(1024, 640)
    ne.show()
    ed = MaterialEditor(s)
    _pump()
    ne.view.set_zoom(2.0)
    ne.view.centerOn(40.0, 24.0)
    before = ne._view_center()
    ne.select_nodes(["n1"])
    ed.set_node_input("metallic", 0.7)
    _pump()
    g = model.find_material(s, m["id"])["graph"]
    assert N.find_node(g, "n1")["inputs"]["metallic"] == 0.7
    assert abs(ne.view.zoom() - 2.0) < 1e-9, ne.view.zoom()
    after = ne._view_center()
    assert abs(after.x() - before.x()) < 2.0 and abs(after.y() - before.y()) < 2.0
    assert ne.selected_node_ids() == ["n1"]
    ne.load(m["id"])
    assert ne.view.zoom() <= 1.0
    sock = ne.items["n1"].socket("base_color", False)
    rect = sock.boundingRect()
    assert rect.width() / 2.0 >= SOCKET_R + 2 + 1
    mp = ne.add_node("mapping")
    ne.select_nodes([mp])
    form = ne.node_form()
    assert form is not None and len(form.editors["location"].spins) == 3
    assert len(form.editors["scale"].spins) == 3
    form.editors["location"].spins[2].setValue(0.5)
    form.editors["scale"].spins[2].setValue(4.0)
    node = N.find_node(model.find_material(s, m["id"])["graph"], mp)
    assert node["inputs"]["location"] == [0.0, 0.0, 0.5]
    assert node["inputs"]["scale"] == [1.0, 1.0, 4.0]
    ne.deleteLater()
    ed.deleteLater()
    _pump()


def test_regression_make_context_shapes_and_guards():
    m = model.new_material()
    res = evaluate.evaluate_material(m, 0.5, 0.5, normal=np.tile([0.0, 1.0, 0.0], (5, 1)))
    assert np.asarray(res["normal"]).shape == (5, 3) and np.asarray(res["metallic"]).shape == (5,)
    assert _close(res["normal"], np.tile([0.0, 1.0, 0.0], (5, 1)))
    res = evaluate.evaluate_material(m, 0.5, 0.5, normal=[0, 0, 0])
    assert _close(res["normal"], [0, 0, 1])
    res = evaluate.evaluate_material(m, np.array([0.1, 0.2]), np.array([0.3, 0.4]),
                                     normal=[[0, 0, 0], [0, 2, 0]])
    assert _close(res["normal"], [[0, 0, 1], [0, 1, 0]])
    tex = model.preset_material("checker")
    res = evaluate.evaluate_material(tex, np.array([np.nan, np.inf, 0.3]), np.array([0.2, -np.inf, np.nan]))
    assert np.all(np.isfinite(res["base_color"])) and np.asarray(res["base_color"]).shape == (3, 3)
    res = evaluate.evaluate_material(m, 0.5, 0.5, normal=[0, 0, 1], tangent=[0, 0, 1])
    assert np.all(np.isfinite(res["normal"]))
    ctx = evaluate.make_context(0.5, 0.5, normal=[0, 0, 1], tangent=[0, 0, 1])
    assert _close(np.linalg.norm(ctx["tangent"], axis=1), [1.0])
    try:
        evaluate.make_context(np.zeros(3), np.zeros(3), pos=np.zeros((4, 3)))
    except ValueError:
        pass
    else:
        raise AssertionError("mismatched sample counts accepted")
    assert evaluate.make_context(np.zeros(0), np.zeros(0))["n"] == 0


def test_regression_library_validation():
    s = reset_scene()
    for name, payload in (("five.json", {"materials": 5}), ("num.json", 7),
                          ("fmt.json", {"format": "other", "materials": []})):
        path = os.path.join(TMP, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        try:
            model.load_library(s, path)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{name} accepted")
    mgr = MaterialManager(s)
    assert mgr.import_files([os.path.join(TMP, "five.json")]) == []
    assert "Could not load" in mgr.status.text()
    mgr.deleteLater()
    bad = {"materials": [
        {"type": "pbr", "name": "Bad", "preview": "torus", "channels": {
            "base_color": {"value": "red", "texture": {"type": "bogus"}},
            "metallic": {"value": "x", "mix": [1]},
            "roughness": {"value": 0.3, "texture": {"type": "noise", "scale": "big", "seed": 3, "junk": 1}},
            "emission": {"enabled": True, "value": [1, 1], "strength": "hot"},
            "normal": 5}},
        {"type": "node", "name": "BadNodes", "graph": {
            "nodes": [{"id": "n1", "type": "principled", "pos": ["a", 1],
                       "inputs": {"metallic": "lots", "base_color": [1, 0], "roughness": 0.25},
                       "props": {}},
                      {"id": "n2", "type": "output", "pos": [0, 0]},
                      {"type": "principled"}, {"id": "n9", "type": "nonsense"}, 5,
                      {"id": "n3", "type": "math", "props": {"op": "explode"}}],
            "links": [{"from": ["n1", "bsdf"], "to": ["n2", "surface"]}, {"from": "x"}, 7,
                      {"from": ["n9", "color"], "to": ["n1", "base_color"]}],
            "next_id": "many"}},
        {"type": "weird"}, 3]}
    path = os.path.join(TMP, "bad_values.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(bad, fh)
    loaded = model.load_library(s, path)
    assert [m["name"] for m in loaded] == ["Bad", "BadNodes"]
    pbr = model.find_material(s, loaded[0]["id"])
    assert pbr["channels"]["base_color"]["value"] == [0.8, 0.8, 0.8]
    assert pbr["channels"]["base_color"]["texture"] is None
    assert pbr["channels"]["metallic"]["value"] == 0.0 and pbr["channels"]["metallic"]["mix"] == 1.0
    tex = pbr["channels"]["roughness"]["texture"]
    assert tex["type"] == "noise" and tex["scale"] == 4.0 and tex["seed"] == 3 and "junk" not in tex
    assert pbr["channels"]["emission"]["enabled"] is True and pbr["channels"]["emission"]["strength"] == 1.0
    assert pbr["preview"] == "sphere" and pbr["channels"]["normal"]["enabled"] is False
    res = evaluate.evaluate_material(pbr, np.array([0.2, 0.7]), np.array([0.4, 0.1]))
    assert np.all(np.isfinite(res["base_color"]))
    nodes_mat = model.find_material(s, loaded[1]["id"])
    g = nodes_mat["graph"]
    assert [n["id"] for n in g["nodes"]] == ["n1", "n2", "n3"]
    assert len(g["links"]) == 1 and g["next_id"] >= 1
    n1 = N.find_node(g, "n1")
    assert n1["inputs"]["metallic"] == 0.0 and n1["inputs"]["roughness"] == 0.25 and n1["pos"] == [0.0, 0.0]
    assert N.find_node(g, "n3")["props"]["op"] == "add"
    res = evaluate.evaluate_material(nodes_mat, 0.5, 0.5)
    assert _close(res["roughness"], 0.25)
    assert preview.render_preview_array(nodes_mat, 8).shape == (8, 8, 4)
    assert textures.IMAGE_SEARCH_PATHS[0] == os.path.abspath(TMP)


def test_regression_missing_image_matches_nodes():
    mat = model.new_material()
    model.set_channel_texture(mat, "alpha", "image")
    model.set_channel(mat, "alpha", "enabled", True)
    model.set_channel_texture(mat, "metallic", textures.new_texture("image", path="does_not_exist.png",
                                                                    use_alpha=True))
    model.set_channel_texture(mat, "roughness", textures.new_texture("image", path=""))
    u = np.linspace(0.0, 1.0, 7)
    v = np.linspace(1.0, 0.0, 7)
    a = evaluate.evaluate_material(mat, u, v)
    b = evaluate.evaluate_material({"type": "node", "graph": convert.pbr_to_graph(mat)}, u, v)
    for key in evaluate.OUTPUT_KEYS:
        assert _close(a[key], b[key], 1e-9), key
    assert _close(a["alpha"], colorutil.luminance(np.array([textures.MISSING_COLOR]))[0])
    assert _close(a["metallic"], 1.0)


def test_regression_object_space_scale_and_mapping():
    s = reset_scene()
    cube = s.objects[0]
    tex = textures.new_texture("checker", color1=[1, 1, 1], color2=[0, 0, 0], space="object")
    mat = model.new_material()
    model.set_channel_texture(mat, "base_color", tex)
    xs = np.linspace(-99.5, 99.5, 4001)
    pts = np.stack([xs, np.full_like(xs, 0.3), np.full_like(xs, 0.3)], axis=1)
    res = evaluate.evaluate_material(mat, np.zeros(len(xs)), np.zeros(len(xs)), pos=pts)
    lum = np.asarray(res["base_color"])[:, 0]
    flips = int(np.sum(np.abs(np.diff(lum)) > 0.5))
    assert 14 <= flips <= 17, flips
    corners = evaluate.evaluate_material(mat, np.zeros(8), np.zeros(8), pos=cube.mesh.points)
    assert np.asarray(corners["base_color"]).shape == (8, 3)
    tex["tiling"] = [2.0, 1.0]
    tex["offset"] = [0.0625, 0.0]
    model.set_channel_texture(mat, "base_color", tex)
    res = evaluate.evaluate_material(mat, np.zeros(len(xs)), np.zeros(len(xs)), pos=pts)
    flips2 = int(np.sum(np.abs(np.diff(np.asarray(res["base_color"])[:, 0])) > 0.5))
    assert 30 <= flips2 <= 34, flips2
    node = evaluate.evaluate_material({"type": "node", "graph": convert.pbr_to_graph(mat)},
                                      np.zeros(len(xs)), np.zeros(len(xs)), pos=pts)
    assert _close(node["base_color"], res["base_color"], 1e-9)
    folder = os.path.join(TMP, "relimg")
    os.makedirs(folder, exist_ok=True)
    src = _write_image("rel_source.png")
    import shutil
    shutil.copy(src, os.path.join(folder, "rel.png"))
    assert textures.resolve_image_path("rel.png") is None or os.path.isfile(textures.resolve_image_path("rel.png"))
    textures.add_image_search_path(folder)
    assert textures.resolve_image_path("rel.png") == os.path.join(os.path.abspath(folder), "rel.png")
    assert textures.load_image("rel.png") is not None
    img_tex = textures.new_texture("image", path="rel.png", interpolation="closest")
    col, _ = textures.sample_texture(img_tex, _ctx([0.25], [0.75]))
    assert _close(col, [[1, 0, 0]], 1e-6)


def test_materials_accept_frontal_and_shrinkwrap():
    from quartz_studio.tags import shading
    assert set(shading.PROJECTIONS) <= set(tags.PROJECTIONS)
    for proj in ("frontal", "shrinkwrap"):
        tag = tags.new_material_tag("m1", projection=proj)
        assert tag["projection"] == proj
    obj = _ProjObj()
    tags.add_material_tag(obj, "m1", projection="frontal")
    assert tags.set_tag_field(obj, 0, "projection", "shrinkwrap")["projection"] == "shrinkwrap"


def test_frontal_projection_defaults_to_minus_z_and_follows_view():
    pts = np.array([[-1.0, -2.0, 0.0], [1.0, 2.0, 3.0], [0.0, 0.0, 1.5]])
    fu, fv = tags.project_uv("frontal", pts)
    lu, lv = tags.project_uv("flat", pts)
    assert np.allclose(fu, lu) and np.allclose(fv, lv)
    xu, xv = tags.project_uv("frontal", pts, view=(-1.0, 0.0, 0.0))
    assert np.allclose(xu, [1.0, 0.0, 0.5]) and np.allclose(xv, [0.0, 1.0, 0.5])
    zu, zv = tags.project_uv("frontal", pts, view=(0.0, 0.0, 0.0))
    assert np.allclose(zu, lu) and np.allclose(zv, lv)


def test_shrinkwrap_projection_maps_to_spherical():
    pts = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, -1.0], [-1.0, -1.0, 1.0]])
    su, sv = tags.project_uv("shrinkwrap", pts)
    pu, pv = tags.project_uv("spherical", pts)
    assert np.allclose(su, pu) and np.allclose(sv, pv)


class _ProjObj:
    pass


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
