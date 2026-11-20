from quartz.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, PointerProperty
from quartz.rna import Struct, builtin_struct
from quartz.types.blenddata import IDCollection
from quartz.types.id import ID, register_id_type
import quartz.types.object

__all__ = ["WorldLighting", "WorldMistSettings", "World", "BlendDataWorlds"]

_S = {"dirty": "SHADING"}


@builtin_struct
class WorldLighting(Struct):

    _q_strict_attrs = True

    use_ambient_occlusion: BoolProperty(meta=_S)
    ao_factor: FloatProperty(default=1.0, min=0.0, soft_max=1.0, meta=_S)
    distance: FloatProperty(subtype="DISTANCE", unit="LENGTH", default=10.0, min=0.0, meta=_S)


@builtin_struct
class WorldMistSettings(Struct):

    _q_strict_attrs = True

    use_mist: BoolProperty(meta=_S)
    intensity: FloatProperty(default=0.0, min=0.0, meta=_S)
    start: FloatProperty(subtype="DISTANCE", unit="LENGTH", default=5.0, min=0.0, meta=_S)
    depth: FloatProperty(subtype="DISTANCE", unit="LENGTH", default=25.0, min=0.0, meta=_S)
    height: FloatProperty(subtype="DISTANCE", unit="LENGTH", default=0.0, min=0.0, meta=_S)
    falloff: EnumProperty(items=[(t, t, "") for t in ("QUADRATIC", "LINEAR", "INVERSE_QUADRATIC")],
                          default="QUADRATIC", meta=_S)


@builtin_struct
class World(ID):

    _q_strict_attrs = True

    color: FloatVectorProperty(subtype="COLOR", size=3, default=(0.05, 0.05, 0.05), min=0.0, soft_max=1.0,
                               step=10.0, precision=3, meta=_S)
    use_nodes: BoolProperty(options=set(), meta=_S)
    light_settings: PointerProperty(type=WorldLighting, meta=_S)
    mist_settings: PointerProperty(type=WorldMistSettings, meta=_S)

    @property
    def node_tree(self):
        return None

    @property
    def animation_data(self):
        return None


class BlendDataWorlds(IDCollection):

    def new(self, name: str) -> World:
        return super().new(name)

    def remove(self, world: World, do_unlink: bool = True, do_id_user: bool = True, do_ui_user: bool = True) -> None:
        super().remove(world, do_unlink, do_id_user, do_ui_user)


register_id_type(World, id_type="WORLD", collection="worlds", default_name="World", collection_cls=BlendDataWorlds)
