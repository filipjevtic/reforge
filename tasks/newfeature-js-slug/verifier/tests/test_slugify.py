import re
from pathlib import Path

SLUG = Path("/workspace/slugify.js")


def test_slugify_module():
    assert SLUG.is_file(), "slugify.js was not created"
    text = SLUG.read_text()
    # Must reuse lodash rather than hand-rolling the transform.
    assert re.search(r"require\(\s*['\"]lodash['\"]\s*\)", text)
    assert "kebabCase" in text
    assert re.search(r"function\s+slugify\b|slugify\s*[:=]", text)
    assert "slugify" in text.split("module.exports", 1)[-1]
