"""Dependency-coverage scorer.

This is the scorer that makes reforge useful for replication: it checks whether
the agent actually wired up the dependencies a correct solution needs, and names
the ones it missed. The task declares the ground-truth dependencies
(``dependency_coverage.required``) and one or more detectors that inspect the
agent's files to see what got wired up.

Detectors are pure functions over ``{path: content}`` and are registered by name,
so language- or infra-specific ones can be added without touching the scorer.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable
from fnmatch import fnmatch

from reforge.scoring.base import Scorer, ScorerResult, TaskScoringContext
from reforge.spec.models import RequiredDeps

Detector = Callable[[dict[str, str]], set[str]]
_REGISTRY: dict[str, Detector] = {}
ENTRY_POINT_GROUP = "reforge.detectors"


def register(name: str) -> Callable[[Detector], Detector]:
    def decorate(fn: Detector) -> Detector:
        _REGISTRY[name] = fn
        return fn

    return decorate


def _entry_point_detectors() -> dict[str, str]:
    from importlib.metadata import entry_points

    return {ep.name: ep.value for ep in entry_points(group=ENTRY_POINT_GROUP)}


def available_detectors() -> list[str]:
    return sorted(set(_REGISTRY) | set(_entry_point_detectors()))


def get_detector(name: str) -> Detector | None:
    """Look up a detector by name: built-ins first, then entry-point plugins."""
    if name in _REGISTRY:
        return _REGISTRY[name]
    from importlib.metadata import entry_points

    for ep in entry_points(group=ENTRY_POINT_GROUP):
        if ep.name == name:
            fn: Detector = ep.load()
            return fn
    return None


@register("python_imports")
def detect_python_imports(files: dict[str, str]) -> set[str]:
    """Modules imported by the changed Python files (both dotted forms)."""
    found: set[str] = set()
    for path, content in files.items():
        if not path.endswith(".py"):
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    found.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module)
                for alias in node.names:
                    found.add(f"{node.module}.{alias.name}")
    return found


_ENV_PATTERNS = [
    re.compile(r"""os\.environ\[\s*['"]([A-Z0-9_]+)['"]"""),
    re.compile(r"""os\.environ\.get\(\s*['"]([A-Z0-9_]+)['"]"""),
    re.compile(r"""(?:os\.)?getenv\(\s*['"]([A-Z0-9_]+)['"]"""),
    re.compile(r"""process\.env\.([A-Z0-9_]+)"""),
    re.compile(r"""\$\{?([A-Z][A-Z0-9_]+)\}?"""),
]


@register("env_refs")
def detect_env_refs(files: dict[str, str]) -> set[str]:
    """Environment/config variable names referenced across the files."""
    found: set[str] = set()
    for content in files.values():
        for pattern in _ENV_PATTERNS:
            found.update(pattern.findall(content))
    return found


_TF_BLOCK = re.compile(r'(?:resource|data)\s+"([a-z0-9_]+)"\s+"([a-z0-9_]+)"')
_TF_MODULE = re.compile(r'module\s+"([a-z0-9_]+)"')


@register("terraform_refs")
def detect_terraform_refs(files: dict[str, str]) -> set[str]:
    """Terraform resource types, resource names, and module names."""
    found: set[str] = set()
    for path, content in files.items():
        if not path.endswith(".tf"):
            continue
        for rtype, rname in _TF_BLOCK.findall(content):
            found.add(rtype)
            found.add(rname)
        found.update(_TF_MODULE.findall(content))
    return found


_COMPOSE_SERVICE = re.compile(r"^\s{2}([a-z0-9_-]+):\s*$", re.MULTILINE)
_IMAGE = re.compile(r"image:\s*([^\s:]+)")


@register("service_deps")
def detect_service_deps(files: dict[str, str]) -> set[str]:
    """Service names and image names from docker-compose / k8s manifests."""
    found: set[str] = set()
    for path, content in files.items():
        base = path.rsplit("/", 1)[-1]
        if "compose" in base or base.endswith((".yml", ".yaml")):
            found.update(_COMPOSE_SERVICE.findall(content))
            for image in _IMAGE.findall(content):
                found.add(image.rsplit("/", 1)[-1])
    return found


_K8S_KIND = re.compile(r"^kind:\s*([A-Za-z0-9]+)", re.MULTILINE)
_K8S_NAME = re.compile(r"^\s+-?\s*name:\s*([a-z0-9][a-z0-9.-]*)", re.MULTILINE)


@register("k8s_refs")
def detect_k8s_refs(files: dict[str, str]) -> set[str]:
    """Kinds, names, and images from Kubernetes manifests."""
    found: set[str] = set()
    for path, content in files.items():
        if not path.endswith((".yml", ".yaml")):
            continue
        found.update(_K8S_KIND.findall(content))
        found.update(_K8S_NAME.findall(content))
        for image in _IMAGE.findall(content):
            found.add(image.rsplit("/", 1)[-1])
    return found


_JS_IMPORT = re.compile(r"""(?:from|require\()\s*['"]([^'"]+)['"]""")


@register("js_imports")
def detect_js_imports(files: dict[str, str]) -> set[str]:
    """Modules imported/required by JS/TS files."""
    found: set[str] = set()
    for path, content in files.items():
        if path.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs")):
            found.update(_JS_IMPORT.findall(content))
    return found


_GO_IMPORT = re.compile(r'"([a-zA-Z0-9_./-]+)"')


@register("go_imports")
def detect_go_imports(files: dict[str, str]) -> set[str]:
    """Packages imported by Go files (from import lines / blocks)."""
    found: set[str] = set()
    for path, content in files.items():
        if not path.endswith(".go"):
            continue
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("import ") or (stripped and stripped[0] == '"'):
                found.update(_GO_IMPORT.findall(stripped))
    return found


@register("package_manifests")
def detect_package_manifests(files: dict[str, str]) -> set[str]:
    """Dependency names from requirements.txt, package.json, and go.mod."""
    found: set[str] = set()
    for path, content in files.items():
        base = path.rsplit("/", 1)[-1]
        if base == "requirements.txt":
            for line in content.splitlines():
                name = re.split(r"[=<>!~;\[ ]", line.strip(), maxsplit=1)[0]
                if name and not name.startswith("#"):
                    found.add(name)
        elif base == "package.json":
            found.update(re.findall(r'"([^"]+)"\s*:\s*"[^"]*"', content))
        elif base == "go.mod":
            # Matches both `require mod vX` and indented lines in a require ( ) block.
            found.update(re.findall(r"([a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)+)\s+v[0-9]", content))
    return found


@register("grep")
def detect_grep(files: dict[str, str]) -> set[str]:
    """Fallback: the raw concatenated text, matched by substring later."""
    return {"\n".join(files.values())}


def _matches(required: str, found: set[str]) -> bool:
    for token in found:
        if required == token:
            return True
        if token.startswith(required + ".") or required.startswith(token + "."):
            return True
        if required in token:
            return True
    return False


class DependencyScorer(Scorer):
    key = "dependency_coverage"

    def score(self, ctx: TaskScoringContext) -> ScorerResult:
        cfg = ctx.spec.dependency_coverage
        required = _required_items(cfg.required)
        if not required:
            return ScorerResult(key=self.key, score=1.0, passed=True, detail={"required": []})

        found: set[str] = set()
        for det in cfg.detectors:
            fn = get_detector(det.type)
            if fn is None:
                continue
            files = _read_scoped_files(ctx, det.scope)
            found |= fn(files)

        missed = [item for item in required if not _matches(item, found)]
        covered = len(required) - len(missed)
        coverage = covered / len(required)
        return ScorerResult(
            key=self.key,
            score=round(coverage, 4),
            passed=not missed,
            detail={
                "required": required,
                "missed": missed,
                "covered": covered,
                "total": len(required),
            },
        )


def _required_items(req: RequiredDeps) -> list[str]:
    return [*req.services, *req.config_refs, *req.imports]


def _read_scoped_files(ctx: TaskScoringContext, scope: str) -> dict[str, str]:
    """Read files under the workspace whose path matches the scope glob."""
    ws = ctx.workspace_path
    listing = ctx.container.exec(["sh", "-c", f"cd {ws} && find . -type f"])
    paths = [line[2:] for line in listing.output.splitlines() if line.startswith("./")]

    matched = [p for p in paths if _path_matches(p, scope)]
    files: dict[str, str] = {}
    for path in matched[:200]:  # bound the read; scopes should be narrow
        res = ctx.container.exec(["cat", path], workdir=ws)
        if res.ok:
            files[path] = res.output
    return files


def _path_matches(path: str, scope: str) -> bool:
    if scope in ("**", "", "*"):
        return True
    if scope.endswith("/**"):
        return path == scope[:-3] or path.startswith(scope[:-2])
    return fnmatch(path, scope) or path == scope
