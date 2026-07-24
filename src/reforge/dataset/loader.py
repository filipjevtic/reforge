"""Resolve a dataset source string to a local directory of task dirs.

Two forms are supported:

* a local path (default), and
* ``hf:owner/repo`` (optionally ``hf:owner/repo@revision``), which pulls a
  HuggingFace *dataset repo* containing reforge task directories via
  ``huggingface_hub.snapshot_download`` and returns the local snapshot path.

Row-based HuggingFace datasets don't map onto reforge's containerized task-dir
format, so the supported convention is a git-backed dataset repo whose files are
task directories (each with task.yaml, Dockerfile, verifier/, gold/).
"""

from __future__ import annotations

from pathlib import Path

from reforge.utils.errors import ConfigError

HF_PREFIX = "hf:"


def resolve_dataset_source(source: str) -> Path:
    """Return a local directory for a dataset source string."""
    if source.startswith(HF_PREFIX):
        return _snapshot_hf_dataset(source[len(HF_PREFIX) :])
    return Path(source)


def _snapshot_hf_dataset(repo_ref: str) -> Path:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise ConfigError(
            "hf: datasets require the huggingface_hub package; install reforge with the [hf] extra"
        ) from exc

    repo_id, _, revision = repo_ref.partition("@")
    if not repo_id:
        raise ConfigError("hf: dataset must be hf:owner/repo (optionally @revision)")

    local = snapshot_download(
        repo_id=repo_id,
        repo_type="dataset",
        revision=revision or None,
    )
    return Path(local)
