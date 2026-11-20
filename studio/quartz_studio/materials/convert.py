from __future__ import annotations

import copy

from .model import channel_spec, find_material, update_material
from .nodes import add_node, arrange_graph, connect, set_node_input
from .textures import texture_params

__all__ = ["pbr_to_graph", "convert_to_nodes", "texture_to_nodes"]

COLUMN = 224.0
ROW = 160.0


class _Builder:

    def __init__(self) -> None:
        self.graph = {"nodes": [], "links": [], "next_id": 1}
        self.row = 0

    def node(self, type_id: str, column: int, **props) -> dict:
        node = add_node(self.graph, type_id, (-COLUMN * column, ROW * self.row), **props)
        return node

    def link(self, a: dict, a_sock: str, b: dict, b_sock: str) -> None:
        connect(self.graph, a["id"], a_sock, b["id"], b_sock)

    def set(self, node: dict, name: str, value) -> None:
        set_node_input(self.graph, node["id"], name, value)


def _values(tex: dict) -> dict:
    out = {p.key: copy.deepcopy(p.default) for p in texture_params(tex["type"])}
    out.update({k: v for k, v in tex.items() if k in out})
    return out


def _vector_source(b: _Builder, vals: dict, column: int):
    tiling = vals.get("tiling", [1.0, 1.0])
    offset = vals.get("offset", [0.0, 0.0])
    identity = list(tiling) == [1.0, 1.0] and list(offset) == [0.0, 0.0]
    if vals.get("space") == "object":
        tc = b.node("texcoord", column + 2 if not identity else column + 1)
        if identity:
            return tc, "object"
        mp = b.node("mapping", column + 1)
        b.link(tc, "object", mp, "vector")
        b.set(mp, "scale", [float(tiling[0]), float(tiling[1]), 1.0])
        b.set(mp, "location", [float(offset[0]), float(offset[1]), 0.0])
        return mp, "vector"
    if identity:
        return None
    mp = b.node("mapping", column + 1)
    b.set(mp, "scale", [float(tiling[0]), float(tiling[1]), 1.0])
    b.set(mp, "location", [float(offset[0]), float(offset[1]), 0.0])
    return mp, "vector"


def _mix_colors(b: _Builder, fac_node: dict, fac_sock: str, c1, c2, column: int) -> tuple[dict, str]:
    mix = b.node("mix_color", column)
    b.set(mix, "color1", c1)
    b.set(mix, "color2", c2)
    b.link(fac_node, fac_sock, mix, "fac")
    return mix, "color"


def texture_to_nodes(b: _Builder, tex: dict, column: int = 2) -> tuple[dict, str, str]:
    kind = tex["type"]
    vals = _values(tex)
    src = _vector_source(b, vals, column + 1)

    def feed(node: dict) -> None:
        if src is not None:
            b.link(src[0], src[1], node, "vector")

    if kind == "checker":
        n = b.node("checker", column)
        feed(n)
        b.set(n, "color1", vals["color1"])
        b.set(n, "color2", vals["color2"])
        b.set(n, "scale", vals["scale"])
        return n, "color", "color"
    if kind == "noise":
        n = b.node("noise", column + 1, noise_type=vals["noise_type"], lacunarity=vals["lacunarity"],
                   seed=vals["seed"])
        feed(n)
        for key in ("scale", "detail", "roughness", "distortion"):
            b.set(n, key, vals[key])
        fac_node, fac_sock = n, "fac"
        contrast = float(vals.get("contrast", 1.0))
        if contrast != 1.0:
            sub = b.node("math", column, op="subtract")
            b.link(n, "fac", sub, "a")
            b.set(sub, "b", 0.5)
            mul = b.node("math", column, op="multiply")
            b.link(sub, "value", mul, "a")
            b.set(mul, "b", contrast)
            add = b.node("math", column, op="add", clamp=True)
            b.link(mul, "value", add, "a")
            b.set(add, "b", 0.5)
            fac_node, fac_sock = add, "value"
        mix, sock = _mix_colors(b, fac_node, fac_sock, vals["color1"], vals["color2"], column)
        return mix, sock, sock
    if kind == "gradient":
        n = b.node("gradient", column + 1, gradient_type=vals["gradient_type"], repeat=vals["repeat"])
        feed(n)
        ramp = b.node("color_ramp", column, stops=vals["ramp"], interpolation=vals["interpolation"])
        b.link(n, "fac", ramp, "fac")
        return ramp, "color", "color"
    if kind == "brick":
        bricks = float(vals["bricks"])
        n = b.node("brick", column, rows_ratio=float(vals["rows"]) / max(bricks, 1e-9),
                   row_offset=vals["row_offset"], mortar_smooth=vals["smooth"], seed=vals["seed"])
        feed(n)
        b.set(n, "color1", vals["color1"])
        b.set(n, "color2", vals["color2"])
        b.set(n, "mortar", vals["mortar_color"])
        b.set(n, "scale", bricks)
        b.set(n, "mortar_size", vals["mortar"])
        b.set(n, "bias", vals["variation"])
        return n, "color", "color"
    if kind == "voronoi":
        n = b.node("voronoi", column + 1, feature=vals["feature"], metric=vals["metric"], seed=vals["seed"])
        feed(n)
        b.set(n, "scale", vals["scale"])
        b.set(n, "randomness", vals["randomness"])
        if vals["coloring"] == "cells":
            return n, "color", "color"
        clamp = b.node("math", column, op="minimum")
        b.link(n, "distance", clamp, "a")
        b.set(clamp, "b", 1.0)
        mix, sock = _mix_colors(b, clamp, "value", vals["color1"], vals["color2"], column)
        return mix, sock, sock
    if kind == "image":
        n = b.node("image_texture", column, path=vals["path"], interpolation=vals["interpolation"],
                   extension=vals["extension"])
        feed(n)
        return n, "color", ("alpha" if vals["use_alpha"] else "color")
    raise ValueError(f"unknown texture type {kind!r}")


def _channel_source(b: _Builder, ch: dict, key: str, is_color: bool):
    tex = ch.get("texture")
    if not tex:
        return None
    node, col_sock, fac_sock = texture_to_nodes(b, tex)
    sock = col_sock if is_color else fac_sock
    spec = channel_spec(key)
    if not is_color and spec.texture_range is not None:
        lo, hi = spec.texture_range
        mul = b.node("math", 1, op="multiply")
        b.link(node, sock, mul, "a")
        b.set(mul, "b", float(hi) - float(lo))
        add = b.node("math", 1, op="add")
        b.link(mul, "value", add, "a")
        b.set(add, "b", float(lo))
        node, sock = add, "value"
    mix = float(ch.get("mix", 1.0))
    if mix >= 1.0:
        return node, sock
    value = ch.get("value", 0.0)
    base = list(value) if is_color else [float(value)] * 3
    blend = b.node("mix_color", 1)
    b.set(blend, "fac", mix)
    b.set(blend, "color1", base)
    b.link(node, sock, blend, "color2")
    return blend, "color"


_FLOAT_INPUTS = {"metallic": "metallic", "roughness": "roughness", "specular": "specular", "ior": "ior",
                 "alpha": "alpha", "transmission": "transmission", "clearcoat": "clearcoat", "sheen": "sheen"}
_NEUTRAL = {"alpha": 1.0, "transmission": 0.0, "clearcoat": 0.0, "sheen": 0.0}


def pbr_to_graph(material: dict) -> dict:
    b = _Builder()
    channels = material.get("channels") or {}
    bsdf = add_node(b.graph, "principled", (0.0, 0.0))
    out = add_node(b.graph, "output", (COLUMN * 1.5, 0.0))
    b.link(bsdf, "bsdf", out, "surface")

    def active(key: str) -> bool:
        ch = channels.get(key)
        return bool(ch) and (not channel_spec(key).optional or bool(ch.get("enabled")))

    def place(key: str, target: dict, socket: str, is_color: bool) -> None:
        ch = channels[key]
        src = _channel_source(b, ch, key, is_color)
        if src is not None:
            b.link(src[0], src[1], target, socket)
            b.row += 1
        elif "value" in ch:
            b.set(target, socket, ch["value"])

    if "base_color" in channels:
        place("base_color", bsdf, "base_color", True)
    for key, socket in _FLOAT_INPUTS.items():
        if key not in channels:
            continue
        if not active(key):
            if key in _NEUTRAL:
                b.set(bsdf, socket, _NEUTRAL[key])
            continue
        place(key, bsdf, socket, False)
    if active("emission"):
        place("emission", bsdf, "emission", True)
        b.set(bsdf, "emission_strength", float(channels["emission"].get("strength", 1.0)))
    else:
        b.set(bsdf, "emission", [0.0, 0.0, 0.0])
    if active("clearcoat"):
        b.set(bsdf, "clearcoat_roughness", float(channels["clearcoat"].get("roughness", 0.03)))
    if active("sheen"):
        b.set(bsdf, "sheen_tint", channels["sheen"].get("tint", [1.0, 1.0, 1.0]))
        b.set(bsdf, "sheen_roughness", float(channels["sheen"].get("roughness", 0.5)))
    normal_src = None
    nm = channels.get("normal")
    if active("normal") and nm.get("texture"):
        node, col_sock, _ = texture_to_nodes(b, nm["texture"])
        nmap = b.node("normal_map", 1, flip_green=bool(nm.get("flip_green")))
        b.set(nmap, "strength", float(nm.get("strength", 1.0)))
        b.link(node, col_sock, nmap, "color")
        normal_src = nmap
        b.row += 1
    bp = channels.get("bump")
    if active("bump") and bp.get("texture"):
        node, _, fac_sock = texture_to_nodes(b, bp["texture"])
        bump = b.node("bump", 1, invert=bool(bp.get("invert")))
        b.set(bump, "strength", float(bp.get("strength", 1.0)))
        b.set(bump, "distance", float(bp.get("distance", 0.02)))
        b.link(node, fac_sock, bump, "height")
        if normal_src is not None:
            b.link(normal_src, "normal", bump, "normal")
        normal_src = bump
        b.row += 1
    if normal_src is not None:
        b.link(normal_src, "normal", bsdf, "normal")
    dp = channels.get("displacement")
    if active("displacement") and dp.get("texture"):
        node, _, fac_sock = texture_to_nodes(b, dp["texture"])
        sub = b.node("math", 1, op="subtract")
        b.link(node, fac_sock, sub, "a")
        b.set(sub, "b", float(dp.get("midlevel", 0.5)))
        mul = b.node("math", 0, op="multiply")
        b.link(sub, "value", mul, "a")
        b.set(mul, "b", float(dp.get("height", 1.0)))
        b.link(mul, "value", out, "displacement")
    arrange_graph(b.graph)
    return b.graph


def convert_to_nodes(scene, mid: str) -> dict:
    mat = find_material(scene, mid)
    if mat is None:
        raise KeyError(f"no material {mid!r}")
    if mat.get("type") == "node":
        return mat
    new = copy.deepcopy(mat)
    new["graph"] = pbr_to_graph(mat)
    new["type"] = "node"
    return update_material(scene, new)
