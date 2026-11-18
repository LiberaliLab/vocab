# Liberali Lab controlled vocabularies

The lab's annotation vocabularies (`tissue_type`, `labelling_method`, `imaging_modality`, …), published as versioned static files:

```
https://liberalilab.github.io/vocab/latest/imaging_modality.json
https://liberalilab.github.io/vocab/v1.4.0/imaging_modality.json
```

Pipelines should pin a version; interactive tools may use `latest`.

```python
import requests

BASE = "https://liberalilab.github.io/vocab"
vocab = requests.get(f"{BASE}/v1.4.0/imaging_modality.json").json()
```

Each release has, per vocabulary, `<name>.json` and `<name>.csv`. It also has `terms.json` mapping every ID to its vocabulary, and `index.json` listing what the release contains.

SKOS/Turtle files (`<name>.ttl`, `all.ttl`) and term IRIs in the JSON are switched off until the `w3id.org/liblab/` namespace is registered and the IRIs resolve. Both are turned back on under `[publish]` in `vocab.toml`.

## How it works

1. Lab members edit the shared Google Sheet. There is one tab per vocabulary. They leave `id` empty on new rows and never delete rows.
2. A sync job (nightly, or Actions → sync → Run workflow) reads the sheet, assigns IDs and writes them back into the sheet, validates, and opens or updates one pull request from the branch `sheet-sync`. Validation problems are listed in the pull request so the editor can fix them in the sheet.
3. The curator reviews and merges the pull request. Nothing is published yet.
4. The curator tags a release (`vX.Y.Z`). CI checks the version number, builds the files and publishes them under the new version and `latest`.

`vocabularies/*.tsv` holds the reviewed state, and the sheet is where people edit. Changes flow one way, from the sheet to the repo: an edit made directly to a TSV file is overwritten by the next sync unless the same edit is made in the sheet. One-time configuration of GitHub and Google is in [docs/setup.md](docs/setup.md).

## Term columns

| Column | Required | Meaning |
| --- | --- | --- |
| `id` | yes (assigned automatically) | `LIBLAB:` plus seven digits. Opaque, unique across all vocabularies, never reused. |
| `label` | yes | Preferred name, unique within its vocabulary (ignoring case). |
| `definition` | yes | One or two sentences. |
| `synonyms` | no | Alternative names separated by `\|`. |
| `parent_id` | no | ID of the broader term in the same vocabulary. New rows may give the parent's label instead; it is turned into the ID when IDs are assigned. |
| `status` | yes | `active` or `deprecated`. |
| `replaced_by` | no | For deprecated terms: ID (or label) of the active term that replaces it. |
| `external_mapping` | no | Matching term in another ontology, e.g. `FBbi:00000241`. Several are separated by `\|`. Allowed prefixes are listed in `vocab.toml`. In SKOS output (when enabled) it becomes `skos:exactMatch`. |

## Releasing (curator)

Pick the version from what changed since the last release. The `validate` check on each pull request prints the required bump.

| Change | Bump |
| --- | --- |
| Term deprecated or deleted, term moved to another vocabulary | major |
| New term, new vocabulary, term reactivated, `parent_id` changed | minor |
| Label, definition, synonyms, mapping or `replaced_by` changed | patch |

Then tag `main` and push the tag:

```bash
git checkout main && git pull
```

```bash
git tag v1.5.0 && git push origin v1.5.0
```

The release workflow refuses a version that is too small a bump, a tag that is not on `main`, and a version that is already published. Published versions are never rebuilt or overwritten.

## Development

Needs [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

```bash
uv run pytest
```

```bash
uv run vocab validate --against-latest-release
```

Other commands: `vocab sync-sheet --sheet <ID> --no-write-back` (needs `uv sync --extra sheets` and `gcloud auth application-default login --scopes=https://www.googleapis.com/auth/spreadsheets,https://www.googleapis.com/auth/cloud-platform`), `vocab assign-ids`, `vocab diff <ref>`, `vocab check-version vX.Y.Z`, `vocab build --version X.Y.Z --out build/`. Run `uv run vocab --help` for details.
