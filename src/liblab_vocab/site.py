"""Assembling the GitHub Pages site: one folder per release plus latest/.

The site lives on the gh-pages branch and only ever grows: a published version
folder is never rebuilt, so v1.4.0 stays byte-for-byte what was released even if
the build code changes later.
"""

from __future__ import annotations

import filecmp
import html
import json
import shutil
from pathlib import Path

from .config import Config
from .gitrefs import VERSION_RE, format_version, parse_version


class SiteError(RuntimeError):
    pass


def _same_tree(a: Path, b: Path) -> bool:
    cmp = filecmp.dircmp(a, b)
    if cmp.left_only or cmp.right_only or cmp.funny_files:
        return False
    _, mismatch, errors = filecmp.cmpfiles(a, b, cmp.common_files, shallow=False)
    if mismatch or errors:
        return False
    return all(_same_tree(a / d, b / d) for d in cmp.common_dirs)


def published_versions(site: Path) -> list[str]:
    versions = [
        parse_version(p.name)
        for p in site.iterdir()
        if p.is_dir() and p.name.startswith("v") and VERSION_RE.match(p.name)
    ] if site.exists() else []
    return [format_version(v) for v in sorted(versions)]


def publish(site_dir: str | Path, build_dir: str | Path, version: str, config: Config) -> str:
    """Add a release to the site and point latest/ at the highest version.

    Returns the version that latest/ now holds.
    """
    site, build = Path(site_dir), Path(build_dir)
    version = format_version(parse_version(version))
    target = site / f"v{version}"
    if target.exists():
        if not _same_tree(target, build):
            raise SiteError(
                f"v{version} is already published with different content; "
                "published releases are never overwritten. Tag a new version instead."
            )
    else:
        shutil.copytree(build, target)

    versions = published_versions(site)
    latest = versions[-1]
    latest_dir = site / "latest"
    if latest_dir.exists():
        shutil.rmtree(latest_dir)
    shutil.copytree(site / f"v{latest}", latest_dir)

    (site / ".nojekyll").write_text("", encoding="utf-8")
    (site / "versions.json").write_text(
        json.dumps({"latest": latest, "versions": versions[::-1]}, indent=2) + "\n", encoding="utf-8"
    )
    (site / "index.html").write_text(_index_html(site, versions, latest, config), encoding="utf-8")
    return latest


def _index_html(site: Path, versions: list[str], latest: str, config: Config) -> str:
    index = json.loads((site / "latest" / "index.json").read_text(encoding="utf-8"))
    esc = html.escape
    rows = "\n".join(
        f"<tr><td>{esc(v['name'])}</td><td>{v['active_terms']} active / {v['terms']} total</td><td>"
        + " · ".join(
            f'<a href="latest/{esc(f)}">{ext.upper()}</a>' for ext, f in v["files"].items()
        )
        + "</td></tr>"
        for v in index["vocabularies"]
    )
    releases = "\n".join(f'<li><a href="v{esc(v)}/index.json">v{esc(v)}</a></li>' for v in versions[::-1])
    title = esc(config.title)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 48rem; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ text-align: left; padding: .4rem .6rem; border-bottom: 1px solid #ddd; }}
code {{ background: #f3f3f3; padding: 0 .25rem; }}
</style>
</head>
<body>
<h1>{title}</h1>
<p>Latest release: <strong>v{esc(latest)}</strong>. Every release stays available under its own version folder.</p>
<table>
<thead><tr><th>Vocabulary</th><th>Terms</th><th>Files (latest)</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
<h2>Use</h2>
<p>Pipelines should pin a version, for example <code>{esc(config.publish_url)}v{esc(latest)}/&lt;vocabulary&gt;.json</code>.
Interactive tools may use <code>{esc(config.publish_url)}latest/&lt;vocabulary&gt;.json</code>.
<code>terms.json</code> in each release maps every ID to its vocabulary.</p>
<h2>Releases</h2>
<ul>
{releases}
</ul>
</body>
</html>
"""
