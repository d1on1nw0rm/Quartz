from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .colorutil import as_rgb, hsv_to_rgb, luminance, rgb_to_hsv, srgb_to_linear
from .noise import NOISE_TYPES, fractal
from .params import Param, coerce, defaults_of
from .ramp import DEFAULT_RAMP, INTERPOLATIONS, evaluate_ramp
from .textures import (EXTENSIONS, GRADIENT_TYPES, MISSING_COLOR, VORONOI_FEATURES, VORONOI_METRICS,
                       brick_pattern, checker_mask, gradient_value, load_image, sample_image,
                       voronoi_pattern)

__all__ = [
    "sanitize_graph",
    "SOCKET_TYPES",
    "SOCKET_COLORS",
    "CATEGORIES",
    "SocketSpec",
    "NodeType",
    "NODE_TYPES",
    "node_type",
    "node_types_by_category",
    "BLEND_MODES",
    "MATH_OPS",
    "SHADER_KEYS",
    "EMISSION_LINEAR",
    "default_shader",
    "new_graph",
    "add_node",
    "find_node",
    "remove_node",
    "duplicate_node",
    "move_node",
    "connect",
    "can_connect",
    "disconnect",
    "link_into",
    "links_from",
    "set_node_input",
    "set_node_prop",
    "output_node",
    "prune_graph",
    "upstream",
    "GraphEvaluator",
    "evaluate_graph",
    "convert_value",
    "arrange_graph",
    "node_height",
    "NODE_WIDTH",
    "NODE_HEADER",
    "NODE_ROW",
]

SOCKET_TYPES = ("float", "color", "vector", "shader")
SOCKET_COLORS = {"float": "#a3abbb", "color": "#ffb53d", "vector": "#9d8cff", "shader": "#5ee6c8"}
CATEGORIES = ("Output", "Shader", "Texture", "Color", "Converter", "Vector", "Input")


@dataclass(frozen=True)
class SocketSpec:
    name: str
    label: str
    type: str
    default: object = None
    minimum: float | None = None
    maximum: float | None = None

    def __post_init__(self) -> None:
        if self.type not in SOCKET_TYPES:
            raise ValueError(f"socket {self.name!r}: unknown type {self.type!r}")

    def editable(self) -> bool:
        return self.type != "shader" and not isinstance(self.default, str) and self.default is not None


@dataclass
class NodeType:
    id: str
    label: str
    category: str
    inputs: tuple = ()
    outputs: tuple = ()
    props: tuple = ()
    fn: Callable | None = None
    removable: bool = True
    description: str = field(default="")

    def input(self, name: str) -> SocketSpec | None:
        for s in self.inputs:
            if s.name == name:
                return s
        return None

    def output(self, name: str) -> SocketSpec | None:
        for s in self.outputs:
            if s.name == name:
                return s
        return None

    def prop(self, key: str) -> Param | None:
        for p in self.props:
            if p.key == key:
                return p
        return None


NODE_TYPES: dict[str, NodeType] = {}


def _register(nt: NodeType) -> NodeType:
    if nt.category not in CATEGORIES:
        raise ValueError(f"node {nt.id!r}: unknown category {nt.category!r}")
    NODE_TYPES[nt.id] = nt
    return nt


def node_type(type_id: str) -> NodeType:
    if type_id not in NODE_TYPES:
        raise KeyError(f"unknown node type {type_id!r}")
    return NODE_TYPES[type_id]


def node_types_by_category() -> dict[str, list[NodeType]]:
    out: dict[str, list[NodeType]] = {c: [] for c in CATEGORIES}
    for nt in NODE_TYPES.values():
        out[nt.category].append(nt)
    return {c: v for c, v in out.items() if v}


SHADER_KEYS = ("base_color", "metallic", "roughness", "specular", "ior", "normal", "emission", "alpha",
               "transmission", "clearcoat", "clearcoat_roughness", "sheen", "sheen_tint",
               "sheen_roughness")
EMISSION_LINEAR = "_emission_linear"


def default_shader(ctx: dict) -> dict:
    n = ctx["n"]
    return {
        "base_color": np.full((n, 3), 0.8),
        "metallic": np.zeros(n),
        "roughness": np.full(n, 0.5),
        "specular": np.full(n, 0.5),
        "ior": np.full(n, 1.45),
        "normal": np.array(ctx["normal"], float, copy=True),
        "emission": np.zeros((n, 3)),
        "alpha": np.ones(n),
        "transmission": np.zeros(n),
        "clearcoat": np.zeros(n),
        "clearcoat_roughness": np.full(n, 0.03),
        "sheen": np.zeros(n),
        "sheen_tint": np.ones((n, 3)),
        "sheen_roughness": np.full(n, 0.5),
        EMISSION_LINEAR: np.zeros((n, 3)),
    }


def convert_value(value, src: str, dst: str, n: int):
    if src == dst:
        return value
    if dst == "shader" or src == "shader":
        return None
    if src == "float":
        return np.repeat(np.asarray(value, float).reshape(n, 1), 3, axis=1)
    if dst == "float":
        if src == "color":
            return luminance(value)
        return np.mean(np.asarray(value, float), axis=1)
    return np.asarray(value, float)


def _broadcast(value, stype: str, n: int):
    if stype == "float":
        return np.full(n, float(value))
    return np.broadcast_to(as_rgb(value), (n, 3)).copy()


def _normalize(v: np.ndarray) -> np.ndarray:
    length = np.linalg.norm(v, axis=1, keepdims=True)
    return v / np.where(length > 1e-12, length, 1.0)


class NodeCall:

    def __init__(self, evaluator: "GraphEvaluator", node: dict, nt: NodeType, ctx: dict) -> None:
        self.evaluator = evaluator
        self.node = node
        self.type = nt
        self.ctx = ctx
        self.n = ctx["n"]
        props = defaults_of(nt.props)
        props.update(node.get("props") or {})
        self.props = props

    def get(self, name: str, ctx: dict | None = None):
        return self.evaluator.input(self.node, self.type, name, ctx or self.ctx)

    def linked(self, name: str) -> bool:
        return self.evaluator.link(self.node["id"], name) is not None


def _vec_uv(call: NodeCall) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    vec = call.get("vector")
    return vec[:, 0], vec[:, 1], vec


def _fn_output(call: NodeCall) -> dict:
    return {}


def _fn_principled(call: NodeCall) -> dict:
    g = call.get
    normal = _normalize(g("normal")) if call.linked("normal") else np.array(call.ctx["normal"], float, copy=True)
    emission = g("emission")
    strength = g("emission_strength")[:, None]
    return {"bsdf": {
        "base_color": g("base_color"),
        "metallic": np.clip(g("metallic"), 0.0, 1.0),
        "roughness": np.clip(g("roughness"), 0.0, 1.0),
        "specular": np.clip(g("specular"), 0.0, 1.0),
        "ior": np.maximum(g("ior"), 1.0),
        "normal": normal,
        "emission": emission * strength,
        EMISSION_LINEAR: srgb_to_linear(np.maximum(emission, 0.0)) * strength,
        "alpha": np.clip(g("alpha"), 0.0, 1.0),
        "transmission": np.clip(g("transmission"), 0.0, 1.0),
        "clearcoat": np.clip(g("clearcoat"), 0.0, 1.0),
        "clearcoat_roughness": np.clip(g("clearcoat_roughness"), 0.0, 1.0),
        "sheen": np.clip(g("sheen"), 0.0, 1.0),
        "sheen_tint": g("sheen_tint"),
        "sheen_roughness": np.clip(g("sheen_roughness"), 0.0, 1.0),
    }}


def _shader_value(shader: dict, key: str):
    if key in shader:
        return shader[key]
    if key == EMISSION_LINEAR:
        return srgb_to_linear(np.maximum(np.asarray(shader["emission"], float), 0.0))
    raise KeyError(key)


def _fn_mix_shader(call: NodeCall) -> dict:
    fac = np.clip(call.get("fac"), 0.0, 1.0)
    a = call.get("shader1") or default_shader(call.ctx)
    b = call.get("shader2") or default_shader(call.ctx)
    out = {}
    for key in SHADER_KEYS + (EMISSION_LINEAR,):
        va, vb = np.asarray(_shader_value(a, key), float), np.asarray(_shader_value(b, key), float)
        f = fac[:, None] if va.ndim == 2 else fac
        out[key] = va * (1.0 - f) + vb * f
    out["normal"] = _normalize(out["normal"])
    return {"shader": out}


def _fn_image(call: NodeCall) -> dict:
    u, v, _ = _vec_uv(call)
    img = load_image(call.props["path"])
    if img is None:
        return {"color": np.broadcast_to(np.array(MISSING_COLOR), (call.n, 3)).copy(), "alpha": np.ones(call.n)}
    rgba = sample_image(img, u, v, call.props["interpolation"], call.props["extension"])
    return {"color": rgba[:, :3], "alpha": rgba[:, 3]}


def _fn_checker(call: NodeCall) -> dict:
    _, _, vec = _vec_uv(call)
    scale = call.get("scale")
    q = np.floor(vec * scale[:, None] + 1e-9).astype(np.int64)
    m = ((q[:, 0] + q[:, 1] + q[:, 2]) & 1).astype(float)
    c1, c2 = call.get("color1"), call.get("color2")
    return {"color": c1 * (1.0 - m)[:, None] + c2 * m[:, None], "fac": m}


def _fn_noise(call: NodeCall) -> dict:
    _, _, vec = _vec_uv(call)
    p = vec * call.get("scale")[:, None]
    detail = float(np.mean(call.get("detail")))
    rough = float(np.mean(call.get("roughness")))
    dist = float(np.mean(call.get("distortion")))
    lac = float(call.props["lacunarity"])
    kind = call.props["noise_type"]
    seed = int(call.props["seed"])
    fac = fractal(p, kind, detail, rough, lac, dist, seed)
    g = fractal(p + 19.31, kind, detail, rough, lac, dist, seed + 1)
    b = fractal(p + 47.77, kind, detail, rough, lac, dist, seed + 2)
    return {"fac": fac, "color": np.stack([fac, g, b], axis=1)}


def _fn_gradient(call: NodeCall) -> dict:
    u, v, _ = _vec_uv(call)
    t = gradient_value(u, v, call.props["gradient_type"], bool(call.props["repeat"]))
    return {"fac": t, "color": np.repeat(t[:, None], 3, axis=1)}


def _fn_voronoi(call: NodeCall) -> dict:
    _, _, vec = _vec_uv(call)
    p = vec * call.get("scale")[:, None]
    dims = 2 if bool(np.all(vec[:, 2] == 0.0)) else 3
    res = voronoi_pattern(p, dims, call.props["feature"], call.props["metric"],
                          float(np.mean(call.get("randomness"))), int(call.props["seed"]))
    return {"distance": res["distance"], "color": res["color"], "position": res["position"]}


def _fn_brick(call: NodeCall) -> dict:
    u, v, _ = _vec_uv(call)
    scale = float(np.mean(call.get("scale")))
    rows = scale * float(call.props["rows_ratio"])
    mask, rnd = brick_pattern(u, v, scale, rows, float(np.mean(call.get("mortar_size"))),
                              float(call.props["mortar_smooth"]), float(call.props["row_offset"]),
                              int(call.props["seed"]))
    bias = np.clip(rnd * call.get("bias") * 2.0, 0.0, 1.0)
    brick = call.get("color1") * (1.0 - bias)[:, None] + call.get("color2") * bias[:, None]
    col = brick * (1.0 - mask)[:, None] + call.get("mortar") * mask[:, None]
    return {"color": col, "fac": mask}


BLEND_MODES = ("mix", "add", "multiply", "subtract", "screen", "overlay", "darken", "lighten",
               "difference", "divide")


def blend(mode: str, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    if mode == "add":
        return a + b
    if mode == "multiply":
        return a * b
    if mode == "subtract":
        return a - b
    if mode == "screen":
        return 1.0 - (1.0 - a) * (1.0 - b)
    if mode == "overlay":
        return np.where(a < 0.5, 2.0 * a * b, 1.0 - 2.0 * (1.0 - a) * (1.0 - b))
    if mode == "darken":
        return np.minimum(a, b)
    if mode == "lighten":
        return np.maximum(a, b)
    if mode == "difference":
        return np.abs(a - b)
    if mode == "divide":
        return np.where(np.abs(b) > 1e-12, a / np.where(np.abs(b) > 1e-12, b, 1.0), 0.0)
    return b


def _fn_mix_color(call: NodeCall) -> dict:
    fac = np.clip(call.get("fac"), 0.0, 1.0)[:, None]
    a, b = call.get("color1"), call.get("color2")
    out = a * (1.0 - fac) + blend(call.props["blend"], a, b) * fac
    if call.props["clamp"]:
        out = np.clip(out, 0.0, 1.0)
    return {"color": out}


MATH_OPS = ("add", "subtract", "multiply", "divide", "power", "minimum", "maximum", "modulo",
            "absolute", "less_than", "greater_than")


def math_op(op: str, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    if op == "add":
        return a + b
    if op == "subtract":
        return a - b
    if op == "multiply":
        return a * b
    if op == "divide":
        return np.where(np.abs(b) > 1e-12, a / np.where(np.abs(b) > 1e-12, b, 1.0), 0.0)
    if op == "power":
        with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
            r = np.power(a, b)
        return np.where(np.isfinite(r), r, 0.0)
    if op == "minimum":
        return np.minimum(a, b)
    if op == "maximum":
        return np.maximum(a, b)
    if op == "modulo":
        return np.where(np.abs(b) > 1e-12, np.fmod(a, np.where(np.abs(b) > 1e-12, b, 1.0)), 0.0)
    if op == "absolute":
        return np.abs(a)
    if op == "less_than":
        return (a < b).astype(float)
    if op == "greater_than":
        return (a > b).astype(float)
    raise ValueError(f"unknown math op {op!r}")


def _fn_math(call: NodeCall) -> dict:
    out = math_op(call.props["op"], call.get("a"), call.get("b"))
    if call.props["clamp"]:
        out = np.clip(out, 0.0, 1.0)
    return {"value": out}


def _fn_ramp(call: NodeCall) -> dict:
    rgba = evaluate_ramp(call.props["stops"], call.get("fac"), call.props["interpolation"])
    return {"color": rgba[:, :3], "alpha": rgba[:, 3]}


def dielectric_fresnel(cos_i: np.ndarray, ior: np.ndarray) -> np.ndarray:
    c = np.abs(cos_i)
    g2 = ior * ior - 1.0 + c * c
    tir = g2 < 0.0
    g = np.sqrt(np.maximum(g2, 0.0))
    a = (g - c) / np.where(g + c > 1e-12, g + c, 1e-12)
    den = c * (g - c) + 1.0
    b = (c * (g + c) - 1.0) / np.where(np.abs(den) > 1e-12, den, 1e-12)
    f = 0.5 * a * a * (1.0 + b * b)
    return np.where(tir, 1.0, np.clip(f, 0.0, 1.0))


def _fn_fresnel(call: NodeCall) -> dict:
    nrm = _normalize(call.get("normal"))
    view = _normalize(np.asarray(call.ctx["view"], float))
    cos_i = np.sum(nrm * view, axis=1)
    return {"fac": dielectric_fresnel(cos_i, np.maximum(call.get("ior"), 1.0))}


def _frame(ctx: dict, normal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    t = np.asarray(ctx["tangent"], float)
    t = _normalize(t - normal * np.sum(t * normal, axis=1, keepdims=True))
    b = np.cross(normal, t)
    return t, b


def apply_normal_map(ctx: dict, normal: np.ndarray, color: np.ndarray, strength, flip_green: bool,
                     space: str = "tangent") -> np.ndarray:
    m = np.array(color, float, copy=True) * 2.0 - 1.0
    if flip_green:
        m[:, 1] = -m[:, 1]
    s = np.broadcast_to(np.asarray(strength, float).reshape(-1), (len(m),))
    if space == "object":
        target = _normalize(m)
    else:
        t, b = _frame(ctx, normal)
        target = _normalize(t * m[:, 0:1] + b * m[:, 1:2] + normal * np.maximum(m[:, 2:3], 1e-4))
    return _normalize(normal + (target - normal) * s[:, None])


def shifted_context(ctx: dict, du: float, dv: float) -> dict:
    out = dict(ctx)
    out["u"] = ctx["u"] + du
    out["v"] = ctx["v"] + dv
    t = np.asarray(ctx["tangent"], float)
    b = np.asarray(ctx["bitangent"], float)
    out["pos"] = np.asarray(ctx["pos"], float) + t * du + b * dv
    if "opos" in ctx:
        out["opos"] = np.asarray(ctx["opos"], float) + t * du + b * dv
    out["_shift"] = (ctx.get("_shift", (0.0, 0.0))[0] + du, ctx.get("_shift", (0.0, 0.0))[1] + dv)
    return out


BUMP_EPS = 1.0 / 1024.0


def bump_normal(ctx: dict, normal: np.ndarray, h0: np.ndarray, hu: np.ndarray, hv: np.ndarray,
                strength, distance, invert: bool = False) -> np.ndarray:
    gu = (hu - h0) / BUMP_EPS
    gv = (hv - h0) / BUMP_EPS
    k = np.asarray(strength, float) * np.asarray(distance, float)
    if invert:
        k = -k
    t, b = _frame(ctx, normal)
    k = np.broadcast_to(k, gu.shape)
    return _normalize(normal - (t * (gu * k)[:, None] + b * (gv * k)[:, None]))


def _fn_normal_map(call: NodeCall) -> dict:
    base = np.array(call.ctx["normal"], float)
    out = apply_normal_map(call.ctx, base, call.get("color"), call.get("strength"),
                           bool(call.props["flip_green"]), call.props["space"])
    return {"normal": out}


def _fn_bump(call: NodeCall) -> dict:
    base = _normalize(call.get("normal"))
    if not call.linked("height"):
        return {"normal": base}
    h0 = call.get("height")
    hu = call.get("height", shifted_context(call.ctx, BUMP_EPS, 0.0))
    hv = call.get("height", shifted_context(call.ctx, 0.0, BUMP_EPS))
    return {"normal": bump_normal(call.ctx, base, h0, hu, hv, call.get("strength"), call.get("distance"),
                                  bool(call.props["invert"]))}


def _fn_invert(call: NodeCall) -> dict:
    fac = np.clip(call.get("fac"), 0.0, 1.0)[:, None]
    c = call.get("color")
    return {"color": c * (1.0 - fac) + (1.0 - c) * fac}


def _fn_hsv(call: NodeCall) -> dict:
    c = call.get("color")
    hsv = rgb_to_hsv(np.clip(c, 0.0, None))
    hsv[:, 0] = (hsv[:, 0] + call.get("hue") - 0.5) % 1.0
    hsv[:, 1] = np.clip(hsv[:, 1] * call.get("saturation"), 0.0, 1.0)
    hsv[:, 2] = np.maximum(hsv[:, 2] * call.get("value"), 0.0)
    fac = np.clip(call.get("fac"), 0.0, 1.0)[:, None]
    return {"color": c * (1.0 - fac) + hsv_to_rgb(hsv) * fac}


def _fn_value(call: NodeCall) -> dict:
    return {"value": np.full(call.n, float(call.props["value"]))}


def _fn_rgb(call: NodeCall) -> dict:
    return {"color": np.broadcast_to(as_rgb(call.props["color"]), (call.n, 3)).copy()}


def _fn_texcoord(call: NodeCall) -> dict:
    ctx = call.ctx
    uv = np.stack([ctx["u"], ctx["v"], np.zeros(call.n)], axis=1)
    return {"uv": uv, "object": np.array(ctx.get("opos", ctx["pos"]), float), "normal": np.array(ctx["normal"], float),
            "tangent": np.array(ctx["tangent"], float)}


def _fn_separate(call: NodeCall) -> dict:
    c = call.get("color")
    return {"r": c[:, 0], "g": c[:, 1], "b": c[:, 2]}


def _fn_combine(call: NodeCall) -> dict:
    return {"color": np.stack([call.get("r"), call.get("g"), call.get("b")], axis=1)}


def _fn_mapping(call: NodeCall) -> dict:
    vec = call.get("vector")
    scale = call.get("scale")
    loc = call.get("location")
    ang = np.radians(float(call.props["rotation"]))
    c, s = np.cos(ang), np.sin(ang)
    x = vec[:, 0] * scale[:, 0]
    y = vec[:, 1] * scale[:, 1]
    rx = x * c - y * s
    ry = x * s + y * c
    return {"vector": np.stack([rx, ry, vec[:, 2] * scale[:, 2]], axis=1) + loc}


_VEC = SocketSpec("vector", "Vector", "vector", "@uv")
_F = "float"
_C = "color"

_register(NodeType("output", "Material Output", "Output",
                   inputs=(SocketSpec("surface", "Surface", "shader"),
                           SocketSpec("displacement", "Displacement", _F, 0.0)),
                   fn=_fn_output, removable=False))
_register(NodeType("principled", "Principled BSDF", "Shader",
                   inputs=(SocketSpec("base_color", "Base Color", _C, [0.8, 0.8, 0.8]),
                           SocketSpec("metallic", "Metallic", _F, 0.0, 0.0, 1.0),
                           SocketSpec("roughness", "Roughness", _F, 0.5, 0.0, 1.0),
                           SocketSpec("specular", "Specular", _F, 0.5, 0.0, 1.0),
                           SocketSpec("ior", "IOR", _F, 1.45, 1.0, 4.0),
                           SocketSpec("normal", "Normal", "vector", "@normal"),
                           SocketSpec("emission", "Emission", _C, [0.0, 0.0, 0.0]),
                           SocketSpec("emission_strength", "Emission Strength", _F, 1.0, 0.0, 1000.0),
                           SocketSpec("alpha", "Alpha", _F, 1.0, 0.0, 1.0),
                           SocketSpec("transmission", "Transmission", _F, 0.0, 0.0, 1.0),
                           SocketSpec("clearcoat", "Clearcoat", _F, 0.0, 0.0, 1.0),
                           SocketSpec("clearcoat_roughness", "Coat Roughness", _F, 0.03, 0.0, 1.0),
                           SocketSpec("sheen", "Sheen", _F, 0.0, 0.0, 1.0),
                           SocketSpec("sheen_tint", "Sheen Tint", _C, [1.0, 1.0, 1.0]),
                           SocketSpec("sheen_roughness", "Sheen Roughness", _F, 0.5, 0.0, 1.0)),
                   outputs=(SocketSpec("bsdf", "BSDF", "shader"),), fn=_fn_principled))
_register(NodeType("mix_shader", "Mix Shader", "Shader",
                   inputs=(SocketSpec("fac", "Factor", _F, 0.5, 0.0, 1.0),
                           SocketSpec("shader1", "Shader", "shader"),
                           SocketSpec("shader2", "Shader", "shader")),
                   outputs=(SocketSpec("shader", "Shader", "shader"),), fn=_fn_mix_shader))
_register(NodeType("image_texture", "Image Texture", "Texture",
                   inputs=(_VEC,),
                   outputs=(SocketSpec("color", "Color", _C), SocketSpec("alpha", "Alpha", _F)),
                   props=(Param("path", "File", "path", ""),
                          Param("interpolation", "Interpolation", "enum", "linear", options=("linear", "closest")),
                          Param("extension", "Extension", "enum", "repeat", options=EXTENSIONS)),
                   fn=_fn_image))
_register(NodeType("checker", "Checker Texture", "Texture",
                   inputs=(_VEC, SocketSpec("color1", "Color 1", _C, [0.8, 0.8, 0.8]),
                           SocketSpec("color2", "Color 2", _C, [0.2, 0.2, 0.2]),
                           SocketSpec("scale", "Scale", _F, 5.0, 0.0, 1000.0)),
                   outputs=(SocketSpec("color", "Color", _C), SocketSpec("fac", "Factor", _F)),
                   fn=_fn_checker))
_register(NodeType("noise", "Noise Texture", "Texture",
                   inputs=(_VEC, SocketSpec("scale", "Scale", _F, 5.0, 0.0, 1000.0),
                           SocketSpec("detail", "Detail", _F, 2.0, 0.0, 12.0),
                           SocketSpec("roughness", "Roughness", _F, 0.5, 0.0, 1.0),
                           SocketSpec("distortion", "Distortion", _F, 0.0, 0.0, 10.0)),
                   outputs=(SocketSpec("fac", "Factor", _F), SocketSpec("color", "Color", _C)),
                   props=(Param("noise_type", "Type", "enum", "fbm", options=NOISE_TYPES),
                          Param("lacunarity", "Lacunarity", "float", 2.0, 1.0, 6.0, step=0.1),
                          Param("seed", "Seed", "int", 0, 0, 9999, step=1)),
                   fn=_fn_noise))
_register(NodeType("gradient", "Gradient Texture", "Texture",
                   inputs=(_VEC,),
                   outputs=(SocketSpec("color", "Color", _C), SocketSpec("fac", "Factor", _F)),
                   props=(Param("gradient_type", "Type", "enum", "linear", options=GRADIENT_TYPES),
                          Param("repeat", "Repeat", "bool", False)),
                   fn=_fn_gradient))
_register(NodeType("voronoi", "Voronoi Texture", "Texture",
                   inputs=(_VEC, SocketSpec("scale", "Scale", _F, 5.0, 0.0, 1000.0),
                           SocketSpec("randomness", "Randomness", _F, 1.0, 0.0, 1.0)),
                   outputs=(SocketSpec("distance", "Distance", _F), SocketSpec("color", "Color", _C),
                            SocketSpec("position", "Position", "vector")),
                   props=(Param("feature", "Feature", "enum", "f1", options=VORONOI_FEATURES,
                                option_labels=("F1", "F2", "F2 - F1")),
                          Param("metric", "Metric", "enum", "euclidean", options=VORONOI_METRICS),
                          Param("seed", "Seed", "int", 0, 0, 9999, step=1)),
                   fn=_fn_voronoi))
_register(NodeType("brick", "Brick Texture", "Texture",
                   inputs=(_VEC, SocketSpec("color1", "Color 1", _C, [0.62, 0.24, 0.16]),
                           SocketSpec("color2", "Color 2", _C, [0.48, 0.18, 0.12]),
                           SocketSpec("mortar", "Mortar", _C, [0.78, 0.76, 0.72]),
                           SocketSpec("scale", "Scale", _F, 4.0, 0.1, 256.0),
                           SocketSpec("mortar_size", "Mortar Size", _F, 0.08, 0.0, 0.5),
                           SocketSpec("bias", "Bias", _F, 0.5, 0.0, 1.0)),
                   outputs=(SocketSpec("color", "Color", _C), SocketSpec("fac", "Factor", _F)),
                   props=(Param("rows_ratio", "Rows Ratio", "float", 2.0, 0.1, 16.0, step=0.1),
                          Param("row_offset", "Row Offset", "float", 0.5, 0.0, 1.0),
                          Param("mortar_smooth", "Mortar Smooth", "float", 0.02, 0.0, 0.5),
                          Param("seed", "Seed", "int", 0, 0, 9999, step=1)),
                   fn=_fn_brick))
_register(NodeType("mix_color", "Mix Color", "Color",
                   inputs=(SocketSpec("fac", "Factor", _F, 0.5, 0.0, 1.0),
                           SocketSpec("color1", "A", _C, [0.5, 0.5, 0.5]),
                           SocketSpec("color2", "B", _C, [0.5, 0.5, 0.5])),
                   outputs=(SocketSpec("color", "Result", _C),),
                   props=(Param("blend", "Blend", "enum", "mix", options=BLEND_MODES),
                          Param("clamp", "Clamp", "bool", False)),
                   fn=_fn_mix_color))
_register(NodeType("invert", "Invert", "Color",
                   inputs=(SocketSpec("fac", "Factor", _F, 1.0, 0.0, 1.0),
                           SocketSpec("color", "Color", _C, [0.0, 0.0, 0.0])),
                   outputs=(SocketSpec("color", "Color", _C),), fn=_fn_invert))
_register(NodeType("hue_saturation", "Hue/Saturation", "Color",
                   inputs=(SocketSpec("hue", "Hue", _F, 0.5, 0.0, 1.0),
                           SocketSpec("saturation", "Saturation", _F, 1.0, 0.0, 2.0),
                           SocketSpec("value", "Value", _F, 1.0, 0.0, 2.0),
                           SocketSpec("fac", "Factor", _F, 1.0, 0.0, 1.0),
                           SocketSpec("color", "Color", _C, [0.8, 0.8, 0.8])),
                   outputs=(SocketSpec("color", "Color", _C),), fn=_fn_hsv))
_register(NodeType("math", "Math", "Converter",
                   inputs=(SocketSpec("a", "Value", _F, 0.5), SocketSpec("b", "Value", _F, 0.5)),
                   outputs=(SocketSpec("value", "Value", _F),),
                   props=(Param("op", "Operation", "enum", "add", options=MATH_OPS),
                          Param("clamp", "Clamp", "bool", False)),
                   fn=_fn_math))
_register(NodeType("color_ramp", "Color Ramp", "Converter",
                   inputs=(SocketSpec("fac", "Factor", _F, 0.5, 0.0, 1.0),),
                   outputs=(SocketSpec("color", "Color", _C), SocketSpec("alpha", "Alpha", _F)),
                   props=(Param("stops", "Colors", "ramp", copy.deepcopy(DEFAULT_RAMP)),
                          Param("interpolation", "Interpolation", "enum", "linear", options=INTERPOLATIONS)),
                   fn=_fn_ramp))
_register(NodeType("separate_rgb", "Separate RGB", "Converter",
                   inputs=(SocketSpec("color", "Color", _C, [0.8, 0.8, 0.8]),),
                   outputs=(SocketSpec("r", "R", _F), SocketSpec("g", "G", _F), SocketSpec("b", "B", _F)),
                   fn=_fn_separate))
_register(NodeType("combine_rgb", "Combine RGB", "Converter",
                   inputs=(SocketSpec("r", "R", _F, 0.0), SocketSpec("g", "G", _F, 0.0),
                           SocketSpec("b", "B", _F, 0.0)),
                   outputs=(SocketSpec("color", "Color", _C),), fn=_fn_combine))
_register(NodeType("fresnel", "Fresnel", "Input",
                   inputs=(SocketSpec("ior", "IOR", _F, 1.45, 1.0, 4.0),
                           SocketSpec("normal", "Normal", "vector", "@normal")),
                   outputs=(SocketSpec("fac", "Factor", _F),), fn=_fn_fresnel))
_register(NodeType("normal_map", "Normal Map", "Vector",
                   inputs=(SocketSpec("strength", "Strength", _F, 1.0, 0.0, 8.0),
                           SocketSpec("color", "Color", _C, [0.5, 0.5, 1.0])),
                   outputs=(SocketSpec("normal", "Normal", "vector"),),
                   props=(Param("space", "Space", "enum", "tangent", options=("tangent", "object")),
                          Param("flip_green", "Flip Green", "bool", False)),
                   fn=_fn_normal_map))
_register(NodeType("bump", "Bump", "Vector",
                   inputs=(SocketSpec("strength", "Strength", _F, 1.0, 0.0, 16.0),
                           SocketSpec("distance", "Distance", _F, 0.02, 0.0, 1.0),
                           SocketSpec("height", "Height", _F, 0.0),
                           SocketSpec("normal", "Normal", "vector", "@normal")),
                   outputs=(SocketSpec("normal", "Normal", "vector"),),
                   props=(Param("invert", "Invert", "bool", False),),
                   fn=_fn_bump))
_register(NodeType("mapping", "Mapping", "Vector",
                   inputs=(_VEC, SocketSpec("location", "Location", "vector", [0.0, 0.0, 0.0]),
                           SocketSpec("scale", "Scale", "vector", [1.0, 1.0, 1.0])),
                   outputs=(SocketSpec("vector", "Vector", "vector"),),
                   props=(Param("rotation", "Rotation", "float", 0.0, -360.0, 360.0, step=1.0),),
                   fn=_fn_mapping))
_register(NodeType("value", "Value", "Input",
                   outputs=(SocketSpec("value", "Value", _F),),
                   props=(Param("value", "Value", "float", 0.5, -1.0e6, 1.0e6, soft_max=1.0),),
                   fn=_fn_value))
_register(NodeType("rgb", "RGB", "Input",
                   outputs=(SocketSpec("color", "Color", _C),),
                   props=(Param("color", "Color", "color", [0.5, 0.5, 0.5]),),
                   fn=_fn_rgb))
_register(NodeType("texcoord", "Texture Coordinates", "Input",
                   outputs=(SocketSpec("uv", "UV", "vector"), SocketSpec("object", "Object", "vector"),
                            SocketSpec("normal", "Normal", "vector"), SocketSpec("tangent", "Tangent", "vector")),
                   fn=_fn_texcoord))


def _node_defaults(nt: NodeType) -> dict:
    return {s.name: copy.deepcopy(s.default) for s in nt.inputs if s.editable()}


def _next_id(graph: dict) -> str:
    taken = {n["id"] for n in graph.get("nodes", [])}
    k = int(graph.get("next_id", 1))
    while f"n{k}" in taken:
        k += 1
    graph["next_id"] = k + 1
    return f"n{k}"


def add_node(graph: dict, type_id: str, pos=(0.0, 0.0), **props) -> dict:
    nt = node_type(type_id)
    node = {"id": _next_id(graph), "type": type_id, "pos": [float(pos[0]), float(pos[1])],
            "inputs": _node_defaults(nt), "props": defaults_of(nt.props)}
    for key, value in props.items():
        p = nt.prop(key)
        if p is None:
            raise KeyError(f"node {type_id!r} has no property {key!r}")
        node["props"][key] = coerce(p, value)
    graph.setdefault("nodes", []).append(node)
    graph.setdefault("links", [])
    return node


def new_graph() -> dict:
    graph = {"nodes": [], "links": [], "next_id": 1}
    bsdf = add_node(graph, "principled", (-256.0, -96.0))
    out = add_node(graph, "output", (64.0, -48.0))
    connect(graph, bsdf["id"], "bsdf", out["id"], "surface")
    return graph


def find_node(graph: dict, node_id: str) -> dict | None:
    for n in graph.get("nodes", []):
        if n.get("id") == node_id:
            return n
    return None


def output_node(graph: dict) -> dict | None:
    for n in graph.get("nodes", []):
        if n.get("type") == "output":
            return n
    return None


def link_into(graph: dict, node_id: str, socket: str) -> dict | None:
    for link in graph.get("links", []):
        if link["to"][0] == node_id and link["to"][1] == socket:
            return link
    return None


def links_from(graph: dict, node_id: str, socket: str | None = None) -> list:
    return [l for l in graph.get("links", [])
            if l["from"][0] == node_id and (socket is None or l["from"][1] == socket)]


def upstream(graph: dict, node_id: str) -> set:
    seen: set = set()
    stack = [node_id]
    while stack:
        cur = stack.pop()
        for link in graph.get("links", []):
            if link["to"][0] == cur and link["from"][0] not in seen:
                seen.add(link["from"][0])
                stack.append(link["from"][0])
    return seen


def _compatible(src: str, dst: str) -> bool:
    if src == "shader" or dst == "shader":
        return src == dst
    return True


def can_connect(graph: dict, src_id: str, src_sock: str, dst_id: str, dst_sock: str) -> tuple[bool, str]:
    src = find_node(graph, src_id)
    dst = find_node(graph, dst_id)
    if src is None or dst is None:
        return False, "missing node"
    if src_id == dst_id:
        return False, "cannot link a node to itself"
    so = node_type(src["type"]).output(src_sock)
    di = node_type(dst["type"]).input(dst_sock)
    if so is None:
        return False, f"{src['type']} has no output {src_sock!r}"
    if di is None:
        return False, f"{dst['type']} has no input {dst_sock!r}"
    if not _compatible(so.type, di.type):
        return False, f"cannot link {so.type} to {di.type}"
    if dst_id in upstream(graph, src_id):
        return False, "link would create a cycle"
    return True, ""


def connect(graph: dict, src_id: str, src_sock: str, dst_id: str, dst_sock: str) -> dict:
    ok, why = can_connect(graph, src_id, src_sock, dst_id, dst_sock)
    if not ok:
        raise ValueError(why)
    graph["links"] = [l for l in graph.get("links", []) if not (l["to"][0] == dst_id and l["to"][1] == dst_sock)]
    link = {"from": [src_id, src_sock], "to": [dst_id, dst_sock]}
    graph["links"].append(link)
    return link


def disconnect(graph: dict, dst_id: str, dst_sock: str) -> bool:
    before = len(graph.get("links", []))
    graph["links"] = [l for l in graph.get("links", []) if not (l["to"][0] == dst_id and l["to"][1] == dst_sock)]
    return len(graph["links"]) != before


def remove_node(graph: dict, node_id: str) -> bool:
    node = find_node(graph, node_id)
    if node is None:
        return False
    graph["nodes"] = [n for n in graph["nodes"] if n["id"] != node_id]
    graph["links"] = [l for l in graph.get("links", []) if l["from"][0] != node_id and l["to"][0] != node_id]
    return True


def duplicate_node(graph: dict, node_id: str, offset=(32.0, 32.0)) -> dict:
    node = find_node(graph, node_id)
    if node is None:
        raise KeyError(f"no node {node_id!r}")
    copy_node = copy.deepcopy(node)
    copy_node["id"] = _next_id(graph)
    copy_node["pos"] = [node["pos"][0] + float(offset[0]), node["pos"][1] + float(offset[1])]
    graph["nodes"].append(copy_node)
    return copy_node


def move_node(graph: dict, node_id: str, pos) -> None:
    node = find_node(graph, node_id)
    if node is None:
        raise KeyError(f"no node {node_id!r}")
    node["pos"] = [float(pos[0]), float(pos[1])]


def _coerce_socket(spec: SocketSpec, value):
    if spec.type == "float":
        v = float(value)
        if spec.minimum is not None:
            v = max(v, float(spec.minimum))
        if spec.maximum is not None:
            v = min(v, float(spec.maximum))
        return v
    vals = [float(x) for x in (value if np.ndim(value) else [value] * 3)][:3]
    if len(vals) != 3:
        raise ValueError(f"{spec.name} needs 3 values")
    return vals


def set_node_input(graph: dict, node_id: str, name: str, value) -> None:
    node = find_node(graph, node_id)
    if node is None:
        raise KeyError(f"no node {node_id!r}")
    spec = node_type(node["type"]).input(name)
    if spec is None or not spec.editable():
        raise KeyError(f"{node['type']} has no editable input {name!r}")
    node.setdefault("inputs", {})[name] = _coerce_socket(spec, value)


def set_node_prop(graph: dict, node_id: str, key: str, value) -> None:
    node = find_node(graph, node_id)
    if node is None:
        raise KeyError(f"no node {node_id!r}")
    p = node_type(node["type"]).prop(key)
    if p is None:
        raise KeyError(f"{node['type']} has no property {key!r}")
    node.setdefault("props", {})[key] = coerce(p, value)


def _finite_float(value) -> float:
    v = float(value)
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError("value is not finite")
    return v


def _sock_ref(value) -> list | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    if not all(isinstance(x, str) and x for x in value):
        return None
    return [value[0], value[1]]


def sanitize_graph(graph) -> dict:
    if not isinstance(graph, dict):
        return new_graph()
    nodes = []
    taken = set()
    for raw in graph.get("nodes") or []:
        if not isinstance(raw, dict) or raw.get("type") not in NODE_TYPES:
            continue
        nid = raw.get("id")
        if not isinstance(nid, str) or not nid or nid in taken:
            continue
        nt = node_type(raw["type"])
        try:
            pos = [_finite_float(raw["pos"][0]), _finite_float(raw["pos"][1])]
        except (KeyError, IndexError, TypeError, ValueError):
            pos = [0.0, 0.0]
        inputs = _node_defaults(nt)
        given = raw.get("inputs") if isinstance(raw.get("inputs"), dict) else {}
        for spec in nt.inputs:
            if spec.editable() and spec.name in given:
                try:
                    value = _coerce_socket(spec, given[spec.name])
                    if spec.type == "float":
                        _finite_float(value)
                    else:
                        [_finite_float(x) for x in value]
                    inputs[spec.name] = value
                except (TypeError, ValueError):
                    pass
        props = defaults_of(nt.props)
        given = raw.get("props") if isinstance(raw.get("props"), dict) else {}
        for prm in nt.props:
            if prm.key in given:
                try:
                    props[prm.key] = coerce(prm, given[prm.key])
                except (TypeError, ValueError, IndexError):
                    pass
        node = {"id": nid, "type": raw["type"], "pos": pos, "inputs": inputs, "props": props}
        nodes.append(node)
        taken.add(nid)
    links = []
    for raw in graph.get("links") or []:
        if not isinstance(raw, dict):
            continue
        a, b = _sock_ref(raw.get("from")), _sock_ref(raw.get("to"))
        if a is None or b is None or a[0] == b[0]:
            continue
        links.append({"from": a, "to": b})
    try:
        next_id = max(1, int(graph.get("next_id", 1)))
    except (TypeError, ValueError):
        next_id = 1
    out = {"nodes": nodes, "links": links, "next_id": next_id}
    prune_graph(out)
    return out


def prune_graph(graph: dict) -> int:
    ids = {n["id"]: n for n in graph.get("nodes", []) if n.get("type") in NODE_TYPES}
    graph["nodes"] = list(ids.values())
    keep = []
    seen_inputs = set()
    for link in reversed(graph.get("links", [])):
        src, dst = ids.get(link["from"][0]), ids.get(link["to"][0])
        if src is None or dst is None:
            continue
        so = node_type(src["type"]).output(link["from"][1])
        di = node_type(dst["type"]).input(link["to"][1])
        key = tuple(link["to"])
        if so is None or di is None or not _compatible(so.type, di.type) or key in seen_inputs:
            continue
        seen_inputs.add(key)
        keep.append(link)
    keep.reverse()
    removed = len(graph.get("links", [])) - len(keep)
    graph["links"] = keep
    return removed


class GraphEvaluator:

    def __init__(self, graph: dict) -> None:
        self.graph = graph
        self.nodes = {n["id"]: n for n in graph.get("nodes", []) if n.get("type") in NODE_TYPES}
        self.links = {(l["to"][0], l["to"][1]): (l["from"][0], l["from"][1]) for l in graph.get("links", [])}
        self._memo: dict = {}
        self._contexts: list = []
        self._stack: set = set()

    def link(self, node_id: str, socket: str):
        return self.links.get((node_id, socket))

    def _ctx_key(self, ctx: dict) -> int:
        for i, c in enumerate(self._contexts):
            if c is ctx:
                return i
        self._contexts.append(ctx)
        return len(self._contexts) - 1

    def _default(self, node: dict, spec: SocketSpec, ctx: dict):
        n = ctx["n"]
        if spec.type == "shader":
            return None
        value = (node.get("inputs") or {}).get(spec.name, spec.default)
        if isinstance(spec.default, str):
            value = spec.default
        if value == "@uv":
            return np.stack([ctx["u"], ctx["v"], np.zeros(n)], axis=1)
        if value == "@normal":
            return np.array(ctx["normal"], float, copy=True)
        if value == "@position":
            return np.array(ctx.get("opos", ctx["pos"]), float, copy=True)
        if value is None:
            return np.zeros(n) if spec.type == "float" else np.zeros((n, 3))
        return _broadcast(value, spec.type, n)

    def input(self, node: dict, nt: NodeType, name: str, ctx: dict):
        spec = nt.input(name)
        if spec is None:
            raise KeyError(f"{nt.id} has no input {name!r}")
        src = self.link(node["id"], name)
        if src is not None and src[0] in self.nodes:
            snode = self.nodes[src[0]]
            snt = node_type(snode["type"])
            sspec = snt.output(src[1])
            if sspec is not None and _compatible(sspec.type, spec.type):
                outputs = self.outputs(src[0], ctx)
                if outputs is not None and src[1] in outputs:
                    value = convert_value(outputs[src[1]], sspec.type, spec.type, ctx["n"])
                    if value is not None or spec.type == "shader":
                        return value
        return self._default(node, spec, ctx)

    def outputs(self, node_id: str, ctx: dict):
        key = (self._ctx_key(ctx), node_id)
        if key in self._memo:
            return self._memo[key]
        if key in self._stack:
            return None
        node = self.nodes.get(node_id)
        if node is None:
            return None
        nt = node_type(node["type"])
        self._stack.add(key)
        try:
            result = nt.fn(NodeCall(self, node, nt, ctx)) if nt.fn else {}
        finally:
            self._stack.discard(key)
        self._memo[key] = result
        return result

    def output(self, node_id: str, socket: str, ctx: dict):
        res = self.outputs(node_id, ctx)
        return None if res is None else res.get(socket)


def evaluate_graph(graph: dict, ctx: dict) -> dict:
    ev = GraphEvaluator(graph)
    out = output_node(graph)
    shader = None
    displacement = np.zeros(ctx["n"])
    if out is not None:
        nt = node_type("output")
        shader = ev.input(out, nt, "surface", ctx)
        displacement = ev.input(out, nt, "displacement", ctx)
    result = default_shader(ctx)
    if isinstance(shader, dict):
        for key in SHADER_KEYS:
            if key in shader:
                result[key] = np.asarray(shader[key], float)
        if EMISSION_LINEAR in shader:
            result[EMISSION_LINEAR] = np.asarray(shader[EMISSION_LINEAR], float)
        else:
            result[EMISSION_LINEAR] = srgb_to_linear(np.maximum(result["emission"], 0.0))
    result["displacement"] = np.asarray(displacement, float)
    return result


NODE_WIDTH = 176.0
NODE_HEADER = 24.0
NODE_ROW = 24.0
NODE_PAD = 8.0


def node_rows(nt: NodeType, node: dict | None = None) -> int:
    return len(nt.outputs) + len(nt.inputs)


def node_height(nt: NodeType, node: dict | None = None) -> float:
    return NODE_HEADER + NODE_ROW * node_rows(nt, node) + NODE_PAD


def arrange_graph(graph: dict, column_gap: float = 64.0, row_gap: float = 24.0) -> dict:
    nodes = {n["id"]: n for n in graph.get("nodes", []) if n.get("type") in NODE_TYPES}
    if not nodes:
        return {}
    downstream: dict[str, set] = {k: set() for k in nodes}
    for link in graph.get("links", []):
        a, b = link["from"][0], link["to"][0]
        if a in nodes and b in nodes:
            downstream[a].add(b)
    depth: dict[str, int] = {}

    def visit(nid: str, trail: frozenset) -> int:
        if nid in depth:
            return depth[nid]
        if nid in trail:
            return 0
        kids = downstream[nid]
        d = 0 if not kids else 1 + max(visit(k, trail | {nid}) for k in kids)
        depth[nid] = d
        return d

    for nid in nodes:
        visit(nid, frozenset())
    columns: dict[int, list[str]] = {}
    for nid, d in depth.items():
        columns.setdefault(d, []).append(nid)
    placed: dict[str, float] = {}
    for d in sorted(columns):
        ids = columns[d]

        def order(nid: str) -> float:
            ys = [placed[k] for k in downstream[nid] if k in placed]
            return sum(ys) / len(ys) if ys else float(nodes[nid]["pos"][1])

        ids.sort(key=order)
        heights = [node_height(node_type(nodes[i]["type"])) for i in ids]
        total = sum(heights) + row_gap * (len(ids) - 1)
        y = -total / 2.0
        x = -d * (NODE_WIDTH + column_gap)
        for nid, h in zip(ids, heights):
            nodes[nid]["pos"] = [float(x), float(y)]
            placed[nid] = y + h / 2.0
            y += h + row_gap
    return {nid: tuple(n["pos"]) for nid, n in nodes.items()}
