"""End-to-end runs of the CLI against a throwaway Git repository."""

from liblab_vocab.cli import main
from liblab_vocab.model import load_dir

from .conftest import git, tsv


def write(repo, name, *rows):
    (repo / "vocabularies" / f"{name}.tsv").write_text(tsv(*rows))


def commit(repo, message, tag=None):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    if tag:
        git(repo, "tag", tag)


def run(repo, *args):
    return main(["--repo", str(repo), *args])


def test_release_cycle(repo, capsys):
    # An editor adds two terms without IDs, the child naming its parent by label.
    write(repo, "stain", ["", "nuclear stain", "Stains nuclei.", "", "", "active", "", ""],
          ["", "DAPI", "A blue DNA stain.", "", "nuclear stain", "active", "", ""])
    assert run(repo, "validate") == 1
    assert run(repo, "assign-ids") == 0
    assert run(repo, "validate") == 0
    terms = load_dir(repo / "vocabularies")["stain"]
    assert [t.id for t in terms] == ["LIBLAB:0000001", "LIBLAB:0000002"]
    assert terms[1].parent_id == "LIBLAB:0000001"
    commit(repo, "first terms")
    assert run(repo, "check-version", "v1.0.0") == 0
    git(repo, "tag", "v1.0.0")

    # Deleting a released term is refused...
    write(repo, "stain", ["LIBLAB:0000001", "nuclear stain", "Stains nuclei.", "", "", "active", "", ""])
    assert run(repo, "validate", "--against-latest-release") == 1
    assert "exists in v1.0.0 but is missing now" in capsys.readouterr().out

    # ...deprecating it is a major change.
    write(repo, "stain", ["LIBLAB:0000001", "nuclear stain", "Stains nuclei.", "", "", "active", "", ""],
          ["LIBLAB:0000002", "DAPI", "A blue DNA stain.", "", "LIBLAB:0000001", "deprecated", "", ""])
    assert run(repo, "validate", "--against-latest-release") == 0
    commit(repo, "deprecate DAPI")
    assert run(repo, "check-version", "v1.1.0") == 1
    assert "need a major release" in capsys.readouterr().out
    assert run(repo, "check-version", "v2.0.0") == 0
    capsys.readouterr()

    assert run(repo, "previous-tag", "v2.0.0") == 0
    assert capsys.readouterr().out.strip() == "v1.0.0"

    out = repo / "build"
    assert run(repo, "build", "--version", "v2.0.0", "--out", str(out)) == 0
    assert run(repo, "publish-site", "--site", str(repo / "site"), "--build", str(out), "--version", "v2.0.0") == 0
    assert (repo / "site" / "latest" / "stain.json").exists()


def test_new_ids_skip_numbers_used_in_last_release(repo):
    write(repo, "stain", ["LIBLAB:0000001", "a", "A.", "", "", "active", "", ""],
          ["LIBLAB:0000002", "b", "B.", "", "", "active", "", ""])
    commit(repo, "release", tag="v1.0.0")
    write(repo, "stain", ["LIBLAB:0000001", "a", "A.", "", "", "active", "", ""],
          ["", "c", "C.", "", "", "active", "", ""])
    assert run(repo, "assign-ids", "--against-latest-release") == 0
    assert load_dir(repo / "vocabularies")["stain"][1].id == "LIBLAB:0000003"


def test_diff_writes_summary(repo, tmp_path):
    write(repo, "stain", ["LIBLAB:0000001", "a", "A.", "", "", "active", "", ""])
    commit(repo, "one", tag="v1.0.0")
    write(repo, "stain", ["LIBLAB:0000001", "a", "Better.", "", "", "active", "", ""])
    summary = tmp_path / "summary.md"
    assert run(repo, "diff", "v1.0.0", "--summary", str(summary)) == 0
    assert "Required version bump: **patch**" in summary.read_text()


def test_build_refuses_invalid_vocabularies(repo, tmp_path):
    write(repo, "stain", ["", "a", "", "", "", "active", "", ""])
    assert run(repo, "build", "--version", "1.0.0", "--out", str(tmp_path / "out")) == 1
    assert not (tmp_path / "out").exists()


def test_bad_header_is_reported_not_crashing(repo, capsys):
    (repo / "vocabularies" / "stain.tsv").write_text("id\tname\n")
    assert run(repo, "validate") == 1
    assert "header must be exactly" in capsys.readouterr().err
