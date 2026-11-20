from __future__ import annotations

import importlib
import re
import sys
import traceback

__all__ = ["install", "PACKAGES", "PAGE_LAYOUTS", "DOCK_LAYOUTS", "LAYOUT_MENU", "report", "slug"]

PACKAGES = (
    ("materials", "quartz_studio.materials.menus"),
    ("tags", "quartz_studio.tags"),
    ("uv", "quartz_studio.uv"),
    ("sculpt", "quartz_studio.sculpt"),
    ("rig", "quartz_studio.rig"),
    ("anim", "quartz_studio.anim"),
    ("scripting", "quartz_studio.scripting"),
    ("render", "quartz_studio.render"),
)

PAGE_LAYOUTS = ("Materials", "UV Edit", "Script", "Render")

TOP_MENUS = {
    "Materials": ("Materials", None),
    "Tags": ("Materials", "Tags"),
    "Texture": ("Materials", "Texture"),
    "UV": ("UV", None),
    "Sculpt": ("Sculpt", None),
    "Animate": ("Animate", None),
    "Character": ("Animate", "Character"),
    "Render": ("Render", None),
    "Extensions": ("Extensions", None),
}

PACKAGE_MENU = {
    "materials": "Materials", "tags": "Tags", "uv": "UV", "sculpt": "Sculpt", "rig": "Character",
    "anim": "Animate", "scripting": "Extensions", "render": "Render",
}

RESERVED_SHORTCUTS = frozenset({
    "Ctrl+Z", "Ctrl+Y", "Ctrl+N", "Ctrl+O", "Ctrl+Shift+O", "Ctrl+S", "Ctrl+Shift+S", "Ctrl+Alt+S",
    "Alt+F4", "Alt+C", "Ctrl+A", "Ctrl+Shift+A", "Ctrl+B", "Ctrl+E", "Ctrl+I", "Ctrl+Shift+I",
    "Ctrl+Q", "Ctrl+R", "Ctrl+Shift+Y", "Ctrl+Shift+Z", "Ctrl+,", "Shift+F12",
})
DOCK_LAYOUTS = ("Sculpt", "Animate", "Rigging", "Tagging")
LAYOUT_MENU = "Layout"

DOCK_AREAS = {
    "Timeline": "bottom",
    "Dope Sheet": "bottom",
    "F-Curves": "bottom",
    "Console": "bottom",
    "Material Manager": "bottom",
    "Sculpt Brushes": "left",
    "Sculpt Layers": "left",
    "Joints": "left",
    "Rig": "right",
    "Weight Paint": "right",
    "Tags": "right",
}

_SHORTCUT = re.compile(r"^(?:(?:Ctrl|Shift|Alt|Meta)\+)*(?:F\d{1,2}|[A-Z0-9]|Up|Down|Left|Right|Home|End|Space|Del|Delete|Tab|PgUp|PgDown|\[|\]|[,.;'/\\=-])$")

report: dict = {"installed": [], "failed": {}, "menus": [], "docks": [], "pages": [], "shortcuts": [], "skipped_shortcuts": []}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _is_shortcut(text) -> bool:
    return isinstance(text, str) and bool(_SHORTCUT.match(text))


def _normalise_key_action(entry) -> tuple[str, str | None, object] | None:
    if not isinstance(entry, (tuple, list)):
        return None
    fn = next((x for x in entry if callable(x)), None)
    strings = [x for x in entry if isinstance(x, str)]
    if not strings:
        return None
    shortcut = next((s for s in strings if _is_shortcut(s)), None)
    names = [s for s in strings if s is not shortcut and not re.match(r"^[a-z_]+\.[a-z_.]+$", s)]
    name = names[0] if names else strings[0]
    return name, shortcut, fn


def _existing_shortcuts(window) -> set[str]:
    from PySide6.QtGui import QAction, QShortcut

    taken: set[str] = set()
    for act in window.findChildren(QAction):
        for seq in act.shortcuts():
            text = seq.toString()
            if text:
                taken.add(text)
        label = act.text()
        if "\t" in label:
            taken.add(label.split("\t", 1)[1].strip())
    for sc in window.findChildren(QShortcut):
        text = sc.key().toString()
        if text:
            taken.add(text)
    return taken


def _allowed(shortcut: str, used: set[str]) -> bool:
    if shortcut in used or shortcut in RESERVED_SHORTCUTS:
        return False
    parts = shortcut.split("+")
    return "Ctrl" in parts[:-1] or "Alt" in parts[:-1]


def _regroup(tree: dict) -> dict:
    out: dict = {}
    for title, node in tree.items():
        top, sub = TOP_MENUS.get(title, ("Extensions", title))
        target = out.setdefault(top, {})
        if sub is None:
            for key, value in node.items():
                target[key] = value
        else:
            target.setdefault(("sub", sub), {}).update(node)
    return {k: out[k] for k in ("Materials", "UV", "Sculpt", "Animate", "Render", "Extensions") if k in out}


def _safe(fn):
    def run():
        try:
            return fn()
        except Exception:
            traceback.print_exc(file=sys.stderr)
            return None

    return run


def _tree(commands: list, shortcuts: dict[str, str]) -> dict:
    root: dict = {}
    for path, fn in commands:
        path = tuple(path)
        if len(path) < 2:
            continue
        node = root.setdefault(path[0], {})
        for part in path[1:-1]:
            node = node.setdefault(("sub", part), {})
        node[("item", path[-1])] = (fn, shortcuts.pop(path[-1], None))
    return root


def _entries(node: dict) -> list:
    out = []
    for key, value in node.items():
        kind, label = key
        if kind == "sub":
            out.append((label, _entries(value)))
        else:
            fn, shortcut = value
            out.append((label, _safe(fn), shortcut))
    return out


def _load(name: str, module: str):
    try:
        return importlib.import_module(module)
    except Exception:
        report["failed"][name] = traceback.format_exc()
        return None


def _call(mod, attr: str) -> list:
    fn = getattr(mod, attr, None)
    if fn is None:
        return []
    try:
        return list(fn())
    except Exception:
        report["failed"].setdefault(mod.__name__, traceback.format_exc())
        return []


def _make(factory, scene):
    try:
        return factory(scene)
    except TypeError:
        return factory()


def _page_widget(titles: list[str], factories: dict, scene):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QSplitter

    split = QSplitter(Qt.Orientation.Horizontal)
    split.setChildrenCollapsible(False)
    for title in titles:
        factory = factories.get(title)
        if factory is None:
            continue
        widget = _make(factory, scene)
        widget.setWindowTitle(title)
        split.addWidget(widget)
    if split.count():
        split.setStretchFactor(0, 2)
    return split


def install(window) -> dict:
    from quartz_studio.scene import get_scene

    try:
        from quartz_studio.ext import icon_overrides
        report["icons"] = icon_overrides.apply()
    except Exception:
        report["failed"]["icons"] = traceback.format_exc()
    scene = get_scene()
    if getattr(window, "_ext_installed", False):
        return report
    window._ext_installed = True
    taken = _existing_shortcuts(window)
    all_commands: list = []
    factories: dict = {}
    areas: dict = {}
    layouts: dict[str, list[str]] = {}
    actions: list = []
    for name, module in PACKAGES:
        mod = _load(name, module)
        if mod is None:
            continue
        all_commands.extend(_call(mod, "commands"))
        for title, factory, area in _call(mod, "docks"):
            factories.setdefault(title, factory)
            areas.setdefault(title, DOCK_AREAS.get(title, area if area in ("left", "right", "bottom") else "right"))
        for layout, titles in _call(mod, "pages"):
            layouts.setdefault(layout, list(titles))
        for entry in _call(mod, "key_actions"):
            norm = _normalise_key_action(entry)
            if norm is not None:
                actions.append(norm + (name,))
        report["installed"].append(name)

    shortcuts: dict[str, str] = {}
    extra_actions: list = []
    used = set(taken)
    for label, shortcut, fn, _pkg in actions:
        if shortcut and not _allowed(shortcut, used):
            report["skipped_shortcuts"].append((label, shortcut))
            shortcut = None
        if shortcut:
            used.add(shortcut)
            report["shortcuts"].append((label, shortcut))
        shortcuts[label] = shortcut
        if fn is not None:
            extra_actions.append((label, fn, _pkg))

    command_labels = {tuple(p)[-1] for p, _f in all_commands}
    for label, fn, pkg in extra_actions:
        if label not in command_labels:
            all_commands.append(((PACKAGE_MENU.get(pkg, "Extensions"), label), fn))
            command_labels.add(label)
    tree = _regroup(_tree(all_commands, dict(shortcuts)))

    bar = window.menu_bar
    for title, node in tree.items():
        entries = _entries(node)
        if not entries:
            continue
        try:
            if title in bar.titles():
                bar.add_entries(title, entries)
            else:
                bar.add_menu(title, entries)
            report["menus"].append(title)
        except Exception:
            report["failed"][f"menu:{title}"] = traceback.format_exc()

    dock_ids: dict[str, str] = {}
    for title, factory in factories.items():
        dock_id = f"ext_{slug(title)}"
        try:
            widget = _make(factory, scene)
            window.add_dock(dock_id, title, widget, areas[title])
            window.set_dock_visible(dock_id, False)
            dock_ids[title] = dock_id
            report["docks"].append((dock_id, title, areas[title]))
        except Exception:
            report["failed"][f"dock:{title}"] = traceback.format_exc()

    page_ids: dict[str, str] = {}
    for layout in PAGE_LAYOUTS:
        titles = layouts.get(layout)
        if not titles:
            continue
        page_id = f"ext_{slug(layout)}"
        try:
            window.add_page(page_id, layout, _page_widget(titles, factories, scene))
            page_ids[layout] = page_id
            report["pages"].append((page_id, layout))
        except Exception:
            report["failed"][f"page:{layout}"] = traceback.format_exc()

    def show_layout(layout: str) -> None:
        if layout in page_ids:
            window.show_page(page_ids[layout])
            return
        window.show_page("model")
        wanted = {dock_ids[t] for t in layouts.get(layout, []) if t in dock_ids}
        for dock_id in dock_ids.values():
            window.set_dock_visible(dock_id, dock_id in wanted)

    entries = [("Model", lambda: show_layout("Model"), None)]
    for layout in DOCK_LAYOUTS + PAGE_LAYOUTS:
        if layout in layouts and (layout in page_ids or any(t in dock_ids for t in layouts[layout])):
            entries.append((layout, _safe(lambda l=layout: show_layout(l)), None))
    entries.append(None)
    panels = []
    for title, dock_id in dock_ids.items():
        def toggle(d=dock_id):
            window.set_dock_visible(d, not window.is_dock_visible(d))
        panels.append((title, toggle, None))
    entries.append(("Panels", panels))
    try:
        layout_entry = [None, (LAYOUT_MENU, entries)]
        if "Extensions" in bar.titles():
            bar.add_entries("Extensions", layout_entry)
        else:
            bar.add_menu("Extensions", layout_entry[1:])
            report["menus"].append("Extensions")
    except Exception:
        report["failed"]["menu:Layout"] = traceback.format_exc()
    window.show_ext_layout = show_layout

    _attach_runtime(window, scene)
    return report


def _attach_runtime(window, scene) -> None:
    canvas = getattr(getattr(window, "viewport", None), "canvas", None)
    steps = [
        ("materials.hub", lambda m: m.install_listener()),
        ("scripting", lambda m: m.install_frame_driver(scene)),
    ]
    if canvas is not None:
        steps.append(("sculpt.viewport", lambda m: m.attach_viewport(canvas, scene)))
    for module, fn in steps:
        try:
            fn(importlib.import_module(f"quartz_studio.{module}"))
        except Exception:
            report["failed"][f"runtime:{module}"] = traceback.format_exc()
