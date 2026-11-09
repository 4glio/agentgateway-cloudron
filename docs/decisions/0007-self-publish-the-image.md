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

From 1.0.7 the documented maintainer is 4GL: `author`, `contactEmail`, `packagerName` and
`packagerUrl` all name 4GL. Entries 1.0.0 through 1.0.6 keep OrcVole in their embedded manifest
copies, because a published feed entry records what a box installed and is not rewritten. The
manifest `id` is unchanged: an install from this feed is the same Cloudron app, so a box can move
between the two feeds without becoming a second application.

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
- `author` and `contactEmail` named a person who was not the publisher between 1.0.6 and 1.0.6
  inclusive; 1.0.7 moves both to 4GL, and the historical feed entries keep the old values because
  they are not rewritten.
- Upstream improvements remain welcome. If the original repository merges this work, the only
  fork-specific part is the image namespace.
