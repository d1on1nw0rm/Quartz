import inspect

import quartz.geometry as geometry


EXPECTED = [
    "DATA_TYPES",
    "DOMAINS",
    "REQUIRED_ATTRIBUTES",
    "AttributeArray",
    "AttributeStore",
    "MeshGeometry",
    "bound_box",
    "bounds",
    "calc_edges",
    "circle",
    "compose_trs",
    "cone",
    "corner_normals",
    "cube",
    "cylinder",
    "decompose_trs",
    "default_fill",
    "edge_keys",
    "euler_to_matrix3",
    "face_areas",
    "face_centers",
    "face_edge_keys",
    "face_normals",
    "faces_to_offsets",
    "flip_faces",
    "grid",
    "ico_sphere",
    "join",
    "loose_edges",
    "loose_verts",
    "matrix3_to_quat",
    "merge_by_distance",
    "plane",
    "quat_to_matrix3",
    "torus",
    "transform_directions",
    "transform_normals",
    "transform_points",
    "triangulate",
    "triangulated",
    "uv_sphere",
    "vertex_normals",
]


def test_public_names_are_reexported():
    missing = [name for name in EXPECTED if not hasattr(geometry, name)]
    assert missing == []
    assert sorted(EXPECTED) == sorted(geometry.__all__)


def test_public_functions_have_no_docstrings():
    for name in geometry.__all__:
        value = getattr(geometry, name)
        if inspect.isfunction(value):
            assert value.__doc__ is None, name
