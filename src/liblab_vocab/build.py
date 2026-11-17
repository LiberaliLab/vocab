"""Release outputs: JSON for our tooling, CSV and SKOS/Turtle for interop."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, SKOS, XSD

from .config import Config
from .model import COLUMNS, LIST_SEPARATOR, Term, Vocabularies, all_terms

LANG = "en"


def term_record(term: Term, config: Config) -> dict:
    return {
        "id": term.id,
        "iri": config.term_iri(term.id),
        "label": term.label,
        "definition": term.definition,
        "synonyms": term.synonym_list,
        "parent_id": term.parent_id or None,
        "status": term.status,
        "replaced_by": term.replaced_by or None,
        "external_mappings": term.mapping_list,
    }


def vocabulary_json(name: str, terms: list[Term], config: Config, version: str) -> dict:
    return {
        "vocabulary": name,
        "version": version,
        "iri": config.scheme_iri(name),
        "terms": [term_record(t, config) for t in terms],
    }


def vocabulary_csv(terms: list[Term]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    for term in terms:
        writer.writerow([term.values()[c] for c in COLUMNS])
    return out.getvalue()


def skos_graph(vocabs: Vocabularies, config: Config, version: str) -> Graph:
    graph = Graph()
    graph.bind("skos", SKOS)
    graph.bind("dcterms", DCTERMS)
    graph.bind("owl", OWL)
    graph.bind(config.id_prefix.lower(), Namespace(config.base_iri))
    for prefix, iri in config.mapping_prefixes.items():
        graph.bind(prefix.lower(), Namespace(iri))

    by_id = {t.id: t for t in all_terms(vocabs)}
    for name, terms in sorted(vocabs.items()):
        scheme = URIRef(config.scheme_iri(name))
        graph.add((scheme, RDF.type, SKOS.ConceptScheme))
        graph.add((scheme, DCTERMS.title, Literal(name)))
        graph.add((scheme, OWL.versionInfo, Literal(version)))
        for term in terms:
            concept = URIRef(config.term_iri(term.id))
            graph.add((concept, RDF.type, SKOS.Concept))
            graph.add((concept, SKOS.inScheme, scheme))
            graph.add((concept, SKOS.notation, Literal(term.id)))
            graph.add((concept, SKOS.prefLabel, Literal(term.label, lang=LANG)))
            graph.add((concept, SKOS.definition, Literal(term.definition, lang=LANG)))
            for synonym in term.synonym_list:
                graph.add((concept, SKOS.altLabel, Literal(synonym, lang=LANG)))
            if term.parent_id and term.parent_id in by_id:
                parent = URIRef(config.term_iri(term.parent_id))
                graph.add((concept, SKOS.broader, parent))
                graph.add((parent, SKOS.narrower, concept))
            else:
                graph.add((concept, SKOS.topConceptOf, scheme))
                graph.add((scheme, SKOS.hasTopConcept, concept))
            if not term.active:
                graph.add((concept, OWL.deprecated, Literal(True, datatype=XSD.boolean)))
            if term.replaced_by:
                graph.add((concept, DCTERMS.isReplacedBy, URIRef(config.term_iri(term.replaced_by))))
            for mapping in term.mapping_list:
                iri = config.mapping_iri(mapping)
                if iri:
                    graph.add((concept, SKOS.exactMatch, URIRef(iri)))
    return graph


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _json(data: object) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def build(vocabs: Vocabularies, config: Config, version: str, out_dir: str | Path) -> list[Path]:
    """Write every output for one release into out_dir. Returns the files written."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, terms in sorted(vocabs.items()):
        written.append(_write(out / f"{name}.json", _json(vocabulary_json(name, terms, config, version))))
        written.append(_write(out / f"{name}.csv", vocabulary_csv(terms)))
        graph = skos_graph({name: terms}, config, version)
        written.append(_write(out / f"{name}.ttl", graph.serialize(format="turtle")))

    written.append(_write(out / "all.ttl", skos_graph(vocabs, config, version).serialize(format="turtle")))

    # One lookup table for every ID, whichever vocabulary it is in. A w3id.org
    # redirect or a client can use it to resolve an ID on its own.
    terms_index = {
        t.id: {"vocabulary": t.vocabulary, "label": t.label, "status": t.status, "iri": config.term_iri(t.id)}
        for t in sorted(all_terms(vocabs), key=lambda t: t.id)
    }
    written.append(_write(out / "terms.json", _json(terms_index)))

    index = {
        "title": config.title,
        "version": version,
        "id_prefix": config.id_prefix,
        "list_separator": LIST_SEPARATOR,
        "vocabularies": [
            {
                "name": name,
                "terms": len(terms),
                "active_terms": sum(t.active for t in terms),
                "files": {ext: f"{name}.{ext}" for ext in ("json", "csv", "ttl")},
            }
            for name, terms in sorted(vocabs.items())
        ],
    }
    written.append(_write(out / "index.json", _json(index)))
    return written
