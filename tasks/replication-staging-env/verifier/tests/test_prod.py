from pathlib import Path

import yaml

PROD = Path("/workspace/environments/prod/docker-compose.yml")


def test_prod_intact():
    data = yaml.safe_load(PROD.read_text())
    services = set(data.get("services", {}))
    assert {"web", "postgres", "redis"} <= services
