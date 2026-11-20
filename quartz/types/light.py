import math
from typing import ClassVar

import numpy as np

from quartz.errors import NotImplementedInQuartz, PropertyTypeError, PropertyValueError
from quartz.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty
from quartz.rna import builtin_struct
from quartz.types.blenddata import IDCollection
from quartz.types.id import ID, register_id_type
from quartz.types.object import register_object_data_type

__all__ = ["LIGHT_TYPES", "Light", "PointLight", "SunLight", "SpotLight", "AreaLight", "BlendDataLights"]

LIGHT_TYPES: tuple[str, ...] = ("POINT", "SUN", "SPOT", "AREA")


def _items(*identifiers):
    return [(i, i, "") for i in identifiers]


def _enum_error(value, items) -> PropertyTypeError:
    listing = ", ".join(repr(i) for i in items)
    return PropertyTypeError(f'enum "{value}" not found in ({listing})')


@builtin_struct
class Light(ID):

    _q_light_type: ClassVar[str] = "POINT"
    q_schema_version: ClassVar[int] = 1

    type: EnumProperty(items=_items(*LIGHT_TYPES), default="POINT", meta={"dirty": "SHADING", "virtual_get": lambda s: s._q_get_type(), "virtual_set": lambda s, v: s._q_set_type(v)})
    use_temperature: BoolProperty(meta={"dirty": 'SHADING'})
    color: FloatVectorProperty(subtype='COLOR', size=3, default=(1.0, 1.0, 1.0), min=0.0, soft_max=1.0, step=10.0, precision=3, meta={"dirty": 'SHADING'})
    temperature: FloatProperty(subtype='COLOR_TEMPERATURE', unit='COLOR_TEMPERATURE', default=6500.0, min=800.0, max=20000.0, step=400.0, precision=1, meta={"dirty": 'SHADING'})
    specular_factor: FloatProperty(subtype='FACTOR', default=1.0, min=0.0, soft_max=1.0, step=0.01, meta={"dirty": 'SHADING'})
    diffuse_factor: FloatProperty(subtype='FACTOR', default=1.0, min=0.0, soft_max=1.0, step=0.01, meta={"dirty": 'SHADING'})
    transmission_factor: FloatProperty(subtype='FACTOR', default=1.0, min=0.0, soft_max=1.0, step=0.01, meta={"dirty": 'SHADING'})
    volume_factor: FloatProperty(subtype='FACTOR', default=1.0, min=0.0, soft_max=1.0, step=0.01, meta={"dirty": 'SHADING'})
    use_custom_distance: BoolProperty(meta={"dirty": 'SHADING'})
    cutoff_distance: FloatProperty(subtype='DISTANCE', unit='LENGTH', default=40.0, min=0.0, soft_min=0.01, soft_max=100.0, step=1.0, meta={"dirty": 'SHADING'})
    use_shadow: BoolProperty(default=True, meta={"dirty": 'SHADING'})
    exposure: FloatProperty(subtype='FACTOR', min=-32.0, max=32.0, soft_min=-10.0, soft_max=10.0, step=1.0, precision=3, meta={"dirty": 'SHADING'})
    normalize: BoolProperty(default=True, options=set(), meta={"dirty": 'SHADING'})
    use_nodes: BoolProperty(options=set(), meta={"dirty": 'SHADING'})

    @classmethod
    def _q_construct(cls, name):
        target = cls
        if target is Light:
            target = PointLight
        return super(Light, target)._q_construct(name)

    def _q_get_type(self) -> str:
        return type(self)._q_light_type

    def _q_set_type(self, value: str) -> None:
        new_cls = _LIGHT_CLASSES[value]
        if type(self) is not new_cls:
            object.__setattr__(self, "__class__", new_cls)

    @property
    def node_tree(self):
        return None

    @property
    def animation_data(self):
        return None

    def inline_shader_nodes(self, *a, **k):
        raise NotImplementedInQuartz("Light.inline_shader_nodes")

    def area(self, matrix_world=None) -> float:
        if matrix_world is None:
            m = np.eye(4)
        else:
            try:
                m = np.array(matrix_world, dtype=np.float64)
            except (TypeError, ValueError) as exc:
                raise PropertyValueError("Light.area(): matrix_world expected a 4x4 matrix") from exc
            if m.shape == (16,):
                m = m.reshape(4, 4)
            if m.shape != (4, 4):
                raise PropertyValueError("Light.area(): matrix_world expected a 4x4 matrix")
        sx, sy, sz = (float(np.linalg.norm(m[:3, i])) for i in range(3))
        kind = type(self)._q_light_type
        if kind == "AREA":
            size = float(self.size)
            size_y = float(self.size_y)
            shape = self.shape
            if shape == "SQUARE":
                base = size * size
            elif shape == "RECTANGLE":
                base = size * size_y
            elif shape == "DISK":
                base = math.pi * (size / 2.0) ** 2
            else:
                base = math.pi * size * size_y / 4.0
            return base * sx * sy
        if kind == "SUN":
            return math.pi * math.tan(float(self.angle) / 2.0) ** 2
        radius = float(self.shadow_soft_size) * (sx + sy + sz) / 3.0
        return 4.0 * math.pi * radius * radius

    def _q_state_get(self) -> dict:
        state = super()._q_state_get()
        state["light_type"] = type(self)._q_light_type
        return state

    def _q_state_set(self, state: dict) -> None:
        kind = state.get("light_type")
        if kind in _LIGHT_CLASSES and type(self) is not _LIGHT_CLASSES[kind]:
            object.__setattr__(self, "__class__", _LIGHT_CLASSES[kind])
        super()._q_state_set(state)


@builtin_struct
class PointLight(Light):

    _q_light_type: ClassVar[str] = "POINT"

    use_soft_falloff: BoolProperty(default=True, meta={"dirty": 'SHADING'})
    energy: FloatProperty(default=10.0, soft_min=0.0, soft_max=1000000.0, step=10.0, precision=3, meta={"dirty": 'SHADING'})
    shadow_buffer_clip_start: FloatProperty(subtype='DISTANCE', unit='LENGTH', default=0.05, min=0.000001, soft_min=0.001, step=10.0, precision=3, meta={"dirty": 'SHADING'})
    shadow_soft_size: FloatProperty(subtype='DISTANCE', unit='LENGTH', min=0.0, soft_max=100.0, step=0.1, precision=3, meta={"dirty": 'SHADING'})
    shadow_filter_radius: FloatProperty(default=1.0, min=0.0, soft_max=5.0, step=1.0, meta={"dirty": 'SHADING'})
    shadow_maximum_resolution: FloatProperty(subtype='DISTANCE', unit='LENGTH', default=0.001, min=0.0, soft_min=0.0001, soft_max=0.02, step=0.05, precision=4, meta={"dirty": 'SHADING'})
    use_shadow_jitter: BoolProperty(meta={"dirty": 'SHADING'})
    shadow_jitter_overblur: FloatProperty(subtype='PERCENTAGE', default=10.0, min=0.0, max=100.0, soft_max=20.0, step=10.0, precision=0, meta={"dirty": 'SHADING'})
    use_absolute_resolution: BoolProperty(meta={"dirty": 'SHADING'})


@builtin_struct
class SunLight(Light):

    _q_light_type: ClassVar[str] = "SUN"

    angle: FloatProperty(subtype='ANGLE', unit='ROTATION', default=0.009180432, min=0.0, max=3.1415927, step=10.0, precision=3, meta={"dirty": 'SHADING'})
    energy: FloatProperty(default=10.0, soft_min=0.0, soft_max=10.0, step=1.0, precision=3, meta={"dirty": 'SHADING'})
    shadow_buffer_clip_start: FloatProperty(subtype='DISTANCE', unit='LENGTH', default=0.05, min=0.000001, soft_min=0.001, step=10.0, precision=3, meta={"dirty": 'SHADING'})
    shadow_soft_size: FloatProperty(subtype='DISTANCE', unit='LENGTH', min=0.0, soft_max=100.0, step=0.1, precision=3, meta={"dirty": 'SHADING'})
    shadow_filter_radius: FloatProperty(default=1.0, min=0.0, soft_max=5.0, step=1.0, meta={"dirty": 'SHADING'})
    shadow_maximum_resolution: FloatProperty(subtype='DISTANCE', unit='LENGTH', default=0.001, min=0.0, soft_min=0.0001, soft_max=0.02, step=0.05, precision=4, meta={"dirty": 'SHADING'})
    use_shadow_jitter: BoolProperty(meta={"dirty": 'SHADING'})
    shadow_jitter_overblur: FloatProperty(subtype='PERCENTAGE', default=10.0, min=0.0, max=100.0, soft_max=20.0, step=10.0, precision=0, meta={"dirty": 'SHADING'})
    shadow_cascade_max_distance: FloatProperty(subtype='DISTANCE', unit='LENGTH', default=200.0, min=0.0, step=10.0, precision=3, meta={"dirty": 'SHADING'})
    shadow_cascade_count: IntProperty(default=4, min=1, max=4, meta={"dirty": 'SHADING'})
    shadow_cascade_exponent: FloatProperty(subtype='FACTOR', default=0.8, min=0.0, max=1.0, step=10.0, precision=3, meta={"dirty": 'SHADING'})
    shadow_cascade_fade: FloatProperty(subtype='FACTOR', default=0.1, min=0.0, max=1.0, step=10.0, precision=3, meta={"dirty": 'SHADING'})


@builtin_struct
class SpotLight(Light):

    _q_light_type: ClassVar[str] = "SPOT"

    energy: FloatProperty(default=10.0, soft_min=0.0, soft_max=1000000.0, step=10.0, precision=3, meta={"dirty": 'SHADING'})
    shadow_buffer_clip_start: FloatProperty(subtype='DISTANCE', unit='LENGTH', default=0.05, min=0.000001, soft_min=0.001, step=10.0, precision=3, meta={"dirty": 'SHADING'})
    shadow_soft_size: FloatProperty(subtype='DISTANCE', unit='LENGTH', min=0.0, soft_max=100.0, step=0.1, precision=3, meta={"dirty": 'SHADING'})
    shadow_filter_radius: FloatProperty(default=1.0, min=0.0, soft_max=5.0, step=1.0, meta={"dirty": 'SHADING'})
    shadow_maximum_resolution: FloatProperty(subtype='DISTANCE', unit='LENGTH', default=0.001, min=0.0, soft_min=0.0001, soft_max=0.02, step=0.05, precision=4, meta={"dirty": 'SHADING'})
    use_shadow_jitter: BoolProperty(meta={"dirty": 'SHADING'})
    shadow_jitter_overblur: FloatProperty(subtype='PERCENTAGE', default=10.0, min=0.0, max=100.0, soft_max=20.0, step=10.0, precision=0, meta={"dirty": 'SHADING'})
    use_absolute_resolution: BoolProperty(meta={"dirty": 'SHADING'})
    use_square: BoolProperty(meta={"dirty": 'SHADING'})
    spot_blend: FloatProperty(default=0.15, min=0.0, max=1.0, step=10.0, precision=3, meta={"dirty": 'SHADING'})
    spot_size: FloatProperty(subtype='ANGLE', unit='ROTATION', default=0.7853982, min=0.017453292, max=3.1415927, step=10.0, precision=3, meta={"dirty": 'SHADING'})
    show_cone: BoolProperty(meta={"dirty": 'SHADING'})
    use_soft_falloff: BoolProperty(default=True, meta={"dirty": 'SHADING'})


@builtin_struct
class AreaLight(Light):

    _q_light_type: ClassVar[str] = "AREA"

    energy: FloatProperty(default=10.0, soft_min=0.0, soft_max=1000000.0, step=10.0, precision=3, meta={"dirty": 'SHADING'})
    shadow_buffer_clip_start: FloatProperty(subtype='DISTANCE', unit='LENGTH', default=0.05, min=0.000001, soft_min=0.001, step=10.0, precision=3, meta={"dirty": 'SHADING'})
    shadow_soft_size: FloatProperty(subtype='DISTANCE', unit='LENGTH', min=0.0, soft_max=100.0, step=0.1, precision=3, meta={"dirty": 'SHADING'})
    shadow_filter_radius: FloatProperty(default=1.0, min=0.0, soft_max=5.0, step=1.0, meta={"dirty": 'SHADING'})
    shadow_maximum_resolution: FloatProperty(subtype='DISTANCE', unit='LENGTH', default=0.001, min=0.0, soft_min=0.0001, soft_max=0.02, step=0.05, precision=4, meta={"dirty": 'SHADING'})
    use_shadow_jitter: BoolProperty(meta={"dirty": 'SHADING'})
    shadow_jitter_overblur: FloatProperty(subtype='PERCENTAGE', default=10.0, min=0.0, max=100.0, soft_max=20.0, step=10.0, precision=0, meta={"dirty": 'SHADING'})
    use_absolute_resolution: BoolProperty(meta={"dirty": 'SHADING'})
    shape: EnumProperty(items=_items('SQUARE', 'RECTANGLE', 'DISK', 'ELLIPSE'), default='SQUARE', meta={"dirty": 'SHADING'})
    size: FloatProperty(subtype='DISTANCE', unit='LENGTH', default=0.25, min=0.0, soft_max=100.0, step=0.1, precision=3, meta={"dirty": 'SHADING'})
    size_y: FloatProperty(subtype='DISTANCE', unit='LENGTH', default=0.25, min=0.0, soft_max=100.0, step=0.1, precision=3, meta={"dirty": 'SHADING'})
    spread: FloatProperty(subtype='ANGLE', unit='ROTATION', default=3.1415927, min=0.0, max=3.1415927, step=10.0, precision=3, meta={"dirty": 'SHADING'})


_LIGHT_CLASSES: dict[str, type] = {"POINT": PointLight, "SUN": SunLight, "SPOT": SpotLight, "AREA": AreaLight}


class BlendDataLights(IDCollection):
    def new(self, name: str, type: str) -> Light:
        if type not in LIGHT_TYPES:
            raise _enum_error(type, LIGHT_TYPES)
        light = IDCollection.new(self, name)
        light._q_set_type(type)
        return light

    def remove(self, light: Light, do_unlink: bool = True, do_id_user: bool = True, do_ui_user: bool = True) -> None:
        IDCollection.remove(self, light, do_unlink, do_id_user, do_ui_user)


register_id_type(Light, id_type="LIGHT", collection="lights", default_name="Light", collection_cls=BlendDataLights)
register_object_data_type(Light, "LIGHT")
