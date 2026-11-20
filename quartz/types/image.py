import os
from typing import ClassVar

import numpy as np

from quartz.errors import NotImplementedInQuartz, PropertyTypeError, PropertyValueError
from quartz.path import basename
from quartz.props import BoolProperty, EnumProperty, FloatVectorProperty, IntProperty, IntVectorProperty, StringProperty
from quartz.rna import PropArray, builtin_struct, get_property
from quartz.types.blenddata import IDCollection
from quartz.types.id import ID, register_id_type

__all__ = ["Image", "BlendDataImages"]

_MIN_SIZE = 1
_MAX_SIZE = 65536
_FORMAT_BY_EXT = {
    ".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".exr": "OPEN_EXR", ".hdr": "HDR", ".tga": "TARGA",
    ".tif": "TIFF", ".tiff": "TIFF", ".bmp": "BMP", ".webp": "WEBP",
}


def _items(*identifiers):
    return [(i, i, "") for i in identifiers]


def _never_none(cls, *names) -> None:
    for name in names:
        cls.__dict__[name].is_never_none = True


def _regen(self, context) -> None:
    self._q_regenerate_if_generated()


def _check_size(width, height, where: str) -> tuple[int, int]:
    for label, value in (("width", width), ("height", height)):
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
            raise PropertyTypeError(f"{where}: {label} expected an int type, not {type(value).__name__}")
        if not _MIN_SIZE <= int(value) <= _MAX_SIZE:
            raise PropertyValueError(f"{where}: {label} {int(value)} not in range [{_MIN_SIZE}, {_MAX_SIZE}]")
    return int(width), int(height)


@builtin_struct
class Image(ID):

    filepath: StringProperty(subtype='FILE_PATH', maxlen=1024, options=set())
    filepath_raw: StringProperty(subtype='FILE_PATH', maxlen=1024, options=set())
    file_format: EnumProperty(items=_items('AVIF', 'JPEG', 'OPEN_EXR', 'PNG', 'WEBP', 'BMP', 'CINEON', 'DPX', 'IRIS', 'JPEG2000', 'HDR', 'TARGA', 'TARGA_RAW', 'TIFF', 'OPEN_EXR_MULTILAYER', 'FFMPEG'), default='TARGA')
    source: EnumProperty(items=_items('FILE', 'SEQUENCE', 'MOVIE', 'GENERATED', 'VIEWER', 'TILED'), default='FILE')
    type: EnumProperty(items=_items('IMAGE', 'MULTILAYER', 'UV_TEST', 'RENDER_RESULT', 'COMPOSITING'), default='IMAGE', meta={"virtual_get": lambda s: s._q_get_type()})
    use_view_as_render: BoolProperty()
    use_deinterlace: BoolProperty()
    use_multiview: BoolProperty()
    is_stereo_3d: BoolProperty(meta={"virtual_get": lambda s: s._q_get_is_stereo_3d()})
    is_multiview: BoolProperty(meta={"virtual_get": lambda s: s._q_get_is_multiview()})
    is_dirty: BoolProperty(meta={"virtual_get": lambda s: s._q_get_is_dirty()})
    generated_type: EnumProperty(items=_items('BLANK', 'UV_GRID', 'COLOR_GRID'), default='UV_GRID', options=set(), update=_regen)
    generated_width: IntProperty(subtype='PIXEL', default=1024, min=1, max=65536, options=set(), update=_regen)
    generated_height: IntProperty(subtype='PIXEL', default=1024, min=1, max=65536, options=set(), update=_regen)
    use_generated_float: BoolProperty(options=set(), update=_regen)
    generated_color: FloatVectorProperty(subtype='COLOR_GAMMA', size=4, min=0.0, soft_max=1.0, step=10.0, precision=3, options=set(), update=_regen)
    display_aspect: FloatVectorProperty(subtype='XYZ', size=2, default=(1.0, 1.0), min=0.1, soft_max=5000.0, step=1.0)
    has_data: BoolProperty(meta={"virtual_get": lambda s: s._q_get_has_data()})
    depth: IntProperty(subtype='UNSIGNED', min=0, soft_max=10000, meta={"virtual_get": lambda s: s._q_get_depth()})
    size: IntVectorProperty(subtype='PIXEL', size=2, soft_min=0, soft_max=0, meta={"virtual_get": lambda s: s._q_get_size()})
    resolution: FloatVectorProperty(subtype='XYZ', size=2, soft_min=0.0, soft_max=0.0, step=1.0, precision=3)
    frame_duration: IntProperty(subtype='UNSIGNED', min=0, soft_max=10000, meta={"virtual_get": lambda s: s._q_get_frame_duration()})
    channels: IntProperty(subtype='UNSIGNED', min=0, soft_max=10000, meta={"virtual_get": lambda s: s._q_get_channels()})
    is_float: BoolProperty(meta={"virtual_get": lambda s: s._q_get_is_float()})
    alpha_mode: EnumProperty(items=_items('STRAIGHT', 'PREMUL', 'CHANNEL_PACKED', 'NONE'), default='STRAIGHT')
    use_half_precision: BoolProperty(default=True)
    seam_margin: IntProperty(default=8, min=-32768, max=32767, soft_min=1, soft_max=100)
    views_format: EnumProperty(items=_items('INDIVIDUAL', 'STEREO_3D'), default='INDIVIDUAL')

    q_schema_version: ClassVar[int] = 1

    @classmethod
    def _q_construct(cls, name):
        self = super()._q_construct(name)
        self._q_size = (0, 0)
        self._q_pixels = None
        self._q_float = False
        self._q_alpha = False
        self._q_is_dirty = False
        return self

    def _q_get_type(self) -> str:
        return "IMAGE"

    def _q_get_is_stereo_3d(self) -> bool:
        return False

    def _q_get_is_multiview(self) -> bool:
        return False

    def _q_get_is_dirty(self) -> bool:
        return bool(self._q_is_dirty)

    def _q_get_has_data(self) -> bool:
        return self._q_pixels is not None

    def _q_get_depth(self) -> int:
        if self._q_pixels is None:
            return 0
        if self._q_float:
            return 128 if self._q_alpha else 96
        return 32 if self._q_alpha else 24

    def _q_get_size(self):
        return np.array(self._q_size, dtype=np.int32)

    def _q_get_frame_duration(self) -> int:
        return 0

    def _q_get_channels(self) -> int:
        return 4 if self._q_pixels is not None else 0

    def _q_get_is_float(self) -> bool:
        return bool(self._q_float)

    def _q_fill_generated(self, width: int, height: int) -> None:
        color = np.asarray(get_property(Image, "generated_color").read_raw(self), dtype=np.float32).reshape(4)
        pixels = np.empty((height * width, 4), dtype=np.float32)
        pixels[...] = color
        self._q_size = (int(width), int(height))
        self._q_pixels = pixels.reshape(-1)
        self._q_quantize()

    def _q_regenerate_if_generated(self) -> None:
        if self.source not in ("GENERATED", "TILED"):
            return
        self._q_float = bool(self.use_generated_float)
        self._q_fill_generated(int(self.generated_width), int(self.generated_height))
        self.q_tag("DATA")

    def _q_quantize(self) -> None:
        if self._q_pixels is not None and not self._q_float:
            np.clip(self._q_pixels, 0.0, 1.0, out=self._q_pixels)
            np.multiply(np.round(self._q_pixels * 255.0), 1.0 / 255.0, out=self._q_pixels, casting="unsafe")

    def _q_pixels_written(self) -> None:
        self._q_quantize()
        self._q_is_dirty = True
        self.q_tag("DATA")

    @property
    def pixels(self):
        buf = self._q_pixels if self._q_pixels is not None else np.zeros(0, dtype=np.float32)
        return PropArray(buf, on_write=self._q_pixels_written, owner=self)

    @pixels.setter
    def pixels(self, value) -> None:
        if not isinstance(value, np.ndarray):
            value = list(value)
        values = np.asarray(value, dtype=np.float64).reshape(-1)
        expected = 0 if self._q_pixels is None else int(self._q_pixels.size)
        if values.size != expected:
            raise PropertyValueError(
                f"bpy_struct: item.attr = val: Image.pixels: sequence should contain {expected} items, not {values.size}")
        if self._q_pixels is None:
            return
        self._q_pixels[...] = values.astype(np.float32)
        self._q_pixels_written()

    @property
    def packed_file(self):
        return None

    def scale(self, width: int, height: int, frame: int = 0, tile_index: int = 0) -> None:
        if self._q_pixels is None:
            raise PropertyValueError(f"Image '{self._q_name}' does not have any image data")
        new_w, new_h = _check_size(width, height, "Image.scale()")
        old_w, old_h = self._q_size
        src = self._q_pixels.reshape(old_h, old_w, 4)
        ys = np.minimum(((np.arange(new_h) + 0.5) * old_h / new_h).astype(np.int64), old_h - 1)
        xs = np.minimum(((np.arange(new_w) + 0.5) * old_w / new_w).astype(np.int64), old_w - 1)
        self._q_pixels = np.ascontiguousarray(src[ys][:, xs]).reshape(-1).astype(np.float32)
        self._q_size = (new_w, new_h)
        self._q_is_dirty = True
        self.q_tag("DATA")

    def reload(self) -> None:
        if self.source in ("GENERATED", "TILED"):
            self._q_float = bool(self.use_generated_float)
            self._q_fill_generated(int(self.generated_width), int(self.generated_height))
            self.q_tag("DATA")
        self._q_is_dirty = False

    def update(self) -> None:
        self.q_tag("DATA")

    def filepath_from_user(self, image_user: object = None) -> str:
        return self.filepath

    def gl_free(self) -> None:
        return None

    def buffers_free(self) -> None:
        return None

    def gl_touch(self, *a, **k):
        raise NotImplementedInQuartz("Image.gl_touch")

    def gl_load(self, *a, **k):
        raise NotImplementedInQuartz("Image.gl_load")

    def save(self, *a, **k):
        raise NotImplementedInQuartz("Image.save")

    def save_render(self, *a, **k):
        raise NotImplementedInQuartz("Image.save_render")

    def pack(self, *a, **k):
        raise NotImplementedInQuartz("Image.pack")

    def unpack(self, *a, **k):
        raise NotImplementedInQuartz("Image.unpack")

    def _q_state_get(self) -> dict:
        state = super()._q_state_get()
        state["image_buffer"] = {
            "size": tuple(int(v) for v in self._q_size),
            "pixels": None if self._q_pixels is None else self._q_pixels.copy(),
            "is_float": bool(self._q_float),
            "alpha": bool(self._q_alpha),
            "dirty": bool(self._q_is_dirty),
        }
        return state

    def _q_state_set(self, state: dict) -> None:
        super()._q_state_set(state)
        buf = state.get("image_buffer")
        if buf is not None:
            self._q_size = tuple(int(v) for v in buf.get("size", (0, 0)))
            pixels = buf.get("pixels")
            self._q_pixels = None if pixels is None else np.array(pixels, dtype=np.float32, copy=True).reshape(-1)
            self._q_float = bool(buf.get("is_float", False))
            self._q_alpha = bool(buf.get("alpha", False))
            self._q_is_dirty = bool(buf.get("dirty", False))


_never_none(Image, "filepath", "filepath_raw")


class BlendDataImages(IDCollection):
    def new(self, name: str, width: int, height: int, alpha: bool = False, float_buffer: bool = False,
            stereo3d: bool = False, is_data: bool = False, tiled: bool = False) -> Image:
        if not isinstance(name, str):
            raise PropertyTypeError(f"BlendDataImages.new(): name expected a string type, not {type(name).__name__}")
        w, h = _check_size(width, height, "BlendDataImages.new()")
        image = IDCollection.new(self, name)
        raw = lambda ident, value: get_property(Image, ident).write_raw(image, value)
        raw("source", "TILED" if tiled else "GENERATED")
        raw("generated_type", "BLANK")
        raw("generated_width", w)
        raw("generated_height", h)
        raw("generated_color", np.array((0.0, 0.0, 0.0, 1.0), dtype=np.float32))
        raw("use_generated_float", bool(float_buffer))
        image._q_float = bool(float_buffer)
        image._q_alpha = bool(alpha)
        image._q_fill_generated(w, h)
        image._q_is_dirty = False
        return image

    def load(self, filepath: str, check_existing: bool = False) -> Image:
        if not isinstance(filepath, str):
            raise PropertyTypeError(f"BlendDataImages.load(): filepath expected a string type, not {type(filepath).__name__}")
        if check_existing:
            wanted = os.path.normcase(os.path.abspath(filepath))
            for image in self._q_items():
                if os.path.normcase(os.path.abspath(image.filepath)) == wanted and image.filepath:
                    return image
        image = IDCollection.new(self, basename(filepath))
        raw = lambda ident, value: get_property(Image, ident).write_raw(image, value)
        raw("filepath", filepath)
        raw("filepath_raw", filepath)
        raw("source", "FILE")
        ext = os.path.splitext(filepath)[1].lower()
        if ext in _FORMAT_BY_EXT:
            raw("file_format", _FORMAT_BY_EXT[ext])
        return image

    def remove(self, image: Image, do_unlink: bool = True, do_id_user: bool = True, do_ui_user: bool = True) -> None:
        IDCollection.remove(self, image, do_unlink, do_id_user, do_ui_user)


register_id_type(Image, id_type="IMAGE", collection="images", default_name="Image", collection_cls=BlendDataImages)
