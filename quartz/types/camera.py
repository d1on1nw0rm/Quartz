import math
from typing import ClassVar

from quartz.math import Vector
from quartz.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, PointerProperty, StringProperty
from quartz.rna import IDRef, Struct, builtin_struct
from quartz.types.blenddata import IDCollection
from quartz.types.id import ID, register_id_type
from quartz.types.object import Object, register_object_data_type

__all__ = ["Camera", "CameraDOFSettings", "BlendDataCameras"]


def _items(*identifiers):
    return [(i, i, "") for i in identifiers]


def _never_none(cls, *names) -> None:
    for name in names:
        cls.__dict__[name].is_never_none = True


@builtin_struct
class CameraDOFSettings(Struct):

    _q_strict_attrs = True

    use_dof: BoolProperty()
    focus_object: PointerProperty(type=Object, options=set(), meta={"counts_user": False})
    focus_subtarget: StringProperty(maxlen=64, options=set())
    focus_distance: FloatProperty(subtype='DISTANCE', unit='LENGTH', default=10.0, min=0.0, soft_max=5000.0, step=1.0, precision=4)
    aperture_fstop: FloatProperty(default=2.8, min=0.0, soft_min=0.1, soft_max=128.0, step=10.0, precision=1)
    aperture_blades: IntProperty(min=0, max=16)
    aperture_rotation: FloatProperty(subtype='ANGLE', unit='ROTATION', min=-3.1415927, max=3.1415927, step=10.0, precision=3)
    aperture_ratio: FloatProperty(default=1.0, min=0.01, soft_max=2.0, step=0.1, precision=3)


_never_none(CameraDOFSettings, "focus_subtarget")


@builtin_struct
class Camera(ID):

    type: EnumProperty(items=_items('PERSP', 'ORTHO', 'PANO', 'CUSTOM'), default='PERSP')
    sensor_fit: EnumProperty(items=_items('AUTO', 'HORIZONTAL', 'VERTICAL'), default='AUTO')
    passepartout_alpha: FloatProperty(subtype='FACTOR', default=0.5, min=0.0, max=1.0, step=10.0, precision=3)
    angle_x: FloatProperty(subtype='ANGLE', unit='ROTATION', min=0.006405358, max=3.0167491, step=10.0, precision=3, options=set(), meta={"virtual_get": lambda s: s._q_get_angle_x(), "virtual_set": lambda s, v: s._q_set_angle_x(v)})
    angle_y: FloatProperty(subtype='ANGLE', unit='ROTATION', min=0.006405358, max=3.0167491, step=10.0, precision=3, options=set(), meta={"virtual_get": lambda s: s._q_get_angle_y(), "virtual_set": lambda s, v: s._q_set_angle_y(v)})
    angle: FloatProperty(subtype='ANGLE', unit='ROTATION', default=0.6911504, min=0.006405358, max=3.0167491, step=10.0, precision=3, options=set(), meta={"virtual_get": lambda s: s._q_get_angle(), "virtual_set": lambda s, v: s._q_set_angle(v)})
    clip_start: FloatProperty(subtype='DISTANCE', unit='LENGTH', default=0.1, min=0.000001, soft_min=0.001, step=10.0, precision=3)
    clip_end: FloatProperty(subtype='DISTANCE', unit='LENGTH', default=1000.0, min=0.000001, soft_min=0.001, step=10.0, precision=3)
    lens: FloatProperty(subtype='DISTANCE_CAMERA', unit='CAMERA', default=50.0, min=1.0, soft_max=5000.0, step=100.0, precision=4)
    sensor_width: FloatProperty(subtype='DISTANCE_CAMERA', unit='CAMERA', default=36.0, min=1.0, soft_max=100.0, step=100.0, precision=4)
    sensor_height: FloatProperty(subtype='DISTANCE_CAMERA', unit='CAMERA', default=24.0, min=1.0, soft_max=100.0, step=100.0, precision=4)
    ortho_scale: FloatProperty(default=6.0, min=0.0, soft_min=0.001, soft_max=10000.0, step=10.0, precision=3)
    display_size: FloatProperty(subtype='DISTANCE', unit='LENGTH', default=1.0, min=0.01, max=1000.0, soft_max=100.0, step=1.0)
    shift_x: FloatProperty(soft_min=-2.0, soft_max=2.0, step=1.0, precision=3)
    shift_y: FloatProperty(soft_min=-2.0, soft_max=2.0, step=1.0, precision=3)
    show_limits: BoolProperty()
    show_mist: BoolProperty()
    show_passepartout: BoolProperty(default=True)
    show_safe_areas: BoolProperty()
    show_safe_center: BoolProperty()
    show_name: BoolProperty()
    show_sensor: BoolProperty()
    show_background_images: BoolProperty()
    lens_unit: EnumProperty(items=_items('MILLIMETERS', 'FOV'), default='MILLIMETERS')
    composition_guide_color: FloatVectorProperty(subtype='COLOR', size=4, default=(0.5, 0.5, 0.5, 1.0), min=0.0, soft_max=1.0, step=10.0, precision=3)
    show_composition_center: BoolProperty()
    show_composition_center_diagonal: BoolProperty()
    show_composition_thirds: BoolProperty()
    show_composition_golden: BoolProperty()
    show_composition_golden_tria_a: BoolProperty()
    show_composition_golden_tria_b: BoolProperty()
    show_composition_harmony_tri_a: BoolProperty()
    show_composition_harmony_tri_b: BoolProperty()
    panorama_type: EnumProperty(items=_items('EQUIRECTANGULAR', 'EQUIANGULAR_CUBEMAP_FACE', 'MIRRORBALL', 'FISHEYE_EQUIDISTANT', 'FISHEYE_EQUISOLID', 'FISHEYE_LENS_POLYNOMIAL', 'CENTRAL_CYLINDRICAL'), default='FISHEYE_EQUISOLID')
    fisheye_fov: FloatProperty(subtype='ANGLE', unit='ROTATION', default=3.1415927, min=0.1745, max=31.415926, soft_max=6.2831855)
    fisheye_lens: FloatProperty(default=10.5, min=0.01, max=100.0, soft_max=15.0)
    latitude_min: FloatProperty(subtype='ANGLE', unit='ROTATION', default=-1.5707964, min=-1.5707964, max=1.5707964)
    latitude_max: FloatProperty(subtype='ANGLE', unit='ROTATION', default=1.5707964, min=-1.5707964, max=1.5707964)
    longitude_min: FloatProperty(subtype='ANGLE', unit='ROTATION', default=-3.1415927, soft_min=-3.1415927, soft_max=3.1415927)
    longitude_max: FloatProperty(subtype='ANGLE', unit='ROTATION', default=3.1415927, soft_min=-3.1415927, soft_max=3.1415927)
    fisheye_polynomial_k0: FloatProperty(subtype='ANGLE', unit='ROTATION', default=-0.0000117351, step=0.1, precision=6)
    fisheye_polynomial_k1: FloatProperty(subtype='ANGLE', unit='ROTATION', default=-0.019988736, step=0.1, precision=6)
    fisheye_polynomial_k2: FloatProperty(subtype='ANGLE', unit='ROTATION', default=-0.0000033525, step=0.1, precision=6)
    fisheye_polynomial_k3: FloatProperty(subtype='ANGLE', unit='ROTATION', default=0.0000030993, step=0.1, precision=6)
    fisheye_polynomial_k4: FloatProperty(subtype='ANGLE', unit='ROTATION', default=-0.0000000261, step=0.1, precision=6)
    central_cylindrical_range_u_min: FloatProperty(subtype='ANGLE', unit='ROTATION', default=-3.1415927, soft_min=-3.1415927, soft_max=3.1415927)
    central_cylindrical_range_u_max: FloatProperty(subtype='ANGLE', unit='ROTATION', default=3.1415927, soft_min=-3.1415927, soft_max=3.1415927)
    central_cylindrical_range_v_min: FloatProperty(subtype='DISTANCE', unit='LENGTH', default=-1.0, soft_min=-10.0, soft_max=10.0, step=0.1, precision=3)
    central_cylindrical_range_v_max: FloatProperty(subtype='DISTANCE', unit='LENGTH', default=1.0, soft_min=-10.0, soft_max=10.0, step=0.1, precision=3)
    central_cylindrical_radius: FloatProperty(subtype='DISTANCE', unit='LENGTH', default=1.0, min=0.00001, soft_max=10.0, step=0.1, precision=3)
    custom_filepath: StringProperty(subtype='FILE_PATH', maxlen=1024, options=set())
    custom_mode: EnumProperty(items=_items('INTERNAL', 'EXTERNAL'), default='INTERNAL')
    custom_bytecode: StringProperty(options=set())
    custom_bytecode_hash: StringProperty(maxlen=64, options=set())
    dof: PointerProperty(type=CameraDOFSettings, options=set(), meta={"readonly": True})

    q_schema_version: ClassVar[int] = 1

    @property
    def animation_data(self):
        return None

    def _q_sensor(self) -> float:
        return float(self.sensor_height if self.sensor_fit == "VERTICAL" else self.sensor_width)

    @staticmethod
    def _q_angle_for(sensor: float, lens: float) -> float:
        return 2.0 * math.atan(sensor / (2.0 * lens))

    def _q_set_lens_for(self, sensor: float, angle: float) -> None:
        self.lens = sensor / (2.0 * math.tan(float(angle) / 2.0))

    def _q_get_angle(self) -> float:
        return self._q_angle_for(self._q_sensor(), float(self.lens))

    def _q_set_angle(self, value) -> None:
        self._q_set_lens_for(self._q_sensor(), value)

    def _q_get_angle_x(self) -> float:
        return self._q_angle_for(float(self.sensor_width), float(self.lens))

    def _q_set_angle_x(self, value) -> None:
        self._q_set_lens_for(float(self.sensor_width), value)

    def _q_get_angle_y(self) -> float:
        return self._q_angle_for(float(self.sensor_height), float(self.lens))

    def _q_set_angle_y(self, value) -> None:
        self._q_set_lens_for(float(self.sensor_height), value)

    def view_frame(self, scene=None):
        ax, ay = 1.0, 1.0
        fit = self.sensor_fit
        if scene is not None:
            render = scene.render
            rx = float(render.resolution_x) * float(getattr(render, "pixel_aspect_x", 1.0))
            ry = float(render.resolution_y) * float(getattr(render, "pixel_aspect_y", 1.0))
            horizontal = fit == "HORIZONTAL" or (fit == "AUTO" and rx >= ry)
            if horizontal:
                ax, ay = 1.0, (ry / rx if rx else 1.0)
            else:
                ax, ay = (rx / ry if ry else 1.0), 1.0
        if self.type == "ORTHO":
            half = float(self.ortho_scale) / 2.0
            hx, hy = half * ax, half * ay
            dx = float(self.shift_x) * float(self.ortho_scale)
            dy = float(self.shift_y) * float(self.ortho_scale)
            z = -1.0
        else:
            h = 0.5
            sensor = self._q_sensor()
            z = -h * float(self.lens) / (sensor / 2.0)
            hx, hy = h * ax, h * ay
            dx = float(self.shift_x) * 2.0 * h
            dy = float(self.shift_y) * 2.0 * h
        return (
            Vector((hx + dx, hy + dy, z)),
            Vector((hx + dx, -hy + dy, z)),
            Vector((-hx + dx, -hy + dy, z)),
            Vector((-hx + dx, hy + dy, z)),
        )

    def _q_refs(self):
        refs = list(super()._q_refs())
        yield from refs
        dof = self._p.get("dof")
        if dof is None or any(ref.owner is dof for ref in refs):
            return
        target = dof._p.get("focus_object")
        if target is None:
            return
        pdef = CameraDOFSettings.__dict__["focus_object"]

        def clear():
            pdef.write_raw(dof, None)
            dof._q_on_change(pdef)

        def remap(new):
            pdef.write_raw(dof, new)
            dof._q_on_change(pdef)
        yield IDRef(target, dof, "POINTER", False, "CLEAR", clear, remap)


_never_none(Camera, "custom_filepath", "custom_bytecode", "custom_bytecode_hash")


class BlendDataCameras(IDCollection):
    def new(self, name: str) -> Camera:
        return IDCollection.new(self, name)

    def remove(self, camera: Camera, do_unlink: bool = True, do_id_user: bool = True, do_ui_user: bool = True) -> None:
        IDCollection.remove(self, camera, do_unlink, do_id_user, do_ui_user)


register_id_type(Camera, id_type="CAMERA", collection="cameras", default_name="Camera", collection_cls=BlendDataCameras)
register_object_data_type(Camera, "CAMERA")
