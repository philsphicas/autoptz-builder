#!/usr/bin/env python3
"""Decide whether to build, and at what version, for a given upstream release.

The build is fully determined by two inputs: the upstream source commit and this
builder's own commit. A release records both in a `build-manifest.json` asset, so
this script can rebuild whenever *either* changed — a new upstream version, or a
builder-side fix against an unchanged upstream — without anyone clicking "force".

Version scheme (PEP 440 post-releases):
  - No release yet for the upstream base version -> build that plain version.
  - A release exists but the recorded upstream/builder commit differs (or --force)
    -> build the next post-release (X.Y.Z.post1, .post2, ...).
  - A release exists and both commits match -> nothing to do.

Pure logic: the caller passes the existing release tags via $RELEASE_TAGS and the
newest matching release's manifest (if any) via --prev-manifest, so this is
testable without network access. Emits `key=value` lines for $GITHUB_OUTPUT.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys


def _base_version(upstream_tag: str) -> str:
    base = re.sub(r"^v", "", upstream_tag)
    return re.sub(r"\.post\d+$", "", base)


def _matching_posts(tags: str, base: str) -> list[int]:
    pat = re.compile(rf"^v{re.escape(base)}(?:\.post(\d+))?$")
    posts = []
    for tag in tags.split():
        m = pat.match(tag.strip())
        if m:
            posts.append(int(m.group(1)) if m.group(1) else 0)
    return posts


def decide(
    upstream_tag: str,
    upstream_sha: str,
    builder_sha: str,
    force: bool,
    tags: str,
    prev_manifest: dict | None,
) -> dict[str, str]:
    base = _base_version(upstream_tag)
    posts = _matching_posts(tags, base)

    if not posts:
        # First build for this upstream version.
        return {
            "should_build": "true",
            "version": base,
            "short_version": base,
            "release_tag": f"v{base}",
            "reason": "no existing release for this upstream version",
        }

    # An older release with no manifest counts as "inputs unknown" -> rebuild, so
    # the very first self-healing run refreshes a pre-provenance release.
    if prev_manifest is None:
        changed, why = True, "previous release has no build manifest"
    else:
        up_changed = prev_manifest.get("upstream_sha") != upstream_sha
        bld_changed = prev_manifest.get("builder_sha") != builder_sha
        changed = up_changed or bld_changed
        why = ", ".join(
            w for w, c in (("upstream commit changed", up_changed),
                           ("builder commit changed", bld_changed)) if c
        ) or "inputs unchanged"

    if force or changed:
        n = max(posts) + 1
        return {
            "should_build": "true",
            "version": f"{base}.post{n}",
            "short_version": base,
            "release_tag": f"v{base}.post{n}",
            "reason": "force requested" if force and not changed else why,
        }
    return {
        "should_build": "false",
        "version": base,
        "short_version": base,
        "release_tag": f"v{base}",
        "reason": why,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--upstream-tag", required=True)
    ap.add_argument("--upstream-sha", required=True)
    ap.add_argument("--builder-sha", required=True)
    ap.add_argument("--force", default="false")
    ap.add_argument(
        "--prev-manifest",
        default="",
        help="path to the newest matching release's build-manifest.json, if any",
    )
    args = ap.parse_args(argv)

    prev = None
    if args.prev_manifest and os.path.exists(args.prev_manifest):
        try:
            prev = json.loads(open(args.prev_manifest).read())
        except (OSError, ValueError):
            prev = None

    result = decide(
        upstream_tag=args.upstream_tag,
        upstream_sha=args.upstream_sha,
        builder_sha=args.builder_sha,
        force=args.force == "true",
        tags=os.environ.get("RELEASE_TAGS", ""),
        prev_manifest=prev,
    )
    print(f"decide_release: {result['reason']}", file=sys.stderr)
    for k, v in result.items():
        if k != "reason":
            print(f"{k}={v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
