"""The validation rules from the design summary."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .config import Config
from .model import STATUSES, Term, Vocabularies, all_terms

VOCAB_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class Issue:
    severity: str  # "error" or "warning"
    message: str
    where: str = ""
    term_id: str = ""

    def __str__(self) -> str:
        parts = [self.severity.upper()]
        if self.where:
            parts.append(self.where)
        if self.term_id:
            parts.append(f"[{self.term_id}]")
        return " ".join(parts) + f": {self.message}"


def _error(message: str, term: Term | None = None, where: str = "") -> Issue:
    return Issue("error", message, term.where() if term else where, term.id if term else "")


def _warning(message: str, term: Term | None = None) -> Issue:
    return Issue("warning", message, term.where() if term else "", term.id if term else "")


def validate(
    vocabs: Vocabularies,
    config: Config,
    baselines: Sequence[tuple[str, Vocabularies]] = (),
) -> list[Issue]:
    """Check the vocabularies.

    baselines are earlier states (e.g. the last release, the PR's base branch) as
    (name, vocabularies) pairs; no ID present in any of them may disappear.
    """
    issues: list[Issue] = []
    terms = list(all_terms(vocabs))

    for name in sorted(vocabs):
        if not VOCAB_NAME_RE.match(name):
            issues.append(
                _error(
                    f"vocabulary name {name!r} must be lowercase letters, digits and underscores",
                    where=f"{name}.tsv",
                )
            )

    by_id: dict[str, Term] = {}
    for term in terms:
        issues.extend(_check_term(term, config))
        if not term.id:
            continue
        if term.id in by_id:
            first = by_id[term.id]
            issues.append(_error(f"ID is already used at {first.where()}", term))
        else:
            by_id[term.id] = term

    for name, vocab_terms in sorted(vocabs.items()):
        issues.extend(_check_unique_labels(vocab_terms))

    for term in terms:
        issues.extend(_check_references(term, by_id))

    issues.extend(_check_cycles(by_id))

    for baseline_name, baseline in baselines:
        for old in all_terms(baseline):
            if old.id and old.id not in by_id:
                issues.append(
                    _error(
                        f"{old.id} ({old.label!r}, in {old.vocabulary}) exists in {baseline_name} "
                        "but is missing now. Terms are never deleted: set status to deprecated instead.",
                        where=f"{old.vocabulary}.tsv",
                    )
                )
    return issues


def _check_term(term: Term, config: Config) -> Iterable[Issue]:
    if not term.id:
        yield _error("id is empty; run the ID assignment step first", term)
    elif config.id_number(term.id) is None:
        example = config.format_id(123)
        yield _error(f"id {term.id!r} does not look like {example}", term)
    if not term.label:
        yield _error("label is empty", term)
    if not term.definition:
        yield _error("definition is empty", term)
    if term.status not in STATUSES:
        yield _error(f"status is {term.status!r}; it must be one of {', '.join(STATUSES)}", term)
    if term.replaced_by and term.status == "active":
        yield _error("replaced_by is set, but only deprecated terms can be replaced", term)

    synonyms = term.synonym_list
    if term.synonyms and len(synonyms) != term.synonyms.count("|") + 1:
        yield _warning("synonyms contain an empty entry (doubled or trailing '|')", term)
    seen: set[str] = set()
    for synonym in synonyms:
        key = _normalise(synonym)
        if key == _normalise(term.label):
            yield _warning(f"synonym {synonym!r} repeats the label", term)
        elif key in seen:
            yield _warning(f"synonym {synonym!r} is listed twice", term)
        seen.add(key)

    for mapping in term.mapping_list:
        prefix = mapping.partition(":")[0]
        if config.mapping_iri(mapping) is None:
            known = ", ".join(f"{p}:" for p in config.mapping_prefixes)
            if prefix in config.mapping_prefixes:
                yield _error(f"external_mapping {mapping!r} has nothing after the prefix", term)
            else:
                yield _error(
                    f"external_mapping {mapping!r} does not use a known prefix ({known})", term
                )


def _normalise(label: str) -> str:
    return " ".join(label.casefold().split())


def _check_unique_labels(terms: list[Term]) -> Iterable[Issue]:
    seen: dict[str, Term] = {}
    for term in terms:
        if not term.label:
            continue
        key = _normalise(term.label)
        if key in seen:
            yield _error(f"label {term.label!r} is already used at {seen[key].where()}", term)
        else:
            seen[key] = term


def _check_references(term: Term, by_id: dict[str, Term]) -> Iterable[Issue]:
    if term.parent_id:
        parent = by_id.get(term.parent_id)
        if parent is None:
            yield _error(f"parent_id {term.parent_id} does not exist", term)
        elif parent is term:
            yield _error("parent_id points to the term itself", term)
        elif parent.vocabulary != term.vocabulary:
            yield _error(
                f"parent_id {term.parent_id} is in {parent.vocabulary}; "
                "the parent must be in the same vocabulary",
                term,
            )
        elif term.active and not parent.active:
            yield _warning(f"active term has a deprecated parent ({term.parent_id})", term)
    if term.replaced_by:
        target = by_id.get(term.replaced_by)
        if target is None:
            yield _error(f"replaced_by {term.replaced_by} does not exist", term)
        elif target is term:
            yield _error("replaced_by points to the term itself", term)
        elif not target.active:
            yield _error(f"replaced_by {term.replaced_by} is deprecated; it must be active", term)


def _check_cycles(by_id: dict[str, Term]) -> Iterable[Issue]:
    reported: set[str] = set()
    done: set[str] = set()
    for start in by_id:
        path: list[str] = []
        on_path: set[str] = set()
        current: str | None = start
        while current and current in by_id and current not in done:
            if current in on_path:
                cycle = path[path.index(current) :]
                key = min(cycle)
                if key not in reported:
                    reported.add(key)
                    chain = " -> ".join(cycle + [current])
                    yield _error(f"parent_id hierarchy has a cycle: {chain}", by_id[current])
                break
            path.append(current)
            on_path.add(current)
            current = by_id[current].parent_id or None
        done.update(path)


def has_errors(issues: Iterable[Issue]) -> bool:
    return any(issue.severity == "error" for issue in issues)
