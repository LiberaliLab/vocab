"""Repository settings, read from vocab.toml."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Config:
    title: str
    id_prefix: str
    id_digits: int
    base_iri: str
    publish_url: str
    directory: str
    mapping_prefixes: dict[str, str] = field(default_factory=dict)

    @property
    def id_regex(self) -> re.Pattern[str]:
        return re.compile(rf"^{re.escape(self.id_prefix)}:(\d{{{self.id_digits}}})$")

    def format_id(self, number: int) -> str:
        return f"{self.id_prefix}:{number:0{self.id_digits}d}"

    def id_number(self, term_id: str) -> int | None:
        match = self.id_regex.match(term_id)
        return int(match.group(1)) if match else None

    def term_iri(self, term_id: str) -> str:
        return self.base_iri + term_id.replace(":", "_", 1)

    def scheme_iri(self, vocabulary: str) -> str:
        return f"{self.base_iri}vocabulary/{vocabulary}"

    def mapping_iri(self, curie: str) -> str | None:
        prefix, sep, local = curie.partition(":")
        if not sep or not local or prefix not in self.mapping_prefixes:
            return None
        return self.mapping_prefixes[prefix] + local


def load_config(path: str | Path = "vocab.toml") -> Config:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    vocab = data["vocabulary"]
    return Config(
        title=vocab["title"],
        id_prefix=vocab["id_prefix"],
        id_digits=int(vocab["id_digits"]),
        base_iri=vocab["base_iri"],
        publish_url=vocab["publish_url"],
        directory=vocab.get("directory", "vocabularies"),
        mapping_prefixes=dict(data.get("mapping_prefixes", {})),
    )
