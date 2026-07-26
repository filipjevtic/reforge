"""Tests for JUnit XML parsing and test-id matching."""

from __future__ import annotations

from reforge.scoring.log_parsers import (
    TestStatus,
    match_status,
    parse_go_json,
    parse_junit_xml,
)

JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="3" failures="1" errors="0" skipped="1">
    <testcase classname="test_calc" name="test_add" file="test_calc.py"/>
    <testcase classname="test_calc" name="test_existing" file="test_calc.py"/>
    <testcase classname="test_calc" name="test_broken" file="test_calc.py">
      <failure message="boom">assert 1 == 2</failure>
    </testcase>
  </testsuite>
</testsuites>
"""


def test_parse_counts_statuses() -> None:
    results = parse_junit_xml(JUNIT)
    by_id = {r.nodeid: r.status for r in results}
    assert by_id["test_calc.py::test_add"] is TestStatus.passed
    assert by_id["test_calc.py::test_broken"] is TestStatus.failed


def test_match_exact() -> None:
    results = parse_junit_xml(JUNIT)
    assert match_status("test_calc.py::test_add", results) is TestStatus.passed


def test_match_suffix() -> None:
    results = parse_junit_xml(JUNIT)
    # A rootdir-prefixed id still matches the reported node.
    assert match_status("sub/test_calc.py::test_add", results) is TestStatus.passed


def test_match_missing_returns_none() -> None:
    results = parse_junit_xml(JUNIT)
    assert match_status("test_calc.py::nope", results) is None


def test_bare_function_name_does_not_match_qualified_id() -> None:
    """A reported bare ``test_add`` must not be credited to ``pkg.mod::test_add``.

    This is the reward-hacking collision: an unrelated trivially-passing test
    named the same as a held-out one should not satisfy the qualified id.
    """
    from reforge.scoring.log_parsers import TestCaseResult

    # A qualified id only matches when the module lines up; a same-named test in
    # another module does not satisfy it.
    results = [TestCaseResult("other_mod.py::test_add", TestStatus.passed)]
    assert match_status("app.core.calc::test_add", results) is None
    # A deliberately-bare id matches a unique function name...
    assert match_status("test_add", results) is TestStatus.passed
    # ...but not when two different modules both report it.
    results.append(TestCaseResult("yet_another.py::test_add", TestStatus.passed))
    assert match_status("test_add", results) is None


def test_py_extension_not_stripped_midname() -> None:
    from reforge.scoring.log_parsers import TestCaseResult

    results = [TestCaseResult("test_python_thing.py::test_x", TestStatus.passed)]
    assert match_status("test_python_thing.py::test_x", results) is TestStatus.passed


GO_JSON = """{"Action":"run","Package":"calc","Test":"TestAdd"}
{"Action":"pass","Package":"calc","Test":"TestAdd"}
{"Action":"run","Package":"calc","Test":"TestBroken"}
{"Action":"fail","Package":"calc","Test":"TestBroken"}
"""


def test_parse_go_json() -> None:
    results = parse_go_json(GO_JSON)
    by_id = {r.nodeid: r.status for r in results}
    assert by_id["calc::TestAdd"] is TestStatus.passed
    assert by_id["calc::TestBroken"] is TestStatus.failed
    assert match_status("TestAdd", results) is TestStatus.passed
