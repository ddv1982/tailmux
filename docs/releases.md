# Verify and prepare a release

Tailmux supports a no-checkout direct installer for macOS and Linux. The README's short command downloads `install.sh` from an exact commit and checks its independently pinned SHA-256 before passing the verified bytes to Bash. Obtain that command through a channel you trust. Its literals are the first trust boundary. A compromised command distribution channel can replace those expectations.

The shell entrypoint pins v0.2.3, release source `0d109df952d45dede3c91647455ca0f6da3c2204`, the signing workflow, and certificate publisher IDs. It is distributed in a later commit; the release tag and signed assets remain at the original source. A subsequent README commit pins the shell entrypoint's exact commit and digest, so neither the script nor the release needs to contain its own future commit SHA.

The short command bounds HTTPS downloads and hashes the complete script in memory before any downloaded shell code runs. Python runs in isolated mode and launches Bash with only PATH, HOME, optional TMPDIR, and optional ZDOTDIR. The shell entrypoint then applies the private-staging and standard attestation checks below. It accepts install, update, and uninstall actions, plus an optional absolute prefix. All actions authenticate and validate the package before invoking its existing lifecycle writer. Update removes a different owned client only after the replacement passes authentication; removal retains a protected backup. The entrypoint currently selects v0.2.3 rather than discovering a mutable latest release.

## Install from authenticated release assets

The direct block requires independently installed, trusted Python 3.11 or later, gh 2.103.0 or later with the reviewed verification flags, jq, curl 8.4.0 or later, Bash, and OS utilities. Install or update those tools through their existing owners before using the block. No Python packages or GitHub login are required for the explicit bundle path. Standard Sigstore trust metadata can still require network access.

The block refuses root and unsupported platforms. Before downloads, it validates temporary-directory ancestry and creates private staging. It downloads only the exact versioned installer and standard Sigstore bundle over HTTPS, with bounded redirects, time, and bytes. curl configuration is disabled. curl 8.4.0 is the minimum because earlier versions cannot enforce the size limit during unknown-length transfers.

Trusted gh authenticates the installer before Python executes it. Successful verifier JSON must be a nonempty array. Every result's `verificationResult.signature.certificate` must contain string `sourceRepositoryIdentifier` equal to `1144643418` and string `sourceRepositoryOwnerIdentifier` equal to `240215896`. Missing, null, numeric, mixed, and wrong IDs fail. These fields come from successful standard verification, not the workflow-controlled predicate or raw bundle.

The authenticated installer downloads exactly `tailmux-TAG.tar.gz`. It authenticates a private archive snapshot with the same constraints before gzip or archive parsing. It then invokes the packaged local `setup.sh` with a clean subprocess environment. Setup retains ownership of destination safety, locking, receipts, retries, and legacy shell-block migration. It installs only the user-owned executable and receipt. It adds no PATH code, provisions no dependencies, and uses no sudo. A different installed version requires the existing reviewed uninstall procedure before replacement.

The three release assets are `tailmux-TAG-installer.py`, `tailmux-TAG.tar.gz`, and `tailmux-TAG.sigstore.json`. The installer is the exact committed bytes of `scripts/release/package.py`. The archive and installer are explicit subjects of the pinned standard attestation action. The bundle is copied unchanged from that action's `bundle-path` output.

## Verify with a trusted checkout

The existing manual verifier remains available. Obtain the exact tag and full source commit independently. Do not derive the expected commit from the downloaded manifest, an adjacent checksum, a tag lookup, or `latest`. Download the archive as inert bytes. From a separately trusted checkout, run:

```sh
python3 /trusted/tailmux/scripts/release/package.py verify \
  /downloads/tailmux-vVERSION.tar.gz \
  --tag vVERSION --source-sha EXPECTED_FULL_SOURCE_SHA \
  --output-parent /private/output
```

The placeholders above describe inputs, not a finalized release identity. Without `--bundle`, this uses the existing online gh verification path and needs gh authentication. To use the explicit anonymous bundle path, add `--bundle /downloads/tailmux-vVERSION.sigstore.json`. There is no automatic fallback after failed verification.

A successful verifier prints a new private `tailmux-verified-*` directory. Inspect its manifest and files. Install through `bash /private/output/tailmux-verified-.../setup.sh install`, with an optional absolute `--prefix`. The manual `verify` subcommand never executes archive content. Never use a verifier downloaded with an unauthenticated package to authenticate that package.

Both paths invoke trusted `gh attestation verify` with `--hostname github.com`, fixed repository `ddv1982/tailmux`, signer workflow `ddv1982/tailmux/.github/workflows/release.yml`, independently expected signer digest and source digest, exact `refs/tags/TAG`, `--deny-self-hosted-runners`, and `--format json`. Both enforce the certificate IDs above. Bundle verification binds historical certificate names and immutable IDs. It does not establish the online API's current repository-name mapping after renames.

## Canonical archive format

Authentication precedes the sole strict parser. Compressed bytes are limited to 8 MiB, expanded bytes to 16 MiB, each payload to 2 MiB, and the manifest to 32 KiB. The parser accepts exactly 21 regular USTAR members in a fixed order. It refuses extensions, links, directories, devices, FIFOs, traversal, duplicate or unexpected paths, unsupported metadata, malformed padding, and terminators. Every payload hash is checked before a stage or payload is written.

The canonical manifest records `format`, `version`, `source_sha`, and `members`. Member records contain exact `size` and lowercase SHA-256 `sha256`. Duplicate keys, extra fields, and noncanonical encodings fail. The new stage has mode `0700`. `bin/tailmux` alone has mode `0755`. Other files, including `setup.sh`, have mode `0644`.

`manifest.json` precedes these payloads:

```text
LICENSE
README.md
SECURITY.md
VERSION
bin/tailmux
docs/acceptance.md
docs/architecture.md
docs/compatibility.md
docs/dependencies.md
docs/taildrive.md
docs/releases.md
docs/troubleshooting.md
docs/usage.md
scripts/lib/cli.sh
scripts/lib/install.sh
scripts/lib/managed_blocks.sh
scripts/lib/platform.sh
scripts/lib/rc_blocks.sh
scripts/lib/uninstall.sh
setup.sh
```

The builders read committed Git blobs only. Working-tree changes and `.audit` data cannot enter either executable asset. Three literal versions must match the requested tag. The same Python and zlib implementation produces the same archive bytes for the same source. Cross-version compression equivalence is not promised. Outputs are created exclusively.

## Prepare stable v0.2.3

The parent release owner performs publication and repository changes. This guide grants no authority. Source-bound independent code review, actual exact-source successful hosted CI, explicit owner approval, source identity, and artifact authentication remain required. A sole maintainer's GitHub approval is owner authorization and does not claim independent human review.

1. Review the final source S. Keep `VERSION`, `bin/tailmux`, and `setup.sh` at `0.2.3`. Protect the independent repository variable `RELEASE_SOURCE_SHA` and set it to S. Do not infer S from the release event or tag.
2. Require PRs on main with zero GitHub approval reviews, stale-review dismissal, resolved review threads, and no last-push approval requirement. Require strict `full-linux`, `full-macos`, and `workflow-policy` checks from GitHub Actions app `15368`. Independent code review is recorded separately against S.
3. Establish the `release` environment with exactly User `82675328` as required reviewer, `prevent_self_review=false`, and exactly one tag deployment policy named `v0.2.3`. No branch or wildcard deployment policy is accepted. The validator binds that sole exact tag policy to the requested release; wildcards remain forbidden.
4. Preserve version tags with active repository rules forbidding updates and deletion, without exclusions or bypass actors. Readback accepts the exact tag, `refs/tags/v*`, or all tags. The read-only API can omit bypass actors. The release owner records their authorized readback separately.
5. Record the environment administrator-bypass state only if an authorized observable source establishes it. The documented environment GET response does not expose it. An unavailable settings page supplies no proof. Do not invent disabled bypass or independent GitHub human approval.
6. For normal releases, supply real exact-source acceptance evidence through the existing protected variables. A v0.2.3 live-only exception requires a new explicit release-owner decision and its own repository variable `RELEASE_LIVE_ONLY_WAIVER` record below, replacing its source value with S. Previous release authorizations do not carry forward automatically. Missing live acceptance remains `NOT_VERIFIED` in [compatibility](compatibility.md). This exception waives live acceptance only.
7. Create the lightweight `v0.2.3` tag at S and let its push start the publisher. Review the captured source, main, waiver digest, controls, independent review, and successful source CI before explicitly approving the release environment as the owner.
8. After publication, independently authenticate both installer and archive as a consumer. Record actual verification output, source and asset digests, owner approval, and remaining live evidence gaps.

The external waiver record has exactly these fields and types:

```json
{
  "schema": "tailmux-live-only-waiver-v1",
  "repository": "ddv1982/tailmux",
  "tag": "v0.2.3",
  "source_sha": "FINAL_40_LOWERCASE_HEX_SOURCE_SHA",
  "scope": "live-acceptance-only",
  "live_acceptance": "NOT_VERIFIED",
  "operator_id": 82675328,
  "reason": "Release owner accepts live SSH coverage as NOT_VERIFIED for the v0.2.3 daemon selection patch."
}
```

The source value above is documentation, not an accepted SHA. Only the finite v0.2.0, v0.2.1, v0.2.2, and v0.2.3 exceptions are implemented; every other tag still requires real acceptance evidence. An implemented selector is not owner approval: do not set the v0.2.3 record until the release owner explicitly authorizes it. The parser rejects duplicates, extra or missing fields, wrong types or values, oversized records, other tags, and a different source. The SHA-256 of the exact variable bytes is captured before approval and compared afterward. A missing value selects the unchanged real acceptance validator. An invalid value fails closed. The separate selector never fabricates evidence or makes the acceptance validator accept absent evidence.

The unprivileged job reads environment protections, active main rules, tag-preservation rules, and exact-source CI. It requires the latest CI push run at S to complete successfully and independently checks each required job and its app-attributed check run. Skipped, missing, wrong-source, wrong-workflow, wrong-app, or unsuccessful work rejects publication. Minimum read permissions cover contents, Actions, and checks.

The publisher repeats every check after owner approval. It refuses a changed expected source, captured main, or waiver bytes. Both jobs bind the tag push, hosted runner, event SHA, workflow SHA and ref, checkout HEAD, peeled tag, independent S, and source ancestry to captured main. It never dispatches from main and checks out another source. It then builds exact subjects, attests them, copies the standard bundle, and publishes all three explicit assets with `--verify-tag --prerelease=false --latest`. Release-exists failures require owner inspection. There is no overwrite or delete-and-republish automation.

After S exists, generate its literal install block from trusted source tools:

```sh
python3 scripts/release/package.py bootstrap-command \
  --tag v0.2.3 --source-sha INDEPENDENTLY_REVIEWED_SOURCE_SHA > /private/install-command.sh
```

Review the output and add it only in documentation descendant D or another separately reviewed distribution channel. The generator validates explicit inputs. It does not discover or authenticate the expected source for the operator.

## Check the infrastructure locally

Development dependencies support Python 3.11 through 3.14. Use the hashed `requirements-dev.txt` in a development environment. PyYAML is only for workflow policy. No Python package is needed by the installer or runtime.

```sh
bash scripts/tests/run.sh full
actionlint -oneline .github/workflows/*.yml
```

CI runs the same full suite on Linux and macOS. It includes the rendered bootstrap, actual installer CLI, installed executable, failure paths, and retry. Downloads, gh verification, and host commands are isolated fixtures. Fixtures prove behavior and sequencing, not real signatures, hosted publication, or live SSH compatibility. The policy job also checks workflow syntax and mutation tests. Repository settings separately make the checks mandatory.

Pinned actions disable persisted checkout credentials. The publisher disables registry upload and storage records. Review action updates, development hashes, runner compatibility, policy, and actionlint together. No PR test receives protected environment access or tailnet secrets.

## Recover an installation

Stop using a faulty candidate. Use its reviewed uninstall path to remove receipt-owned client files while preserving configuration. Networking identity, daemons, packages, server settings, and tailnet policy remain with their operators.

There is no previous authenticated operational artifact recorded in this source. Restore an earlier release only when it exists, independently matches its expected identity, and passes the same verification. Otherwise use a reviewed recovery checkout with connections disabled until recovery is accepted. Recovery must preserve fail-closed resolution, the single Tailscale SSH transport, and operator-owned provisioning.

## Source contracts

The official [gh verification manual](https://cli.github.com/manual/gh_attestation_verify) documents successful JSON and verification constraints. GitHub's [offline guidance](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/verify-attestations-offline) explains certificate repository-ID checks. The reviewed [gh 2.103.0 source](https://github.com/cli/cli/blob/7948e8056e45ac3c729b829e0eafe2d0797a95c6/pkg/cmd/attestation/verify/verify.go) defines the bundle login exemption and flag contract. The [curl manual](https://curl.se/docs/manpage.html#--max-filesize) defines transfer size enforcement.

GitHub documents [environment reads](https://docs.github.com/en/rest/deployments/environments), [ruleset reads and bypass visibility](https://docs.github.com/en/rest/repos/rules), [workflow runs](https://docs.github.com/en/rest/actions/workflow-runs), [jobs](https://docs.github.com/en/rest/actions/workflow-jobs), and [check runs](https://docs.github.com/en/rest/checks/runs). The pinned [attestation action](https://github.com/actions/attest/blob/1e69f48acb82d1966a394da916b4c1698aa569d6/action.yml) defines subject paths and the standard bundle output.
