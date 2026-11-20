from __future__ import annotations

import itertools

from quartz.props import BoolProperty, IntProperty, IntVectorProperty
from quartz.rna.struct import Struct, builtin_struct

__all__ = ["new", "remove", "ImagePreviewCollection", "ImagePreview"]

_ICON_IDS = itertools.count(1)
_FILETYPES = ("IMAGE", "MOVIE", "BLEND", "FONT")


@builtin_struct
class ImagePreview(Struct):
    _q_strict_attrs = True

    icon_id: IntProperty(name="Icon ID", meta={"virtual_get": lambda self: self._q_icon_id})
    image_size: IntVectorProperty(name="Image Size", size=2, default=(0, 0))
    icon_size: IntVectorProperty(name="Icon Size", size=2, default=(0, 0))
    is_image_custom: BoolProperty(name="Custom Image")
    is_icon_custom: BoolProperty(name="Custom Icon")

    def __new__(cls, *args, **kwargs):
        inst = super().__new__(cls)
        object.__setattr__(inst, "_q_icon_id", next(_ICON_IDS))
        object.__setattr__(inst, "_q_filepath", "")
        object.__setattr__(inst, "_q_filetype", "")
        return inst

    @property
    def image_pixels(self) -> list:
        return []

    @property
    def icon_pixels(self) -> list:
        return []

    @property
    def q_filepath(self) -> str:
        return self._q_filepath

    @property
    def q_filetype(self) -> str:
        return self._q_filetype

    def reload(self) -> None:
        return None


class ImagePreviewCollection(dict):

    def __repr__(self) -> str:
        return f"<ImagePreviewCollection id=0x{id(self):x}[{len(self)}]>"

    def new(self, name: str) -> ImagePreview:
        if name in self:
            raise KeyError(f"key {name!r} already exists")
        preview = ImagePreview()
        dict.__setitem__(self, name, preview)
        return preview

    def load(self, name: str, filepath: str, filetype: str, force_reload: bool = False) -> ImagePreview:
        if filetype not in _FILETYPES:
            listing = ", ".join(repr(t) for t in _FILETYPES)
            raise ValueError(f"load(): filetype {filetype!r} not in ({listing})")
        preview = self.get(name)
        if preview is not None and not force_reload:
            raise KeyError(f"key {name!r} already exists")
        if preview is None:
            preview = ImagePreview()
            dict.__setitem__(self, name, preview)
        object.__setattr__(preview, "_q_filepath", str(filepath))
        object.__setattr__(preview, "_q_filetype", filetype)
        return preview

    def clear(self) -> None:
        dict.clear(self)

    def close(self) -> None:
        self.clear()


def new() -> ImagePreviewCollection:
    return ImagePreviewCollection()


def remove(pcoll: ImagePreviewCollection) -> None:
    pcoll.close()
