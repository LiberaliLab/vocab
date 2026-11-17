"""Assigning IDs to new terms."""

from __future__ import annotations

from collections.abc import Sequence

from .config import Config
from .model import Term, Vocabularies, all_terms


def resolve_label_references(vocabs: Vocabularies, config: Config) -> list[tuple[Term, str, str]]:
    """Let editors name a parent or replacement by its label instead of its ID.

    A parent_id or replaced_by value that is not an ID but matches a label is
    replaced by that term's ID. A parent is looked up in the term's own
    vocabulary. A replacement is looked up in the term's own vocabulary first,
    then in all vocabularies if the label is unique across them.
    Run this after assign_ids so that new terms can be referenced too.

    Returns (term, column, old value) for each change.
    """
    own: dict[str, dict[str, Term]] = {}
    anywhere: dict[str, list[Term]] = {}
    for term in all_terms(vocabs):
        if term.label and term.id:
            key = term.label.casefold().strip()
            own.setdefault(term.vocabulary, {})[key] = term
            anywhere.setdefault(key, []).append(term)

    changes = []
    for term in all_terms(vocabs):
        for column in ("parent_id", "replaced_by"):
            value = getattr(term, column)
            if not value or config.id_number(value) is not None:
                continue
            key = value.casefold().strip()
            target = own.get(term.vocabulary, {}).get(key)
            if target is None and column == "replaced_by" and len(anywhere.get(key, [])) == 1:
                target = anywhere[key][0]
            if target is not None:
                setattr(term, column, target.id)
                changes.append((term, column, value))
    return changes


def next_free_number(
    vocabs: Vocabularies, config: Config, baselines: Sequence[Vocabularies] = ()
) -> int:
    numbers = [
        n
        for source in (vocabs, *baselines)
        for term in all_terms(source)
        if (n := config.id_number(term.id)) is not None
    ]
    return max(numbers, default=0) + 1


def assign_ids(
    vocabs: Vocabularies, config: Config, baselines: Sequence[Vocabularies] = ()
) -> list[Term]:
    """Give every term with an empty id the next free ID, in a stable order.

    IDs already used in the baselines (e.g. the last release) are never handed out
    again, even if a term was wrongly deleted since.
    """
    number = next_free_number(vocabs, config, baselines)
    assigned = []
    for term in all_terms(vocabs):
        if not term.id:
            term.id = config.format_id(number)
            number += 1
            assigned.append(term)
    return assigned
