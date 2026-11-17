# One-time setup

The settings that live outside the code. Tick each item when done.

## GitHub (LiberaliLab/vocab)

- [x] Repository `LiberaliLab/vocab` created.
- [ ] **Public visibility.** Pages on the Free organisation plan needs a public repository, and the vocabularies are public anyway.
- [ ] **Team `vocab-curators`** (Maks for now) with the Maintain role on the repository. Other lab members need no GitHub access.
- [ ] **Branch ruleset on `main`** (Settings → Rules → Rulesets → New branch ruleset, target `main` only):
  - require a pull request before merging, with 1 approval;
  - require the status check `validate` (it shows up after the first workflow run);
  - block force pushes and deletion.

  Do **not** include `gh-pages`: the release workflow pushes to it.
- [ ] **Tag ruleset on `v*`** (New tag ruleset): restrict creation, update and deletion, and add `vocab-curators` (and repository admins) to the bypass list. Pushing a tag is what publishes a release, so this controls who can publish.
- [ ] **Pages:** Settings → Pages → Build and deployment → Source = **GitHub Actions**.
- [ ] **Let tags deploy to Pages:** Settings → Environments → `github-pages` → Deployment branches and tags → add a **tag** rule `v*`. The environment allows only `main` by default, so the release workflow would be refused without it. The environment appears once Pages is switched to GitHub Actions.
- [ ] **Bot for the sheet sync** (needed only when the sync is built): pull requests opened with the workflow's own token do not trigger other workflows, so `validate` would never run on them. Create a GitHub App owned by LiberaliLab with repository permissions *Contents: read & write* and *Pull requests: read & write*, no webhook, installed on `vocab` only. Then store its ID as the repository variable `SYNC_APP_ID` and a private key as the repository secret `SYNC_APP_PRIVATE_KEY`.

## Google

- [ ] **Google Cloud project** (e.g. `liblab-vocab`) with the **Google Sheets API** enabled.
- [ ] **Service account** (e.g. `vocab-sync`). How GitHub Actions signs in as it is still to be decided:
  - *Workload Identity Federation* (recommended, keyless): a workload identity pool with a GitHub provider limited to `LiberaliLab/vocab`. The exact `gcloud` commands will come with the sync workflow.
  - *JSON key*: stored as the repository secret `GOOGLE_SA_KEY`. Simpler, but a long-lived secret.
- [ ] **The sheet**, shared as Editor with lab members and with the service account's email address. The service account writes the new IDs back, so it needs edit rights.
  - One tab per vocabulary, named exactly like the file: `tissue_type`, `labelling_method`, `imaging_modality`. Seed each tab by importing the matching `vocabularies/*.tsv` (File → Import → Upload → *Insert new sheet*, separator *Tab*).
  - Row 1 holds the headers `id, label, definition, synonyms, parent_id, status, replaced_by, external_mapping`.
  - Data validation on `status`: a dropdown with `active` and `deprecated`.
  - Protected range on column `id` (Data → Protect sheets and ranges), editable only by the service account and the curator.
  - Optional: a `README` tab with the editing rules. Tabs that have no matching vocabulary header are ignored.
- [ ] The **sheet ID** (the long part of its URL) stored as the repository variable `SHEET_ID`. It is not secret.

## Later

- [ ] Register `https://w3id.org/liblab/` (a pull request to [perma-id/w3id.org](https://github.com/perma-id/w3id.org)) so term IRIs resolve. Each release's `terms.json` maps every ID to its vocabulary, which the redirect can use.
- [ ] Optionally submit releases to OLS or the TIB Terminology Service for discoverability.
