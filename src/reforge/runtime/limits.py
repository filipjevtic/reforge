"""Resource limits translated into container runtime arguments."""

from __future__ import annotations

from dataclasses import dataclass

from reforge.spec.models import Resources


@dataclass(frozen=True)
class ResourceLimits:
    """Concrete limits applied when a task container starts.

    Kept separate from the spec's :class:`~reforge.spec.models.Resources` so the
    runtime layer does not depend on the schema, and so limits can be overridden
    from the CLI without mutating a frozen spec.
    """

    cpus: float = 2.0
    memory: str = "4g"
    pids: int = 512
    network: str = "none"
    disk_quota: str | None = None

    @classmethod
    def from_spec(cls, resources: Resources, network_override: str | None = None) -> ResourceLimits:
        return cls(
            cpus=resources.cpus,
            memory=resources.memory,
            pids=resources.pids,
            network=network_override or resources.network.value,
            disk_quota=resources.disk_quota,
        )

    def to_docker_kwargs(self, *, with_disk_quota: bool = True) -> dict[str, object]:
        """Map limits onto docker-py ``containers.run``/``create`` keyword args."""
        from docker.types import Ulimit

        # nano_cpus is CPU count expressed in billionths of a CPU.
        kwargs: dict[str, object] = {
            "nano_cpus": int(self.cpus * 1_000_000_000),
            "mem_limit": self.memory,
            "pids_limit": self.pids,
            "network_mode": self.network,
            # Defense in depth: drop all capabilities, block privilege escalation, and
            # cap open file descriptors (pids_limit already caps processes).
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges"],
            "ulimits": [Ulimit(name="nofile", soft=4096, hard=8192)],
        }
        # storage_opt size requires a quota-capable storage driver (overlay2 on
        # xfs with pquota, or btrfs). It is best-effort; the runtime retries
        # without it if the driver rejects it.
        if with_disk_quota and self.disk_quota:
            kwargs["storage_opt"] = {"size": self.disk_quota}
        return kwargs
