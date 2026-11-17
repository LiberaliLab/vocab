import pytest

from liblab_vocab.model import load_dir
from liblab_vocab.validate import has_errors, validate

from .conftest import ROOT, term, vocabs


def errors(v, config, baselines=()):
    return [str(i) for i in validate(v, config, baselines) if i.severity == "error"]


def warnings(v, config):
    return [str(i) for i in validate(v, config) if i.severity == "warning"]


def test_repository_vocabularies_are_valid(config):
    issues = validate(load_dir(ROOT / "vocabularies"), config)
    assert issues == []


def test_valid_hierarchy(config):
    v = vocabs(
        term(id="LIBLAB:0000001", label="stain"),
        term(id="LIBLAB:0000002", label="DAPI", parent_id="LIBLAB:0000001"),
    )
    assert validate(v, config) == []


@pytest.mark.parametrize(
    "values, message",
    [
        ({"id": ""}, "id is empty"),
        ({"id": "LIBLAB:123"}, "does not look like LIBLAB:0000123"),
        ({"id": "OTHER:0000001"}, "does not look like"),
        ({"label": ""}, "label is empty"),
        ({"definition": ""}, "definition is empty"),
        ({"status": "retired"}, "status is 'retired'"),
        ({"status": ""}, "status is ''"),
        ({"external_mapping": "GO:0000001"}, "does not use a known prefix"),
        ({"external_mapping": "FBbi:"}, "nothing after the prefix"),
        ({"external_mapping": "FBbi:00000241|nope"}, "does not use a known prefix"),
        ({"parent_id": "LIBLAB:0000099"}, "parent_id LIBLAB:0000099 does not exist"),
        ({"parent_id": "LIBLAB:0000001"}, "points to the term itself"),
        ({"status": "deprecated", "replaced_by": "LIBLAB:0000099"}, "replaced_by LIBLAB:0000099 does not exist"),
        ({"status": "deprecated", "replaced_by": "LIBLAB:0000001"}, "replaced_by points to the term itself"),
        ({"replaced_by": "LIBLAB:0000002"}, "only deprecated terms can be replaced"),
    ],
)
def test_single_term_errors(config, values, message):
    base = {"id": "LIBLAB:0000001", "label": "DAPI", **values}
    other = term(id="LIBLAB:0000002", label="Hoechst")
    found = errors(vocabs(term(**base), other), config)
    assert any(message in e for e in found), found


def test_ids_unique_across_vocabularies(config):
    v = vocabs(
        term("stain", id="LIBLAB:0000001", label="DAPI"),
        term("cell_line", id="LIBLAB:0000001", label="HeLa"),
    )
    assert any("already used at cell_line.tsv:2" in e for e in errors(v, config))


def test_labels_unique_within_vocabulary_ignoring_case(config):
    v = vocabs(
        term(id="LIBLAB:0000001", label="DAPI"),
        term(id="LIBLAB:0000002", label="dapi", line=3),
    )
    assert any("label 'dapi' is already used" in e for e in errors(v, config))


def test_same_label_in_two_vocabularies_is_fine(config):
    v = vocabs(
        term("stain", id="LIBLAB:0000001", label="unknown"),
        term("cell_line", id="LIBLAB:0000002", label="unknown"),
    )
    assert errors(v, config) == []


def test_replaced_by_must_be_active(config):
    v = vocabs(
        term(id="LIBLAB:0000001", label="a", status="deprecated", replaced_by="LIBLAB:0000002"),
        term(id="LIBLAB:0000002", label="b", status="deprecated"),
    )
    assert any("is deprecated; it must be active" in e for e in errors(v, config))


def test_replaced_by_may_point_to_another_vocabulary(config):
    v = vocabs(
        term("stain", id="LIBLAB:0000001", label="a", status="deprecated", replaced_by="LIBLAB:0000002"),
        term("labelling_method", id="LIBLAB:0000002", label="b"),
    )
    assert errors(v, config) == []


def test_parent_must_be_in_same_vocabulary(config):
    v = vocabs(
        term("stain", id="LIBLAB:0000001", label="a", parent_id="LIBLAB:0000002"),
        term("labelling_method", id="LIBLAB:0000002", label="b"),
    )
    assert any("must be in the same vocabulary" in e for e in errors(v, config))


def test_cycle_detected_once(config):
    v = vocabs(
        term(id="LIBLAB:0000001", label="a", parent_id="LIBLAB:0000003"),
        term(id="LIBLAB:0000002", label="b", parent_id="LIBLAB:0000001"),
        term(id="LIBLAB:0000003", label="c", parent_id="LIBLAB:0000002"),
        term(id="LIBLAB:0000004", label="d", parent_id="LIBLAB:0000003"),
    )
    cycles = [e for e in errors(v, config) if "cycle" in e]
    assert len(cycles) == 1


def test_deleted_id_is_an_error(config):
    baseline = vocabs(term(id="LIBLAB:0000001", label="a"), term(id="LIBLAB:0000002", label="b"))
    current = vocabs(term(id="LIBLAB:0000001", label="a"))
    found = errors(current, config, [("v1.0.0", baseline)])
    assert found == [
        "ERROR stain.tsv: LIBLAB:0000002 ('b', in stain) exists in v1.0.0 but is missing now. "
        "Terms are never deleted: set status to deprecated instead."
    ]


def test_moving_a_term_to_another_vocabulary_is_not_a_deletion(config):
    baseline = vocabs(term("stain", id="LIBLAB:0000001", label="a"))
    current = vocabs(term("dye", id="LIBLAB:0000001", label="a"))
    assert errors(current, config, [("v1.0.0", baseline)]) == []


def test_bad_vocabulary_name(config):
    assert any("must be lowercase" in e for e in errors(vocabs(term("Bad-Name", id="LIBLAB:0000001", label="a")), config))


def test_warnings(config):
    v = vocabs(
        term(id="LIBLAB:0000001", label="a", status="deprecated"),
        term(id="LIBLAB:0000002", label="b", parent_id="LIBLAB:0000001", synonyms="B|x||x"),
    )
    found = warnings(v, config)
    assert any("deprecated parent" in w for w in found)
    assert any("repeats the label" in w for w in found)
    assert any("listed twice" in w for w in found)
    assert any("empty entry" in w for w in found)
    assert not has_errors(validate(v, config))
