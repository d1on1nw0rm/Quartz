import ast
import importlib.util
from pathlib import Path

_TOOL = Path(__file__).resolve().parent.parent / "tools" / "scan_bpy_usage.py"
_spec = importlib.util.spec_from_file_location("scan_bpy_usage", _TOOL)
sbu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sbu)

SAMPLE = '''
import bpy
import bmesh as bm
from bpy.props import FloatProperty as FP
from bpy.types import Operator
from mathutils import Vector
C = bpy.context

class Base(Operator):
    bl_idname = "x.y"
    bl_label = "Y"

class Child(Base):
    size: FP(default=1.0)
    def execute(self, context):
        layout = self.layout
        row = layout.row()
        row.prop(self, "size")
        bm.new()
        bpy.ops.mesh.primitive_cube_add(size=2)
        v = Vector((1, 2, 3))
        context.scene.frame_set(1)
        C.view_layer.update()
        self.report({"INFO"}, "ok")
        return {"FINISHED"}

def unrelated(op):
    return op.module_name

def menu_func(self, context):
    pass

def register():
    bpy.types.TOPBAR_MT_file_import.append(menu_func)
    bpy.types.Scene.my_prop = FP()
'''


def _scan(src: str) -> "sbu.GroupStats":
    st = sbu.GroupStats("sample", "addon")
    sbu.ModuleScanner(st, set(), set()).scan(ast.parse(src))
    return st


def test_aliases_and_depth():
    st = _scan(SAMPLE)
    assert st.calls["bpy.props.FloatProperty"] == 2
    assert st.calls["bmesh.new"] == 1
    assert st.calls["bpy.ops.mesh.primitive_cube_add"] == 1
    assert st.calls["mathutils.Vector"] == 1
    assert st.refs["bpy.context.view_layer"] == 1
    assert st.refs["bpy.types.TOPBAR_MT_file_import"] == 1
    assert not any(s.startswith("bpy.ops.module_name") for s in st.refs)


def test_implicit_surface_and_rna_extension():
    st = _scan(SAMPLE)
    assert st.layout_attrs["row"] == 1
    assert st.layout_attrs["prop"] == 1
    assert st.context_attrs["scene"] == 1
    assert st.self_report == 1
    assert st.rna_extensions["Scene"] == 1


def test_inherited_base_resolution():
    st = _scan(SAMPLE)
    direct, effective, per_base = sbu.resolve_class_bases(st)
    assert direct["bpy.types.Operator"] == 1
    assert effective["bpy.types.Operator"] == 2
    assert per_base["bpy.types.Operator"]["methods"]["execute"] == 1


def test_cut_depth_rules():
    assert sbu.cut_depth("bpy.ops.mesh.primitive_cube_add".split(".")) == 4
    assert sbu.cut_depth("bpy.app.handlers.load_post".split(".")) == 4
    assert sbu.cut_depth("mathutils.geometry.intersect_line_line".split(".")) == 3
    assert sbu.cut_depth("mathutils.Vector".split(".")) == 2
    assert sbu.is_easy_core("bpy.props.EnumProperty")
    assert not sbu.is_easy_core("bpy.ops.object.mode_set")
