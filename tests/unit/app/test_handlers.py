import quartz.app.handlers as h


def test_handler_lists_count():
    assert len(h.BLENDER_HANDLER_NAMES) == 39
    assert len(h.QUARTZ_HANDLER_NAMES) == 5
    assert len(h.all_lists()) == 44


def test_persistent():
    def f():
        pass
    g = h.persistent(f)
    assert g is f
    assert h.is_persistent(f) is True


def test_dispatch_keyerror():
    try:
        h.dispatch("nope")
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError")


def test_dispatch_captures():
    lst = h.all_lists()["frame_change_pre"]
    def bad(*a):
        raise ValueError("boom")
    lst.append(bad)
    try:
        res = h.dispatch("frame_change_pre", 1, 2)
        assert len(res) == 1
    finally:
        lst.clear()


def test_clear_non_persistent():
    lst = h.all_lists()["startup_post"]
    def f():
        pass
    def g():
        pass
    h.persistent(g)
    lst.append(f)
    lst.append(g)
    removed = h.clear_non_persistent()
    assert removed >= 1
    assert f not in lst
    assert g in lst
    lst.clear()


def test_snapshot_restore():
    lst = h.all_lists()["startup_post"]
    def f():
        pass
    lst.append(f)
    snap = h.snapshot()
    lst.clear()
    h.restore(snap)
    assert f in lst
    lst.clear()
