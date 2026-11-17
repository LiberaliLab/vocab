import pytest

from liblab_vocab.model import VocabFormatError, load_dir, parse_tsv, serialize_tsv

from .conftest import ROOT, tsv


def test_parse_and_roundtrip():
    text = tsv(
        ["LIBLAB:0000001", "DAPI", "A blue DNA stain.", "4',6-diamidino-2-phenylindole| dapi ", "", "active", "", ""],
    )
    terms = parse_tsv("stain", text)
    assert len(terms) == 1
    t = terms[0]
    assert (t.id, t.label, t.line) == ("LIBLAB:0000001", "DAPI", 2)
    assert t.synonym_list == ["4',6-diamidino-2-phenylindole", "dapi"]
    assert parse_tsv("stain", serialize_tsv(terms))[0] == t


def test_quotes_are_kept_literally():
    text = tsv(["", '"quoted" label', 'He said "hi".', "", "", "active", "", ""])
    t = parse_tsv("stain", text)[0]
    assert t.label == '"quoted" label'
    assert parse_tsv("stain", serialize_tsv([t]))[0].definition == 'He said "hi".'


def test_short_rows_are_padded_and_blank_rows_skipped():
    text = tsv(["", "DAPI", "A stain.", "", "", "active"], [""], ["", "", "", "", "", "", "", ""])
    terms = parse_tsv("stain", text)
    assert len(terms) == 1
    assert terms[0].external_mapping == ""


@pytest.mark.parametrize(
    "text, message",
    [
        ("", "empty"),
        ("id\tlabel\n", "header must be exactly"),
        (tsv(["", "a", "b", "", "", "active", "", "", "extra"]), "more than 8 columns"),
    ],
)
def test_format_errors(text, message):
    with pytest.raises(VocabFormatError, match=message):
        parse_tsv("stain", text)


def test_serialize_rejects_tabs():
    t = parse_tsv("stain", tsv(["", "a", "b", "", "", "active", "", ""]))[0]
    t.definition = "has\ta tab"
    with pytest.raises(VocabFormatError, match="tab or line break"):
        serialize_tsv([t])


def test_repository_vocabularies_load():
    vocabs = load_dir(ROOT / "vocabularies")
    assert {"tissue_type", "labelling_method", "imaging_modality"} <= set(vocabs)
