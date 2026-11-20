from typing import ClassVar

from quartz.app.settings import settings
from quartz.errors import NotImplementedInQuartz
from quartz.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty
from quartz.rna import builtin_struct
from quartz.types.blenddata import IDCollection
from quartz.types.id import ID, register_id_type

__all__ = ["Material", "BlendDataMaterials"]


def _items(*identifiers):
    return [(i, i, "") for i in identifiers]


@builtin_struct
class Material(ID):

    surface_render_method: EnumProperty(items=_items('DITHERED', 'BLENDED'), default='DITHERED', meta={"dirty": 'SHADING'})
    displacement_method: EnumProperty(items=_items('BUMP', 'DISPLACEMENT', 'BOTH'), default='BUMP', meta={"dirty": 'SHADING'})
    blend_method: EnumProperty(items=_items('OPAQUE', 'CLIP', 'HASHED', 'BLEND'), default='OPAQUE', meta={"dirty": 'SHADING'})
    alpha_threshold: FloatProperty(subtype='FACTOR', default=0.5, min=0.0, max=1.0, step=10.0, precision=3, meta={"dirty": 'SHADING'})
    use_transparency_overlap: BoolProperty(default=True, meta={"dirty": 'SHADING'})
    show_transparent_back: BoolProperty(default=True, meta={"dirty": 'SHADING'})
    use_backface_culling: BoolProperty(meta={"dirty": 'SHADING'})
    use_backface_culling_shadow: BoolProperty(meta={"dirty": 'SHADING'})
    use_backface_culling_lightprobe_volume: BoolProperty(default=True, meta={"dirty": 'SHADING'})
    use_transparent_shadow: BoolProperty(default=True, meta={"dirty": 'SHADING'})
    use_raytrace_refraction: BoolProperty(meta={"dirty": 'SHADING'})
    use_screen_refraction: BoolProperty(meta={"dirty": 'SHADING'})
    use_sss_translucency: BoolProperty(meta={"dirty": 'SHADING'})
    refraction_depth: FloatProperty(subtype='DISTANCE', unit='LENGTH', min=0.0, step=10.0, precision=3, meta={"dirty": 'SHADING'})
    thickness_mode: EnumProperty(items=_items('SPHERE', 'SLAB'), default='SPHERE', meta={"dirty": 'SHADING'})
    use_thickness_from_shadow: BoolProperty(meta={"dirty": 'SHADING'})
    volume_intersection_method: EnumProperty(items=_items('FAST', 'ACCURATE'), default='FAST', meta={"dirty": 'SHADING'})
    max_vertex_displacement: FloatProperty(subtype='DISTANCE', unit='LENGTH', min=0.0, step=10.0, precision=3, meta={"dirty": 'SHADING'})
    preview_render_type: EnumProperty(items=_items('FLAT', 'SPHERE', 'CUBE', 'HAIR', 'SHADERBALL', 'CLOTH', 'FLUID'), default='SPHERE', meta={"dirty": 'SHADING'})
    use_preview_world: BoolProperty(meta={"dirty": 'SHADING'})
    pass_index: IntProperty(subtype='UNSIGNED', min=0, max=32767, meta={"dirty": 'SHADING'})
    use_nodes: BoolProperty(options=set(), meta={"dirty": 'SHADING'})
    paint_active_slot: IntProperty(subtype='UNSIGNED', min=0, max=32767, meta={"dirty": 'SHADING'})
    paint_clone_slot: IntProperty(subtype='UNSIGNED', min=0, max=32767, meta={"dirty": 'SHADING'})
    diffuse_color: FloatVectorProperty(subtype='COLOR', size=4, default=(0.8, 0.8, 0.8, 1.0), min=0.0, soft_max=1.0, step=10.0, precision=3, meta={"dirty": 'SHADING'})
    specular_color: FloatVectorProperty(subtype='COLOR', size=3, default=(1.0, 1.0, 1.0), min=0.0, soft_max=1.0, step=10.0, precision=3, meta={"dirty": 'SHADING'})
    roughness: FloatProperty(subtype='FACTOR', default=0.4, min=0.0, max=1.0, step=10.0, precision=3, meta={"dirty": 'SHADING'})
    specular_intensity: FloatProperty(subtype='FACTOR', default=0.5, min=0.0, max=1.0, step=10.0, precision=3, meta={"dirty": 'SHADING'})
    metallic: FloatProperty(subtype='FACTOR', min=0.0, max=1.0, step=10.0, precision=3, meta={"dirty": 'SHADING'})
    line_color: FloatVectorProperty(subtype='COLOR', size=4, min=0.0, soft_max=1.0, step=10.0, precision=3, meta={"dirty": 'SHADING'})
    line_priority: IntProperty(min=0, max=32767, meta={"dirty": 'SHADING'})
    is_grease_pencil: BoolProperty(meta={"dirty": 'SHADING', "readonly": True})

    q_schema_version: ClassVar[int] = 1

    @property
    def node_tree(self):
        return None

    @property
    def animation_data(self):
        return None

    def inline_shader_nodes(self, *a, **k):
        raise NotImplementedInQuartz("Material.inline_shader_nodes")


class BlendDataMaterials(IDCollection):
    def new(self, name: str) -> Material:
        return IDCollection.new(self, name)

    def create_gpencil_data(self, material):
        raise NotImplementedInQuartz(f"{settings.api_prefix}.data.materials.create_gpencil_data")

    def remove_gpencil_data(self, material):
        raise NotImplementedInQuartz(f"{settings.api_prefix}.data.materials.remove_gpencil_data")

    def remove(self, material: Material, do_unlink: bool = True, do_id_user: bool = True, do_ui_user: bool = True) -> None:
        IDCollection.remove(self, material, do_unlink, do_id_user, do_ui_user)


register_id_type(Material, id_type="MATERIAL", collection="materials", default_name="Material",
                 collection_cls=BlendDataMaterials)
