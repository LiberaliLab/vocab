import pytest

from liblab_vocab.diff import Bump, actual_bump, diff, format_markdown, required_bump

from .conftest import term, vocabs


def base():
    return vocabs(
        term(id="LIBLAB:0000001", label="a"),
        term(id="LIBLAB:0000002", label="b", line=3),
    )


def kinds(changes):
    return [(c.bump, c.kind, c.term_id) for c in changes]


def test_no_changes():
    changes = diff(base(), base())
    assert changes == []
    assert required_bump(changes) == Bump.NONE
    assert "No changes." in format_markdown(changes, "x")


@pytest.mark.parametrize(
    "edit, expected",
    [
        (lambda t: setattr(t, "label", "A"), (Bump.PATCH, "label changed")),
        (lambda t: setattr(t, "definition", "New."), (Bump.PATCH, "definition changed")),
        (lambda t: setattr(t, "synonyms", "x"), (Bump.PATCH, "synonyms changed")),
        (lambda t: setattr(t, "external_mapping", "FBbi:1"), (Bump.PATCH, "external_mapping changed")),
        (lambda t: setattr(t, "parent_id", "LIBLAB:0000002"), (Bump.MINOR, "parent_id changed")),
        (lambda t: setattr(t, "status", "deprecated"), (Bump.MAJOR, "deprecated")),
        (lambda t: setattr(t, "vocabulary", "other"), (Bump.MAJOR, "moved to another vocabulary")),
    ],
)
def test_term_edits(edit, expected):
    new = base()
    edit(new["stain"][0])
    changes = diff(base(), new)
    assert (changes[0].bump, changes[0].kind) == expected


def test_deprecation_with_replacement_is_one_change():
    new = base()
    new["stain"][0].status = "deprecated"
    new["stain"][0].replaced_by = "LIBLAB:0000002"
    changes = diff(base(), new)
    assert kinds(changes) == [(Bump.MAJOR, "deprecated", "LIBLAB:0000001")]
    assert changes[0].detail == "replaced by LIBLAB:0000002"


def test_added_removed_and_new_vocabulary():
    new = base()
    del new["stain"][1]
    new["stain"].append(term(id="LIBLAB:0000003", label="c"))
    new["cell_line"] = [term("cell_line", id="LIBLAB:0000004", label="HeLa")]
    assert kinds(diff(base(), new)) == [
        (Bump.MAJOR, "term deleted", "LIBLAB:0000002"),
        (Bump.MINOR, "new vocabulary", ""),
        (Bump.MINOR, "term added", "LIBLAB:0000004"),
        (Bump.MINOR, "term added", "LIBLAB:0000003"),
    ]


def test_reactivation_is_minor():
    old = base()
    old["stain"][0].status = "deprecated"
    assert kinds(diff(old, base())) == [(Bump.MINOR, "reactivated", "LIBLAB:0000001")]


@pytest.mark.parametrize(
    "old, new, bump",
    [
        ((1, 4, 0), (2, 0, 0), Bump.MAJOR),
        ((1, 4, 0), (1, 5, 0), Bump.MINOR),
        ((1, 4, 0), (1, 4, 1), Bump.PATCH),
        ((1, 4, 0), (1, 4, 0), Bump.NONE),
        ((1, 4, 0), (1, 3, 9), Bump.NONE),
    ],
)
def test_actual_bump(old, new, bump):
    assert actual_bump(old, new) == bump


def test_markdown_escapes_pipes():
    new = base()
    new["stain"][0].synonyms = "x|y"
    text = format_markdown(diff(base(), new), "Changes")
    assert "Required version bump: **patch**" in text
    assert "x\\|y" in text
