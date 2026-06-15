import pytest

from taskboard import (
    AlreadyDone,
    BadPriority,
    EmptyTitle,
    NotFound,
    TaskBoard,
    TaskStatus,
)


def test_add_valid():
    b = TaskBoard()
    assert b.add("write spec", 3) == 1
    assert b.add("review", 5) == 2


def test_add_empty_title():
    b = TaskBoard()
    with pytest.raises(EmptyTitle):
        b.add("   ", 3)


def test_add_bad_priority():
    b = TaskBoard()
    with pytest.raises(BadPriority):
        b.add("x", 0)
    with pytest.raises(BadPriority):
        b.add("x", 6)


def test_complete_ok():
    b = TaskBoard()
    i = b.add("x", 2)
    b.complete(i)
    assert b.stats() == (1, 1, 0)


def test_complete_not_found():
    b = TaskBoard()
    with pytest.raises(NotFound):
        b.complete(99)


def test_complete_twice():
    b = TaskBoard()
    i = b.add("x", 2)
    b.complete(i)
    with pytest.raises(AlreadyDone):
        b.complete(i)


def test_pending_ordering():
    b = TaskBoard()
    b.add("low", 1)
    b.add("high", 5)
    b.add("mid", 3)
    order = [t.title for t in b.pending()]
    assert order == ["high", "mid", "low"]


def test_pending_excludes_done():
    b = TaskBoard()
    a = b.add("a", 2)
    b.add("b", 4)
    b.complete(a)
    titles = [t.title for t in b.pending()]
    assert titles == ["b"]
    assert all(t.status is TaskStatus.TODO for t in b.pending())


def test_stats():
    b = TaskBoard()
    b.add("a", 2)
    x = b.add("b", 4)
    b.complete(x)
    assert b.stats() == (2, 1, 1)
