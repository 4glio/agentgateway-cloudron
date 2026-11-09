# Releasing

A release is one command. `scripts/release.sh` is the runbook, executable, and
`.github/workflows/release.yml` runs it on a runner with the workflow token. There is no personal
registry token, no local digest to read by hand, and no window in which the changelog, the manifest
and the feed can disagree.

The package version and the upstream agentgateway version move independently. The package version is
plain semver in `CloudronManifest.json`. The upstream version is the `AGENTGATEWAY_VERSION` build
argument in the `Dockerfile`, which is the single source of truth for what upstream binary ships.

## Identity

All published artifacts are this repository's own:

- Repository: `github.com/4glio/agentgateway-cloudron`
- Image: `ghcr.io/4glio/agentgateway-cloudron`
- Feed: `https://raw.githubusercontent.com/4glio/agentgateway-cloudron/main/CloudronVersions.json`

The package began as a packaging of agentgateway by OrcVole, whose image this repository consumed until
1.0.5. From 1.0.6 it publishes its own image: a package that points at a registry namespace it cannot
push to is a package that cannot ship a security fix without someone else's consent, and that request
went unanswered. From 1.0.7 the documented maintainer is 4GL: `author`, `contactEmail`,
`packagerName` and `packagerUrl` all name 4GL, and `ciso@4gl.io` is the address a Cloudron operator
writes to. Entries 1.0.0 through 1.0.6 keep OrcVole in their embedded manifest copies, because a
published feed entry is the record of what a box installed and is not rewritten; `.scan-allowlist`
carries that address for that reason alone, with the removal condition beside it.

The packaging design and the topology decisions are still OrcVole's, and README and the ADRs credit
that where it matters. Naming the maintainer 4GL is about who answers, not about erasing who built it.

The single rule that remains from the earlier identity policy: **no personal host, email, username,
key or token may appear in any tracked file.** `.anonymize-list` (gitignored) holds the estate's
denylist and `test/secret-scan.sh` enforces it. A fork that publishes under an organisation still
leaks the person behind the workstation if that rule is dropped.

## Cutting a release

1. **Write the notes.** Add the release's bullets to `CHANGELOG.md` under `[Unreleased]`. The
   bracket form is required: the Cloudron changelog parser wants a literal `[x.y.z]` line, and
   `scripts/pin_release.py` renames `[Unreleased]` to `[x.y.z]` at release time. Nothing else in the
   repository names the new version yet, which is deliberate: a version that exists in the changelog
   but not in the feed is the half-release this flow exists to prevent.
2. **Bump the upstream version, if it moved.** Change `AGENTGATEWAY_VERSION` in the `Dockerfile` and
   `upstreamVersion` in `CloudronManifest.json`. Nothing else.
3. **Run Release.** Actions, Release, Run workflow, version `x.y.z`. It builds, runs every gate,
   pushes, reads the digest from the registry, writes `CloudronManifest.json` and
   `CloudronVersions.json`, commits `release: x.y.z`, and tags `vx.y.z`.

Locally, the same command is:

```bash
scripts/release.sh 1.0.6
```

Set `COMMIT=1` to have it commit and tag, `PUSH=0` to build and gate without publishing, and
`SKIP_ANON=1` only against a local registry. A local run needs `podman` (or `docker`), `skopeo`, and
`trivy` on `PATH`.

## What the script gates, in order

1. **Preconditions.** The version is `x.y.z`, is not already in the feed, and has changelog notes.
2. **Linkage (Gate 1).** `ldd /app/code/agentgateway` inside the built image shows no missing library
   and no `GLIBC_x.y not found`, and `--version` prints the pinned version. The upstream binary is
   dynamically linked against an exact glibc: a newer upstream toolchain than the pinned
   `cloudron/base` produces an image that builds, pushes, and then dies on first boot.
3. **secret-scan.** No identity string, host, or token in the repo or in the image.
4. **smoke.** The image runs the way Cloudron runs it and the two-surface topology still holds.
5. **trivy.** No HIGH or CRITICAL vulnerability with a fix, and no HIGH or CRITICAL build
   misconfiguration. Exceptions live in `.trivyignore`, one line each, with the reason and the
   condition that removes it.
6. **Push, then read the digest from the registry.** A local build's manifest digest is not the
   registry digest; pinning the local one points the feed at an image nobody can pull.
7. **Anonymous pull.** `skopeo inspect` with an empty authfile against `repo@digest`. GHCR packages
   are private when first created: profile, Packages, the package, Package settings, Danger Zone,
   Change visibility, Public. There is no REST API for that flip, so the first release of a new
   package name will fail this gate once, deliberately, before it can publish a feed entry strangers
   cannot use.
8. **Pin and re-gate.** `scripts/pin_release.py` writes both files and renames the changelog heading;
   `test/version_consistency.py` then proves manifest, feed, Dockerfile, changelog and namespace
   agree. A failure here stops the commit.

## Gates that are not automated

- **Config migration (Gate 3).** A same-schema update does not exercise the migration
  transformation. When an upstream release changes the configuration schema, run the migrate
  transformation against an old configuration before releasing, and confirm the app comes up on the
  migrated config. See `UPGRADING.md`.
- **Update survival.** Install the previous version on a box, then update it to the new one, and
  confirm the admin UI and the data plane both survive with their configuration intact.

Both need a live Cloudron, so they belong on a proving ground rather than in CI.

## One-time repository setup

- **Actions enabled.** A fork starts with workflows disabled: Settings, Actions, General, Enable.
- **Workflow permissions.** Settings, Actions, General, Workflow permissions: read and write. The
  release job needs it to push the release commit, and `packages: write` is requested by the
  workflow itself.
- **Branch protection on `main`.** The release job commits the pinned manifest and feed entry back
  to the branch it was dispatched from. With a pull-request-only rule and no bypass, that push is
  rejected at the last step, after the image is already public. Either allow the GitHub Actions
  app to bypass the rule for this repository, or run the Release workflow from a branch that is not
  protected and merge the resulting commit forward.
- **`ANONYMIZE_LIST` secret.** Settings, Secrets and variables, Actions: paste the contents of the
  estate's `.anonymize-list`. Without it the anonymity job fails closed and the release job refuses
  to publish, which is the intended behaviour: an identity scan that cannot run would otherwise
  report the same green as one that ran clean.
- **Package visibility.** First release of `ghcr.io/4glio/agentgateway-cloudron` creates it private;
  flip it public with the steps in gate 7.

## Rollback

The feed is the state. To withdraw a version, set its `publishState` to `unpublished` (or delete the
entry) in `CloudronVersions.json` and push: a box reads the feed and will not offer it. Do not
delete the image: boxes already running that digest need it on update and rollback.
