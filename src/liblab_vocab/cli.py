"""Command line: `vocab <command>`. Run `vocab --help` for the list."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import gitrefs
from .build import build
from .config import Config, load_config
from .diff import actual_bump, diff, format_markdown, required_bump
from .ids import assign_ids, resolve_label_references
from .model import VocabFormatError, Vocabularies, load_dir, write_dir
from .site import SiteError, publish
from .validate import has_errors, validate

WORKTREE = "WORKTREE"


def _load(ref: str, config: Config, repo: str) -> Vocabularies:
    if ref == WORKTREE:
        return load_dir(Path(repo) / config.directory)
    return gitrefs.load_ref(ref, config.directory, repo)


def _baselines(args: argparse.Namespace, config: Config) -> list[tuple[str, Vocabularies]]:
    refs = list(args.baseline or [])
    if args.against_latest_release:
        latest = gitrefs.latest_release(args.repo)
        if latest:
            refs.append(latest)
        else:
            print("No release tag yet, so there is no last release to compare against.")
    baselines = []
    for ref in dict.fromkeys(refs):
        if gitrefs.ref_exists(ref, args.repo):
            baselines.append((ref, gitrefs.load_ref(ref, config.directory, args.repo)))
        else:
            print(f"Baseline {ref!r} does not exist; skipping it.")
    return baselines


def cmd_validate(args: argparse.Namespace, config: Config) -> int:
    vocabs = _load(WORKTREE, config, args.repo)
    issues = validate(vocabs, config, _baselines(args, config))
    for issue in issues:
        print(issue)
    terms = sum(len(t) for t in vocabs.values())
    errors = sum(i.severity == "error" for i in issues)
    print(f"{len(vocabs)} vocabularies, {terms} terms: {errors} errors, {len(issues) - errors} warnings.")
    return 1 if has_errors(issues) else 0


def cmd_assign_ids(args: argparse.Namespace, config: Config) -> int:
    vocabs = _load(WORKTREE, config, args.repo)
    baselines = [b for _, b in _baselines(args, config)]
    assigned = assign_ids(vocabs, config, baselines)
    resolved = resolve_label_references(vocabs, config)
    for term in assigned:
        print(f"{term.where()}: assigned {term.id} to {term.label!r}")
    for term, column, old in resolved:
        print(f"{term.where()}: {column} {old!r} -> {getattr(term, column)}")
    if assigned or resolved:
        write_dir(vocabs, Path(args.repo) / config.directory)
    print(f"{len(assigned)} IDs assigned, {len(resolved)} label references resolved.")
    return 0


def cmd_diff(args: argparse.Namespace, config: Config) -> int:
    old, new = _load(args.old, config, args.repo), _load(args.new, config, args.repo)
    new_name = "working tree" if args.new == WORKTREE else args.new
    text = format_markdown(diff(old, new), f"Changes from {args.old} to {new_name}")
    print(text)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as handle:
            handle.write(text + "\n")
    return 0


def cmd_check_version(args: argparse.Namespace, config: Config) -> int:
    version = gitrefs.parse_version(args.version)
    previous = args.previous or gitrefs.previous_release(args.version, args.repo)
    if previous is None:
        print(f"v{gitrefs.format_version(version)} is the first release; any version is fine.")
        return 0
    changes = diff(_load(previous, config, args.repo), _load(WORKTREE, config, args.repo))
    needed = required_bump(changes)
    actual = actual_bump(gitrefs.parse_version(previous), version)
    print(format_markdown(changes, f"Changes since {previous}"))
    if actual < needed:
        print(
            f"ERROR: going from {previous} to v{gitrefs.format_version(version)} is a {actual} "
            f"release, but the changes need a {needed} release."
        )
        return 1
    print(f"OK: {previous} -> v{gitrefs.format_version(version)} is a {actual} release (needs {needed}).")
    return 0


def cmd_previous_tag(args: argparse.Namespace, config: Config) -> int:
    previous = gitrefs.previous_release(args.version, args.repo)
    if previous:
        print(previous)
    return 0


def cmd_latest_tag(args: argparse.Namespace, config: Config) -> int:
    latest = gitrefs.latest_release(args.repo)
    if latest:
        print(latest)
    return 0


def cmd_build(args: argparse.Namespace, config: Config) -> int:
    version = gitrefs.format_version(gitrefs.parse_version(args.version))
    vocabs = _load(WORKTREE, config, args.repo)
    issues = validate(vocabs, config)
    if has_errors(issues):
        for issue in issues:
            print(issue)
        print("Not building: the vocabularies have errors.")
        return 1
    for path in build(vocabs, config, version, args.out):
        print(path)
    return 0


def cmd_publish_site(args: argparse.Namespace, config: Config) -> int:
    latest = publish(args.site, args.build, args.version, config)
    print(f"Published {args.version} into {args.site}; latest/ is now v{latest}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vocab", description=__doc__)
    parser.add_argument("--config", default=None, help="path to vocab.toml (default: <repo>/vocab.toml)")
    parser.add_argument("--repo", default=".", help="repository root (default: current directory)")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_baseline_options(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--baseline", action="append", metavar="REF",
            help="Git ref whose IDs must all still exist (repeatable), e.g. origin/main",
        )
        p.add_argument(
            "--against-latest-release", action="store_true",
            help="also use the highest vX.Y.Z tag as a baseline",
        )

    p = sub.add_parser("validate", help="check the vocabularies against every rule")
    add_baseline_options(p)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("assign-ids", help="give new terms IDs and turn label references into IDs")
    add_baseline_options(p)
    p.set_defaults(func=cmd_assign_ids)

    p = sub.add_parser("diff", help="list changes between two Git refs as Markdown")
    p.add_argument("old", help="Git ref to compare from")
    p.add_argument("new", nargs="?", default=WORKTREE, help="Git ref to compare to (default: working tree)")
    p.add_argument("--summary", help="also append the Markdown to this file (e.g. $GITHUB_STEP_SUMMARY)")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("check-version", help="check that a version number is a big enough bump")
    p.add_argument("version", help="the new version, e.g. v1.5.0")
    p.add_argument("--previous", help="release to compare with (default: the highest lower tag)")
    p.set_defaults(func=cmd_check_version)

    p = sub.add_parser("previous-tag", help="print the highest release tag below a version")
    p.add_argument("version")
    p.set_defaults(func=cmd_previous_tag)

    p = sub.add_parser("latest-tag", help="print the highest release tag (nothing if there is none)")
    p.set_defaults(func=cmd_latest_tag)

    p = sub.add_parser("build", help="write JSON, CSV and SKOS outputs for a release")
    p.add_argument("--version", required=True)
    p.add_argument("--out", required=True, help="output directory")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("publish-site", help="add a built release to the Pages site folder")
    p.add_argument("--site", required=True, help="checkout of the gh-pages branch")
    p.add_argument("--build", required=True, help="output directory of `vocab build`")
    p.add_argument("--version", required=True)
    p.set_defaults(func=cmd_publish_site)

    args = parser.parse_args(argv)
    config = load_config(args.config or Path(args.repo) / "vocab.toml")
    try:
        return args.func(args, config)
    except (VocabFormatError, SiteError, RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
