import os
import tempfile

import quartz.app.settings as st
import quartz.app.paths as pa


def test_settings_reset_same_object():
    obj = st.settings
    st.settings.trust_scripts = True
    st.reset()
    assert st.settings is obj
    assert st.settings.trust_scripts is False


def test_settings_snapshot_restore():
    snap = st.snapshot()
    st.settings.debug if hasattr(st.settings, "debug") else None
    st.settings.undo_steps = 99
    st.restore(snap)
    assert st.settings.undo_steps == 32


def test_paths_user_dir_env(monkeypatch, tmp_path):
    pa.reset()
    monkeypatch.setenv("QUARTZ_USER_DIR", str(tmp_path / "u"))
    p = pa.user_dir()
    assert p.exists()
    assert pa.temp_dir().exists()
    pa.reset()


def test_add_extension_repo_validation():
    pa.reset()
    try:
        pa.add_extension_repo("123bad", "/tmp")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
    pa.reset()
