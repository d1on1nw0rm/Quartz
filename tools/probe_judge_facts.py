import json
import math
import os
import traceback

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "blender_facts_judge.json")
R = {}


def rec(key, fn):
    try:
        R[key] = fn()
    except Exception as exc:
        R[key] = {"__exc__": type(exc).__name__, "msg": str(exc)[:300]}


def r6(seq):
    return [round(float(x), 6) for x in seq]


def mat(m):
    return [r6(row) for row in m]


rec("path.clean_name", lambda: bpy.path.clean_name("my file-1.2 ç!"))
rec("path.display_name", lambda: bpy.path.display_name("my_file-name.blend"))
rec("path.display_name_nolower", lambda: bpy.path.display_name("my_File-NAME"))
rec("path.display_name_from_filepath", lambda: bpy.path.display_name_from_filepath("/a/b/my_file.blend"))
rec("path.ensure_ext_upper", lambda: bpy.path.ensure_ext("a.TXT", ".txt"))
rec("path.ensure_ext_none", lambda: bpy.path.ensure_ext("a", ".txt"))
rec("path.ensure_ext_other", lambda: bpy.path.ensure_ext("a.png", ".txt"))
rec("path.abspath_unsaved", lambda: bpy.path.abspath("//x/y.png"))
rec("path.abspath_plain", lambda: bpy.path.abspath("C:/q/x.png"))
rec("path.basename", lambda: bpy.path.basename("//foo/bar.png"))
rec("path.is_subdir", lambda: [bpy.path.is_subdir("C:/a/b/c", "C:/a"), bpy.path.is_subdir("C:/ab", "C:/a")])
rec("data.filepath_unsaved", lambda: bpy.data.filepath)

def id_order():
    names = ["b", "B", "a", "A", "a10", "a2", "Zed", "_x"]
    made = [bpy.data.meshes.new("QZORD_" + n) for n in names]
    order = [m.name for m in bpy.data.meshes if m.name.startswith("QZORD_")]
    for m in made:
        bpy.data.meshes.remove(m)
    return order
rec("id.order", id_order)

def id_order_rename():
    a = bpy.data.materials.new("QZR_c")
    b = bpy.data.materials.new("QZR_a")
    before = [m.name for m in bpy.data.materials if m.name.startswith("QZR_")]
    a.name = "QZR_0"
    after = [m.name for m in bpy.data.materials if m.name.startswith("QZR_")]
    bpy.data.materials.remove(a)
    bpy.data.materials.remove(b)
    return [before, after]
rec("id.order_after_rename", id_order_rename)

def rename_results():
    a = bpy.data.meshes.new("QZRN")
    b = bpy.data.meshes.new("QZRN2")
    out = []
    try:
        out.append(b.rename("QZRN"))
    except Exception as exc:
        out.append(repr(exc))
    out.append(b.name)
    try:
        out.append(b.rename("QZRN_free"))
    except Exception as exc:
        out.append(repr(exc))
    try:
        out.append(b.rename("QZRN", mode="ALWAYS"))
    except Exception as exc:
        out.append(repr(exc))
    out.append([a.name, b.name])
    bpy.data.meshes.remove(a)
    bpy.data.meshes.remove(b)
    return out
rec("id.rename", rename_results)

def users():
    sc = bpy.context.scene
    out = {}
    w = bpy.data.worlds.new("QZW")
    out["world_new"] = w.users
    old_world = sc.world
    sc.world = w
    out["world_after_scene"] = w.users
    sc.world = old_world
    cam_ob = bpy.data.objects["Camera"]
    out["camera_ob_users"] = cam_ob.users
    out["scene_camera_is"] = sc.camera.name if sc.camera else None
    me = bpy.data.meshes.new("QZU")
    mat_ = bpy.data.materials.new("QZUM")
    out["mat_new"] = mat_.users
    me.materials.append(mat_)
    out["mat_after_mesh_append"] = mat_.users
    p = bpy.data.objects.new("QZP", None)
    c = bpy.data.objects.new("QZC", None)
    out["parent_before"] = p.users
    c.parent = p
    out["parent_after_child"] = p.users
    bpy.types.Scene.qz_ptr = bpy.props.PointerProperty(type=bpy.types.Object)
    out["ptr_before"] = p.users
    sc.qz_ptr = p
    out["ptr_after"] = p.users
    sc.qz_ptr = None
    del bpy.types.Scene.qz_ptr
    col = bpy.data.collections.new("QZCOL")
    out["collection_new"] = col.users
    sc.collection.children.link(col)
    out["collection_linked"] = col.users
    sc.collection.children.unlink(col)
    out["scene_users"] = sc.users
    out["mesh_cube_users"] = bpy.data.meshes["Cube"].users
    out["material_users"] = bpy.data.materials["Material"].users
    for idb, coll in ((c, bpy.data.objects), (p, bpy.data.objects), (me, bpy.data.meshes),
                      (mat_, bpy.data.materials), (w, bpy.data.worlds), (col, bpy.data.collections)):
        coll.remove(idb)
    return out
rec("id.users", users)

def cls_register():
    log = []

    class QZPROBE_PG_reg(bpy.types.PropertyGroup):
        x: bpy.props.IntProperty()

        @classmethod
        def register(cls):
            log.append("register")

        @classmethod
        def unregister(cls):
            log.append("unregister")

    bpy.utils.register_class(QZPROBE_PG_reg)
    bpy.utils.unregister_class(QZPROBE_PG_reg)
    return log
rec("register.classmethod_hooks", cls_register)

def mw_stale():
    ob = bpy.data.objects.new("QZMW", None)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.update()
    ob.location = (1.0, 2.0, 3.0)
    before = r6(ob.matrix_world.translation)
    bpy.context.view_layer.update()
    after = r6(ob.matrix_world.translation)
    ob.matrix_world = Matrix.Translation((5.0, 0.0, 0.0))
    loc_after_set = r6(ob.location)
    p = bpy.data.objects.new("QZMWP", None)
    bpy.context.scene.collection.objects.link(p)
    p.location = (10.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    ob.parent = p
    child_world_no_update = r6(ob.matrix_world.translation)
    bpy.context.view_layer.update()
    child_world_after_update = r6(ob.matrix_world.translation)
    mpi = mat(ob.matrix_parent_inverse)
    bpy.data.objects.remove(ob)
    bpy.data.objects.remove(p)
    return {"before_update": before, "after_update": after, "loc_after_set_world": loc_after_set,
            "child_world_no_update": child_world_no_update,
            "child_world_after_update": child_world_after_update, "parent_inverse": mpi}
rec("object.matrix_world", mw_stale)

rec("math.euler_xyz", lambda: mat(Euler((0.1, 0.2, 0.3), "XYZ").to_matrix()))
rec("math.euler_zyx", lambda: mat(Euler((0.1, 0.2, 0.3), "ZYX").to_matrix()))
rec("math.quat_from_euler", lambda: r6(Euler((0.1, 0.2, 0.3), "XYZ").to_quaternion()))
rec("math.float32", lambda: Vector((0.1, 0.0, 0.0)).x)
rec("math.repr_vector", lambda: repr(Vector((1.0, 2.5, -3.0))))
rec("math.str_vector", lambda: str(Vector((1.0, 2.5, -3.0))))
rec("math.repr_matrix", lambda: repr(Matrix.Identity(3)))
rec("math.repr_euler", lambda: repr(Euler((0.1, 0.2, 0.3))))
rec("math.repr_quat", lambda: repr(Quaternion((1.0, 0.0, 0.0, 0.0))))
rec("math.mat_vec3", lambda: r6(Matrix.Translation((1, 2, 3)) @ Vector((1, 1, 1))))
rec("math.vec_mat", lambda: r6(Vector((1, 0, 0)) @ Matrix.Rotation(math.pi / 2, 3, "Z")))
rec("math.rot_z", lambda: mat(Matrix.Rotation(math.pi / 2, 3, "Z")))
rec("math.vec_mul_vec", lambda: r6(Vector((1, 2, 3)) * Vector((2, 3, 4))))
rec("math.vec_matmul_vec", lambda: Vector((1, 2, 3)) @ Vector((2, 3, 4)))
rec("math.vector_hash", lambda: hash(Vector((1, 2, 3))))
rec("math.vector_eq_tuple", lambda: Vector((1, 2, 3)) == (1, 2, 3))
rec("math.decompose", lambda: [r6(x) for x in Matrix.LocRotScale((1, 2, 3), Euler((0.1, 0.2, 0.3)), (2, 2, 2)).decompose()])
rec("math.to_track_quat", lambda: r6(Vector((0, 1, 0)).to_track_quat("Z", "Y")))
rec("math.quat_axis_angle", lambda: r6(Quaternion((0, 0, 1), math.pi / 2)))
rec("math.color_hsv", lambda: r6(__import__("mathutils").Color((1.0, 0.5, 0.0)).hsv))
rec("math.length_vec2", lambda: Vector((3, 4)).length)
rec("math.cross2", lambda: Vector((1, 0)).cross(Vector((0, 1))))
rec("math.matrix_default", lambda: mat(Matrix()))
rec("math.vector_default", lambda: r6(Vector()))

def obj_defaults():
    ob = bpy.data.objects.new("QZD", None)
    out = {
        "rotation_quaternion": r6(ob.rotation_quaternion),
        "rotation_axis_angle": r6(ob.rotation_axis_angle),
        "rotation_mode": ob.rotation_mode,
        "empty_display_type": ob.empty_display_type,
        "empty_display_size": ob.empty_display_size,
        "display_type": ob.display_type,
        "repr": repr(ob),
        "location_is_same_obj": ob.location is ob.location,
        "location_type": type(ob.location).__name__,
        "location_owner_is_ob": ob.location.owner == ob,
        "dimensions": r6(ob.dimensions),
        "color": r6(ob.color),
    }
    try:
        ob.qz_unknown_attr = 1
        out["unknown_attr_assign"] = "ok"
    except Exception as exc:
        out["unknown_attr_assign"] = type(exc).__name__ + ": " + str(exc)[:200]
    try:
        ob.rotation_mode = "NOPE"
    except Exception as exc:
        out["bad_enum_assign"] = type(exc).__name__ + ": " + str(exc)[:200]
    try:
        ob.location = (1, 2)
    except Exception as exc:
        out["bad_len_assign"] = type(exc).__name__ + ": " + str(exc)[:200]
    try:
        ob.type = "MESH"
    except Exception as exc:
        out["type_assign"] = type(exc).__name__ + ": " + str(exc)[:200]
    ob.rotation_mode = "QUATERNION"
    out["euler_order_when_quat"] = ob.rotation_euler.order
    ob.rotation_mode = "ZYX"
    out["euler_order_when_zyx"] = ob.rotation_euler.order
    bpy.data.objects.remove(ob)
    return out
rec("object.defaults", obj_defaults)

def pg_unknown_attr():
    class QZPROBE_PG_attr(bpy.types.PropertyGroup):
        x: bpy.props.IntProperty()
    bpy.utils.register_class(QZPROBE_PG_attr)
    bpy.types.Scene.qz_attr_pg = bpy.props.PointerProperty(type=QZPROBE_PG_attr)
    out = {}
    pg = bpy.context.scene.qz_attr_pg
    try:
        pg.not_declared = 3
        out["pg_unknown_attr"] = "ok"
    except Exception as exc:
        out["pg_unknown_attr"] = type(exc).__name__ + ": " + str(exc)[:200]
    try:
        pg.x = True
        out["int_from_bool"] = pg.x
    except Exception as exc:
        out["int_from_bool"] = type(exc).__name__ + ": " + str(exc)[:200]
    try:
        pg.x = 2.0
        out["int_from_float"] = pg.x
    except Exception as exc:
        out["int_from_float"] = type(exc).__name__ + ": " + str(exc)[:200]
    out["pg_repr"] = repr(pg)
    del bpy.types.Scene.qz_attr_pg
    bpy.utils.unregister_class(QZPROBE_PG_attr)
    return out
rec("props.pg_attrs", pg_unknown_attr)

def float_prop_types():
    bpy.types.Scene.qz_f = bpy.props.FloatProperty()
    bpy.types.Scene.qz_s = bpy.props.StringProperty(maxlen=5)
    bpy.types.Scene.qz_b = bpy.props.BoolProperty()
    sc = bpy.context.scene
    out = {}
    sc.qz_f = 3
    out["float_from_int"] = sc.qz_f
    sc.qz_f = 0.1
    out["float_value_0_1"] = sc.qz_f
    try:
        sc.qz_f = "x"
    except Exception as exc:
        out["float_from_str"] = type(exc).__name__
    sc.qz_s = "ÃÃÃÃÃÃ"
    out["string_maxlen_multibyte"] = sc.qz_s
    try:
        sc.qz_b = 1
        out["bool_from_int"] = sc.qz_b
    except Exception as exc:
        out["bool_from_int"] = type(exc).__name__ + ": " + str(exc)[:200]
    try:
        sc.qz_b = 2
        out["bool_from_int2"] = sc.qz_b
    except Exception as exc:
        out["bool_from_int2"] = type(exc).__name__ + ": " + str(exc)[:200]
    del bpy.types.Scene.qz_f
    del bpy.types.Scene.qz_s
    del bpy.types.Scene.qz_b
    return out
rec("props.scalar_coercion", float_prop_types)

def enum_get_set():
    log = []
    store = {"v": 1}

    def g(self):
        log.append(("get",))
        return store["v"]

    def s(self, value):
        log.append(("set", value))
        store["v"] = value

    bpy.types.Scene.qz_e = bpy.props.EnumProperty(items=[("A", "a", ""), ("B", "b", ""), ("C", "c", "", 0, 7)], get=g, set=s)
    sc = bpy.context.scene
    out = {"read": sc.qz_e}
    sc.qz_e = "C"
    out["after_set"] = sc.qz_e
    out["log"] = log
    del bpy.types.Scene.qz_e
    return out
rec("props.enum_get_set", enum_get_set)

def factory():
    cam = bpy.data.objects["Camera"]
    light = bpy.data.objects["Light"]
    cube = bpy.data.objects["Cube"]
    me = cube.data
    return {
        "camera_rot": r6(cam.rotation_euler), "camera_scale": r6(cam.scale),
        "camera_lens": cam.data.lens, "camera_sensor": cam.data.sensor_width,
        "camera_clip": [cam.data.clip_start, cam.data.clip_end], "camera_type": cam.data.type,
        "light_rot": r6(light.rotation_euler), "light_type": light.data.type,
        "light_energy": light.data.energy, "light_radius": light.data.shadow_soft_size,
        "light_color": r6(light.data.color),
        "cube_verts": [r6(v.co) for v in me.vertices],
        "cube_faces": [list(p.vertices) for p in me.polygons],
        "cube_edges": [list(e.vertices) for e in me.edges],
        "cube_material_slots": [s.material.name if s.material else None for s in cube.material_slots],
        "cube_use_smooth": [p.use_smooth for p in me.polygons],
        "world_color": r6(bpy.data.worlds["World"].color),
        "scene_camera": bpy.context.scene.camera.name,
        "scene_world": bpy.context.scene.world.name,
        "render_res": [bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y,
                       bpy.context.scene.render.resolution_percentage, bpy.context.scene.render.fps],
        "view_layer_name": bpy.context.view_layer.name,
        "selected": [o.name for o in bpy.context.selected_objects],
        "wm_name": bpy.context.window_manager.name,
        "screen_name": bpy.context.screen.name,
        "workspace_name": bpy.context.workspace.name,
        "material_diffuse": r6(bpy.data.materials["Material"].diffuse_color),
        "material_users": bpy.data.materials["Material"].users,
        "dots_users": bpy.data.materials["Dots Stroke"].users,
        "uv_first4": [r6(d.uv) for d in list(me.uv_layers["UVMap"].data)[:4]],
        "cursor": r6(bpy.context.scene.cursor.location),
        "collection_children": [c.name for c in bpy.context.scene.collection.children],
        "scene_objects": [o.name for o in bpy.context.scene.objects],
        "view_layer_objects": [o.name for o in bpy.context.view_layer.objects],
    }
rec("factory", factory)

def primitives():
    out = {}
    for op in ("plane", "cube", "circle", "uv_sphere", "ico_sphere", "cylinder", "cone", "grid", "torus"):
        getattr(bpy.ops.mesh, "primitive_%s_add" % op)()
        ob = bpy.context.active_object
        me = ob.data
        out[op] = {"v": len(me.vertices), "e": len(me.edges), "f": len(me.polygons), "l": len(me.loops),
                   "name": ob.name, "mesh": me.name,
                   "bbox": [r6(min(v.co[i] for v in me.vertices) for i in range(3)),
                            r6(max(v.co[i] for v in me.vertices) for i in range(3))],
                   "uv": [uv.name for uv in me.uv_layers], "smooth": any(p.use_smooth for p in me.polygons)}
        bpy.data.objects.remove(ob)
        bpy.data.meshes.remove(me)
    return out
rec("primitives", primitives)

def modes():
    out = {}
    cube = bpy.data.objects["Cube"]
    bpy.context.view_layer.objects.active = cube
    bpy.ops.object.mode_set(mode="EDIT")
    out["context_mode_edit"] = bpy.context.mode
    out["objects_in_mode"] = [o.name for o in bpy.context.objects_in_mode]
    out["mesh_is_editmode"] = cube.data.is_editmode
    bpy.ops.object.mode_set(mode="OBJECT")
    out["context_mode_object"] = bpy.context.mode
    try:
        bpy.ops.object.mode_set(mode="POSE")
        out["pose_on_mesh"] = "ok"
    except Exception as exc:
        out["pose_on_mesh"] = type(exc).__name__ + ": " + str(exc)[:200]
    bpy.ops.object.mode_set(mode="EDIT", toggle=True)
    out["toggle_edit"] = bpy.context.mode
    bpy.ops.object.mode_set(mode="EDIT", toggle=True)
    out["toggle_back"] = bpy.context.mode
    return out
rec("modes", modes)

def select_all():
    out = {}
    bpy.ops.object.select_all(action="TOGGLE")
    out["after_toggle_1"] = sorted(o.name for o in bpy.context.selected_objects)
    bpy.ops.object.select_all(action="TOGGLE")
    out["after_toggle_2"] = sorted(o.name for o in bpy.context.selected_objects)
    bpy.ops.object.select_all(action="INVERT")
    out["after_invert"] = sorted(o.name for o in bpy.context.selected_objects)
    bpy.ops.object.select_all(action="DESELECT")
    bpy.data.objects["Cube"].select_set(True)
    return out
rec("ops.select_all", select_all)

def dup():
    cube = bpy.data.objects["Cube"]
    for o in bpy.context.selected_objects:
        o.select_set(False)
    cube.select_set(True)
    bpy.context.view_layer.objects.active = cube
    r = bpy.ops.object.duplicate()
    new = bpy.context.active_object
    out = {"ret": sorted(r), "new_name": new.name, "new_mesh": new.data.name,
           "selected": sorted(o.name for o in bpy.context.selected_objects),
           "cube_selected": cube.select_get()}
    r2 = bpy.ops.object.duplicate(linked=True)
    new2 = bpy.context.active_object
    out["linked_mesh"] = new2.data.name
    for o in (new, new2):
        me = o.data
        bpy.data.objects.remove(o)
    bpy.data.meshes.remove(bpy.data.meshes[out["new_mesh"]])
    cube.select_set(True)
    bpy.context.view_layer.objects.active = cube
    return out
rec("ops.duplicate", dup)

def contexts():
    c = bpy.app.translations.contexts
    names = [n for n in dir(c) if not n.startswith("_") and n not in ("count", "index", "n_fields", "n_sequence_fields", "n_unnamed_fields")]
    return {n: getattr(c, n) for n in names}
rec("translations.contexts", contexts)
rec("translations.locale", lambda: bpy.app.translations.locale)
rec("translations.pgettext_none_ctx", lambda: bpy.app.translations.pgettext_iface("Add", None))

def op_defaults():
    class QZPROBE_OT_defaults(bpy.types.Operator):
        bl_idname = "qzprobe.defaults"
        bl_label = "Defaults"
    bpy.utils.register_class(QZPROBE_OT_defaults)
    out = {"bl_translation_context": QZPROBE_OT_defaults.bl_translation_context,
           "bl_options": sorted(getattr(QZPROBE_OT_defaults, "bl_options", set())),
           "bl_description": QZPROBE_OT_defaults.bl_description,
           "rna_type_name": QZPROBE_OT_defaults.bl_rna.identifier,
           "call_without_execute": None}
    try:
        out["call_without_execute"] = sorted(bpy.ops.qzprobe.defaults())
    except Exception as exc:
        out["call_without_execute"] = type(exc).__name__ + ": " + str(exc)[:200]
    out["dir_has_qzprobe"] = "qzprobe" in dir(bpy.ops)
    out["op_repr"] = repr(bpy.ops.qzprobe.defaults)
    bpy.utils.unregister_class(QZPROBE_OT_defaults)
    return out
rec("ops.defaults", op_defaults)

rec("utils.escape_identifier", lambda: bpy.utils.escape_identifier('a"b\\c'))
rec("utils.flip_name", lambda: [bpy.utils.flip_name("Hand.L"), bpy.utils.flip_name("left_arm"), bpy.utils.flip_name("Foot.R.001"), bpy.utils.flip_name("Foot.R.001", strip_digits=True)])
rec("utils.smpte", lambda: bpy.utils.smpte_from_frame(100))
rec("utils.time_from_frame", lambda: str(bpy.utils.time_from_frame(48)))

rec("repr.data_objects", lambda: repr(bpy.data.objects))
rec("repr.mesh", lambda: repr(bpy.data.meshes["Cube"]))
rec("repr.vertex", lambda: repr(bpy.data.meshes["Cube"].vertices[0]))
rec("repr.scene_collection", lambda: repr(bpy.context.scene.collection))
rec("object.select_get_unlinked", lambda: bpy.data.objects.new("QZSG", None).select_get())

def light_swap():
    l = bpy.data.lights.new("QZL", "POINT")
    out = {"cls_point": type(l).__name__, "energy": l.energy}
    l.type = "SUN"
    out["cls_after"] = type(l).__name__
    out["energy_after"] = l.energy
    out["has_angle"] = hasattr(l, "angle")
    bpy.data.lights.remove(l)
    return out
rec("light.swap", light_swap)

def mesh_shade():
    me = bpy.data.meshes.new("QZSH")
    me.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0)], [], [(0, 1, 2)])
    out = {"smooth_default": me.polygons[0].use_smooth, "has_shade_flat": hasattr(me, "shade_flat"),
           "has_shade_smooth": hasattr(me, "shade_smooth"), "edges": [list(e.vertices) for e in me.edges]}
    me2 = bpy.data.meshes.new("QZSH2")
    me2.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0)], [], [(0, 1, 2)], shade_flat=False)
    out["smooth_shade_flat_false"] = me2.polygons[0].use_smooth
    bpy.data.meshes.remove(me)
    bpy.data.meshes.remove(me2)
    return out
rec("mesh.shade", mesh_shade)

with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(R, fh, indent=1, ensure_ascii=False, default=str)
print("JUDGE_PROBE_WRITTEN", OUT)
