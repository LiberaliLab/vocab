from liblab_vocab.ids import assign_ids, next_free_number, resolve_label_references

from .conftest import term, vocabs


def test_assigns_next_free_number_across_vocabularies(config):
    v = vocabs(
        term("stain", id="LIBLAB:0000007", label="a"),
        term("stain", label="b", line=3),
        term("cell_line", label="c"),
        term("cell_line", id="LIBLAB:0000003", label="d", line=3),
    )
    assigned = assign_ids(v, config)
    # Vocabularies are processed in name order, rows in file order.
    assert [(t.label, t.id) for t in assigned] == [("c", "LIBLAB:0000008"), ("b", "LIBLAB:0000009")]


def test_never_reuses_ids_from_baseline(config):
    baseline = vocabs(term(id="LIBLAB:0000042", label="deleted by mistake"))
    current = vocabs(term(id="LIBLAB:0000001", label="a"), term(label="new", line=3))
    assert next_free_number(current, config, [baseline]) == 43
    assert assign_ids(current, config, [baseline])[0].id == "LIBLAB:0000043"


def test_starts_at_one(config):
    v = vocabs(term(label="a"))
    assert assign_ids(v, config)[0].id == "LIBLAB:0000001"


def test_ignores_malformed_ids_when_counting(config):
    v = vocabs(term(id="LIBLAB:9", label="a"), term(label="b", line=3))
    assert assign_ids(v, config)[0].id == "LIBLAB:0000001"


def test_resolves_label_references(config):
    v = vocabs(
        term("stain", id="LIBLAB:0000001", label="Nuclear stain"),
        term("stain", id="LIBLAB:0000002", label="DAPI", parent_id="nuclear STAIN", line=3),
        term("stain", id="LIBLAB:0000003", label="old", status="deprecated", replaced_by="DAPI", line=4),
        term("stain", id="LIBLAB:0000004", label="other", parent_id="no such term", line=5),
        term("method", id="LIBLAB:0000005", label="IF"),
        term("method", id="LIBLAB:0000006", label="old IF", status="deprecated", replaced_by="Nuclear stain", line=3),
        term("method", id="LIBLAB:0000007", label="child", parent_id="DAPI", line=4),
    )
    changes = resolve_label_references(v, config)
    by_label = {t.label: t for terms in v.values() for t in terms}
    assert by_label["DAPI"].parent_id == "LIBLAB:0000001"
    assert by_label["old"].replaced_by == "LIBLAB:0000002"
    # Replacements may be found in another vocabulary...
    assert by_label["old IF"].replaced_by == "LIBLAB:0000001"
    # ...parents may not, and unknown labels are left for validation to report.
    assert by_label["child"].parent_id == "DAPI"
    assert by_label["other"].parent_id == "no such term"
    assert len(changes) == 3


def test_new_terms_can_reference_each_other(config):
    v = vocabs(term(label="parent"), term(label="child", parent_id="parent", line=3))
    assign_ids(v, config)
    resolve_label_references(v, config)
    assert v["stain"][1].parent_id == v["stain"][0].id == "LIBLAB:0000001"
