from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

from quartz_studio import objects
from quartz_studio.objects import registry
from quartz_studio.objects.registry import ObjectSpec, Param, curve_value, link_keys
from quartz_studio.scene import Mesh


def _raises(fn, *args) -> bool:
    try:
        fn(*args)
    except (ValueError, TypeError):
        return True
    return False


def _build(p: dict, inputs: list) -> Mesh:
    return Mesh.empty()


def test_new_names_are_exported():
    for name in ("curve_value", "link_keys"):
        assert name in registry.__all__, name
        assert hasattr(registry, name), name


def test_param_new_field_defaults():
    p = Param("size", "Size", "float", 1.0)
    assert p.show == ()
    assert p.axes == ("X", "Y", "Z")
    assert p.ref == ""


def test_visible_without_show():
    p = Param("size", "Size", "float", 1.0)
    assert p.visible({})
    assert p.visible({"size": 3.0, "other": "x"})


def test_visible_one_condition():
    p = Param("offset", "Offset", "float", 0.0,
              show=(("direction", ("Auto", "X", "Y", "Z")),))
    assert p.visible({"direction": "X"})
    assert p.visible({"direction": "Auto"})
    assert not p.visible({"direction": "Custom"})
    assert not p.visible({})


def test_visible_two_conditions():
    p = Param("tension", "Tension", "float", 1.0,
              show=(("shape", ("Round",)), ("mode", ("A", "B"))))
    assert p.visible({"shape": "Round", "mode": "A"})
    assert p.visible({"shape": "Round", "mode": "B"})
    assert not p.visible({"shape": "Step", "mode": "A"})
    assert not p.visible({"shape": "Round", "mode": "C"})


def test_visible_bool_condition():
    p = Param("end_size", "End Size", "float", 0.0, show=(("separate_bevels", (True,)),))
    assert p.visible({"separate_bevels": True})
    assert not p.visible({"separate_bevels": False})


def test_axes_hpb():
    p = Param("rotation", "Rotation", "vector", (0.0, 0.0, 0.0), axes=("H", "P", "B"))
    assert p.axes == ("H", "P", "B")
    assert p.clamp([1, 2, 3]) == (1.0, 2.0, 3.0)


def test_ref_field():
    p = Param("font_style", "Style", "font_style", "", ref="font")
    assert p.ref == "font"


def test_clamp_font():
    p = Param("font", "Font", "font", "Arial")
    assert p.clamp(None) == "Arial"
    assert p.clamp("") == "Arial"
    assert p.clamp("Verdana") == "Verdana"
    assert p.clamp(12) == "12"
    assert isinstance(p.clamp("Verdana"), str)


def test_clamp_font_style():
    p = Param("font_style", "Style", "font_style", "", ref="font")
    assert p.clamp(None) == ""
    assert p.clamp("") == ""
    assert p.clamp("Bold") == "Bold"
    assert p.clamp(3) == "3"


def test_clamp_link():
    p = Param("target", "Target", "link", "")
    assert p.clamp(None) == ""
    assert p.clamp("") == ""
    assert p.clamp("Cube") == "Cube"
    assert p.clamp(7) == "7"
    assert p.clamp(1.5) == "1.5"


def test_clamp_curve_sorted_and_clamped():
    p = Param("profile", "Profile", "curve", ((0.0, 1.0), (1.0, 1.0)))
    out = p.clamp([(0.8, 0.2), (0.1, 0.5), (0.5, 0.7)])
    assert out == ((0.0, 0.5), (0.5, 0.7), (1.0, 0.2)), out
    out = p.clamp([(-1.0, 2.0), (0.5, -3.0), (4.0, 0.25)])
    assert out == ((0.0, 1.0), (0.5, 0.0), (1.0, 0.25)), out


def test_clamp_curve_first_and_last_forced():
    p = Param("profile", "Profile", "curve", ((0.0, 1.0), (1.0, 1.0)))
    out = p.clamp([(0.2, 0.3), (0.4, 0.6), (0.7, 0.9)])
    assert out == ((0.0, 0.3), (0.4, 0.6), (1.0, 0.9)), out


def test_clamp_curve_duplicate_x_dropped():
    p = Param("profile", "Profile", "curve", ((0.0, 1.0), (1.0, 1.0)))
    out = p.clamp([(0.0, 0.1), (0.5, 0.2), (0.5, 0.9), (1.0, 0.3)])
    assert out == ((0.0, 0.1), (0.5, 0.2), (1.0, 0.3)), out


def test_clamp_curve_json_lists_give_tuples():
    p = Param("profile", "Profile", "curve", ((0.0, 1.0), (1.0, 1.0)))
    raw = json.loads(json.dumps(p.default))
    assert isinstance(raw, list) and isinstance(raw[0], list)
    out = p.clamp(raw)
    assert isinstance(out, tuple) and all(isinstance(pt, tuple) for pt in out)
    assert out == p.default
    assert p.clamp(p.default) == p.default


def test_clamp_curve_errors():
    p = Param("profile", "Profile", "curve", ((0.0, 1.0), (1.0, 1.0)))
    assert _raises(p.clamp, [(0.5, 0.5)])
    assert _raises(p.clamp, [])
    assert _raises(p.clamp, [(0.0, 0.0), (0.5, 0.5), (0.5, 0.6)]) is False
    assert _raises(p.clamp, [(0.3, 0.0), (0.3, 0.5)])
    assert _raises(p.clamp, [(0.0, "a"), (1.0, 1.0)])
    assert _raises(p.clamp, [(0.0, None), (1.0, 1.0)])
    assert _raises(p.clamp, [(0.0, float("nan")), (1.0, 1.0)])
    assert _raises(p.clamp, [(0.0, float("inf")), (1.0, 1.0)])
    assert _raises(p.clamp, [(0.0, 1.0, 2.0), (1.0, 1.0)])
    assert _raises(p.clamp, None)
    assert _raises(p.clamp, "curve")


def test_clamp_curve_forty_points_gives_32():
    p = Param("profile", "Profile", "curve", ((0.0, 1.0), (1.0, 1.0)))
    pts = [(i / 39.0, (i % 5) / 4.0) for i in range(40)]
    out = p.clamp(pts)
    assert len(out) == 32, len(out)
    assert out[0][0] == 0.0 and out[-1][0] == 1.0
    assert out[:31] == tuple((x, y) for x, y in pts[:31])
    assert out[-1] == (1.0, pts[-1][1])
    xs = [pt[0] for pt in out]
    assert all(b > a for a, b in zip(xs, xs[1:]))


def test_clamp_color():
    p = Param("tint", "Tint", "color", (1.0, 1.0, 1.0))
    assert p.clamp([0.5, 0.25, 1.0]) == (0.5, 0.25, 1.0)
    assert p.clamp((2, -1, 0.5)) == (1.0, 0.0, 0.5)
    out = p.clamp([1, 0, 0])
    assert isinstance(out, tuple) and all(isinstance(v, float) for v in out)
    assert _raises(p.clamp, (1.0, 1.0))
    assert _raises(p.clamp, (1.0, 1.0, 1.0, 1.0))
    assert _raises(p.clamp, (1.0, float("nan"), 1.0))
    assert _raises(p.clamp, (1.0, "x", 1.0))
    assert _raises(p.clamp, None)


def test_existing_kinds_unchanged():
    assert Param("t", "T", "text", "").clamp(None) == ""
    assert Param("b", "B", "bool", False).clamp(1) is True
    assert Param("c", "C", "choice", "A", choices=("A", "B")).clamp("Z") == "A"
    assert Param("i", "I", "int", 1, 0, 10).clamp(12.6) == 10
    assert Param("f", "F", "float", 1.0, 0.0).clamp(-3) == 0.0
    assert Param("v", "V", "vector", (0.0, 0.0, 0.0), 0.0).clamp((-1, 2, 3)) == (0.0, 2.0, 3.0)


def test_curve_value_flat_is_exact():
    flat = ((0.0, 1.0), (1.0, 1.0))
    for x in (0.0, 0.1, 0.25, 0.5, 0.999, 1.0):
        v = curve_value(flat, x)
        assert v == 1.0 and isinstance(v, float), (x, v)


def test_curve_value_linear():
    assert curve_value(((0, 0), (1, 1)), 0.25) == 0.25
    assert curve_value(((0.0, 0.0), (0.5, 1.0), (1.0, 0.0)), 0.75) == 0.5


def test_migrate_applied_by_clamp_not_by_defaults():
    calls = []

    def migrate(values: dict) -> dict:
        calls.append(dict(values))
        if "old" in values and "new" not in values:
            values["new"] = values["old"] * 2.0
        return values

    spec = ObjectSpec("probe_migrate", "Probe", "generator", _build,
                      (Param("old", "Old", "float", 1.0), Param("new", "New", "float", 5.0)),
                      migrate=migrate)
    assert spec.defaults() == {"old": 1.0, "new": 5.0}
    assert calls == []
    raw = {"old": 3.0}
    out = spec.clamp(raw)
    assert out == {"old": 3.0, "new": 6.0}, out
    assert raw == {"old": 3.0}
    assert len(calls) == 1
    again = spec.clamp(out)
    assert again == out
    assert spec.clamp(spec.defaults()) == spec.defaults()


def test_spec_without_migrate_behaves_as_before():
    spec = ObjectSpec("probe_plain", "Probe", "generator", _build,
                      (Param("a", "A", "float", 1.0, 0.0), Param("b", "B", "choice", "X", choices=("X", "Y"))))
    assert spec.migrate is None
    assert spec.clamp({"a": -2, "b": "Q", "zzz": 1}) == {"a": 0.0, "b": "X"}
    assert spec.clamp({}) == spec.defaults()


def test_applies_field_default():
    spec = ObjectSpec("probe_applies", "Probe", "generator", _build, ())
    assert spec.applies == {}
    other = ObjectSpec("probe_applies2", "Probe", "generator", _build, ())
    spec.applies["x"] = lambda values: True
    assert other.applies == {}
    positional = ObjectSpec("probe_pos", "Probe", "generator", _build, (), "children", "icon", "desc")
    assert positional.inputs == "children" and positional.description == "desc"
    assert positional.applies == {} and positional.migrate is None


def test_link_keys():
    spec = ObjectSpec("probe_links", "Probe", "generator", _build,
                      (Param("a", "A", "float", 1.0), Param("target", "Target", "link", ""),
                       Param("b", "B", "bool", False), Param("source", "Source", "link", "")))
    assert link_keys(spec) == ("target", "source")
    plain = ObjectSpec("probe_nolinks", "Probe", "generator", _build, (Param("a", "A", "float", 1.0),))
    assert link_keys(plain) == ()
    assert spec.clamp({"target": None, "source": "Cube"}) == {"a": 1.0, "target": "", "b": False,
                                                              "source": "Cube"}


def test_every_registered_spec_clamps_its_defaults():
    specs = registry.all_specs()
    assert len(specs) > 0
    bad = []
    for spec in specs:
        d = spec.defaults()
        if spec.clamp(d) != d:
            bad.append(spec.id)
    assert not bad, bad


def test_registered_specs_unchanged_by_new_fields():
    for spec in registry.all_specs():
        for p in spec.params:
            assert isinstance(p.show, tuple), (spec.id, p.key)
            assert len(p.axes) == 3, (spec.id, p.key)
            assert p.visible(spec.defaults()) or p.show, (spec.id, p.key)


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
