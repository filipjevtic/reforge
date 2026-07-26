import re
from pathlib import Path

ID = Path("/workspace/id.go")


def test_id_module():
    assert ID.is_file(), "id.go was not created"
    text = ID.read_text()
    # Must reuse the uuid package rather than hand-rolling an id.
    assert re.search(r'"github\.com/google/uuid"', text)
    assert re.search(r"func\s+NewID\s*\(", text)
    assert "uuid." in text
