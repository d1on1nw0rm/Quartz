from __future__ import annotations

from pathlib import Path

from . import paths

__all__ = ["EXAMPLE_SCRIPTS", "EXAMPLE_PLUGINS", "install_examples"]

RING_OF_CUBES = '''import math

import quartz

count = 8
radius = 400.0
size = 80.0

with quartz.undo_group():
    ring = quartz.create("null", name="Cube Ring")
    for i in range(count):
        angle = 2.0 * math.pi * i / count
        quartz.create(
            "cube",
            name=f"Ring Cube {i + 1}",
            parent=ring,
            activate=False,
            size_x=size, size_y=size, size_z=size,
            position=(math.cos(angle) * radius, 0.0, math.sin(angle) * radius),
            rotation=(0.0, -math.degrees(angle), 0.0),
        )

quartz.select(ring)
quartz.message(f"Created {count} cubes under {ring.name}")
'''

EXTRUDE_UPWARD_FACES = '''import quartz

op = quartz.active_object()
if op is None:
    raise SystemExit("Select an object first")
if op.kind != "polygon":
    op = quartz.make_editable(op)

normals = quartz.polygon_normals(op)
upward = [i for i, n in enumerate(normals) if n[1] > 0.7]
if not upward:
    raise SystemExit(f"{op.name} has no faces pointing up")

quartz.select_polygons(upward, obj=op)
result = quartz.run_tool("extrude", {"offset": 40.0}, obj=op)
print(f"Extruded {len(upward)} faces of {op.name}: {result.ok}")
print(f"{op.name} now has {quartz.polygon_count(op)} polygons")
'''

SCENE_REPORT = '''import quartz

rows = []
for obj in quartz.objects():
    depth = 0
    p = obj.parent
    while p is not None:
        depth += 1
        p = p.parent
    rows.append((
        "  " * depth + obj.name,
        obj.kind,
        quartz.point_count(obj),
        quartz.polygon_count(obj),
        len(quartz.tags(obj)),
    ))

width = max([len(r[0]) for r in rows] + [6])
print(f"{'Object':<{width}}  {'Kind':<20} {'Points':>8} {'Polys':>8} {'Tags':>5}")
for name, kind, pts, polys, ntags in rows:
    print(f"{name:<{width}}  {kind:<20} {pts:>8} {polys:>8} {ntags:>5}")
print(f"{len(rows)} objects, {sum(r[2] for r in rows)} points, {sum(r[3] for r in rows)} polygons")
'''

EXAMPLE_PLUGIN = '''import numpy as np

PLUGIN = {
    "name": "Example Tools",
    "type": "command",
    "version": "1.0",
    "author": "Quartz",
    "description": "Adds Drop To Floor and Jitter Points commands to the Extensions menu.",
}


def drop_to_floor(api):
    op = api.active_object()
    if op is None:
        api.message("Drop To Floor: no active object")
        return
    low, _high = api.bounds(op, world=True)
    world = api.world_position(op)
    api.set_world_position(op, (world[0], world[1] - low[1], world[2]))
    api.message(f"Dropped {op.name} onto the floor")


def jitter_points(api, amount=0.02, seed=7):
    op = api.active_object()
    if op is None:
        api.message("Jitter Points: no active object")
        return
    with api.undo_group():
        if op.kind != "polygon":
            op = api.make_editable(op)
        pts = api.points(op)
        if len(pts) == 0:
            return
        extent = float(np.max(pts.max(axis=0) - pts.min(axis=0)))
        rng = np.random.default_rng(seed)
        api.set_points(op, pts + rng.uniform(-1.0, 1.0, pts.shape) * extent * amount)
    api.message(f"Jittered {len(pts)} points of {op.name}")


def register(api):
    api.register_command("Drop To Floor", lambda: drop_to_floor(api))
    api.register_command("Jitter Points", lambda: jitter_points(api))
'''

EXAMPLE_SCRIPTS = {
    "Ring Of Cubes.py": RING_OF_CUBES,
    "Extrude Upward Faces.py": EXTRUDE_UPWARD_FACES,
    "Scene Report.py": SCENE_REPORT,
}

EXAMPLE_PLUGINS = {
    "example_tools.py": EXAMPLE_PLUGIN,
}


def _write(folder: Path, files: dict, overwrite: bool) -> list[Path]:
    written = []
    for name, text in files.items():
        target = folder / name
        if target.exists() and not overwrite:
            continue
        with open(target, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        written.append(target)
    return written


def install_examples(overwrite: bool = False, scripts: bool = True, plugins: bool = True) -> list[Path]:
    written: list[Path] = []
    if scripts:
        written += _write(paths.scripts_dir(), EXAMPLE_SCRIPTS, overwrite)
    if plugins:
        written += _write(paths.plugins_dir(), EXAMPLE_PLUGINS, overwrite)
    return written
