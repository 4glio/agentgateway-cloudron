#!/usr/bin/env python3
"""Write one release into CloudronManifest.json and CloudronVersions.json.

A Cloudron box reads CloudronManifest.json to build and CloudronVersions.json to
install, and nothing compares the two. This script is the only thing that writes
a new version into either, so the two cannot disagree: it expands the file://
fields into the flattened manifest a feed entry carries, pins the image by
digest, and appends the entry in the same commit.

It does NOT build, push or tag anything. scripts/release.sh does that and calls
this with the digest the registry actually returned.

  scripts/pin_release.py --version 1.0.6 \
      --image-repo ghcr.io/4glio/agentgateway-cloudron \
      --digest sha256:...

Dry run (parse, expand, validate, print, write nothing):

  scripts/pin_release.py --version 1.0.6 --digest sha256:... --check

The changelog block for the version must already exist in CHANGELOG.md, either
as [x.y.z] or as [Unreleased] (which this script renames to the version). The
gate in test/version_consistency.py enforces the result.
"""
import argparse
import datetime
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        return fh.read()


def load(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        return json.load(fh)


def semver_key(text):
    return tuple(int(p) for p in text.split("."))


def expand(manifest, version):
    """Turn the build manifest into the flattened form a feed entry carries.

    cloudron versions add expands file:// references and inlines the changelog
    block. Reproduce that exactly, so a hand-written entry and a generated one
    are the same shape and the next release does not produce a spurious diff.
    """
    out = dict(manifest)
    for key, filename in (("description", "DESCRIPTION.md"),
                          ("postInstallMessage", "POSTINSTALL.md")):
        ref = manifest.get(key, "")
        if isinstance(ref, str) and ref.startswith("file://"):
            out[key] = read(ref[len("file://"):])
    out["version"] = version
    out["changelog"] = changelog_block(version)
    return out


def changelog_text():
    return read("CHANGELOG.md")


def changelog_block(version):
    """The lines under [version], up to the next bracket line, without the heading."""
    text = changelog_text()
    for heading in ("[%s]" % version, "[Unreleased]"):
        marker = heading + "\n"
        at = text.find(marker)
        if at < 0:
            continue
        rest = text[at + len(marker):]
        stop = re.search(r"^\[[^\]]*\]", rest, re.M)
        body = rest[:stop.start()] if stop else rest
        return body.lstrip("\n").rstrip("\n") + "\n"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--digest", required=True)
    ap.add_argument("--image-repo", required=True)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    if not SEMVER.match(args.version):
        sys.exit("pin_release: --version must be x.y.z, got %r" % args.version)
    if not re.match(r"^sha256:[0-9a-f]{64}$", args.digest):
        sys.exit("pin_release: --digest must be sha256:<64 hex>, got %r" % args.digest)

    manifest = load("CloudronManifest.json")
    feed = load("CloudronVersions.json")
    versions = feed.setdefault("versions", {})

    if args.version in versions:
        current = (versions[args.version].get("manifest") or {}).get("dockerImage")
        if current == "%s@%s" % (args.image_repo, args.digest):
            print("pin_release: %s already points at this digest, nothing to do" % args.version)
            return 0
        sys.exit("pin_release: %s is already in the feed with %s, refusing to rewrite a "
                 "published entry" % (args.version, current))

    block = changelog_block(args.version)
    if block is None:
        sys.exit("pin_release: CHANGELOG.md has no [%s] and no [Unreleased] block - "
                 "write the release notes first" % args.version)

    image = "%s@%s" % (args.image_repo, args.digest)
    manifest["version"] = args.version
    manifest["dockerImage"] = image
    entry_manifest = expand(manifest, args.version)
    entry_manifest["dockerImage"] = image

    now = datetime.datetime.now(datetime.timezone.utc)
    entry = {
        "manifest": entry_manifest,
        "creationDate": now.strftime("%a, %d %b %Y %H:%M:%S GMT"),
        "ts": int(now.timestamp() * 1000),
        "publishState": "published",
    }

    ordered = dict(sorted(versions.items(), key=lambda kv: semver_key(kv[0]))) if all(
        SEMVER.match(k) for k in versions) else versions
    ordered[args.version] = entry
    ordered = dict(sorted(ordered.items(), key=lambda kv: semver_key(kv[0])))
    feed["versions"] = ordered

    changelog = changelog_text()
    if "[%s]" % args.version in changelog:
        new_changelog = changelog
    else:
        new_changelog = changelog.replace("[Unreleased]\n", "[%s]\n" % args.version, 1)

    if args.check:
        print("pin_release --check: would write version %s" % args.version)
        print("  manifest dockerImage: %s" % image)
        print("  feed entry: %s (published)" % args.version)
        print("  changelog heading: %s" % ("present" if new_changelog is changelog
                                           else "renamed from [Unreleased]"))
        return 0

    with open(os.path.join(ROOT, "CloudronManifest.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(manifest, indent=2) + "\n")
    with open(os.path.join(ROOT, "CloudronVersions.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(feed, indent=4))
    with open(os.path.join(ROOT, "CHANGELOG.md"), "w", encoding="utf-8") as fh:
        fh.write(new_changelog)

    print("pin_release: wrote %s into the manifest and the feed" % args.version)
    print("  image: %s" % image)
    return 0


if __name__ == "__main__":
    sys.exit(main())
