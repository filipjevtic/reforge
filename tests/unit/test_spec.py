"""Tests for task spec loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from reforge.spec import load_task, validate_task
from reforge.spec.loader import load_dataset_dir
from reforge.utils.errors import SpecError

TINY_TASK = Path(__file__).parent.parent / "fixtures" / "tiny-task"


def test_load_tiny_task() -> None:
    spec = load_task(TINY_TASK)
    assert spec.id == "tiny-task"
    assert spec.category == "new_feature"
    assert spec.verification.fail_to_pass == ["test_calc.py::test_add"]
    assert spec.task_dir == TINY_TASK.resolve()


def test_freeform_category_and_tags(tmp_path: Path) -> None:
    (tmp_path / "task.yaml").write_text(
        """
schema_version: 1
id: infra-1
category: cloud-infra
tags: [terraform, aws]
title: t
instruction: do it
source:
  type: local
  path: src
verification:
  entrypoint: verifier/run_tests.sh
  fail_to_pass: ["t::t"]
""",
        encoding="utf-8",
    )
    spec = load_task(tmp_path)
    assert spec.category == "cloud-infra"
    assert spec.tags == ["terraform", "aws"]


def test_validate_tiny_task_is_clean() -> None:
    spec = load_task(TINY_TASK)
    assert validate_task(spec) == []


def test_missing_task_yaml(tmp_path: Path) -> None:
    with pytest.raises(SpecError):
        load_task(tmp_path)


def test_bad_yaml(tmp_path: Path) -> None:
    (tmp_path / "task.yaml").write_text("::not: valid: yaml:", encoding="utf-8")
    with pytest.raises(SpecError):
        load_task(tmp_path)


def test_git_source_requires_ref(tmp_path: Path) -> None:
    (tmp_path / "task.yaml").write_text(
        """
schema_version: 1
id: bad-git
category: new_feature
title: t
instruction: do it
source:
  type: git
  repo: https://example.com/x
verification:
  entrypoint: verifier/run_tests.sh
  fail_to_pass: ["t::t"]
""",
        encoding="utf-8",
    )
    with pytest.raises(SpecError):
        load_task(tmp_path)


def test_validate_flags_missing_files(tmp_path: Path) -> None:
    (tmp_path / "task.yaml").write_text(
        """
schema_version: 1
id: no-files
category: new_feature
title: t
instruction: do it
source:
  type: local
  path: src
environment:
  dockerfile: Dockerfile
verification:
  entrypoint: verifier/run_tests.sh
  fail_to_pass: ["t::t"]
""",
        encoding="utf-8",
    )
    spec = load_task(tmp_path)
    problems = validate_task(spec)
    assert any("dockerfile" in p for p in problems)
    assert any("entrypoint" in p for p in problems)
    assert any("gold" in p for p in problems)


def test_dataset_dir_finds_tiny_task() -> None:
    specs = load_dataset_dir(TINY_TASK.parent)
    assert any(s.id == "tiny-task" for s in specs)
