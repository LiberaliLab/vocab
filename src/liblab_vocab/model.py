"""Terms and the TSV files that hold them."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from dataclasses import dataclass, fields
from pathlib import Path

COLUMNS = (
    "id",
    "label",
    "definition",
    "synonyms",
    "parent_id",
    "status",
    "replaced_by",
    "external_mapping",
)
STATUSES = ("active", "deprecated")
LIST_SEPARATOR = "|"


class VocabFormatError(ValueError):
    """A TSV file cannot be read as a vocabulary."""


@dataclass
class Term:
    vocabulary: str
    line: int  # line number in the TSV file; the header is line 1
    id: str = ""
    label: str = ""
    definition: str = ""
    synonyms: str = ""
    parent_id: str = ""
    status: str = ""
    replaced_by: str = ""
    external_mapping: str = ""

    @property
    def synonym_list(self) -> list[str]:
        return split_list(self.synonyms)

    @property
    def mapping_list(self) -> list[str]:
        return split_list(self.external_mapping)

    @property
    def active(self) -> bool:
        return self.status == "active"

    def values(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in COLUMNS}

    def where(self) -> str:
        return f"{self.vocabulary}.tsv:{self.line}"


assert tuple(f.name for f in fields(Term))[2:] == COLUMNS

# Vocabulary name -> its terms, in file order.
Vocabularies = dict[str, list[Term]]


def split_list(value: str) -> list[str]:
    return [part.strip() for part in value.split(LIST_SEPARATOR) if part.strip()]


def all_terms(vocabs: Vocabularies) -> Iterator[Term]:
    for name in sorted(vocabs):
        yield from vocabs[name]


def has_header(row: list[str]) -> bool:
    cells = [cell.strip() for cell in row]
    while cells and not cells[-1]:
        cells.pop()
    return tuple(cells) == COLUMNS


def parse_rows(vocabulary: str, rows: list[list[str]], source: str | None = None) -> list[Term]:
    """Turn rows (header first) into terms. Term.line is the 1-based row number."""
    source = source or f"{vocabulary}.tsv"
    if not rows:
        raise VocabFormatError(f"{source} is empty; it needs at least the header row")
    if not has_header(rows[0]):
        found = ", ".join(cell.strip() for cell in rows[0] if cell.strip())
        raise VocabFormatError(
            f"{source}: the header must be exactly {', '.join(COLUMNS)} (found {found})"
        )
    terms = []
    for line, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        if any(cell.strip() for cell in row[len(COLUMNS) :]):
            raise VocabFormatError(f"{source}:{line}: more than {len(COLUMNS)} columns")
        cells = [cell.strip() for cell in row[: len(COLUMNS)]]
        cells += [""] * (len(COLUMNS) - len(cells))
        terms.append(Term(vocabulary, line, *cells))
    return terms


def parse_tsv(vocabulary: str, text: str) -> list[Term]:
    rows = list(csv.reader(io.StringIO(text), delimiter="\t", quoting=csv.QUOTE_NONE))
    return parse_rows(vocabulary, rows)


def serialize_tsv(terms: list[Term]) -> str:
    # Values are written as-is (no quoting), matching how parse_tsv reads them.
    lines = ["\t".join(COLUMNS)]
    for term in terms:
        values = [term.values()[c] for c in COLUMNS]
        for column, value in zip(COLUMNS, values):
            if "\t" in value or "\n" in value or "\r" in value:
                raise VocabFormatError(
                    f"{term.where()}: {column} contains a tab or line break, which TSV cannot hold"
                )
        lines.append("\t".join(values))
    return "\n".join(lines) + "\n"


def load_dir(directory: str | Path) -> Vocabularies:
    directory = Path(directory)
    return {
        path.stem: parse_tsv(path.stem, path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("*.tsv"))
    }


def write_dir(vocabs: Vocabularies, directory: str | Path) -> None:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, terms in vocabs.items():
        (directory / f"{name}.tsv").write_text(serialize_tsv(terms), encoding="utf-8")
