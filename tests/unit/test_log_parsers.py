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
