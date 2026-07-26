from pathlib import Path

import yaml

SERVICE = Path("/workspace/service.yaml")


def test_service_kind_and_selector():
    doc = yaml.safe_load(SERVICE.read_text())
    assert doc["kind"] == "Service"
    assert doc["spec"]["selector"]["app"] == "web"


def test_service_targets_container_port():
    doc = yaml.safe_load(SERVICE.read_text())
    ports = doc["spec"]["ports"]
    assert any(p.get("targetPort") == 8080 for p in ports)
