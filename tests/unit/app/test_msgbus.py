import quartz.app.msgbus as m


class FakeProp:
    def __init__(self, struct, ident):
        self._q_struct = struct
        self._q_identifier = ident


def test_notify_changed_tuple():
    calls = []
    m.subscribe_rna(key=(int, "x"), owner="o", args=(), notify=lambda: calls.append("a"))
    m.notify_changed(5, "x")
    assert m.pending() == 1
    assert m.flush() == 1
    assert calls == ["a"]


def test_publish_rna():
    calls = []
    m.subscribe_rna(key="k", owner="o", args=(1,), notify=lambda v: calls.append(v))
    m.publish_rna(key="k")
    assert m.flush() == 1
    assert calls == [1]


def test_property_ref_key():
    struct = object()
    key = FakeProp(struct, "y")
    calls = []
    m.subscribe_rna(key=key, owner="o", args=(), notify=lambda: calls.append("p"))
    m.notify_changed(struct, "y")
    assert m.flush() == 1
    assert calls == ["p"]


def test_clear_by_owner():
    m.clear()
    m.subscribe_rna(key="k", owner="o1", args=(), notify=lambda: None)
    m.subscribe_rna(key="k", owner="o2", args=(), notify=lambda: None)
    m.clear_by_owner("o1")
    assert len(m._SUBS) == 1


def test_flush_exception():
    def bad():
        raise RuntimeError("boom")
    m.clear()
    m.subscribe_rna(key="k", owner="o", args=(), notify=bad)
    m.publish_rna(key="k")
    n = m.flush()
    assert n == 1


def test_flush_counts_raising_and_ok_calls(capsys):
    calls = []

    def bad():
        raise RuntimeError("bus-fail")

    m.clear()
    m.subscribe_rna(key="k", owner="o", args=(), notify=bad)
    m.subscribe_rna(key="k", owner="o", args=(), notify=lambda: calls.append("ok"))
    m.publish_rna(key="k")
    try:
        assert m.flush() == 2
        assert calls == ["ok"]
        err = capsys.readouterr().err
        assert "bus-fail" in err and "Traceback" in err
        assert m.pending() == 0
    finally:
        m.clear()
