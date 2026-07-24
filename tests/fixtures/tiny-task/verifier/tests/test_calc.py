from calc import add, existing


def test_add():
    assert add(2, 3) == 5


def test_existing():
    assert existing() == "ok"
