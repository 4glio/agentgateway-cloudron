# 0006 - This repository publishes its own image

## Context

The package was written by the upstream packager, OrcVole, and published as
`ghcr.io/orcvole/agentgateway-cloudron`. Releases were cut by hand from a workstation with a
personal access token, following `docs/RELEASING.md`.

A change was prepared and a pull request was opened against that repository. It went unanswered.
That left this fork able to run the package but unable to ship a security fix: the changelog, the
Dockerfile and the feed are ours to edit, and the image is not. A package that cannot publish its
own image is a package whose vulnerability window is set by someone else's availability.

## Decision

This repository publishes `ghcr.io/4glio/agentgateway-cloudron` and generates its own
`CloudronVersions.json` entries. The image is built and pushed by `.github/workflows/release.yml`
using the workflow's `GITHUB_TOKEN`, and `scripts/release.sh` writes the manifest and the feed from
the digest the registry returned in that same run.

`author` and `contactEmail` still credit the original packager, because the packaging design and
the topology decisions are theirs. `packagerName` and `packagerUrl` name 4GL, because the artefact
is built here. The manifest `id` is unchanged: an install from this feed is the same Cloudron app,
so a box can move between the two feeds without becoming a second application.

The old identity rule, that all published artifacts use one neutral name and no personal identity
appears anywhere, becomes narrower and sharper: no personal host, email, username, key or token in
any tracked file, enforced by `test/secret-scan.sh`. Publishing under an organisation is not a
licence to leak the person behind the workstation.

## Consequence

- A release no longer depends on a PAT, a workstation, or a maintainer at another project. It
  depends on this repository's own CI.
- The first release of the package creates a private GHCR package. Until its visibility is flipped
  to public, the release fails its anonymous-pull gate, deliberately: a feed entry pointing at an
  image strangers cannot pull is worse than no release.
- `author` and `contactEmail` now identify a person who is not the publisher. That is a
  documentation debt, not a runtime one; it is called out in `docs/RELEASING.md` so the next
  maintainer does not read it as an error.
- Upstream improvements remain welcome. If the original repository merges this work, the only
  fork-specific part is the image namespace.
