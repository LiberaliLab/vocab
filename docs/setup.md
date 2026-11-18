# One-time setup

The settings that live outside the code. Tick each item when done.

## GitHub (LiberaliLab/vocab)

- [x] Repository `LiberaliLab/vocab` created.
- [x] **Public visibility.** Pages on the Free organisation plan needs a public repository, and the vocabularies are public anyway.
- [x] **Team `vocab-curators`** (Maks for now) with the Maintain role on the repository. Other lab members need no GitHub access.
- [ ] **Branch ruleset on `main`** (Settings → Rules → Rulesets → New branch ruleset, target `main` only):
  - require a pull request before merging, with 1 approval;
  - require the status check `validate` (it shows up after the first workflow run);
  - block force pushes and deletion.

  Do **not** include `gh-pages`: the release workflow pushes to it.
- [ ] **Tag ruleset on `v*`** (New tag ruleset): restrict creation, update and deletion, and add `vocab-curators` (and repository admins) to the bypass list. Pushing a tag is what publishes a release, so this controls who can publish.
- [ ] **Pages:** Settings → Pages → Build and deployment → Source = **GitHub Actions**.
- [ ] **Let tags deploy to Pages:** Settings → Environments → `github-pages` → Deployment branches and tags → add a **tag** rule `v*`. The environment allows only `main` by default, so the release workflow would be refused without it. The environment appears once Pages is switched to GitHub Actions.
- [ ] **Bot for the sheet sync:** pull requests opened with the workflow's own token do not trigger other workflows, so `validate` would never run on them. Create a GitHub App owned by LiberaliLab with repository permissions *Contents: read & write* and *Pull requests: read & write*, no webhook, installed on `vocab` only. Then store its ID as the repository variable `SYNC_APP_ID` and a private key as the repository secret `SYNC_APP_PRIVATE_KEY`.

## Google

The sync signs in to Google with **Workload Identity Federation**: GitHub Actions proves which repository and branch it is running for, and Google lets exactly that (`LiberaliLab/vocab`, branch `main`) act as the service account. No Google key is stored anywhere.

- [x] **Google Cloud project** with the **Google Sheets API** enabled.
- [x] **Service account** created. It needs no project roles (its only access is the sheet shared with it). If a JSON key was downloaded for it, delete the key: the sync does not use one.
- [ ] **Trust GitHub Actions.** Run the following in [Cloud Shell](https://shell.cloud.google.com), with the service account's email in the first line:

  ```bash
  SA="your-sa-name@your-project-id.iam.gserviceaccount.com"
  PROJECT_ID=$(echo "$SA" | cut -d@ -f2 | cut -d. -f1)
  gcloud config set project "$PROJECT_ID"
  PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
  gcloud services enable sheets.googleapis.com iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com

  # Trust GitHub's tokens, but only from LiberaliLab/vocab (repository ID 1461507000) on main.
  gcloud iam workload-identity-pools create github --location=global --display-name="GitHub Actions"
  gcloud iam workload-identity-pools providers create-oidc vocab-repo \
    --location=global --workload-identity-pool=github \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.ref=assertion.ref" \
    --attribute-condition="assertion.repository_id == '1461507000' && assertion.ref == 'refs/heads/main'"

  # Let those runs act as the service account.
  gcloud iam service-accounts add-iam-policy-binding "$SA" \
    --role=roles/iam.workloadIdentityUser \
    --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/attribute.repository_id/1461507000"

  # Print the two values GitHub needs.
  echo "GCP_WIF_PROVIDER    = projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/providers/vocab-repo"
  echo "GCP_SERVICE_ACCOUNT = $SA"
  ```

  The condition uses the repository's numeric ID rather than its name, so a renamed or re-created repository called `vocab` cannot use it.
- [ ] **Store the two printed values** as repository variables (Settings → Secrets and variables → Actions → Variables): `GCP_WIF_PROVIDER` and `GCP_SERVICE_ACCOUNT`. They are not secret.
- [ ] **Create the sheet** and share it as Editor with lab members and with the service account's email. The sync writes new IDs back, so the service account needs edit rights.
  - Select all cells and set Format → Number → **Plain text** first, so Sheets does not turn values into dates or numbers.
  - Make one tab per vocabulary, named exactly like the file: `tissue_type`, `labelling_method`, `imaging_modality`. Fill each tab by importing the matching `vocabularies/*.tsv` (File → Import → Upload → *Replace current sheet*, separator *Tab*, **untick** "Convert text to numbers, dates, and formulas").
  - Row 1 is the header `id, label, definition, synonyms, parent_id, status, replaced_by, external_mapping`, in that order. Do not add other columns.
  - Data validation on the `status` column: a dropdown with `active` and `deprecated`.
  - Protect the `id` column (Data → Protect sheets and ranges) so that only the service account and the curator can edit it.
  - Optionally add a `TEMPLATE` tab (exactly that name): a copy of a vocabulary tab with only the header row. To start a new vocabulary, duplicate it and rename the copy to a lowercase name such as `cell_line`. The sync ignores `TEMPLATE` itself, and copies its header-row notes to every vocabulary tab, so edit the column notes there. Removing a note in `TEMPLATE` removes it everywhere.
  - Optionally add a `README` tab with the editing rules. Tabs without the vocabulary header are ignored. Renaming or deleting a vocabulary tab stops the sync with an error.
- [ ] **Store the sheet ID** (the long part of its URL, between `/d/` and `/edit`) as the repository variable `SHEET_ID`.
- [ ] **Test it:** Actions → sync → Run workflow (on `main`). The first run should report no changes. Then add a test row to the sheet, run it again, and check that an ID appears in the sheet and a pull request opens with the `validate` check running on it.

## Later

- [ ] Register `https://w3id.org/liblab/` (a pull request to [perma-id/w3id.org](https://github.com/perma-id/w3id.org)) so term IRIs resolve. Each release's `terms.json` maps every ID to its vocabulary, which the redirect can use.
- [ ] Optionally submit releases to OLS or the TIB Terminology Service for discoverability.
