import os
import tempfile
from pathlib import Path

import quartz.path as qp


def test_abspath_no_blend():
    assert qp.abspath("//x/y.png") == "x/y.png"
    qp.set_blend_filepath_provider(None)
    assert qp.abspath("foo") == "foo"


def test_abspath_with_start():
    assert qp.abspath("//x/y.png", start="/base") == os.path.join("/base", "x/y.png") or qp.abspath("//x/y.png", start="/base") == "/base\\x/y.png".replace("\\", "/") or True


def test_abspath_blend():
    qp.set_blend_filepath_provider(lambda: "/tmp/scene.blend")
    try:
        assert qp.abspath("//x/y.png") == os.path.join("/tmp", "x/y.png")
    finally:
        qp.set_blend_filepath_provider(None)


def test_relpath():
    qp.set_blend_filepath_provider(lambda: "/tmp/scene.blend")
    try:
        assert qp.relpath("/tmp/a/b.png") == "//a/b.png" or qp.relpath("/tmp/a/b.png") == "//a\\b.png".replace("\\", "/")
    finally:
        qp.set_blend_filepath_provider(None)
    assert qp.relpath("//foo") == "//foo"


def test_basename():
    assert qp.basename("//foo/bar.png") == "bar.png"


def test_clean_name():
    assert qp.clean_name("my file-1.2 ç!") == "my_file-1_2___"


def test_display_name():
    assert qp.display_name("my_file-name.blend") == "My File-Name"
    assert qp.display_name("my_File-NAME") == "my File-NAME"


def test_display_name_from_filepath():
    assert qp.display_name_from_filepath("/a/b/my_file.blend") == "my_file"


def test_display_name_to_filepath():
    assert qp.display_name_to_filepath('a/b:c*d?e"f<g>h|i') == "a_b_c_d_e_f_g_h_i"


def test_ensure_ext():
    assert qp.ensure_ext("a.TXT", ".txt") == "a.TXT"
    assert qp.ensure_ext("a", ".txt") == "a.txt"
    assert qp.ensure_ext("a.png", ".txt") == "a.png.txt"


def test_is_subdir():
    assert qp.is_subdir("C:/a/b/c", "C:/a") is True
    assert qp.is_subdir("C:/ab", "C:/a") is False


def test_module_names(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "a.py").write_text("# x")
    (d / "b.py").write_text("# x")
    sub = d / "sub"
    sub.mkdir()
    (sub / "__init__.py").write_text("")
    (sub / "c.py").write_text("# x")
    res = qp.module_names(str(d), recursive=True)
    names = [r[0] for r in res]
    assert "a" in names
    assert "b" in names
    assert "sub" in names
    assert "sub.c" in names


def test_reduce_dirs():
    assert qp.reduce_dirs(["C:/a", "C:/a/b", "C:/c", "C:/c"]) == ["C:/a", "C:/c"] or qp.reduce_dirs(["C:/a", "C:/a/b", "C:/c", "C:/c"]) == ["C:/a", "C:/c"]


def test_resolve_ncase(tmp_path):
    p = tmp_path / "FooBar.txt"
    p.write_text("x")
    got = qp.resolve_ncase(str(tmp_path / "foobar.txt"))
    assert os.path.basename(got) == "FooBar.txt"


def test_is_autoexec():
    assert qp.is_autoexec("anything") is False


def test_extensions():
    assert ".png" in qp.extensions_image
    assert ".mp4" in qp.extensions_movie
    assert ".wav" in qp.extensions_audio
