from app.services.gold_pool_academy import academy_qualification


def test_three_new_completed_videos_qualify():
    r = academy_qualification({"a", "b", "c"}, set())
    assert r["qualified"] and r["new_videos_completed"] == 3 and r["remaining"] == 0


def test_two_videos_do_not_qualify():
    r = academy_qualification({"a", "b"}, set())
    assert not r["qualified"] and r["remaining"] == 1 and r["batch_candidate"] == []


def test_previously_used_videos_do_not_count():
    r = academy_qualification({"a", "b", "c", "d"}, {"a", "b"})
    assert not r["qualified"] and r["new_videos_completed"] == 2


def test_fresh_videos_after_previous_cycle_qualify_again():
    r = academy_qualification({"a", "b", "c", "d", "e", "f"}, {"a", "b", "c"})
    assert r["qualified"] and r["batch_candidate"] == ["d", "e", "f"]


def test_no_watched_videos_is_not_qualified():
    r = academy_qualification(set(), set())
    assert not r["qualified"] and r["new_videos_completed"] == 0 and r["remaining"] == 3
