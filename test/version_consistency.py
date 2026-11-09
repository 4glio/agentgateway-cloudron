#!/usr/bin/env python3
"""The version facts in a Cloudron package must agree, and the image must be ours.

Cloudron builds from CloudronManifest.json and installs from CloudronVersions.json,
and nothing compares the two, so a mismatch is silent until an install fails.
A repo's RELEASING runbook says what has to agree; this is that sentence,
executable.

Checks, each named on failure:

  version    manifest.version == newest feed key == that entry's manifest.version
  upstream   Dockerfile build-arg version == manifest.upstreamVersion (v prefix ignored)
  image      same digest in both files, @sha256 pinned, and in EXPECTED_IMAGE_REPO
  changelog  a [x.y.z] block for the manifest version, and none ahead of it

Run it from one directory below the package root, e.g. test/version_consistency.py:

  EXPECTED_IMAGE_REPO=ghcr.io/<org>/<package> python3 test/version_consistency.py

EXPECTED_IMAGE_REPO unset means the namespace check is skipped with a note, so the
script works for any package; set it in CI for a package that publishes its own
image. Exit 0 when everything agrees, 1 otherwise.
"""
import json
import os
import re
import sys

EXPECTED_IMAGE_REPO = os.environ.get("EXPECTED_IMAGE_REPO", "").strip()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
failures = []


def ok(label, detail):
    print("  ok    %-9s %s" % (label, detail))


def bad(label, detail):
    print("  FAIL  %-9s %s" % (label, detail))
    failures.append(label)


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        return fh.read()


def triple(text):
    if re.match(r"^\d+\.\d+\.\d+$", text or ""):
        return tuple(int(p) for p in text.split("."))
    return None


def main():
    manifest = json.loads(read("CloudronManifest.json"))
    feed = json.loads(read("CloudronVersions.json"))
    dockerfile = read("Dockerfile")
    changelog = read("CHANGELOG.md")

    version = manifest.get("version", "")
    if triple(version) is None:
        bad("version", "manifest.version %r is not x.y.z" % version)
        return 1

    versions = feed.get("versions") or {}
    ranked = [(triple(v), v) for v in versions]
    for t, v in ranked:
        if t is None:
            bad("version", "feed key %r is not x.y.z" % v)
    ranked = [(t, v) for t, v in ranked if t is not None]
    if not ranked:
        bad("version", "CloudronVersions.json has no usable versions")
        return 1
    newest = max(ranked)[1]
    entry = versions[newest].get("manifest") or {}

    if newest != version:
        bad("version", "newest feed entry is %s, manifest says %s" % (newest, version))
    elif entry.get("version") != version:
        bad("version", "feed entry %s carries manifest.version %r" % (newest, entry.get("version")))
    else:
        ok("version", "feed and manifest agree on %s" % version)

    m = re.search(r"^ARG\s+[A-Z0-9_]*VERSION=(\S+)\s*$", dockerfile, re.M)
    upstream = manifest.get("upstreamVersion", "")
    if not m:
        bad("upstream", "no 'ARG <APP>_VERSION=' line in the Dockerfile")
    elif m.group(1).lstrip("v") != upstream.lstrip("v"):
        bad("upstream", "Dockerfile has %s, manifest says %s" % (m.group(1), upstream))
    elif entry.get("upstreamVersion") not in (None, upstream):
        bad("upstream", "feed entry %s says %r" % (newest, entry.get("upstreamVersion")))
    else:
        ok("upstream", "Dockerfile and manifest both say %s" % upstream)

    image = manifest.get("dockerImage", "")
    image_ok = True
    if entry.get("dockerImage") != image:
        bad("image", "manifest %r vs feed entry %r" % (image, entry.get("dockerImage")))
        image_ok = False
    if "@sha256:" not in image:
        bad("image", "%r is not pinned by digest" % image)
        image_ok = False
    repo = image.split("@", 1)[0]
    if EXPECTED_IMAGE_REPO:
        if repo != EXPECTED_IMAGE_REPO:
            bad("image", "points at %s, expected %s - ship the image this repo builds"
                % (repo, EXPECTED_IMAGE_REPO))
            image_ok = False
    else:
        print("  note  %-9s namespace not checked (set EXPECTED_IMAGE_REPO)" % "image")
    if image_ok:
        ok("image", "%s pinned by digest" % repo)

    blocks = [triple(b) for b in re.findall(r"^\[(\d+\.\d+\.\d+)\]", changelog, re.M)]
    blocks = [b for b in blocks if b]
    if not blocks or triple(version) not in blocks:
        bad("changelog", "no [%s] block in CHANGELOG.md" % version)
    elif max(blocks) > triple(version):
        bad("changelog", "CHANGELOG announces %s but the package is %s - half a release"
            % (".".join(str(x) for x in max(blocks)), version))
    else:
        ok("changelog", "[%s] present, nothing ahead of it" % version)

    print()
    if failures:
        print("version consistency: %d check(s) failed" % len(failures))
        return 1
    print("version consistency: manifest, feed, Dockerfile and changelog agree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
