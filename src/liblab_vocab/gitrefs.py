"""Reading vocabularies from Git history, and finding release tags."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .model import Vocabularies, parse_tsv

VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
Version = tuple[int, int, int]


def parse_version(text: str) -> Version:
    match = VERSION_RE.match(text.strip())
    if not match:
        raise ValueError(f"{text!r} is not a version like v1.4.0")
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def format_version(version: Version) -> str:
    return ".".join(str(part) for part in version)


def _git(repo: str | Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def ref_exists(ref: str, repo: str | Path = ".") -> bool:
    try:
        _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    except RuntimeError:
        return False
    return True


def load_ref(ref: str, directory: str, repo: str | Path = ".") -> Vocabularies:
    """Load every vocabulary as it was at a commit, branch or tag."""
    if not ref_exists(ref, repo):
        raise RuntimeError(f"Git ref {ref!r} does not exist")
    listing = _git(repo, "ls-tree", "--name-only", ref, "--", f"{directory.rstrip('/')}/")
    vocabs: Vocabularies = {}
    for path in sorted(listing.splitlines()):
        if path.endswith(".tsv"):
            name = Path(path).stem
            vocabs[name] = parse_tsv(name, _git(repo, "show", f"{ref}:{path}"))
    return vocabs


def release_tags(repo: str | Path = ".") -> list[tuple[Version, str]]:
    """All tags that look like releases (vX.Y.Z), lowest version first."""
    tags = []
    for tag in _git(repo, "tag", "--list", "v*").split():
        try:
            tags.append((parse_version(tag), tag))
        except ValueError:
            continue
    return sorted(tags)


def latest_release(repo: str | Path = ".") -> str | None:
    tags = release_tags(repo)
    return tags[-1][1] if tags else None


def previous_release(version: str, repo: str | Path = ".") -> str | None:
    """The highest release tag below the given version."""
    target = parse_version(version)
    lower = [tag for v, tag in release_tags(repo) if v < target]
    return lower[-1] if lower else None
