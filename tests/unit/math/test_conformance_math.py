import ast
import copy
import inspect
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import quartz.math as qm
from quartz.math import Color, Euler, Matrix, Quaternion, Vector, axis_conversion
from quartz.math import bvhtree, geometry, interpolate, kdtree, noise, scalar

FACTS = json.loads((ROOT / "data" / "blender_facts_judge.json").read_text(encoding="utf-8"))
TOL = 1e-5


def approx_seq(a, b, tol=TOL):
    a = list(a)
    b = list(b)
    assert len(a) == len(b), (a, b)
    for x, y in zip(a, b):
        assert abs(float(x) - float(y)) <= tol, (a, b)


def mat_rows(m):
    return [list(r) for r in np.asarray(m, dtype=np.float64)]


def approx_mat(m, rows, tol=TOL):
    got = np.asarray(m, dtype=np.float64)
    exp = np.asarray(rows, dtype=np.float64)
    assert got.shape == exp.shape, (got, exp)
    assert np.allclose(got, exp, atol=tol), (got, exp)


def approx_quat(q, ref, tol=TOL):
    a = np.asarray(list(q), dtype=np.float64)
    b = np.asarray(ref, dtype=np.float64)
    assert np.allclose(a, b, atol=tol) or np.allclose(a, -b, atol=tol), (a, b)


def f32(x):
    return float(np.float32(x))



MATH_FILES = ["__init__.py", "_base.py", "vector.py", "matrix.py", "quaternion.py", "euler.py", "color.py",
              "scalar.py", "conversion.py", "geometry.py", "kdtree.py", "bvhtree.py", "noise.py", "interpolate.py"]
OWNED = sorted({*(ROOT / "quartz" / "math").glob("*.py"), *(ROOT / "tests" / "unit" / "math").glob("*.py")})


@pytest.mark.parametrize("name", MATH_FILES)
def test_contract_file_exists(name):
    assert (ROOT / "quartz" / "math" / name).is_file()


@pytest.mark.parametrize("path", OWNED, ids=lambda p: p.name)
def test_no_comments_or_docstrings(path):
    import io
    import tokenize
    src = path.read_text(encoding="utf-8")
    assert not [t for t in tokenize.generate_tokens(io.StringIO(src).readline) if t.type == tokenize.COMMENT]
    assert not [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)]


@pytest.mark.parametrize("path", sorted((ROOT / "quartz" / "math").glob("*.py")), ids=lambda p: p.name)
def test_import_rules_l1_math(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    allowed_third = {"numpy"}
    for node in ast.walk(tree):
        mods = []
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            mods = [node.module]
        for m in mods:
            top = m.split(".")[0]
            if top == "quartz":
                assert m == "quartz.math" or m.startswith("quartz.math."), m
            else:
                assert top in allowed_third or top in sys.stdlib_module_names, m


def test_init_reexports():
    for name in ("Vector", "Matrix", "Quaternion", "Euler", "Color", "axis_conversion"):
        assert hasattr(qm, name)
    import types
    for sub in ("geometry", "kdtree", "bvhtree", "noise", "interpolate", "scalar"):
        assert isinstance(getattr(qm, sub), types.ModuleType)



FACTORIES = {
    "Vector": lambda: Vector((1.0, 2.0, 3.0)),
    "Matrix": lambda: Matrix(((1.0, 2.0, 3.0), (4.0, 5.0, 6.0), (7.0, 8.0, 10.0))),
    "Quaternion": lambda: Quaternion((1.0, 2.0, 3.0, 4.0)),
    "Euler": lambda: Euler((0.1, 0.2, 0.3), "ZXY"),
    "Color": lambda: Color((0.1, 0.2, 0.3)),
}
SHAPES = {"Vector": (3,), "Matrix": (3, 3), "Quaternion": (4,), "Euler": (3,), "Color": (3,)}
CLASSES = {"Vector": Vector, "Matrix": Matrix, "Quaternion": Quaternion, "Euler": Euler, "Color": Color}
KINDS = list(FACTORIES)


def mutate(obj):
    if isinstance(obj, Matrix):
        obj[0] = (9.0, 9.0, 9.0)
    else:
        obj[0] = 9.0


@pytest.mark.parametrize("kind", KINDS)
def test_base_fresh_flags(kind):
    o = FACTORIES[kind]()
    assert o.is_wrapped is False
    assert o.is_frozen is False
    assert o.is_valid is True
    assert o.owner is None


@pytest.mark.parametrize("kind", KINDS)
def test_base_storage_float32(kind):
    o = FACTORIES[kind]()
    assert isinstance(o._data, np.ndarray)
    assert o._data.dtype == np.float32
    assert o._data.shape == SHAPES[kind]


@pytest.mark.parametrize("kind", KINDS)
def test_base_copy_independent(kind):
    o = FACTORIES[kind]()
    c = o.copy()
    assert type(c) is type(o)
    assert c == o
    assert c is not o
    mutate(c)
    assert c != o


@pytest.mark.parametrize("kind", KINDS)
def test_base_copy_of_frozen_not_frozen(kind):
    o = FACTORIES[kind]().freeze()
    c = o.copy()
    assert c.is_frozen is False and c.is_wrapped is False


@pytest.mark.parametrize("kind", KINDS)
def test_base_copy_module(kind):
    o = FACTORIES[kind]()
    a = copy.copy(o)
    b = copy.deepcopy(o)
    assert type(a) is type(o) and a == o and a is not o
    assert type(b) is type(o) and b == o and b is not o


@pytest.mark.parametrize("kind", KINDS)
def test_base_freeze_returns_self(kind):
    o = FACTORIES[kind]()
    assert o.freeze() is o
    assert o.is_frozen is True


@pytest.mark.parametrize("kind", KINDS)
def test_base_frozen_mutation_typeerror(kind):
    o = FACTORIES[kind]().freeze()
    before = o._data.copy()
    with pytest.raises(TypeError):
        mutate(o)
    assert np.array_equal(o._data, before)


@pytest.mark.parametrize("kind", KINDS)
def test_base_hash_mutable_message(kind):
    o = FACTORIES[kind]()
    with pytest.raises(TypeError) as ei:
        hash(o)
    assert f"{kind} is not frozen (mutable), call freeze first" in str(ei.value)


@pytest.mark.parametrize("kind", KINDS)
def test_base_hash_frozen(kind):
    a = FACTORIES[kind]().freeze()
    b = FACTORIES[kind]().freeze()
    assert isinstance(hash(a), int)
    assert hash(a) == hash(b)


def test_base_hash_frozen_vector_value():
    v = Vector((1.0, 2.0, 3.0)).freeze()
    assert hash(v) == hash((1.0, 2.0, 3.0))


def test_vector_hash_fact():
    fact = FACTS["math.vector_hash"]
    with pytest.raises(TypeError) as ei:
        hash(Vector((1, 2, 3)))
    assert fact["__exc__"] == "TypeError"
    assert fact["msg"] in str(ei.value)


@pytest.mark.parametrize("kind", KINDS)
def test_base_eq_tuple_list_false(kind):
    o = FACTORIES[kind]()
    if isinstance(o, Matrix):
        seq = [list(r) for r in o._data.tolist()]
    else:
        seq = list(o._data.tolist())
    assert (o == tuple(seq if not isinstance(o, Matrix) else map(tuple, seq))) is False
    assert (o == seq) is False
    assert (o != seq) is True


def test_vector_eq_tuple_fact():
    assert (Vector((1, 2, 3)) == (1, 2, 3)) is FACTS["math.vector_eq_tuple"]


def test_eq_different_class_false():
    assert (Vector((0.1, 0.2, 0.3)) == Color((0.1, 0.2, 0.3))) is False
    assert (Color((0.1, 0.2, 0.3)) == Vector((0.1, 0.2, 0.3))) is False
    assert (Euler((0.1, 0.2, 0.3)) == Vector((0.1, 0.2, 0.3))) is False
    assert (Matrix.Identity(4) == Vector((1, 0, 0, 0))) is False


def test_eq_different_shape_false():
    assert (Vector((1, 2)) == Vector((1, 2, 0))) is False
    assert (Matrix.Identity(3) == Matrix.Identity(4)) is False


@pytest.mark.parametrize("kind", KINDS)
def test_base_ne_complement(kind):
    a = FACTORIES[kind]()
    b = FACTORIES[kind]()
    assert (a != b) is False
    mutate(b)
    assert (a != b) is True


@pytest.mark.parametrize("kind", KINDS)
def test_base_array_copy_float32(kind):
    o = FACTORIES[kind]()
    arr = np.asarray(o)
    assert arr.dtype == np.float32
    assert arr.shape == SHAPES[kind]
    arr2 = o.__array__()
    arr2[...] = 0
    assert not np.all(o._data == 0)


@pytest.mark.parametrize("kind", KINDS)
def test_base_array_dtype(kind):
    o = FACTORIES[kind]()
    arr = o.__array__(dtype=np.float64)
    assert arr.dtype == np.float64


WRAP_VIEWS = {
    "Vector": lambda: np.array([1.0, 2.0, 3.0], dtype=np.float32),
    "Matrix": lambda: np.array([[1, 2, 3], [4, 5, 6], [7, 8, 10]], dtype=np.float32),
    "Quaternion": lambda: np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
    "Euler": lambda: np.array([0.1, 0.2, 0.3], dtype=np.float32),
    "Color": lambda: np.array([0.1, 0.2, 0.3], dtype=np.float32),
}


class _Owner:
    pass


class _RemovedOwner:
    _q_removed = True


@pytest.mark.parametrize("kind", KINDS)
def test_wrap_flags_and_memory(kind):
    view = WRAP_VIEWS[kind]()
    owner = _Owner()
    o = CLASSES[kind]._q_wrap(view, owner=owner)
    assert o.is_wrapped is True
    assert o.owner is owner
    assert o.is_valid is True
    assert np.shares_memory(o._data, view)
    assert o._data.shape == view.shape


@pytest.mark.parametrize("kind", KINDS)
def test_wrap_write_goes_to_view_and_on_write(kind):
    view = WRAP_VIEWS[kind]()
    calls = []
    o = CLASSES[kind]._q_wrap(view, owner=_Owner(), on_write=lambda: calls.append(1))
    mutate(o)
    assert calls, "on_write not called"
    assert np.ravel(view)[0] == 9.0


@pytest.mark.parametrize("kind", KINDS)
def test_wrap_invalid_when_owner_removed(kind):
    o = CLASSES[kind]._q_wrap(WRAP_VIEWS[kind](), owner=_RemovedOwner())
    assert o.is_valid is False


@pytest.mark.parametrize("kind", KINDS)
def test_wrap_freeze_typeerror(kind):
    o = CLASSES[kind]._q_wrap(WRAP_VIEWS[kind](), owner=_Owner())
    with pytest.raises(TypeError) as ei:
        o.freeze()
    assert "Cannot freeze wrapped data" in str(ei.value)


@pytest.mark.parametrize("kind", KINDS)
def test_wrap_copy_not_wrapped(kind):
    o = CLASSES[kind]._q_wrap(WRAP_VIEWS[kind](), owner=_Owner())
    c = o.copy()
    assert c.is_wrapped is False and c.owner is None and c.is_frozen is False
    assert not np.shares_memory(c._data, o._data)


def test_wrap_vector_resize_typeerror():
    v = Vector._q_wrap(np.zeros(3, dtype=np.float32), owner=_Owner())
    for fn in (lambda: v.resize(4), v.resize_2d, v.resize_4d, lambda: v.resize_3d()):
        with pytest.raises(TypeError):
            fn()


def test_wrap_matrix_resize_typeerror():
    m = Matrix._q_wrap(np.eye(3, dtype=np.float32), owner=_Owner())
    with pytest.raises(TypeError):
        m.resize_4x4()


def test_euler_wrap_order_kw():
    e = Euler._q_wrap(np.zeros(3, dtype=np.float32), owner=_Owner(), order="ZYX")
    assert e.order == "ZYX"
    assert e.is_wrapped


def test_euler_copy_preserves_order():
    e = Euler((0.1, 0.2, 0.3), "YZX")
    assert e.copy().order == "YZX"
    assert copy.deepcopy(e).order == "YZX"


@pytest.mark.parametrize("kind", ["Vector", "Quaternion", "Euler", "Color"])
def test_component_read_is_python_float_float32(kind):
    o = CLASSES[kind]((0.1, 0.2, 0.3, 0.4)[: SHAPES[kind][0]])
    assert type(o[0]) is float
    assert o[0] == FACTS["math.float32"]


def test_matrix_component_float32():
    m = Matrix(((0.1, 0.0), (0.0, 1.0)))
    assert m[0][0] == FACTS["math.float32"]
    assert type(m[0][0]) is float


def test_float32_fact_vector_x():
    assert Vector((0.1, 0.0, 0.0)).x == FACTS["math.float32"]


def test_float32_after_math_result():
    r = Vector((0.1, 0.0, 0.0)) * 1.0
    assert r._data.dtype == np.float32
    assert r.x == f32(0.1)


@pytest.mark.parametrize("kind", ["Vector", "Quaternion", "Euler", "Color"])
def test_setter_calls_on_write(kind):
    view = WRAP_VIEWS[kind]()
    calls = []
    o = CLASSES[kind]._q_wrap(view, owner=_Owner(), on_write=lambda: calls.append(1))
    o.x if kind != "Color" else None
    if kind == "Color":
        o.r = 0.5
    else:
        o.x = 0.5
    assert calls
    assert view[0 if kind in ("Vector", "Euler", "Color") else 1] == 0.5



def test_vector_default_fact():
    approx_seq(Vector(), FACTS["math.vector_default"])
    assert len(Vector()) == 3


def test_vector_signature_defaults():
    sig = inspect.signature(Vector.__init__)
    assert sig.parameters["seq"].default == (0.0, 0.0, 0.0)
    assert inspect.signature(Vector.Fill).parameters["fill"].default == 0.0
    p = inspect.signature(Vector.Range).parameters
    assert p["stop"].default is None and p["step"].default == 1
    assert inspect.signature(Vector.to_tuple).parameters["precision"].default == -1
    p = inspect.signature(Vector.to_track_quat).parameters
    assert p["track"].default == "Z" and p["up"].default == "Y"
    assert inspect.signature(Vector.angle).parameters["fallback"].default is None
    assert inspect.signature(Vector.slerp).parameters["fallback"].default is None


@pytest.mark.parametrize("seq", [(), (1.0,), [5]])
def test_vector_invalid_size(seq):
    with pytest.raises(ValueError) as ei:
        Vector(seq)
    assert "Vector(): invalid size" in str(ei.value)


def test_vector_accepts_list_array_vector():
    approx_seq(Vector([1, 2]), (1, 2))
    approx_seq(Vector(np.array([1.0, 2.0, 3.0, 4.0])), (1, 2, 3, 4))
    approx_seq(Vector(Vector((1, 2, 3))), (1, 2, 3))
    approx_seq(Vector(x for x in (1, 2, 3)), (1, 2, 3))


def test_vector_fill():
    v = Vector.Fill(4, 2.5)
    assert isinstance(v, Vector)
    approx_seq(v, (2.5, 2.5, 2.5, 2.5))
    approx_seq(Vector.Fill(3), (0, 0, 0))


def test_vector_range():
    approx_seq(Vector.Range(5), (0, 1, 2, 3, 4))
    approx_seq(Vector.Range(2, 6), (2, 3, 4, 5))
    approx_seq(Vector.Range(1, 8, 3), (1, 4, 7))


def test_vector_linspace():
    approx_seq(Vector.Linspace(0.0, 1.0, 5), (0, 0.25, 0.5, 0.75, 1.0))


def test_vector_repeat():
    approx_seq(Vector.Repeat((1, 2), 5), (1, 2, 1, 2, 1))
    approx_seq(Vector.Repeat(Vector((1, 2, 3)), 4), (1, 2, 3, 1))


def test_vector_xyzw_rw():
    v = Vector((1, 2, 3, 4))
    assert (v.x, v.y, v.z, v.w) == (1.0, 2.0, 3.0, 4.0)
    v.x, v.y, v.z, v.w = 5, 6, 7, 8
    approx_seq(v, (5, 6, 7, 8))


def test_vector_component_beyond_size_attributeerror():
    v = Vector((1, 2))
    with pytest.raises(AttributeError):
        v.z
    with pytest.raises(AttributeError):
        v.z = 1.0
    v3 = Vector((1, 2, 3))
    with pytest.raises(AttributeError):
        v3.w
    with pytest.raises(AttributeError):
        v3.w = 1.0


def test_vector_swizzle_read():
    v = Vector((1, 2, 3, 4))
    s = v.zyx
    assert isinstance(s, Vector)
    approx_seq(s, (3, 2, 1))
    approx_seq(v.xxxx, (1, 1, 1, 1))
    approx_seq(v.wx, (4, 1))
    s.x = 100
    assert v.z == 3.0


def test_vector_swizzle_read_beyond_size():
    v = Vector((1, 2))
    with pytest.raises(AttributeError):
        v.xz
    with pytest.raises(AttributeError):
        Vector((1, 2, 3)).xyzw


def test_vector_swizzle_write():
    v = Vector((1, 2, 3))
    v.zx = (7, 8)
    approx_seq(v, (8, 2, 7))
    v.xyz = Vector((4, 5, 6))
    approx_seq(v, (4, 5, 6))


def test_vector_swizzle_write_repeated_attributeerror():
    v = Vector((1, 2, 3))
    with pytest.raises(AttributeError):
        v.xx = (1, 2)
    approx_seq(v, (1, 2, 3))


def test_vector_swizzle_write_wrong_length():
    v = Vector((1, 2, 3))
    with pytest.raises((ValueError, TypeError, AttributeError)):
        v.xy = (1, 2, 3)


def test_vector_swizzle_write_beyond_size():
    v = Vector((1, 2))
    with pytest.raises(AttributeError):
        v.xz = (1, 2)


def test_vector_swizzle_write_frozen():
    v = Vector((1, 2, 3)).freeze()
    with pytest.raises(TypeError):
        v.xy = (5, 6)


def test_vector_length_fact():
    assert Vector((3, 4)).length == pytest.approx(FACTS["math.length_vec2"], abs=TOL)


def test_vector_length_squared_magnitude():
    v = Vector((3, 4))
    assert v.length_squared == pytest.approx(25.0)
    assert v.magnitude == pytest.approx(5.0)
    assert type(v.length) is float


def test_vector_length_setter():
    v = Vector((3, 4))
    v.length = 10
    approx_seq(v, (6, 8))
    v.magnitude = 5
    approx_seq(v, (3, 4))


def test_vector_length_setter_null_stays_null():
    v = Vector((0, 0, 0))
    v.length = 3.0
    approx_seq(v, (0, 0, 0))


def test_vector_to_tuple():
    v = Vector((1.23456, 2.0))
    t = v.to_tuple()
    assert isinstance(t, tuple) and t == (f32(1.23456), 2.0)
    assert v.to_tuple(2) == (1.23, 2.0)
    assert v.to_tuple(0) == (1.0, 2.0)


def test_vector_to_2d_3d():
    v = Vector((1, 2, 3, 4))
    approx_seq(v.to_2d(), (1, 2))
    approx_seq(v.to_3d(), (1, 2, 3))
    approx_seq(Vector((1, 2)).to_3d(), (1, 2, 0))


def test_vector_to_4d():
    approx_seq(Vector((1, 2, 3)).to_4d(), (1, 2, 3, 1))
    approx_seq(Vector((1, 2)).to_4d(), (1, 2, 0, 1))
    approx_seq(Vector((1, 2, 3, 4)).to_4d(), (1, 2, 3, 4))


def test_vector_resize_new_zero():
    v = Vector((1, 2))
    v.resize(5)
    approx_seq(v, (1, 2, 0, 0, 0))
    v.resize(3)
    approx_seq(v, (1, 2, 0))


def test_vector_resize_generic_to_4_pads_zero():
    v = Vector((1, 2, 3))
    v.resize(4)
    approx_seq(v, (1, 2, 3, 0))


def test_vector_resized():
    v = Vector((1, 2, 3))
    r = v.resized(4)
    assert len(v) == 3
    approx_seq(r, (1, 2, 3, 0))


def test_vector_resize_2d_3d_4d():
    v = Vector((1, 2, 3))
    v.resize_4d()
    approx_seq(v, (1, 2, 3, 1))
    v.resize_2d()
    approx_seq(v, (1, 2))
    v.resize_3d()
    approx_seq(v, (1, 2, 0))


def test_vector_resize_frozen():
    v = Vector((1, 2, 3)).freeze()
    with pytest.raises(TypeError):
        v.resize(4)


def test_vector_normalize():
    v = Vector((3, 4))
    assert v.normalize() is None
    approx_seq(v, (0.6, 0.8))
    n = Vector((0, 0, 2)).normalized()
    approx_seq(n, (0, 0, 1))


def test_vector_normalize_null():
    v = Vector((0, 0, 0))
    v.normalize()
    approx_seq(v, (0, 0, 0))
    approx_seq(Vector((0, 0)).normalized(), (0, 0))


def test_vector_negate_zero():
    v = Vector((1, -2, 3))
    v.negate()
    approx_seq(v, (-1, 2, -3))
    v.zero()
    approx_seq(v, (0, 0, 0))


def test_vector_mutators_frozen():
    for fn in ("normalize", "negate", "zero"):
        v = Vector((1, 2, 3)).freeze()
        with pytest.raises(TypeError):
            getattr(v, fn)()
    v = Vector((1, 2, 3)).freeze()
    with pytest.raises(TypeError):
        v.length = 2.0


def test_vector_dot():
    assert Vector((1, 2, 3)).dot((4, 5, 6)) == pytest.approx(32.0)
    assert type(Vector((1, 2, 3)).dot(Vector((4, 5, 6)))) is float


def test_vector_cross_3d():
    c = Vector((1, 0, 0)).cross(Vector((0, 1, 0)))
    assert isinstance(c, Vector)
    approx_seq(c, (0, 0, 1))


def test_vector_cross_2d_fact():
    r = Vector((1, 0)).cross(Vector((0, 1)))
    assert isinstance(r, float)
    assert r == pytest.approx(FACTS["math.cross2"], abs=TOL)


def test_vector_cross_other_size_valueerror():
    with pytest.raises(ValueError):
        Vector((1, 0, 0, 0)).cross((0, 1, 0, 0))


def test_vector_angle():
    assert Vector((1, 0, 0)).angle((0, 1, 0)) == pytest.approx(math.pi / 2)


def test_vector_angle_null():
    assert Vector((0, 0, 0)).angle((1, 0, 0), 7.0) == 7.0
    with pytest.raises(ValueError):
        Vector((0, 0, 0)).angle((1, 0, 0))


def test_vector_angle_signed():
    assert Vector((1, 0)).angle_signed((0, 1)) == pytest.approx(math.pi / 2, abs=TOL) or \
        Vector((1, 0)).angle_signed((0, 1)) == pytest.approx(-math.pi / 2, abs=TOL)
    a = Vector((1, 0)).angle_signed((0, 1))
    b = Vector((0, 1)).angle_signed((1, 0))
    assert a == pytest.approx(-b)


def test_vector_angle_signed_non2d():
    with pytest.raises(ValueError):
        Vector((1, 0, 0)).angle_signed((0, 1, 0))


def test_vector_angle_signed_null_fallback():
    assert Vector((0, 0)).angle_signed((1, 0), 3.0) == 3.0
    with pytest.raises(ValueError):
        Vector((0, 0)).angle_signed((1, 0))


def test_vector_lerp():
    r = Vector((0, 0, 0)).lerp((2, 4, 6), 0.5)
    assert isinstance(r, Vector)
    approx_seq(r, (1, 2, 3))


def test_vector_slerp():
    r = Vector((1, 0, 0)).slerp((0, 1, 0), 0.5)
    assert isinstance(r, Vector)
    approx_seq(r, (math.sqrt(0.5), math.sqrt(0.5), 0))


def test_vector_slerp_fallback():
    fb = object()
    assert Vector((0, 0, 0)).slerp((0, 1, 0), 0.5, fb) is fb


def test_vector_project():
    r = Vector((1, 1, 0)).project((1, 0, 0))
    approx_seq(r, (1, 0, 0))


def test_vector_reflect():
    r = Vector((1, -1, 0)).reflect((0, 1, 0))
    approx_seq(r, (1, 1, 0))


def test_vector_orthogonal():
    for src in ((1, 0, 0), (0, 0, 1), (1, 2, 3)):
        v = Vector(src)
        o = v.orthogonal()
        assert isinstance(o, Vector) and len(o) == 3
        assert abs(v.dot(o)) < 1e-5
        assert o.length > 1e-6


def test_vector_rotate_quaternion():
    v = Vector((1, 0, 0))
    assert v.rotate(Quaternion((0, 0, 1), math.pi / 2)) is None
    approx_seq(v, (0, 1, 0))


def test_vector_rotate_euler():
    v = Vector((1, 0, 0))
    v.rotate(Euler((0, 0, math.pi / 2)))
    approx_seq(v, (0, 1, 0))


def test_vector_rotate_matrix():
    v = Vector((1, 0, 0))
    v.rotate(Matrix.Rotation(math.pi / 2, 3, "Z"))
    approx_seq(v, (0, 1, 0))


def test_vector_rotate_frozen():
    v = Vector((1, 0, 0)).freeze()
    with pytest.raises(TypeError):
        v.rotate(Euler((0, 0, 1)))


def test_vector_rotation_difference():
    q = Vector((1, 0, 0)).rotation_difference((0, 1, 0))
    assert isinstance(q, Quaternion)
    approx_seq(q @ Vector((1, 0, 0)), (0, 1, 0))


TRACKS = ["X", "Y", "Z", "-X", "-Y", "-Z"]
UPS = ["X", "Y", "Z"]
AX = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}


def axis_vec(s):
    sign = -1.0 if s.startswith("-") else 1.0
    return np.array(AX[s.lstrip("-")], dtype=np.float64) * sign


def test_vector_to_track_quat_fact():
    q = Vector((0, 1, 0)).to_track_quat("Z", "Y")
    assert isinstance(q, Quaternion)
    approx_quat(q, FACTS["math.to_track_quat"])


@pytest.mark.parametrize("track,up", [(t, u) for t in TRACKS for u in UPS if t.lstrip("-") != u])
def test_vector_to_track_quat_maps_track_axis(track, up):
    d = np.array([0.3, -0.5, 0.2])
    q = Vector(d).to_track_quat(track, up)
    R = np.asarray(q.to_matrix(), dtype=np.float64)
    got = R @ axis_vec(track)
    assert np.allclose(got, d / np.linalg.norm(d), atol=1e-5)
    up_world = R @ axis_vec(up)
    dn = d / np.linalg.norm(d)
    z = np.array([0.0, 0.0, 1.0])
    proj = z - np.dot(z, dn) * dn
    proj /= np.linalg.norm(proj)
    assert np.allclose(up_world, proj, atol=1e-5)


@pytest.mark.parametrize("track,up", [("Z", "Z"), ("-Y", "Y"), ("X", "X")])
def test_vector_to_track_quat_same_axis_valueerror(track, up):
    with pytest.raises(ValueError):
        Vector((0, 1, 0)).to_track_quat(track, up)


def test_vector_op_add_sub():
    a = Vector((1, 2, 3))
    b = Vector((4, 5, 6))
    r = a + b
    assert isinstance(r, Vector)
    approx_seq(r, (5, 7, 9))
    approx_seq(b - a, (3, 3, 3))


def test_vector_op_add_size_mismatch():
    with pytest.raises(ValueError):
        Vector((1, 2, 3)) + Vector((1, 2))
    with pytest.raises(ValueError):
        Vector((1, 2, 3)) - Vector((1, 2))


def test_vector_op_scalar_mul():
    v = Vector((1, 2, 3))
    approx_seq(v * 2, (2, 4, 6))
    approx_seq(2 * v, (2, 4, 6))
    assert isinstance(2.0 * v, Vector)


def test_vector_op_elementwise_fact():
    r = Vector((1, 2, 3)) * Vector((2, 3, 4))
    assert isinstance(r, Vector)
    approx_seq(r, FACTS["math.vec_mul_vec"])


def test_vector_op_matmul_vector_fact():
    r = Vector((1, 2, 3)) @ Vector((2, 3, 4))
    assert isinstance(r, float)
    assert r == pytest.approx(FACTS["math.vec_matmul_vec"], abs=TOL)


def test_vector_op_matmul_matrix_fact():
    r = Vector((1, 0, 0)) @ Matrix.Rotation(math.pi / 2, 3, "Z")
    assert isinstance(r, Vector)
    approx_seq(r, FACTS["math.vec_mat"])


def test_vector_op_div():
    approx_seq(Vector((2, 4)) / 2, (1, 2))
    with pytest.raises(ZeroDivisionError):
        Vector((1, 2)) / 0


def test_vector_op_neg_pos():
    v = Vector((1, -2))
    approx_seq(-v, (-1, 2))
    p = +v
    assert isinstance(p, Vector) and p == v


def test_vector_op_inplace():
    v = Vector((1, 2, 3))
    vid = id(v)
    v += (1, 1, 1)
    v -= Vector((0, 1, 0))
    v *= 2
    v /= 4
    assert id(v) == vid
    approx_seq(v, (1, 1, 2))


def test_vector_op_inplace_div_zero():
    v = Vector((1, 2))
    with pytest.raises(ZeroDivisionError):
        v /= 0


def test_vector_op_inplace_frozen():
    v = Vector((1, 2, 3)).freeze()
    with pytest.raises(TypeError):
        v += (1, 1, 1)
    with pytest.raises(TypeError):
        v *= 2


def test_vector_inplace_wrapped_on_write():
    view = np.zeros(3, dtype=np.float32)
    calls = []
    v = Vector._q_wrap(view, owner=_Owner(), on_write=lambda: calls.append(1))
    v += (1, 2, 3)
    assert calls and view.tolist() == [1, 2, 3]
    v.normalize()
    assert len(calls) >= 2


def test_vector_compare_by_length_same_size():
    a = Vector((1, 0, 0))
    b = Vector((0, 2, 0))
    assert a < b
    assert a <= b
    assert b > a
    assert b >= a
    assert not (a > b)


def test_vector_compare_by_length_equal_lengths():
    a = Vector((1, 0, 0))
    b = Vector((0, 1, 0))
    assert a <= b and a >= b
    assert not (a < b) and not (a > b)


def test_vector_compare_by_length_mixed_size():
    assert Vector((10, 0, 0)) > Vector((1, 1))


def test_vector_len_iter():
    v = Vector((1, 2, 3))
    assert len(v) == 3
    assert list(v) == [1.0, 2.0, 3.0]
    assert all(type(x) is float for x in v)


def test_vector_index():
    v = Vector((1, 2, 3))
    assert v[0] == 1.0 and v[-1] == 3.0 and v[-3] == 1.0
    with pytest.raises(IndexError):
        v[3]
    with pytest.raises(IndexError):
        v[-4]


def test_vector_slice_returns_tuple():
    v = Vector((1, 2, 3, 4))
    s = v[1:3]
    assert isinstance(s, tuple) and s == (2.0, 3.0)


def test_vector_setitem():
    v = Vector((1, 2, 3))
    v[0] = 5
    v[-1] = 7
    approx_seq(v, (5, 2, 7))
    v[0:2] = (8, 9)
    approx_seq(v, (8, 9, 7))
    with pytest.raises(IndexError):
        v[3] = 1


def test_vector_repr_fact():
    assert repr(Vector((1.0, 2.5, -3.0))) == FACTS["math.repr_vector"]


def test_vector_str_fact():
    assert str(Vector((1.0, 2.5, -3.0))) == FACTS["math.str_vector"]


def test_vector_repr_float32():
    assert repr(Vector((0.1, 0.0))) == "Vector((0.10000000149011612, 0.0))"



def test_matrix_default_fact():
    approx_mat(Matrix(), FACTS["math.matrix_default"])
    assert len(Matrix()) == 4


@pytest.mark.parametrize("rows", [[[1.0]], [[1, 2, 3, 4, 5]] * 2, [[1, 2]] * 5, [[1, 2]], [1, 2, 3]])
def test_matrix_invalid_size(rows):
    with pytest.raises(ValueError):
        Matrix(rows)


def test_matrix_non_square_ok():
    m = Matrix(((1, 2, 3), (4, 5, 6)))
    assert m._data.shape == (2, 3)
    assert len(m) == 2


def test_matrix_signature_defaults():
    assert inspect.signature(Matrix.__init__).parameters["rows"].default is None
    assert inspect.signature(Matrix.Rotation).parameters["axis"].default is None
    assert inspect.signature(Matrix.Scale).parameters["axis"].default is None
    p = inspect.signature(Matrix.to_euler).parameters
    assert p["order"].default == "XYZ" and p["euler_compat"].default is None
    assert inspect.signature(Matrix.invert).parameters["fallback"].default is None


@pytest.mark.parametrize("n", [2, 3, 4])
def test_matrix_identity(n):
    m = Matrix.Identity(n)
    approx_mat(m, np.eye(n))
    assert m.is_identity


def test_matrix_rotation_fact():
    approx_mat(Matrix.Rotation(math.pi / 2, 3, "Z"), FACTS["math.rot_z"])


def test_matrix_rotation_2d_ignores_axis():
    m = Matrix.Rotation(math.pi / 2, 2, "X")
    approx_mat(m, [[0, -1], [1, 0]])


def test_matrix_rotation_axes_and_vector():
    approx_mat(Matrix.Rotation(math.pi / 2, 3, "X"), [[1, 0, 0], [0, 0, -1], [0, 1, 0]])
    approx_mat(Matrix.Rotation(math.pi / 2, 3, "Y"), [[0, 0, 1], [0, 1, 0], [-1, 0, 0]])
    approx_mat(Matrix.Rotation(math.pi / 2, 3, (0, 0, 1)), FACTS["math.rot_z"])
    m4 = Matrix.Rotation(math.pi / 2, 4, "Z")
    assert m4._data.shape == (4, 4)
    approx_mat(m4.to_3x3(), FACTS["math.rot_z"])
    assert m4[3][3] == 1.0


def test_matrix_translation_fact():
    m = Matrix.Translation((1, 2, 3))
    assert m._data.shape == (4, 4)
    r = m @ Vector((1, 1, 1))
    assert isinstance(r, Vector) and len(r) == 3
    approx_seq(r, FACTS["math.mat_vec3"])


def test_matrix_scale():
    approx_mat(Matrix.Scale(2, 3), np.eye(3) * 2)
    m4 = Matrix.Scale(2, 4)
    approx_mat(m4, np.diag([2, 2, 2, 1]))
    approx_mat(Matrix.Scale(2, 2), np.eye(2) * 2)


def test_matrix_scale_axis():
    m = Matrix.Scale(3, 3, (1, 0, 0))
    approx_mat(m, np.diag([3, 1, 1]))


def test_matrix_diagonal():
    approx_mat(Matrix.Diagonal((1, 2, 3)), np.diag([1, 2, 3]))


def test_matrix_ortho_projection():
    approx_mat(Matrix.OrthoProjection("XY", 3), np.diag([1, 1, 0]))
    approx_mat(Matrix.OrthoProjection("XZ", 3), np.diag([1, 0, 1]))
    approx_mat(Matrix.OrthoProjection("YZ", 3), np.diag([0, 1, 1]))
    approx_mat(Matrix.OrthoProjection("X", 2), np.diag([1, 0]))
    approx_mat(Matrix.OrthoProjection("Y", 2), np.diag([0, 1]))
    approx_mat(Matrix.OrthoProjection((0, 0, 1), 3), np.diag([1, 1, 0]))
    m4 = Matrix.OrthoProjection("XY", 4)
    assert m4._data.shape == (4, 4)


def test_matrix_shear():
    approx_mat(Matrix.Shear("X", 2, 0.5), [[1, 0.5], [0, 1]])
    approx_mat(Matrix.Shear("Y", 2, 0.5), [[1, 0], [0.5, 1]])
    approx_mat(Matrix.Shear("XY", 3, (0.5, 0.25)), [[1, 0, 0.5], [0, 1, 0.25], [0, 0, 1]])


def test_matrix_locrotscale_decompose_fact():
    m = Matrix.LocRotScale((1, 2, 3), Euler((0.1, 0.2, 0.3)), (2, 2, 2))
    loc, rot, sca = m.decompose()
    assert isinstance(loc, Vector) and isinstance(rot, Quaternion) and isinstance(sca, Vector)
    exp = FACTS["math.decompose"]
    approx_seq(loc, exp[0])
    approx_quat(rot, exp[1])
    approx_seq(sca, exp[2])


def test_matrix_locrotscale_trs_order():
    R = Euler((0.3, -0.2, 0.5)).to_matrix()
    m = Matrix.LocRotScale((1, 2, 3), R, (1, 2, 3))
    exp = np.asarray(Matrix.Translation((1, 2, 3))) @ np.asarray(R.to_4x4()) @ np.diag([1, 2, 3, 1])
    approx_mat(m, exp)


def test_matrix_locrotscale_quaternion_and_none():
    q = Quaternion((0, 0, 1), 0.7)
    m = Matrix.LocRotScale(None, q, None)
    approx_mat(m.to_3x3(), np.asarray(q.to_matrix()))
    approx_mat(Matrix.LocRotScale(None, None, None), np.eye(4))


def test_matrix_row_col_wrapped():
    m = Matrix.Identity(3)
    r = m.row[1]
    assert isinstance(r, Vector) and r.is_wrapped
    r[0] = 5
    assert m[1][0] == 5.0
    c = m.col[2]
    assert c.is_wrapped
    c[0] = 7
    assert m[0][2] == 7.0
    approx_seq(m.col[0], (1, 5, 0))


def test_matrix_translation_4x4():
    m = Matrix.Translation((1, 2, 3))
    t = m.translation
    assert isinstance(t, Vector) and t.is_wrapped
    approx_seq(t, (1, 2, 3))
    t.x = 9
    assert m[0][3] == 9.0
    m.translation = (4, 5, 6)
    approx_seq(m.col[3], (4, 5, 6, 1))


def test_matrix_translation_3x3():
    m = Matrix.Identity(3)
    m.translation = (4, 5)
    approx_seq(m.col[2], (4, 5, 1))
    approx_seq(m.translation, (4, 5))


def test_matrix_median_scale():
    assert Matrix.Scale(2, 4).median_scale == pytest.approx(2.0)


def test_matrix_median_scale_rotated():
    m = Matrix.Rotation(math.pi / 2, 3, "Z") @ Matrix.Scale(2, 3)
    assert m.median_scale == pytest.approx(2.0, abs=1e-5)


def test_matrix_is_flags():
    assert Matrix.Identity(3).is_identity
    assert not Matrix.Scale(2, 3).is_identity
    assert Matrix.Scale(-1, 3).is_negative
    assert not Matrix.Identity(3).is_negative
    assert Matrix.Rotation(0.3, 3, "X").is_orthogonal
    assert not Matrix.Shear("XY", 3, (0.5, 0.5)).is_orthogonal
    assert Matrix.Rotation(0.3, 3, "X").is_orthogonal_axis_vectors
    for flag in ("is_identity", "is_negative", "is_orthogonal", "is_orthogonal_axis_vectors"):
        assert isinstance(getattr(Matrix(), flag), bool)


def test_matrix_determinant():
    m = Matrix(((1, 2), (3, 4)))
    assert m.determinant() == pytest.approx(-2.0)
    assert type(m.determinant()) is float


def test_matrix_determinant_non_square():
    with pytest.raises(ValueError):
        Matrix(((1, 2, 3), (4, 5, 6))).determinant()


def test_matrix_transpose():
    m = Matrix(((1, 2), (3, 4)))
    t = m.transposed()
    approx_mat(t, [[1, 3], [2, 4]])
    approx_mat(m, [[1, 2], [3, 4]])
    m.transpose()
    approx_mat(m, [[1, 3], [2, 4]])


def test_matrix_transposed_non_square():
    m = Matrix(((1, 2, 3), (4, 5, 6)))
    assert m.transposed()._data.shape == (3, 2)


def test_matrix_invert():
    m = Matrix(((2, 0), (0, 4)))
    assert m.invert() is None
    approx_mat(m, [[0.5, 0], [0, 0.25]])
    inv = Matrix(((2, 0), (0, 4))).inverted()
    approx_mat(inv, [[0.5, 0], [0, 0.25]])


def test_matrix_invert_singular_valueerror():
    m = Matrix(((1, 2), (2, 4)))
    with pytest.raises(ValueError) as ei:
        m.invert()
    assert "Matrix.invert(ed): matrix does not have an inverse" in str(ei.value)
    with pytest.raises(ValueError):
        m.inverted()


def test_matrix_invert_singular_fallback():
    m = Matrix(((1, 2), (2, 4)))
    fb = Matrix(((7, 7), (7, 7)))
    m.invert(fb)
    approx_mat(m, [[7, 7], [7, 7]])
    sentinel = object()
    assert Matrix(((1, 2), (2, 4))).inverted(sentinel) is sentinel
    assert Matrix(((1, 2), (2, 4))).inverted(None) is None


def test_matrix_invert_safe():
    m = Matrix(((1, 2), (2, 4)))
    m.invert_safe()
    assert np.all(np.isfinite(np.asarray(m)))
    r = Matrix(((2, 0), (0, 4))).inverted_safe()
    approx_mat(r, [[0.5, 0], [0, 0.25]])


def test_matrix_adjugate():
    a = Matrix(((1, 2, 3), (0, 1, 4), (5, 6, 0)))
    adj = a.adjugated()
    exp = np.linalg.det(np.asarray(a, dtype=np.float64)) * np.linalg.inv(np.asarray(a, dtype=np.float64))
    approx_mat(adj, exp, tol=1e-4)
    a.adjugate()
    approx_mat(a, exp, tol=1e-4)


def test_matrix_normalize():
    m = Matrix.Scale(2, 3) @ Matrix.Rotation(0.4, 3, "Z")
    n = m.normalized()
    cols = np.asarray(n, dtype=np.float64)
    assert np.allclose(np.linalg.norm(cols, axis=0), 1.0, atol=1e-5)
    m.normalize()
    approx_mat(m, n)


def test_matrix_normalize_4x4_keeps_translation():
    m = Matrix.LocRotScale((1, 2, 3), None, (2, 3, 4))
    n = m.normalized()
    approx_mat(n.to_3x3(), np.eye(3))
    approx_seq(n.translation, (1, 2, 3))


def test_matrix_zero_identity():
    m = Matrix.Translation((1, 2, 3))
    m.zero()
    approx_mat(m, np.zeros((4, 4)))
    m.identity()
    approx_mat(m, np.eye(4))


def test_matrix_to_sizes():
    m = Matrix.Translation((1, 2, 3))
    assert m.to_2x2()._data.shape == (2, 2)
    approx_mat(m.to_3x3(), np.eye(3))
    m3 = Matrix(((1, 2, 3), (4, 5, 6), (7, 8, 9)))
    m4 = m3.to_4x4()
    approx_mat(m4, [[1, 2, 3, 0], [4, 5, 6, 0], [7, 8, 9, 0], [0, 0, 0, 1]])
    m3.resize_4x4()
    approx_mat(m3, m4)


@pytest.mark.parametrize("order", ["XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"])
def test_matrix_to_euler_roundtrip(order):
    e = Euler((0.1, 0.2, 0.3), order)
    back = e.to_matrix().to_euler(order)
    assert isinstance(back, Euler) and back.order == order
    approx_seq(back, (0.1, 0.2, 0.3))


def test_matrix_to_euler_compat():
    m = Euler((0.0, 0.0, 0.1)).to_matrix()
    e = m.to_euler("XYZ", Euler((0.0, 0.0, 2 * math.pi)))
    assert e.z == pytest.approx(2 * math.pi + 0.1, abs=1e-4)


def test_matrix_to_quaternion():
    q = Euler((0.1, 0.2, 0.3)).to_matrix().to_quaternion()
    assert isinstance(q, Quaternion)
    approx_quat(q, FACTS["math.quat_from_euler"])


def test_matrix_to_scale_translation():
    m = Matrix.LocRotScale((1, 2, 3), Euler((0.4, 0.1, 0.2)), (2, 3, 4))
    approx_seq(m.to_scale(), (2, 3, 4))
    t = m.to_translation()
    approx_seq(t, (1, 2, 3))
    assert not t.is_wrapped


def test_matrix_lerp():
    a = Matrix.Identity(3)
    b = Matrix.Scale(3, 3)
    r = a.lerp(b, 0.5)
    assert isinstance(r, Matrix)
    approx_mat(r, np.eye(3) * 2)


def test_matrix_rotate():
    m = Matrix.Identity(3)
    m.rotate(Euler((0, 0, math.pi / 2)))
    approx_mat(m, FACTS["math.rot_z"])
    m = Matrix.Identity(3)
    m.rotate(Quaternion((0, 0, 1), math.pi / 2))
    approx_mat(m, FACTS["math.rot_z"])


def test_matrix_matmul():
    a = Matrix.Rotation(math.pi / 2, 3, "Z")
    b = Matrix.Rotation(-math.pi / 2, 3, "Z")
    r = a @ b
    assert isinstance(r, Matrix)
    approx_mat(r, np.eye(3))


def test_matrix_matmul_mismatch():
    with pytest.raises(ValueError):
        Matrix.Identity(3) @ Matrix.Identity(4)
    with pytest.raises(ValueError):
        Matrix.Identity(3) @ Vector((1, 2))


def test_matrix_matmul_vector_same_size():
    r = Matrix.Rotation(math.pi / 2, 3, "Z") @ Vector((1, 0, 0))
    approx_seq(r, (0, 1, 0))
    r4 = Matrix.Translation((1, 2, 3)) @ Vector((1, 1, 1, 1))
    approx_seq(r4, (2, 3, 4, 1))


def test_matrix_mul_elementwise():
    a = Matrix(((1, 2), (3, 4)))
    b = Matrix(((2, 2), (2, 2)))
    r = a * b
    assert isinstance(r, Matrix)
    approx_mat(r, [[2, 4], [6, 8]])


def test_matrix_mul_scalar():
    a = Matrix(((1, 2), (3, 4)))
    approx_mat(a * 2, [[2, 4], [6, 8]])


def test_matrix_rmul_scalar():
    a = Matrix(((1, 2), (3, 4)))
    approx_mat(2.0 * a, [[2, 4], [6, 8]])


def test_matrix_add_sub_neg():
    a = Matrix(((1, 2), (3, 4)))
    b = Matrix(((1, 1), (1, 1)))
    approx_mat(a + b, [[2, 3], [4, 5]])
    approx_mat(a - b, [[0, 1], [2, 3]])
    approx_mat(-a, [[-1, -2], [-3, -4]])
    assert isinstance(a + b, Matrix) and isinstance(-a, Matrix)


def test_matrix_getitem_row_wrapped():
    m = Matrix.Identity(3)
    r = m[0]
    assert isinstance(r, Vector) and r.is_wrapped
    r[1] = 4
    assert m[0][1] == 4.0
    approx_seq(m[-1], (0, 0, 1))
    with pytest.raises(IndexError):
        m[3]


def test_matrix_setitem_row():
    m = Matrix.Identity(3)
    m[1] = (4, 5, 6)
    approx_seq(m[1], (4, 5, 6))


def test_matrix_len_iter():
    m = Matrix(((1, 2, 3), (4, 5, 6)))
    assert len(m) == 2
    rows = list(m)
    assert len(rows) == 2 and all(isinstance(r, Vector) for r in rows)
    approx_seq(rows[1], (4, 5, 6))


def test_matrix_repr_fact():
    assert repr(Matrix.Identity(3)) == FACTS["math.repr_matrix"]


def test_matrix_frozen_mutations():
    for fn in (lambda m: m.zero(), lambda m: m.identity(), lambda m: m.transpose(),
               lambda m: m.normalize(), lambda m: m.invert(), lambda m: setattr(m, "translation", (1, 2, 3)),
               lambda m: m.__setitem__(0, (1, 2, 3, 4))):
        m = Matrix.Scale(2, 4).freeze()
        with pytest.raises(TypeError):
            fn(m)


def test_matrix_frozen_row_write_blocked():
    m = Matrix.Identity(4).freeze()
    with pytest.raises(TypeError):
        m[0][0] = 5.0
    assert m._data[0, 0] == 1.0


def test_matrix_frozen_col_write_blocked():
    m = Matrix.Identity(4).freeze()
    with pytest.raises(TypeError):
        m.col[0][1] = 5.0
    assert m._data[1, 0] == 0.0


@pytest.mark.parametrize("op", ["transpose", "invert", "normalize", "adjugate", "identity", "zero", "invert_safe"])
def test_matrix_wrapped_inplace_writes_owner_memory(op):
    view = np.array([[2, 1, 0], [0, 2, 0], [0, 0, 2]], dtype=np.float32)
    ref = Matrix(view.copy())
    getattr(ref, op)()
    calls = []
    m = Matrix._q_wrap(view, owner=_Owner(), on_write=lambda: calls.append(1))
    getattr(m, op)()
    assert np.shares_memory(m._data, view)
    assert np.allclose(view, np.asarray(ref), atol=1e-6)
    assert calls


def test_matrix_rotate_wrapped_writes_owner_memory():
    view = np.eye(4, dtype=np.float32)
    m = Matrix._q_wrap(view, owner=_Owner())
    m.rotate(Matrix.Rotation(math.pi / 2, 4, "Z"))
    assert np.allclose(view[:3, :3], np.asarray(FACTS["math.rot_z"]), atol=1e-6)



def test_quaternion_default_repr_fact():
    q = Quaternion()
    approx_seq(q, (1, 0, 0, 0))
    assert repr(q) == FACTS["math.repr_quat"]
    assert repr(Quaternion((1.0, 0.0, 0.0, 0.0))) == FACTS["math.repr_quat"]


def test_quaternion_signature_defaults():
    p = inspect.signature(Quaternion.__init__).parameters
    assert p["seq"].default == (1.0, 0.0, 0.0, 0.0)
    assert p["angle"].default is None


def test_quaternion_axis_angle_fact():
    approx_seq(Quaternion((0, 0, 1), math.pi / 2), FACTS["math.quat_axis_angle"])


def test_quaternion_exponential_map_ctor():
    q = Quaternion((0, 0, math.pi / 2))
    approx_seq(q, FACTS["math.quat_axis_angle"])


def test_quaternion_seq4():
    q = Quaternion((0.5, 0.1, 0.2, 0.3))
    assert (q.w, q.x, q.y, q.z) == (f32(0.5), f32(0.1), f32(0.2), f32(0.3))


def test_quaternion_components_rw():
    q = Quaternion()
    q.w, q.x, q.y, q.z = 4, 3, 2, 1
    approx_seq(q, (4, 3, 2, 1))
    assert q[0] == 4.0 and q[3] == 1.0


def test_quaternion_angle_rw_keeps_axis():
    q = Quaternion((0, 0, 1), 0.5)
    assert q.angle == pytest.approx(0.5, abs=TOL)
    q.angle = 1.2
    assert q.angle == pytest.approx(1.2, abs=TOL)
    approx_seq(q.axis, (0, 0, 1))


def test_quaternion_axis_rw_keeps_angle():
    q = Quaternion((0, 0, 1), 0.5)
    a = q.axis
    assert isinstance(a, Vector)
    a.x = 5.0
    approx_seq(q.axis, (0, 0, 1))
    q.axis = (1, 0, 0)
    approx_seq(q.axis, (1, 0, 0))
    assert q.angle == pytest.approx(0.5, abs=TOL)


def test_quaternion_magnitude():
    assert Quaternion((1, 2, 2, 4)).magnitude == pytest.approx(5.0)


def test_quaternion_conjugate():
    q = Quaternion((1, 2, 3, 4))
    approx_seq(q.conjugated(), (1, -2, -3, -4))
    q.conjugate()
    approx_seq(q, (1, -2, -3, -4))


def test_quaternion_invert():
    q = Quaternion((1, 2, 3, 4))
    r = q @ q.inverted()
    approx_seq(r, (1, 0, 0, 0))
    q.invert()
    approx_seq(q, np.array([1, -2, -3, -4]) / 30.0)


def test_quaternion_normalize():
    q = Quaternion((1, 2, 2, 4))
    approx_seq(q.normalized(), (0.2, 0.4, 0.4, 0.8))
    q.normalize()
    assert q.magnitude == pytest.approx(1.0, abs=TOL)


def test_quaternion_negate_identity():
    q = Quaternion((1, 2, 3, 4))
    q.negate()
    approx_seq(q, (-1, -2, -3, -4))
    q.identity()
    approx_seq(q, (1, 0, 0, 0))


def test_quaternion_dot():
    assert Quaternion((1, 2, 3, 4)).dot(Quaternion((2, 3, 4, 5))) == pytest.approx(40.0)


def test_quaternion_cross_is_hamilton():
    a = Quaternion((1, 2, 3, 4))
    b = Quaternion((2, 3, 4, 5))
    approx_seq(a.cross(b), a @ b)
    approx_seq(a @ b, (-36, 6, 12, 12))


def test_quaternion_rotation_difference():
    a = Quaternion((0, 0, 1), 0.3)
    b = Quaternion((1, 0, 0), 0.9)
    q = a.rotation_difference(b)
    assert isinstance(q, Quaternion)
    approx_quat(q @ a, list(b))


def test_quaternion_slerp():
    a = Quaternion()
    b = Quaternion((0, 0, 1), math.pi / 2)
    r = a.slerp(b, 0.5)
    approx_quat(r, list(Quaternion((0, 0, 1), math.pi / 4)))


def test_quaternion_rotate():
    q = Quaternion()
    q.rotate(Euler((0, 0, math.pi / 2)))
    approx_quat(q, FACTS["math.quat_axis_angle"])
    q = Quaternion()
    q.rotate(Matrix.Rotation(math.pi / 2, 3, "Z"))
    approx_quat(q, FACTS["math.quat_axis_angle"])


def test_quaternion_make_compatible():
    q = Quaternion((-1, 0, 0, 0))
    q.make_compatible(Quaternion((1, 0, 0, 0)))
    approx_seq(q, (1, 0, 0, 0))
    p = Quaternion((0.5, 0.5, 0.5, 0.5))
    p.make_compatible(Quaternion((1, 0, 0, 0)))
    approx_seq(p, (0.5, 0.5, 0.5, 0.5))


def test_quaternion_to_matrix():
    m = Quaternion((0, 0, 1), math.pi / 2).to_matrix()
    assert isinstance(m, Matrix) and m._data.shape == (3, 3)
    approx_mat(m, FACTS["math.rot_z"])


@pytest.mark.parametrize("order", ["XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"])
def test_quaternion_to_euler_roundtrip(order):
    e = Euler((0.1, 0.2, 0.3), order)
    back = e.to_quaternion().to_euler(order)
    assert back.order == order
    approx_seq(back, (0.1, 0.2, 0.3))


def test_quaternion_from_euler_fact():
    approx_quat(Euler((0.1, 0.2, 0.3), "XYZ").to_quaternion(), FACTS["math.quat_from_euler"])


def test_quaternion_to_axis_angle():
    axis, ang = Quaternion((0, 1, 0), 0.7).to_axis_angle()
    assert isinstance(axis, Vector) and isinstance(ang, float)
    approx_seq(axis, (0, 1, 0))
    assert ang == pytest.approx(0.7, abs=TOL)


def test_quaternion_to_exponential_map():
    e = Quaternion((0, 0, 1), 0.5).to_exponential_map()
    assert isinstance(e, Vector)
    approx_seq(e, (0, 0, 0.5))


def test_quaternion_to_swing_twist():
    q = Quaternion((0, 0, 1), 0.6)
    swing, twist = q.to_swing_twist("Z")
    assert isinstance(swing, Quaternion) and isinstance(twist, float)
    approx_quat(swing, (1, 0, 0, 0))
    assert twist == pytest.approx(0.6, abs=TOL)


def test_quaternion_matmul_vector():
    r = Quaternion((0, 0, 1), math.pi / 2) @ Vector((1, 0, 0))
    assert isinstance(r, Vector)
    approx_seq(r, (0, 1, 0))


def test_quaternion_mul_elementwise():
    r = Quaternion((1, 2, 3, 4)) * Quaternion((2, 3, 4, 5))
    assert isinstance(r, Quaternion)
    approx_seq(r, (2, 6, 12, 20))


def test_quaternion_mul_scalar():
    approx_seq(Quaternion((1, 2, 3, 4)) * 2, (2, 4, 6, 8))
    approx_seq(2 * Quaternion((1, 2, 3, 4)), (2, 4, 6, 8))


def test_quaternion_add_sub_neg():
    a = Quaternion((1, 2, 3, 4))
    b = Quaternion((1, 1, 1, 1))
    approx_seq(a + b, (2, 3, 4, 5))
    approx_seq(a - b, (0, 1, 2, 3))
    approx_seq(-a, (-1, -2, -3, -4))


def test_quaternion_index():
    q = Quaternion((1, 2, 3, 4))
    assert [q[i] for i in range(4)] == [1, 2, 3, 4]
    assert len(q) == 4
    with pytest.raises(IndexError):
        q[4]
    q[2] = 9
    assert q.y == 9.0


def test_quaternion_frozen():
    for fn in (lambda q: q.normalize(), lambda q: q.conjugate(), lambda q: setattr(q, "w", 2.0),
               lambda q: setattr(q, "angle", 0.2), lambda q: q.identity(), lambda q: q.rotate(Euler((0, 0, 1)))):
        q = Quaternion((0, 0, 1), 0.5).freeze()
        with pytest.raises(TypeError):
            fn(q)



def test_euler_orders_constant():
    from quartz.math import euler as euler_mod
    assert euler_mod.EULER_ORDERS == ("XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX")
    assert isinstance(euler_mod.EULER_ORDERS, tuple)


def test_euler_default():
    e = Euler()
    approx_seq(e, (0, 0, 0))
    assert e.order == "XYZ"
    p = inspect.signature(Euler.__init__).parameters
    assert p["angles"].default == (0.0, 0.0, 0.0) and p["order"].default == "XYZ"


def test_euler_invalid_order():
    with pytest.raises(ValueError):
        Euler((0, 0, 0), "XXY")
    e = Euler()
    with pytest.raises(ValueError):
        e.order = "ABC"


def test_euler_rw():
    e = Euler()
    e.x, e.y, e.z = 1, 2, 3
    e.order = "ZYX"
    approx_seq(e, (1, 2, 3))
    assert e.order == "ZYX"


def test_euler_to_matrix_xyz_fact():
    m = Euler((0.1, 0.2, 0.3), "XYZ").to_matrix()
    assert isinstance(m, Matrix) and m._data.shape == (3, 3)
    approx_mat(m, FACTS["math.euler_xyz"])


def test_euler_to_matrix_zyx_fact():
    approx_mat(Euler((0.1, 0.2, 0.3), "ZYX").to_matrix(), FACTS["math.euler_zyx"])


@pytest.mark.parametrize("order", ["XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"])
def test_euler_to_matrix_composition_rule(order):
    ang = {"X": 0.1, "Y": 0.2, "Z": 0.3}
    mats = {k: np.asarray(Matrix.Rotation(v, 3, k), dtype=np.float64) for k, v in ang.items()}
    exp = mats[order[2]] @ mats[order[1]] @ mats[order[0]]
    approx_mat(Euler((0.1, 0.2, 0.3), order).to_matrix(), exp)


def test_euler_to_quaternion_fact():
    q = Euler((0.1, 0.2, 0.3), "XYZ").to_quaternion()
    assert isinstance(q, Quaternion)
    approx_quat(q, FACTS["math.quat_from_euler"])


def test_euler_rotate():
    e = Euler((0, 0, 0.2))
    e.rotate(Euler((0, 0, 0.3)))
    approx_seq(e, (0, 0, 0.5))
    e = Euler((0, 0, 0.2))
    e.rotate(Quaternion((0, 0, 1), 0.3))
    approx_seq(e, (0, 0, 0.5))


def test_euler_rotate_axis_local():
    e = Euler((0.0, 0.0, math.pi / 2))
    base = np.asarray(e.to_matrix(), dtype=np.float64)
    e.rotate_axis("X", 0.4)
    exp = base @ np.asarray(Matrix.Rotation(0.4, 3, "X"), dtype=np.float64)
    approx_mat(e.to_matrix(), exp)


def test_euler_rotate_axis_same_axis():
    e = Euler((0.0, 0.0, 0.2))
    e.rotate_axis("Z", 0.3)
    approx_seq(e, (0, 0, 0.5))


def test_euler_make_compatible():
    e = Euler((2 * math.pi + 0.1, 0.0, -2 * math.pi + 0.2))
    e.make_compatible(Euler((0, 0, 0)))
    approx_seq(e, (0.1, 0.0, 0.2), tol=1e-4)


def test_euler_zero():
    e = Euler((1, 2, 3), "ZYX")
    e.zero()
    approx_seq(e, (0, 0, 0))
    assert e.order == "ZYX"


def test_euler_len_index():
    e = Euler((1, 2, 3))
    assert len(e) == 3
    assert e[0] == 1.0 and e[-1] == 3.0
    with pytest.raises(IndexError):
        e[3]
    e[1] = 5
    assert e.y == 5.0


def test_euler_no_arith_operators():
    with pytest.raises(TypeError):
        Euler() + Euler()
    with pytest.raises(TypeError):
        Euler() * 2
    with pytest.raises(TypeError):
        Euler() @ Euler()


def test_euler_eq():
    assert Euler((0.1, 0.2, 0.3)) == Euler((0.1, 0.2, 0.3))
    assert (Euler((0.1, 0.2, 0.3)) == (0.1, 0.2, 0.3)) is False


def test_euler_repr_fact():
    assert repr(Euler((0.1, 0.2, 0.3))) == FACTS["math.repr_euler"]


def test_euler_frozen():
    for fn in (lambda e: e.zero(), lambda e: setattr(e, "x", 1.0), lambda e: e.rotate_axis("X", 0.1),
               lambda e: e.make_compatible(Euler())):
        e = Euler((7.0, 0.1, 0.1)).freeze()
        with pytest.raises(TypeError):
            fn(e)



def test_color_default():
    c = Color()
    approx_seq(c, (0, 0, 0))
    assert inspect.signature(Color.__init__).parameters["rgb"].default == (0.0, 0.0, 0.0)


@pytest.mark.parametrize("seq", [(1, 2), (1, 2, 3, 4), ()])
def test_color_exactly_three(seq):
    with pytest.raises(ValueError):
        Color(seq)


def test_color_rgb_rw():
    c = Color()
    c.r, c.g, c.b = 0.1, 0.2, 0.3
    assert (c.r, c.g, c.b) == (f32(0.1), f32(0.2), f32(0.3))


def test_color_hsv_fact():
    approx_seq(Color((1.0, 0.5, 0.0)).hsv, FACTS["math.color_hsv"])
    assert isinstance(Color((1.0, 0.5, 0.0)).hsv, tuple)


def test_color_hsv_components():
    c = Color((1.0, 0.5, 0.0))
    assert c.h == pytest.approx(0.083333, abs=TOL)
    assert c.s == pytest.approx(1.0) and c.v == pytest.approx(1.0)


def test_color_hsv_setters():
    c = Color()
    c.hsv = (0.0, 1.0, 1.0)
    approx_seq(c, (1, 0, 0))
    c.v = 0.5
    approx_seq(c, (0.5, 0, 0))
    c.s = 0.0
    approx_seq(c, (0.5, 0.5, 0.5))
    c2 = Color((1, 0, 0))
    c2.h = 1.0 / 3.0
    approx_seq(c2, (0, 1, 0))


def test_color_scene_linear_to_srgb():
    c = Color((0.5, 0.0, 1.0))
    r = c.from_scene_linear_to_srgb()
    assert isinstance(r, Color)
    approx_seq(r, (0.735357, 0.0, 1.0), tol=1e-4)


def test_color_srgb_to_scene_linear():
    r = Color((0.735357, 0.0, 1.0)).from_srgb_to_scene_linear()
    assert isinstance(r, Color)
    approx_seq(r, (0.5, 0.0, 1.0), tol=1e-4)


def test_color_conversion_returns_new_color():
    c = Color((0.5, 0.5, 0.5))
    r = c.from_scene_linear_to_srgb()
    assert r is not c
    approx_seq(c, (0.5, 0.5, 0.5))


COLOR_NI = ["from_aces_to_scene_linear", "from_scene_linear_to_aces", "from_rec709_linear_to_scene_linear",
            "from_scene_linear_to_rec709_linear", "from_rec2020_linear_to_scene_linear",
            "from_scene_linear_to_rec2020_linear", "from_xyz_d65_to_scene_linear", "from_scene_linear_to_xyz_d65"]


@pytest.mark.parametrize("name", COLOR_NI)
def test_color_not_implemented(name):
    c = Color((0.1, 0.2, 0.3))
    assert hasattr(c, name)
    with pytest.raises(NotImplementedError) as ei:
        getattr(c, name)()
    assert f"Color.{name} is not implemented in Quartz" in str(ei.value)


def test_color_unknown_attr_attributeerror():
    with pytest.raises(AttributeError):
        Color().nonexistent_thing


def test_color_operators():
    a = Color((0.1, 0.2, 0.3))
    b = Color((0.1, 0.1, 0.1))
    assert isinstance(a + b, Color)
    approx_seq(a + b, (0.2, 0.3, 0.4))
    approx_seq(a - b, (0.0, 0.1, 0.2))
    approx_seq(a * 2, (0.2, 0.4, 0.6))
    approx_seq(2 * a, (0.2, 0.4, 0.6))
    assert a == Color((0.1, 0.2, 0.3))
    assert a[1] == f32(0.2)
    a[1] = 0.9
    assert a.g == f32(0.9)
    with pytest.raises(IndexError):
        a[3]


def test_color_repr():
    assert repr(Color((1.0, 0.5, 0.0))) == "Color((1.0, 0.5, 0.0))"


def test_color_frozen():
    for fn in (lambda c: setattr(c, "r", 0.5), lambda c: setattr(c, "hsv", (0, 0, 0)), lambda c: setattr(c, "h", 0.5)):
        c = Color((0.1, 0.2, 0.3)).freeze()
        with pytest.raises(TypeError):
            fn(c)



def test_axis_conversion_signature():
    p = inspect.signature(axis_conversion).parameters
    assert [p[k].default for k in ("from_forward", "from_up", "to_forward", "to_up")] == ["Y", "Z", "Y", "Z"]


def test_axis_conversion_default_identity():
    m = axis_conversion()
    assert isinstance(m, Matrix) and m._data.shape == (3, 3)
    approx_mat(m, np.eye(3))


@pytest.mark.parametrize("ff,fu,tf,tu", [("-Z", "Y", "Y", "Z"), ("X", "Z", "Y", "Z"), ("Y", "Z", "-Z", "Y"),
                                         ("-Y", "-Z", "X", "Y"), ("Z", "X", "-X", "-Y")])
def test_axis_conversion_maps_basis(ff, fu, tf, tu):
    m = np.asarray(axis_conversion(ff, fu, tf, tu), dtype=np.float64)
    assert np.allclose(m @ axis_vec(ff), axis_vec(tf), atol=1e-6)
    assert np.allclose(m @ axis_vec(fu), axis_vec(tu), atol=1e-6)
    assert np.linalg.det(m) == pytest.approx(1.0)


@pytest.mark.parametrize("args", [("Y", "Y", "Y", "Z"), ("Z", "-Z", "Y", "Z"), ("Y", "Z", "X", "-X")])
def test_axis_conversion_same_axis_error(args):
    with pytest.raises(ValueError) as ei:
        axis_conversion(*args)
    assert "Invalid axis arguments passed, can't use up/forward on the same axis" in str(ei.value)


def test_scalar_clamp():
    assert scalar.clamp(1.5) == 1.0
    assert scalar.clamp(-0.5) == 0.0
    assert scalar.clamp(0.3) == 0.3
    assert scalar.clamp(5, 1, 3) == 3
    p = inspect.signature(scalar.clamp).parameters
    assert p["min"].default == 0.0 and p["max"].default == 1.0


def test_scalar_lerp():
    assert scalar.lerp(2.0, 4.0, 0.25) == pytest.approx(2.5)
    assert list(inspect.signature(scalar.lerp).parameters) == ["from_value", "to_value", "factor"]


def test_scalar_smoothstep():
    assert scalar.smoothstep(0.0, 1.0, 0.5) == pytest.approx(0.5)
    assert scalar.smoothstep(0.0, 1.0, 0.25) == pytest.approx(3 * 0.0625 - 2 * 0.015625)
    assert scalar.smoothstep(0.0, 1.0, -1.0) == 0.0
    assert scalar.smoothstep(0.0, 1.0, 2.0) == 1.0
    assert scalar.smoothstep(2.0, 4.0, 3.0) == pytest.approx(0.5)
    assert list(inspect.signature(scalar.smoothstep).parameters) == ["from_value", "to_value", "value"]



def test_geometry_names_exist():
    for n in ("intersect_ray_tri", "intersect_line_line", "intersect_line_plane", "intersect_line_sphere",
              "intersect_point_line", "intersect_point_tri", "intersect_point_tri_2d", "closest_point_on_tri",
              "distance_point_to_plane", "normal", "area_tri", "volume_tetrahedron", "barycentric_transform",
              "tessellate_polygon", "interpolate_bezier", "convex_hull_2d", "box_fit_2d", "box_pack_2d",
              "delaunay_2d_cdt"):
        assert callable(getattr(geometry, n)), n


def test_geometry_defaults():
    assert inspect.signature(geometry.intersect_ray_tri).parameters["clip"].default is True
    assert inspect.signature(geometry.intersect_line_plane).parameters["no_flip"].default is False
    assert inspect.signature(geometry.intersect_line_sphere).parameters["clip"].default is True


TRI = ((0, 0, 0), (1, 0, 0), (0, 1, 0))


def test_intersect_ray_tri_hit():
    r = geometry.intersect_ray_tri(*TRI, (0, 0, -1), (0.2, 0.2, 1))
    assert isinstance(r, Vector)
    approx_seq(r, (0.2, 0.2, 0))


def test_intersect_ray_tri_miss_and_noclip():
    assert geometry.intersect_ray_tri(*TRI, (0, 0, -1), (2, 2, 1)) is None
    r = geometry.intersect_ray_tri(*TRI, (0, 0, -1), (2, 2, 1), False)
    approx_seq(r, (2, 2, 0))


def test_intersect_ray_tri_accepts_vector_and_array():
    r = geometry.intersect_ray_tri(Vector(TRI[0]), np.array(TRI[1]), list(TRI[2]), Vector((0, 0, -1)),
                                   np.array([0.2, 0.2, 1.0]))
    approx_seq(r, (0.2, 0.2, 0))


def test_intersect_line_line_skew():
    r = geometry.intersect_line_line((0, 0, 0), (1, 0, 0), (0, 1, 1), (0, 1, 2))
    assert isinstance(r, tuple) and len(r) == 2
    approx_seq(r[0], (0, 0, 0))
    approx_seq(r[1], (0, 1, 0))


def test_intersect_line_line_parallel_none():
    assert geometry.intersect_line_line((0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)) is None


def test_intersect_line_plane():
    r = geometry.intersect_line_plane((0, 0, 1), (0, 0, 2), (0, 0, 0), (0, 0, 1))
    assert isinstance(r, Vector)
    approx_seq(r, (0, 0, 0))
    assert geometry.intersect_line_plane((0, 0, 1), (1, 0, 1), (0, 0, 0), (0, 0, 1)) is None


def test_intersect_line_sphere():
    a, b = geometry.intersect_line_sphere((-2, 0, 0), (2, 0, 0), (0, 0, 0), 1.0)
    approx_seq(a, (-1, 0, 0))
    approx_seq(b, (1, 0, 0))
    assert geometry.intersect_line_sphere((-2, 5, 0), (2, 5, 0), (0, 0, 0), 1.0) == (None, None)


def test_intersect_line_sphere_clip():
    a, b = geometry.intersect_line_sphere((-0.5, 0, 0), (0.5, 0, 0), (0, 0, 0), 1.0)
    assert a is None and b is None
    a, b = geometry.intersect_line_sphere((-0.5, 0, 0), (0.5, 0, 0), (0, 0, 0), 1.0, False)
    approx_seq(a, (-1, 0, 0))
    approx_seq(b, (1, 0, 0))


def test_intersect_point_line():
    p, t = geometry.intersect_point_line((0.5, 1, 0), (0, 0, 0), (1, 0, 0))
    assert isinstance(p, Vector) and isinstance(t, float)
    approx_seq(p, (0.5, 0, 0))
    assert t == pytest.approx(0.5)
    p, t = geometry.intersect_point_line((3, 1, 0), (0, 0, 0), (1, 0, 0))
    approx_seq(p, (3, 0, 0))
    assert t == pytest.approx(3.0)


def test_intersect_point_tri_projection():
    r = geometry.intersect_point_tri((0.2, 0.2, 1.0), *TRI)
    assert isinstance(r, Vector)
    approx_seq(r, (0.2, 0.2, 0.0))


def test_intersect_point_tri_outside_none():
    assert geometry.intersect_point_tri((2, 2, 0), *TRI) is None


def test_intersect_point_tri_2d():
    r = geometry.intersect_point_tri_2d((0.2, 0.2), (0, 0), (1, 0), (0, 1))
    assert r == 1 and isinstance(r, int)
    assert geometry.intersect_point_tri_2d((2, 2), (0, 0), (1, 0), (0, 1)) == 0


def test_closest_point_on_tri_inside():
    approx_seq(geometry.closest_point_on_tri((0.2, 0.2, 3), *TRI), (0.2, 0.2, 0))


@pytest.mark.parametrize("pt,exp", [((2, 0.5, 0), (1, 0, 0)), ((3, -1, 0), (1, 0, 0)), ((-1, -1, 0), (0, 0, 0)),
                                    ((2, 2, 0), (0.5, 0.5, 0)), ((0.5, -1, 0), (0.5, 0, 0))])
def test_closest_point_on_tri_outside(pt, exp):
    r = geometry.closest_point_on_tri(pt, *TRI)
    assert isinstance(r, Vector)
    approx_seq(r, exp)


def test_distance_point_to_plane_signed():
    assert geometry.distance_point_to_plane((0, 0, 2), (0, 0, 0), (0, 0, 1)) == pytest.approx(2.0)
    assert geometry.distance_point_to_plane((0, 0, -2), (0, 0, 0), (0, 0, 1)) == pytest.approx(-2.0)


def test_normal_variadic_and_sequence():
    n1 = geometry.normal((0, 0, 0), (1, 0, 0), (0, 1, 0))
    n2 = geometry.normal([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)])
    n3 = geometry.normal([Vector((0, 0, 0)), Vector((1, 0, 0)), Vector((0, 1, 0))])
    for n in (n1, n2, n3):
        assert isinstance(n, Vector)
        approx_seq(n, (0, 0, 1))


def test_area_tri():
    assert geometry.area_tri((0, 0), (2, 0), (0, 2)) == pytest.approx(2.0)
    assert geometry.area_tri((0, 0, 0), (2, 0, 0), (0, 0, 2)) == pytest.approx(2.0)


def test_volume_tetrahedron():
    v = geometry.volume_tetrahedron((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))
    assert abs(v) == pytest.approx(1.0 / 6.0)


def test_barycentric_transform():
    r = geometry.barycentric_transform((1 / 3, 1 / 3, 0), *TRI, (0, 0, 0), (2, 0, 0), (0, 2, 0))
    assert isinstance(r, Vector)
    approx_seq(r, (2 / 3, 2 / 3, 0))


def _tri_area2d(pts, t):
    a, b, c = (np.asarray(pts[i][:2], dtype=np.float64) for i in t)
    return 0.5 * ((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))


def test_tessellate_polygon_square():
    sq = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    tris = geometry.tessellate_polygon([sq])
    assert isinstance(tris, list) and len(tris) == 2
    assert all(len(t) == 3 for t in tris)
    assert sum(abs(_tri_area2d(sq, t)) for t in tris) == pytest.approx(1.0)


def test_tessellate_polygon_concave():
    poly = [(0, 0, 0), (2, 0, 0), (2, 2, 0), (1, 0.5, 0), (0, 2, 0)]
    tris = geometry.tessellate_polygon([poly])
    assert len(tris) == 3
    areas = [_tri_area2d(poly, t) for t in tris]
    assert all(a > 0 for a in areas) or all(a < 0 for a in areas), areas
    assert sum(abs(a) for a in areas) == pytest.approx(2.5)


def test_tessellate_polygon_indices_concatenated():
    a = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    b = [(5, 0, 0), (6, 0, 0), (5, 1, 0)]
    tris = geometry.tessellate_polygon([a, b])
    flat = {i for t in tris for i in t}
    assert flat <= set(range(6))


def test_interpolate_bezier():
    pts = geometry.interpolate_bezier((0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0), 4)
    assert isinstance(pts, list) and len(pts) == 4
    assert all(isinstance(p, Vector) for p in pts)
    approx_seq(pts[0], (0, 0, 0))
    approx_seq(pts[-1], (3, 0, 0))
    approx_seq(pts[1], (1, 0, 0))


def test_convex_hull_2d_ccw():
    pts = [(0, 0), (1, 0), (0.5, 0.5), (1, 1), (0, 1)]
    hull = geometry.convex_hull_2d(pts)
    assert isinstance(hull, list) and sorted(hull) == [0, 1, 3, 4]
    poly = [pts[i] for i in hull]
    area = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
               for i in range(len(poly)))
    assert area > 0


def test_box_fit_2d():
    pts = [(0, 0), (1, 0), (1, 1), (0, 1)]
    a = geometry.box_fit_2d(pts)
    assert isinstance(a, float)
    rot = Matrix.Rotation(0.3, 2)
    pts_r = [tuple(rot @ Vector(p)) for p in [(0, 0), (4, 0), (4, 1), (0, 1)]]
    ang = geometry.box_fit_2d(pts_r)
    k = (ang - 0.3) / (math.pi / 2)
    k2 = (ang + 0.3) / (math.pi / 2)
    assert abs(k - round(k)) < 1e-4 or abs(k2 - round(k2)) < 1e-4


def test_box_pack_2d():
    boxes = [[0, 0, 1, 1], [0, 0, 2, 1], [0, 0, 1, 2]]
    w, h = geometry.box_pack_2d(boxes)
    assert isinstance(w, float) and isinstance(h, float)
    for i, a in enumerate(boxes):
        assert a[0] >= -1e-9 and a[1] >= -1e-9
        assert a[0] + a[2] <= w + 1e-9 and a[1] + a[3] <= h + 1e-9
        for b in boxes[i + 1:]:
            ox = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
            oy = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
            assert ox <= 1e-9 or oy <= 1e-9


def test_delaunay_not_implemented():
    with pytest.raises(NotImplementedError):
        geometry.delaunay_2d_cdt([(0, 0)], [], [], 0, 0.0)



def _kd(points):
    t = kdtree.KDTree(len(points))
    for i, p in enumerate(points):
        t.insert(p, i)
    t.balance()
    return t


def test_kdtree_insert_beyond_size():
    t = kdtree.KDTree(1)
    t.insert((0, 0, 0), 0)
    with pytest.raises(ValueError):
        t.insert((1, 0, 0), 1)


def test_kdtree_unbalanced_runtimeerror():
    t = kdtree.KDTree(2)
    t.insert((0, 0, 0), 0)
    for fn in (lambda: t.find((0, 0, 0)), lambda: t.find_n((0, 0, 0), 1), lambda: t.find_range((0, 0, 0), 1.0)):
        with pytest.raises(RuntimeError) as ei:
            fn()
        assert "KDTree must be balanced before use" in str(ei.value)


def test_kdtree_insert_after_balance_unbalances():
    t = kdtree.KDTree(2)
    t.insert((0, 0, 0), 0)
    t.balance()
    t.insert((1, 0, 0), 1)
    with pytest.raises(RuntimeError):
        t.find((0, 0, 0))


def test_kdtree_find():
    t = _kd([(0, 0, 0), (1, 0, 0), (5, 5, 5)])
    co, idx, dist = t.find((0.9, 0, 0))
    assert isinstance(co, Vector) and isinstance(idx, int) and isinstance(dist, float)
    approx_seq(co, (1, 0, 0))
    assert idx == 1 and dist == pytest.approx(0.1, abs=1e-6)


def test_kdtree_find_filter():
    t = _kd([(0, 0, 0), (1, 0, 0), (5, 5, 5)])
    co, idx, dist = t.find((0.9, 0, 0), filter=lambda i: i != 1)
    assert idx == 0


def test_kdtree_find_empty_none():
    t = kdtree.KDTree(0)
    t.balance()
    assert t.find((0, 0, 0)) == (None, None, None)


def test_kdtree_tie_lowest_index():
    t = kdtree.KDTree(2)
    t.insert((1, 0, 0), 7)
    t.insert((-1, 0, 0), 3)
    t.balance()
    assert t.find((0, 0, 0))[1] == 3


def test_kdtree_find_n_sorted():
    t = _kd([(3, 0, 0), (1, 0, 0), (2, 0, 0), (0, 0, 0)])
    res = t.find_n((0, 0, 0), 3)
    assert isinstance(res, list) and len(res) == 3
    assert [r[1] for r in res] == [3, 1, 2]
    assert all(isinstance(r[0], Vector) for r in res)
    assert [r[2] for r in res] == sorted(r[2] for r in res)


def test_kdtree_find_range():
    t = _kd([(3, 0, 0), (1, 0, 0), (2, 0, 0), (0, 0, 0)])
    res = t.find_range((0, 0, 0), 2.0)
    assert [r[1] for r in res] == [3, 1, 2]
    assert t.find_range((10, 0, 0), 1.0) == []



VERTS = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (5, 0, 0), (6, 0, 0), (5, 1, 0)]
POLYS = [(0, 1, 2, 3), (4, 5, 6)]


def test_bvh_signatures():
    B = bvhtree.BVHTree
    p = inspect.signature(B.FromPolygons).parameters
    assert p["all_triangles"].default is False and p["epsilon"].default == 0.0
    for name in ("ray_cast", "find_nearest", "find_nearest_range"):
        assert inspect.signature(getattr(B, name)).parameters["distance"].default == sys.float_info.max
    p = inspect.signature(B.FromObject).parameters
    assert p["deform"].kind == inspect.Parameter.KEYWORD_ONLY and p["deform"].default is True
    assert p["render"].default is False and p["cage"].default is False and p["epsilon"].default == 0.0
    assert callable(bvhtree.set_object_adapter) and callable(bvhtree.set_bmesh_adapter)


def test_bvh_ray_cast_hit():
    t = bvhtree.BVHTree.FromPolygons(VERTS, POLYS)
    loc, nor, idx, dist = t.ray_cast((5.2, 0.2, 1), (0, 0, -1))
    assert isinstance(loc, Vector) and isinstance(nor, Vector) and isinstance(idx, int) and isinstance(dist, float)
    approx_seq(loc, (5.2, 0.2, 0))
    assert abs(nor.z) == pytest.approx(1.0)
    assert dist == pytest.approx(1.0)


def test_bvh_ray_cast_index_is_polygon_index():
    t = bvhtree.BVHTree.FromPolygons(VERTS, POLYS)
    assert t.ray_cast((0.2, 0.8, 1), (0, 0, -1))[2] == 0
    assert t.ray_cast((0.8, 0.2, 1), (0, 0, -1))[2] == 0
    assert t.ray_cast((5.2, 0.2, 1), (0, 0, -1))[2] == 1


def test_bvh_ray_cast_miss():
    t = bvhtree.BVHTree.FromPolygons(VERTS, POLYS)
    assert t.ray_cast((10, 10, 1), (0, 0, -1)) == (None, None, None, None)
    assert t.ray_cast((0.5, 0.5, 1), (0, 0, -1), 0.5) == (None, None, None, None)


def test_bvh_find_nearest():
    t = bvhtree.BVHTree.FromPolygons(VERTS, POLYS)
    loc, nor, idx, dist = t.find_nearest((0.5, 0.5, 2))
    approx_seq(loc, (0.5, 0.5, 0))
    assert idx == 0 and dist == pytest.approx(2.0)
    assert t.find_nearest((0.5, 0.5, 2), 1.0) == (None, None, None, None)


def test_bvh_find_nearest_range():
    t = bvhtree.BVHTree.FromPolygons(VERTS, POLYS)
    res = t.find_nearest_range((0.5, 0.5, 1), 1.5)
    assert isinstance(res, list) and res
    assert {r[2] for r in res} == {0}
    for r in res:
        assert len(r) == 4 and r[3] <= 1.5 + 1e-9


def test_bvh_overlap():
    a = bvhtree.BVHTree.FromPolygons([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1, 2)])
    b = bvhtree.BVHTree.FromPolygons([(0.2, 0.2, -1), (0.2, 0.2, 1), (0.3, 0.6, 0)], [(0, 1, 2)])
    far = bvhtree.BVHTree.FromPolygons([(10, 0, 0), (11, 0, 0), (10, 1, 0)], [(0, 1, 2)])
    assert a.overlap(b) == [(0, 0)]
    assert a.overlap(far) == []


def test_bvh_overlap_aabb_only_is_not_overlap():
    a = bvhtree.BVHTree.FromPolygons([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1, 2)])
    b = bvhtree.BVHTree.FromPolygons([(0.9, 0.9, -0.5), (0.9, 0.9, 0.5), (0.95, 0.8, 0)], [(0, 1, 2)])
    assert a.overlap(b) == []


def test_bvh_from_triangles():
    pos = np.array(VERTS, dtype=np.float64)
    tris = np.array([(0, 1, 2), (0, 2, 3), (4, 5, 6)])
    t = bvhtree.BVHTree._q_from_triangles(pos, tris, np.array([0, 0, 1]))
    assert t.ray_cast((0.2, 0.8, 1), (0, 0, -1))[2] == 0
    assert t.ray_cast((5.2, 0.2, 1), (0, 0, -1))[2] == 1


def test_bvh_no_adapter():
    bvhtree.set_object_adapter(None)
    bvhtree.set_bmesh_adapter(None)
    with pytest.raises(NotImplementedError) as ei:
        bvhtree.BVHTree.FromObject(object(), None)
    assert "is not available (adapter not installed)" in str(ei.value)
    assert "BVHTree.FromObject" in str(ei.value)
    with pytest.raises(NotImplementedError) as ei:
        bvhtree.BVHTree.FromBMesh(object())
    assert "is not available (adapter not installed)" in str(ei.value)


def test_bvh_adapters_used():
    sentinel = bvhtree.BVHTree.FromPolygons(VERTS, POLYS)
    seen = []

    def obj_adapter(*a, **k):
        seen.append(("o", a, k))
        return sentinel

    def bm_adapter(*a, **k):
        seen.append(("b", a, k))
        return sentinel

    try:
        bvhtree.set_object_adapter(obj_adapter)
        bvhtree.set_bmesh_adapter(bm_adapter)
        assert bvhtree.BVHTree.FromObject("ob", "dg") is sentinel
        assert bvhtree.BVHTree.FromBMesh("bm") is sentinel
        assert [s[0] for s in seen] == ["o", "b"]
    finally:
        bvhtree.set_object_adapter(None)
        bvhtree.set_bmesh_adapter(None)



def test_noise_random_range():
    noise.seed_set(1)
    vals = [noise.random() for _ in range(200)]
    assert all(0.0 <= v < 1.0 for v in vals)
    assert all(type(v) is float for v in vals)


def test_noise_seed_deterministic_random():
    noise.seed_set(42)
    a = [noise.random() for _ in range(5)]
    noise.seed_set(42)
    b = [noise.random() for _ in range(5)]
    assert a == b


def test_noise_seed_deterministic_random_vector():
    noise.seed_set(7)
    a = noise.random_vector()
    noise.seed_set(7)
    b = noise.random_vector()
    assert a == b


def test_noise_seed_deterministic_random_unit_vector():
    noise.seed_set(7)
    a = noise.random_unit_vector()
    noise.seed_set(7)
    b = noise.random_unit_vector()
    assert a == b


def test_noise_unseeded_deterministic_across_processes():
    code = ("import sys; sys.path.insert(0, r'%s'); from quartz.math import noise; "
            "print(noise.random(), list(noise.random_unit_vector()))" % ROOT)
    outs = [subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60).stdout
            for _ in range(2)]
    assert outs[0] and outs[0] == outs[1]


def test_noise_random_unit_vector():
    noise.seed_set(3)
    v = noise.random_unit_vector()
    assert isinstance(v, Vector) and len(v) == 3
    assert v.length == pytest.approx(1.0, abs=1e-5)
    assert len(noise.random_unit_vector(4)) == 4
    assert inspect.signature(noise.random_unit_vector).parameters["size"].default == 3


def test_noise_random_vector():
    noise.seed_set(3)
    for _ in range(50):
        v = noise.random_vector()
        assert isinstance(v, Vector) and len(v) == 3
        assert all(-1.0 <= c < 1.0 for c in v)
    assert len(noise.random_vector(2)) == 2
    assert inspect.signature(noise.random_vector).parameters["size"].default == 3


NOISE_NI = ["noise", "noise_vector", "turbulence", "turbulence_vector", "fractal", "multi_fractal",
            "hetero_terrain", "hybrid_multi_fractal", "ridged_multi_fractal", "variable_lacunarity", "voronoi",
            "cell", "cell_vector"]


@pytest.mark.parametrize("name", NOISE_NI)
def test_noise_not_implemented(name):
    fn = getattr(noise, name)
    with pytest.raises(NotImplementedError) as ei:
        fn((0.0, 0.0, 0.0))
    assert f"mathutils.noise.{name} is not implemented in Quartz" in str(ei.value)


def test_poly_3d_calc_triangle():
    w = interpolate.poly_3d_calc([(0, 0, 0), (1, 0, 0), (0, 1, 0)], (0.2, 0.3, 0))
    assert isinstance(w, list) and len(w) == 3
    approx_seq(w, (0.5, 0.2, 0.3))


def test_poly_3d_calc_vertex_and_sum():
    w = interpolate.poly_3d_calc([Vector((0, 0, 0)), Vector((1, 0, 0)), Vector((0, 1, 0))], (1, 0, 0))
    approx_seq(w, (0, 1, 0))
    q = interpolate.poly_3d_calc([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], (0.3, 0.6, 0))
    assert len(q) == 4 and sum(q) == pytest.approx(1.0)
