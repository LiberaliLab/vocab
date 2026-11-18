"""Sheet → repository sync.

1. Read every vocabulary tab from the sheet.
2. Give new rows IDs and turn parent/replacement labels into IDs.
3. Write those IDs back into the sheet (after checking nobody moved the rows).
4. Validate, and return the vocabularies plus a Markdown report for the PR.

Validation problems do not stop the sync: they go into the report so the pull
request shows the editor what to fix. Problems that make the sheet unreadable
(a missing tab, a broken header) do stop it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from .config import Config
from .diff import diff, format_markdown, required_bump
from .ids import assign_ids, resolve_label_references
from .model import COLUMNS, Term, VocabFormatError, Vocabularies, has_header, parse_rows
from .sheets import SheetSource
from .validate import VOCAB_NAME_RE, Issue, validate

ID_COLUMN = COLUMNS.index("id") + 1


class SyncError(RuntimeError):
    """The sheet cannot be synced as it is; nothing was written."""


@dataclass
class SyncResult:
    vocabs: Vocabularies
    assigned: list[Term] = field(default_factory=list)
    resolved: list[tuple[Term, str, str]] = field(default_factory=list)
    cleaned: list[str] = field(default_factory=list)
    ignored_tabs: list[str] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]


def _clean(value: str) -> str:
    return " ".join(value.split()) if any(c in value for c in "\t\r\n") else value


def read_sheet(
    tabs: dict[str, list[list[str]]], existing: Sequence[str]
) -> tuple[Vocabularies, list[str], list[str]]:
    """Pick the vocabulary tabs and parse them.

    A tab is a vocabulary when its name is a valid vocabulary name and its first
    row is the standard header. Returns (vocabularies, ignored tab names, notes
    about cleaned-up cells).
    """
    vocabs: Vocabularies = {}
    ignored: list[str] = []
    cleaned: list[str] = []
    for title, rows in tabs.items():
        name = title.strip()
        is_vocab = VOCAB_NAME_RE.match(name) and rows and has_header(rows[0])
        if not is_vocab:
            if name in existing:
                raise SyncError(
                    f"Tab {title!r} must start with the header row "
                    f"{', '.join(COLUMNS)} (in that order)."
                )
            ignored.append(title)
            continue
        if name in vocabs:
            raise SyncError(f"There are two tabs named {name!r}.")
        clean_rows = []
        for r, row in enumerate(rows, start=1):
            clean_row = []
            for c, value in enumerate(row):
                new = _clean(value)
                if new != value:
                    column = COLUMNS[c] if c < len(COLUMNS) else f"column {c + 1}"
                    cleaned.append(f"{name} row {r}, {column}: line breaks or tabs replaced by spaces")
                clean_row.append(new)
            clean_rows.append(clean_row)
        try:
            vocabs[name] = parse_rows(name, clean_rows, source=f"tab {name!r}")
        except VocabFormatError as error:
            raise SyncError(str(error)) from error

    missing = sorted(set(existing) - set(vocabs))
    if missing:
        raise SyncError(
            f"The repository has vocabularies with no tab in the sheet: {', '.join(missing)}. "
            "Restore or rename the tab; vocabularies are never removed."
        )
    return vocabs, ignored, cleaned


def _planned_cells(result: SyncResult) -> dict[str, list[tuple[Term, int, str]]]:
    cells: dict[str, list[tuple[Term, int, str]]] = {}
    for term in result.assigned:
        cells.setdefault(term.vocabulary, []).append((term, ID_COLUMN, term.id))
    for term, column, _ in result.resolved:
        cells.setdefault(term.vocabulary, []).append(
            (term, COLUMNS.index(column) + 1, getattr(term, column))
        )
    return cells


def _check_unchanged(fresh: dict[str, list[list[str]]], planned: dict[str, list[tuple[Term, int, str]]]) -> None:
    """Make sure each row we are about to write to still holds the same term."""
    for tab, cells in planned.items():
        rows = fresh.get(tab, [])
        for term, column, _ in cells:
            row = rows[term.line - 1] if term.line <= len(rows) else []
            row = row + [""] * (len(COLUMNS) - len(row))
            label = _clean(row[COLUMNS.index("label")]).strip()
            id_taken = column == ID_COLUMN and row[ID_COLUMN - 1].strip() != ""
            if label != term.label or id_taken:
                raise SyncError(
                    f"Tab {tab!r} row {term.line} changed while syncing "
                    f"(expected {term.label!r}). Nothing was written; run the sync again."
                )


def sync(
    source: SheetSource,
    config: Config,
    current: Vocabularies,
    baselines: Sequence[tuple[str, Vocabularies]] = (),
    write_back: bool = True,
) -> SyncResult:
    """Run the sync. current is the repository's state (main); baselines are older states."""
    vocabs, ignored, cleaned = read_sheet(source.read_tabs(), list(current))
    result = SyncResult(vocabs, ignored_tabs=ignored, cleaned=cleaned)

    id_sources = [current, *(b for _, b in baselines)]
    result.assigned = assign_ids(vocabs, config, id_sources)
    result.resolved = resolve_label_references(vocabs, config)

    planned = _planned_cells(result)
    if write_back and planned:
        _check_unchanged(source.read_tabs(), planned)
        for tab, cells in planned.items():
            source.write_cells(tab, [(term.line, col, value) for term, col, value in cells])

    result.issues = validate(vocabs, config, [("main", current), *baselines])
    return result


def report(
    result: SyncResult,
    current: Vocabularies,
    sheet_url: str,
    latest_release: tuple[str, Vocabularies] | None = None,
) -> str:
    """Markdown for the pull request body."""
    lines = [
        f"Changes from the [vocabulary sheet]({sheet_url}), synced automatically.",
        "",
        "Locations like `imaging_modality.tsv:5` mean **row 5 of the `imaging_modality` tab**.",
        "",
    ]
    errors = result.errors
    warnings = [i for i in result.issues if i.severity == "warning"]
    if errors:
        lines += [f"## ❌ {len(errors)} problem(s) to fix in the sheet", ""]
        lines += [f"- {i}" for i in errors]
        lines += ["", "Fix these in the sheet; the next sync updates this pull request.", ""]
    else:
        lines += ["## ✅ Validation passed", ""]
    if warnings:
        lines += [f"<details><summary>{len(warnings)} warning(s)</summary>", ""]
        lines += [f"- {i}" for i in warnings]
        lines += ["", "</details>", ""]
    if result.assigned:
        lines += ["## New IDs (also written into the sheet)", ""]
        lines += [f"- `{t.id}` {t.label} ({t.vocabulary} row {t.line})" for t in result.assigned]
        lines.append("")
    if result.resolved:
        lines += ["## Labels turned into IDs", ""]
        lines += [
            f"- {t.vocabulary} row {t.line}, {col}: {old!r} → `{getattr(t, col)}`"
            for t, col, old in result.resolved
        ]
        lines.append("")
    if result.cleaned:
        lines += ["## Cleaned-up cells", ""] + [f"- {c}" for c in result.cleaned] + [""]
    lines.append(format_markdown(diff(current, result.vocabs), "Changes compared with main"))
    if latest_release:
        name, old = latest_release
        changes = diff(old, result.vocabs)
        lines.append(
            f"If released now, the version after {name} needs a **{required_bump(changes)}** bump."
        )
    if result.ignored_tabs:
        lines += ["", f"Tabs ignored (not vocabularies): {', '.join(result.ignored_tabs)}"]
    return "\n".join(lines) + "\n"
