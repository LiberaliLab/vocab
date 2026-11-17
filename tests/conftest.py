from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from liblab_vocab.config import Config, load_config
from liblab_vocab.model import COLUMNS, Term, Vocabularies

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def config() -> Config:
    return load_config(ROOT / "vocab.toml")


def term(vocabulary: str = "stain", line: int = 2, **values: str) -> Term:
    values.setdefault("status", "active")
    values.setdefault("definition", f"Definition of {values.get('label', 'a term')}.")
    unknown = set(values) - set(COLUMNS)
    assert not unknown, unknown
    return Term(vocabulary, line, **values)


def vocabs(*terms: Term) -> Vocabularies:
    result: Vocabularies = {}
    for t in terms:
        result.setdefault(t.vocabulary, []).append(t)
    return result


def tsv(*rows: list[str]) -> str:
    return "\n".join("\t".join(r) for r in [list(COLUMNS), *rows]) + "\n"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """An empty Git repository with vocab.toml and a vocabularies/ folder."""
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "commit.gpgsign", "false")
    git(tmp_path, "config", "tag.gpgsign", "false")
    (tmp_path / "vocab.toml").write_text((ROOT / "vocab.toml").read_text())
    (tmp_path / "vocabularies").mkdir()
    return tmp_path
