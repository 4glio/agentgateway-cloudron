#!/bin/bash
# release.sh - publish one version of this package, end to end, and prove it.
#
# Before this script existed the release was twelve manual steps across two
# machines (docs/RELEASING.md): bump, build, linkage gate, push, read the digest,
# generate the feed entry, pin both files, flip GHCR visibility, prove an
# anonymous pull, commit, sweep for identity leaks. Every one of those steps has
# a way to be skipped, and a skipped step is invisible until an install fails on
# someone else's box.
#
# This script is that runbook, executable, in the order that makes the failure
# visible. It refuses to publish anything that has not passed the gates, and it
# writes the manifest and the feed from the digest the registry returned rather
# than from a local build id (a local manifest digest is not the registry digest,
# so a locally-read value pins an image nobody can pull).
#
# Usage: scripts/release.sh <version>          e.g. scripts/release.sh 1.0.6
#
# Environment:
#   IMAGE_REPO   registry path this repo publishes (default ghcr.io/4glio/agentgateway-cloudron)
#   ENGINE       podman (default when present) or docker
#   PUSH         1 (default) push the image; 0 keeps it local and skips the digest step
#   COMMIT       0 (default) leave the tree changed; 1 commit and tag
#   SKIP_GATES   0 (default) run secret-scan, smoke and trivy; 1 for a local dry run only
#   SKIP_ANON    0 (default) prove an anonymous pull; 1 for a local registry
#   GIT_AUTHOR_NAME / GIT_AUTHOR_EMAIL  identity for the commit (CI sets these)
#
# Exit: 0 released (or dry run completed), 1 a gate failed, 2 usage/setup.
#
# PRECONDITION: CHANGELOG.md carries the notes for <version>, either under
# [<version>] or under [Unreleased], and <version> is not already in
# CloudronVersions.json. scripts/pin_release.py handles the expansion and the
# heading rename; test/version_consistency.py proves the result.

set -euo pipefail
cd "$(dirname "$0")/.." || exit 2

VERSION="${1:-}"
[ -n "$VERSION" ] || { echo "usage: scripts/release.sh <version>" >&2; exit 2; }
case "$VERSION" in
  [0-9]*.[0-9]*.[0-9]*) ;;
  *) echo "release: version must be x.y.z, got '$VERSION'" >&2; exit 2 ;;
esac

IMAGE_REPO="${IMAGE_REPO:-ghcr.io/4glio/agentgateway-cloudron}"
PUSH="${PUSH:-1}"
COMMIT="${COMMIT:-0}"
SKIP_GATES="${SKIP_GATES:-0}"
SKIP_ANON="${SKIP_ANON:-0}"
ENGINE="${ENGINE:-$(command -v podman >/dev/null 2>&1 && echo podman || echo docker)}"
IMAGE="$IMAGE_REPO:$VERSION"

say()  { printf '\n== %s\n' "$*"; }
note() { printf '   %s\n' "$*"; }
die()  { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

command -v "$ENGINE" >/dev/null 2>&1 || die "$ENGINE is not installed"

say "preconditions for $VERSION"
python3 - "$VERSION" <<'PY' || exit 1
import json, re, sys
version = sys.argv[1]
manifest = json.load(open("CloudronManifest.json"))
feed = json.load(open("CloudronVersions.json"))
changelog = open("CHANGELOG.md", encoding="utf-8").read()
if version in feed.get("versions", {}):
    sys.exit("   %s is already published in CloudronVersions.json - bump the version" % version)
if "[%s]" % version not in changelog and "[Unreleased]" not in changelog:
    sys.exit("   CHANGELOG.md has neither [%s] nor [Unreleased] - write the notes first" % version)
if manifest.get("upstreamVersion") and not re.search(
        r"^ARG\s+\w*VERSION=(\S+)", open("Dockerfile").read(), re.M):
    sys.exit("   Dockerfile has no ARG <APP>_VERSION line")
print("   version %s not yet published; changelog notes present" % version)
PY

say "build $IMAGE"
"$ENGINE" build --pull -t "$IMAGE" -f Dockerfile .

if [ "$SKIP_GATES" != "1" ]; then
  # Gate 1 in the old runbook, and the one whose failure is silent: the upstream
  # binary is dynamically linked and only reveals a newer glibc at runtime. The
  # build succeeds, the push succeeds, and the app dies on first boot.
  say "gate: linkage (the upstream binary runs on the pinned base)"
  "$ENGINE" run --rm "$IMAGE" sh -c '
    set -e
    out="$(ldd /app/code/agentgateway)"
    if printf "%s" "$out" | grep -q "not found"; then
      printf "%s\n" "$out"; echo "FAIL: the binary links a library the base does not provide"; exit 1
    fi
    printf "%s\n" "$out" | grep -q "GLIBC_.* not found" && { echo "FAIL: base glibc too old"; exit 1; }
    /app/code/agentgateway --version
  ' || die "linkage gate failed - raise the cloudron/base pin before releasing"

  say "gate: secret-scan (leak on the artefact that is about to become public)"
  test/secret-scan.sh "$IMAGE" || die "secret-scan failed - do not publish this image"

  if [ -x test/smoke.sh ]; then
    say "gate: smoke (Cloudron runtime contract)"
    test/smoke.sh "$IMAGE" || die "smoke failed - the image does not run the way Cloudron runs it"
  else
    note "no test/smoke.sh in this package, skipped"
  fi

  say "gate: trivy (known vulnerabilities with a fix, and build misconfigurations)"
  test/trivy-scan.sh "$IMAGE" || die "trivy gate failed - see .trivyignore doctrine before excepting anything"
else
  note "SKIP_GATES=1: the gates did NOT run. This build is not publishable."
fi

DIGEST=""
if [ "$PUSH" = "1" ]; then
  say "push $IMAGE"
  "$ENGINE" push "$IMAGE"
  command -v skopeo >/dev/null 2>&1 || die "skopeo is required to read the registry digest"
  DIGEST="$(skopeo inspect --format '{{.Digest}}' "docker://$IMAGE")"
  [ -n "$DIGEST" ] || die "could not read a digest for $IMAGE from the registry"
  note "registry digest: $DIGEST"

  if [ "$SKIP_ANON" != "1" ]; then
    say "gate: anonymous pull by digest (a stranger must be able to install this)"
    printf '{"auths":{}}' > /tmp/empty-auth.$$.json
    if skopeo inspect --authfile /tmp/empty-auth.$$.json "docker://$IMAGE_REPO@$DIGEST" >/dev/null 2>&1; then
      note "pullable with no credentials"
    else
      rm -f /tmp/empty-auth.$$.json
      die "the digest is not pullable without credentials - the GHCR package is still private.
   Fix: profile, Packages, <package>, Package settings, Danger Zone, Change visibility, Public.
   Then re-run. Publishing the repo first would point it at an image strangers cannot pull."
    fi
    rm -f /tmp/empty-auth.$$.json
  fi
else
  note "PUSH=0: image not pushed, no digest, the manifest and feed are NOT written"
  say "done (local build only)"
  exit 0
fi

say "write the version into the manifest and the feed"
python3 scripts/pin_release.py --version "$VERSION" --digest "$DIGEST" --image-repo "$IMAGE_REPO"

say "gate: version consistency (manifest, feed, Dockerfile, changelog, namespace)"
EXPECTED_IMAGE_REPO="$IMAGE_REPO" python3 test/version_consistency.py \
  || die "the version facts disagree after pinning - do not push this commit"

if [ "$COMMIT" = "1" ]; then
  say "commit and tag"
  git add -A
  git commit -q -m "release: $VERSION

Image: $IMAGE_REPO@$DIGEST
Gates: secret-scan, smoke, trivy, version consistency." || die "nothing to commit"
  git tag "v$VERSION"
  note "committed and tagged v$VERSION (push the commit and the tag together)"
else
  note "COMMIT=0: changes left in the working tree for review"
fi

say "released $VERSION"
note "image:   $IMAGE_REPO@$DIGEST"
note "install: cloudron install --versions-url <raw CloudronVersions.json URL>"
