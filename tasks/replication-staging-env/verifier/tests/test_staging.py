from pathlib import Path

import yaml

STAGING = Path("/workspace/environments/staging/docker-compose.yml")


def test_staging_has_all_services():
    data = yaml.safe_load(STAGING.read_text())
    services = set(data.get("services", {}))
    assert {"web", "postgres", "redis"} <= services


def test_staging_wires_config():
    text = STAGING.read_text()
    for key in ("DATABASE_URL", "REDIS_URL", "SECRET_KEY"):
        assert key in text
