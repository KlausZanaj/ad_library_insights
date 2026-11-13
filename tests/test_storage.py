from ad_library_insights.storage import DiskCache, Throttle


class Clock:
    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


def test_cache_roundtrip_ttl_and_clear(tmp_path):
    clock = Clock()
    cache = DiskCache(tmp_path, ttl_seconds=100, clock=clock)
    assert cache.get("k") is None
    cache.put("k", {"ads": [1, 2], "text": "caffè"})
    assert cache.get("k") == {"ads": [1, 2], "text": "caffè"}
    assert cache.get("other") is None
    clock.now += 101
    assert cache.get("k") is None
    assert cache.clear() == 1


def test_cache_survives_a_corrupt_file(tmp_path):
    cache = DiskCache(tmp_path)
    cache.put("k", {"a": 1})
    next(tmp_path.glob("*.json")).write_text("{not json", encoding="utf-8")
    assert cache.get("k") is None


def test_throttle_minimum_interval(tmp_path):
    clock = Clock()
    throttle = Throttle(tmp_path / "t.json", min_interval=20, max_per_hour=100, clock=clock)
    assert throttle.delay_needed() == 0
    throttle.record()
    clock.now += 5
    assert throttle.delay_needed() == 15
    clock.now += 15
    assert throttle.delay_needed() == 0


def test_throttle_hourly_budget_and_persistence(tmp_path):
    clock = Clock()
    path = tmp_path / "t.json"
    throttle = Throttle(path, min_interval=1, max_per_hour=2, clock=clock)
    throttle.record()
    clock.now += 600
    throttle.record()
    clock.now += 600
    # a new instance (a restarted server) reads the same state
    restarted = Throttle(path, min_interval=1, max_per_hour=2, clock=clock)
    assert restarted.delay_needed() == 2400  # until the first render is an hour old
    clock.now += 2400
    assert restarted.delay_needed() == 0
