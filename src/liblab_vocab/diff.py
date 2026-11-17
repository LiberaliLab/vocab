"""What changed between two states, and which version bump that needs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from .gitrefs import Version
from .model import Term, Vocabularies, all_terms


class Bump(IntEnum):
    NONE = 0
    PATCH = 1
    MINOR = 2
    MAJOR = 3

    def __str__(self) -> str:
        return self.name.lower()


# Field edits on an existing term, and the bump each needs.
FIELD_BUMPS = {
    "label": Bump.PATCH,
    "definition": Bump.PATCH,
    "synonyms": Bump.PATCH,
    "external_mapping": Bump.PATCH,
    "replaced_by": Bump.PATCH,
    "parent_id": Bump.MINOR,
}


@dataclass(frozen=True)
class Change:
    bump: Bump
    kind: str
    vocabulary: str
    term_id: str = ""
    label: str = ""
    detail: str = ""


def diff(old: Vocabularies, new: Vocabularies) -> list[Change]:
    changes: list[Change] = []
    for name in sorted(set(new) - set(old)):
        changes.append(Change(Bump.MINOR, "new vocabulary", name))
    for name in sorted(set(old) - set(new)):
        changes.append(Change(Bump.MAJOR, "vocabulary removed", name))

    old_terms = {t.id: t for t in all_terms(old) if t.id}
    new_terms = {t.id: t for t in all_terms(new) if t.id}

    for term_id, term in new_terms.items():
        if term_id not in old_terms:
            changes.append(Change(Bump.MINOR, "term added", term.vocabulary, term_id, term.label))
    for term_id, term in old_terms.items():
        if term_id not in new_terms:
            changes.append(Change(Bump.MAJOR, "term deleted", term.vocabulary, term_id, term.label))

    for term_id in sorted(old_terms.keys() & new_terms.keys()):
        changes.extend(_term_changes(old_terms[term_id], new_terms[term_id]))

    return sorted(changes, key=lambda c: (-c.bump, c.vocabulary, c.term_id, c.kind))


def _term_changes(old: Term, new: Term) -> list[Change]:
    changes = []

    def add(bump: Bump, kind: str, detail: str = "") -> None:
        changes.append(Change(bump, kind, new.vocabulary, new.id, new.label, detail))

    if old.vocabulary != new.vocabulary:
        add(Bump.MAJOR, "moved to another vocabulary", f"{old.vocabulary} → {new.vocabulary}")
    if old.status != new.status:
        if new.status == "deprecated":
            add(Bump.MAJOR, "deprecated", f"replaced by {new.replaced_by}" if new.replaced_by else "")
        else:
            add(Bump.MINOR, "reactivated", f"{old.status} → {new.status}")
    for column, bump in FIELD_BUMPS.items():
        before, after = getattr(old, column), getattr(new, column)
        if before != after and not (column == "replaced_by" and old.status != new.status):
            add(bump, f"{column} changed", f"{before or '(empty)'} → {after or '(empty)'}")
    return changes


def required_bump(changes: list[Change]) -> Bump:
    return max((c.bump for c in changes), default=Bump.NONE)


def actual_bump(old: Version, new: Version) -> Bump:
    """The bump that going from version old to version new represents."""
    if new <= old:
        return Bump.NONE
    if new[0] > old[0]:
        return Bump.MAJOR
    if new[1] > old[1]:
        return Bump.MINOR
    return Bump.PATCH


def format_markdown(changes: list[Change], title: str) -> str:
    bump = required_bump(changes)
    lines = [f"### {title}", ""]
    if not changes:
        lines.append("No changes.")
        return "\n".join(lines) + "\n"
    lines.append(f"Required version bump: **{bump}**")
    lines += ["", "| Bump | Change | Vocabulary | Term | Detail |", "| --- | --- | --- | --- | --- |"]
    for c in changes:
        term = f"`{c.term_id}` {c.label}".strip() if c.term_id else ""
        detail = c.detail.replace("|", "\\|")
        lines.append(f"| {c.bump} | {c.kind} | {c.vocabulary} | {term} | {detail} |")
    return "\n".join(lines) + "\n"
