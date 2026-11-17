import csv
import io
import json

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, SKOS

from liblab_vocab.build import build
from liblab_vocab.model import load_dir

from .conftest import ROOT, term, vocabs


def sample():
    return vocabs(
        term("stain", id="LIBLAB:0000001", label="nuclear stain", external_mapping="FBbi:00000241"),
        term("stain", id="LIBLAB:0000002", label="DAPI", parent_id="LIBLAB:0000001", synonyms="dapi blue|D", line=3),
        term("stain", id="LIBLAB:0000003", label="old DAPI", status="deprecated", replaced_by="LIBLAB:0000002", line=4),
        term("cell_line", id="LIBLAB:0000004", label="HeLa"),
    )


def test_json_output(config, tmp_path):
    build(sample(), config, "1.2.3", tmp_path)
    data = json.loads((tmp_path / "stain.json").read_text())
    assert data["vocabulary"] == "stain"
    assert data["version"] == "1.2.3"
    dapi = data["terms"][1]
    assert dapi == {
        "id": "LIBLAB:0000002",
        "iri": "https://w3id.org/liblab/LIBLAB_0000002",
        "label": "DAPI",
        "definition": "Definition of DAPI.",
        "synonyms": ["dapi blue", "D"],
        "parent_id": "LIBLAB:0000001",
        "status": "active",
        "replaced_by": None,
        "external_mappings": [],
    }
    index = json.loads((tmp_path / "index.json").read_text())
    assert [v["name"] for v in index["vocabularies"]] == ["cell_line", "stain"]
    assert index["vocabularies"][1]["active_terms"] == 2
    terms = json.loads((tmp_path / "terms.json").read_text())
    assert terms["LIBLAB:0000004"]["vocabulary"] == "cell_line"


def test_csv_output(config, tmp_path):
    build(sample(), config, "1.2.3", tmp_path)
    rows = list(csv.DictReader(io.StringIO((tmp_path / "stain.csv").read_text())))
    assert rows[1]["synonyms"] == "dapi blue|D"
    assert len(rows) == 3


def test_skos_output(config, tmp_path):
    build(sample(), config, "1.2.3", tmp_path)
    g = Graph().parse(tmp_path / "stain.ttl")
    base = "https://w3id.org/liblab/"
    stain, dapi, old = (URIRef(f"{base}LIBLAB_000000{n}") for n in (1, 2, 3))
    scheme = URIRef(f"{base}vocabulary/stain")
    assert (dapi, SKOS.prefLabel, Literal("DAPI", lang="en")) in g
    assert (dapi, SKOS.altLabel, Literal("D", lang="en")) in g
    assert (dapi, SKOS.broader, stain) in g
    assert (stain, SKOS.narrower, dapi) in g
    assert (scheme, SKOS.hasTopConcept, stain) in g
    assert (stain, SKOS.exactMatch, URIRef("http://purl.obolibrary.org/obo/FBbi_00000241")) in g
    assert (old, OWL.deprecated, Literal(True)) in g
    assert (old, DCTERMS.isReplacedBy, dapi) in g
    assert (scheme, OWL.versionInfo, Literal("1.2.3")) in g
    combined = Graph().parse(tmp_path / "all.ttl")
    assert len(combined) > len(g)


def test_build_repository_vocabularies(config, tmp_path):
    files = build(load_dir(ROOT / "vocabularies"), config, "0.1.0", tmp_path)
    assert (tmp_path / "imaging_modality.ttl") in files
    for path in tmp_path.glob("*.ttl"):
        Graph().parse(path)
