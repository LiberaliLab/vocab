import json

import pytest

from liblab_vocab.build import build
from liblab_vocab.site import SiteError, publish

from .conftest import term, vocabs


def built(config, tmp_path, version, label="a"):
    out = tmp_path / f"build-{version}-{label}"
    build(vocabs(term(id="LIBLAB:0000001", label=label)), config, version, out)
    return out


def test_publish_versions_and_latest(config, tmp_path):
    site = tmp_path / "site"
    assert publish(site, built(config, tmp_path, "1.0.0"), "v1.0.0", config) == "1.0.0"
    assert publish(site, built(config, tmp_path, "1.1.0"), "v1.1.0", config) == "1.1.0"
    # A patch to an older line does not move latest backwards.
    assert publish(site, built(config, tmp_path, "1.0.1"), "v1.0.1", config) == "1.1.0"

    assert json.loads((site / "latest" / "stain.json").read_text())["version"] == "1.1.0"
    assert json.loads((site / "v1.0.0" / "stain.json").read_text())["version"] == "1.0.0"
    assert json.loads((site / "versions.json").read_text()) == {
        "latest": "1.1.0",
        "versions": ["1.1.0", "1.0.1", "1.0.0"],
    }
    index = (site / "index.html").read_text()
    assert "v1.1.0" in index and 'href="latest/stain.json"' in index
    assert (site / ".nojekyll").exists()


def test_republishing_identical_content_is_allowed(config, tmp_path):
    site = tmp_path / "site"
    publish(site, built(config, tmp_path, "1.0.0"), "1.0.0", config)
    publish(site, built(config, tmp_path, "1.0.0"), "1.0.0", config)


def test_published_version_is_never_overwritten(config, tmp_path):
    site = tmp_path / "site"
    publish(site, built(config, tmp_path, "1.0.0"), "1.0.0", config)
    with pytest.raises(SiteError, match="already published"):
        publish(site, built(config, tmp_path, "1.0.0", label="changed"), "1.0.0", config)
