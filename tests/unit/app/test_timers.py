import time

import quartz.app.timers as t


def test_register_unregister():
    def cb():
        return None
    t.register(cb, first_interval=0)
    assert t.is_registered(cb)
    t.pump(now=time.monotonic() + 10)
    assert not t.is_registered(cb)
    try:
        t.unregister(cb)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_timer_reschedule():
    calls = {"n": 0}

    def cb():
        calls["n"] += 1
        return 10.0

    t.register(cb, first_interval=0)
    n = t.pump(now=time.monotonic() + 1)
    assert n == 1
    assert calls["n"] == 1
    assert t.is_registered(cb)
    n2 = t.pump(now=time.monotonic() + 1)
    assert n2 == 0
    t.clear()


def test_timer_exception_unregisters():
    def cb():
        raise RuntimeError("boom")
    t.register(cb, first_interval=0)
    try:
        t.pump(now=time.monotonic() + 1)
    except Exception:
        pass
    assert not t.is_registered(cb)
    t.clear()
