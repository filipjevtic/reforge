"""Tests for secret redaction in persisted error text."""

from __future__ import annotations

from reforge.utils.errors import redact_secrets


def test_redacts_api_keys_and_bearer() -> None:
    text = (
        "auth failed with key sk-ant-api03-abcdEFGH1234567890xyz and "
        "sk-proj-0000111122223333 and AIzaSyAbCdEf0123456789ghijklmno; "
        "header Authorization: Bearer abcDEF1234567890tokenvalue"
    )
    out = redact_secrets(text)
    assert "sk-ant-api03" not in out
    assert "sk-proj-0000" not in out
    assert "AIzaSy" not in out
    assert "abcDEF1234567890tokenvalue" not in out
    assert out.count("[redacted]") == 4


def test_leaves_ordinary_text_alone() -> None:
    text = "agent exited with code 1: NotImplementedError in calc.py"
    assert redact_secrets(text) == text
