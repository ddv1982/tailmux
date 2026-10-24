# Verify and prepare a release

Tailmux supports a no-checkout direct installer for macOS and Linux. The README's short command downloads `install.sh` from an exact commit and checks its independently pinned SHA-256 before passing the verified bytes to Bash. Obtain that command through a channel you trust. Its literals are the first trust boundary. A compromised command distribution channel can replace those expectations.

The prepared shell entrypoint pins v0.3.0 and frozen release source S, `877f8ffedacb68c8f78d0ce38ed506a4456d96ab`.
The v0.3.0 tag and assets are not yet published. The current README command still pins the working v0.2.3 distribution.
Do not merge new public pins until the exact new installer and archive independently authenticate.

Distribution has three distinct commits. S contains the reviewed runtime, setup, release tools, and workflows.
A later installer commit I contains `install.sh` with the literal tag and S.
Only after I exists can descendant README commit D pin I's exact SHA and the SHA-256 of its `install.sh` blob.
Neither I nor D changes the runtime or setup bytes from S. Never invent a future commit ID or publish mismatched URL and checksum pins.
Keep I and D together in an unmerged distribution PR until publication, independent asset authentication, and complete-head checks pass.

The short command hashes the bounded script in memory before downloaded shell code runs.
Python uses isolated mode and launches Bash with only PATH, HOME, optional TMPDIR, and optional ZDOTDIR.
The adapter preserves that scrubbed context for packaged setup and forwards values as literal Bash array arguments.
It accepts `install`, `update`, and `uninstall` with an optional absolute prefix, recovery preview or exact-digest approval, guarded transaction maintenance, and `configure --socket ABS_SOCKET` without a prefix.
Help is offline. Every other public action authenticates the installer and archive before setup or archive parsing.
Installed runtime configuration commands remain offline.

Public update delegates to canonical `install --replace-owned` for an existing regular client.
Setup revalidates ownership under one lifecycle lock and retains a verified content backup. It never removes the executable first.
An absent executable, including valid same-source receipt-only recovery, uses ordinary install. Same-source update is a no-op.
Modified or foreign contents still refuse normal update and uninstall. See the [recovery guide](troubleshooting.md#recover-a-modified-client).
There is no latest lookup or additional release request.

## Install from authenticated release assets

The direct block requires independently installed, trusted Python 3.11 or later, gh 2.103.0 or later with the reviewed verification flags, jq, curl 8.4.0 or later, Bash, and OS utilities. Install or update those tools through their existing owners before using the block. No Python packages or GitHub login are required for the explicit bundle path. Standard Sigstore trust metadata can still require network access.

The block refuses root and unsupported platforms. Before downloads, it validates temporary-directory ancestry and creates private staging. It downloads only the exact versioned installer and standard Sigstore bundle over HTTPS, with bounded redirects, time, and bytes. curl configuration is disabled. curl 8.4.0 is the minimum because earlier versions cannot enforce the size limit during unknown-length transfers.

Trusted gh authenticates the installer before Python executes it. Successful verifier JSON must be a nonempty array. Every result's `verificationResult.signature.certificate` must contain string `sourceRepositoryIdentifier` equal to `1144643418` and string `sourceRepositoryOwnerIdentifier` equal to `240215896`. Missing, null, numeric, mixed, and wrong IDs fail. These fields come from successful standard verification, not the workflow-controlled predicate or raw bundle.

The adapter downloads exactly three release assets per successful invocation, the versioned installer, standard bundle, and `tailmux-TAG.tar.gz`. The authenticated installer verifies a private archive snapshot with the same constraints before gzip or archive parsing. The adapter then invokes packaged `setup.sh` with its scrubbed environment and validated literal request. Setup retains ownership of destination safety, locking, receipts, retries, and legacy shell-block migration. It installs only the user-owned executable and receipt. It adds no PATH code, provisions no dependencies, and uses no sudo. A different unchanged receipt-owned version uses the shared replacement operation. Recovery and configuration also delegate only to the authenticated package's setup, never the installed executable.

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

## Prepare stable v0.3.0

The parent release owner performs publication and repository changes. This guide grants no authority. Source-bound independent code review, actual exact-source successful hosted CI, explicit owner approval, source identity, and artifact authentication remain required. A sole maintainer's GitHub approval is owner authorization and does not claim independent human review.

1. Review the final source S. Keep `VERSION`, `bin/tailmux`, and `setup.sh` at `0.3.0`. Protect the independent repository variable `RELEASE_SOURCE_SHA` and set it to S. Do not infer S from the release event or tag.
2. Require PRs on main with zero GitHub approval reviews, stale-review dismissal, resolved review threads, and no last-push approval requirement. Require strict `full-linux`, `full-macos`, and `workflow-policy` checks from GitHub Actions app `15368`. Independent code review is recorded separately against S.
3. Establish the `release` environment with exactly User `82675328` as required reviewer, `prevent_self_review=false`, and exactly one tag deployment policy named `v0.3.0`. No branch or wildcard deployment policy is accepted. The validator binds that sole exact tag policy to the requested release; wildcards remain forbidden.
4. Preserve version tags with active repository rules forbidding updates and deletion, without exclusions or bypass actors. Readback accepts the exact tag, `refs/tags/v*`, or all tags. The read-only API can omit bypass actors. The release owner records their authorized readback separately.
5. Record the environment administrator-bypass state only if an authorized observable source establishes it. The documented environment GET response does not expose it. An unavailable settings page supplies no proof. Do not invent disabled bypass or independent GitHub human approval.
6. For normal releases, supply real exact-source acceptance evidence through the existing protected variables. A v0.3.0 live-only exception requires a new explicit release-owner decision and its own repository variable `RELEASE_LIVE_ONLY_WAIVER` record below, replacing its source value with S. Previous release authorizations do not carry forward automatically. Missing live acceptance remains `NOT_VERIFIED` in [compatibility](compatibility.md). This exception waives live acceptance only.
7. Create the lightweight `v0.3.0` tag at S and let its push start the publisher. Review the captured source, main, waiver digest, controls, independent review, and successful source CI before explicitly approving the release environment as the owner.
8. After publication, independently authenticate both installer and archive as a consumer. Record actual verification output, source and asset digests, owner approval, and remaining live evidence gaps.

The external waiver record has exactly these fields and types:

```json
{
  "schema": "tailmux-live-only-waiver-v1",
  "repository": "ddv1982/tailmux",
  "tag": "v0.3.0",
  "source_sha": "FINAL_40_LOWERCASE_HEX_SOURCE_SHA",
  "scope": "live-acceptance-only",
  "live_acceptance": "NOT_VERIFIED",
  "operator_id": 82675328,
  "reason": "Release owner accepts live SSH coverage as NOT_VERIFIED for the v0.3.0 installation recovery and saved daemon selection release."
}
```

The source value above is documentation, not an accepted SHA. Only the finite v0.2.0, v0.2.1, v0.2.2, v0.2.3, and v0.3.0 exceptions are implemented; every other tag still requires real acceptance evidence. An implemented selector is not owner approval: do not set the v0.3.0 record until the release owner explicitly authorizes it. The parser rejects duplicates, extra or missing fields, wrong types or values, oversized records, other tags, and a different source. The SHA-256 of the exact variable bytes is captured before approval and compared afterward. A missing value selects the unchanged real acceptance validator. An invalid value fails closed. The separate selector never fabricates evidence or makes the acceptance validator accept absent evidence.

The unprivileged job reads environment protections, active main rules, tag-preservation rules, and exact-source CI. It requires the latest CI push run at S to complete successfully and independently checks each required job and its app-attributed check run. Skipped, missing, wrong-source, wrong-workflow, wrong-app, or unsuccessful work rejects publication. Minimum read permissions cover contents, Actions, and checks.

The publisher repeats every check after owner approval. It refuses a changed expected source, captured main, or waiver bytes. Both jobs bind the tag push, hosted runner, event SHA, workflow SHA and ref, checkout HEAD, peeled tag, independent S, and source ancestry to captured main. It never dispatches from main and checks out another source. It then builds exact subjects, attests them, copies the standard bundle, and publishes all three explicit assets with `--verify-tag --prerelease=false --latest`. Release-exists failures require owner inspection. There is no overwrite or delete-and-republish automation.

The trusted source generator can render the longer direct-asset command below. It does not produce the short README URL and checksum pins for future I. Keep the README block unchanged until the actual installer commit exists:

```sh
python3 scripts/release/package.py bootstrap-command \
  --tag v0.3.0 --source-sha INDEPENDENTLY_REVIEWED_SOURCE_SHA > /private/install-command.sh
```

The generator validates explicit tag and source inputs. It does not discover or authenticate them. For the short README command, the parent release owner creates I first, reads its exact committed `install.sh` blob, then records its real SHA and digest in D. Final checks must fetch and verify that actual pin chain separately from private fixtures.

## Check the infrastructure locally

Development dependencies support Python 3.11 through 3.14. Use the hashed `requirements-dev.txt` in a development environment. PyYAML is only for workflow policy. No Python package is needed by the installer or runtime.

```sh
bash scripts/tests/run.sh full
actionlint -oneline .github/workflows/*.yml
```

CI runs the same full suite on Linux and macOS. It includes the rendered bootstrap, actual installer CLI, installed executable, failure paths, and retry. Downloads, gh verification, and host commands are isolated fixtures. Fixtures prove behavior and sequencing, not real signatures, hosted publication, or live SSH compatibility. The policy job also checks workflow syntax and mutation tests. Repository settings separately make the checks mandatory.

Pinned actions disable persisted checkout credentials. The publisher disables registry upload and storage records. Review action updates, development hashes, runner compatibility, policy, and actionlint together. No PR test receives protected environment access or tailnet secrets.

## Recover an installation

Stop using a faulty candidate. Use the [recovery guide](troubleshooting.md#recover-a-modified-client) to inspect a modified or pending installation and preserve its verified backups. Use reviewed uninstall only when ownership remains valid. Networking identity, daemons, packages, server settings, and tailnet policy remain with their operators.

There is no previous authenticated operational artifact recorded in this source. Restore an earlier release only when it exists, independently matches its expected identity, and passes the same verification. Otherwise use a reviewed recovery checkout with connections disabled until recovery is accepted. Recovery must preserve fail-closed resolution, the single Tailscale SSH transport, and operator-owned provisioning.

## Source contracts

The official [gh verification manual](https://cli.github.com/manual/gh_attestation_verify) documents successful JSON and verification constraints. GitHub's [offline guidance](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/verify-attestations-offline) explains certificate repository-ID checks. The reviewed [gh 2.103.0 source](https://github.com/cli/cli/blob/7948e8056e45ac3c729b829e0eafe2d0797a95c6/pkg/cmd/attestation/verify/verify.go) defines the bundle login exemption and flag contract. The [curl manual](https://curl.se/docs/manpage.html#--max-filesize) defines transfer size enforcement.

GitHub documents [environment reads](https://docs.github.com/en/rest/deployments/environments), [ruleset reads and bypass visibility](https://docs.github.com/en/rest/repos/rules), [workflow runs](https://docs.github.com/en/rest/actions/workflow-runs), [jobs](https://docs.github.com/en/rest/actions/workflow-jobs), and [check runs](https://docs.github.com/en/rest/checks/runs). The pinned [attestation action](https://github.com/actions/attest/blob/1e69f48acb82d1966a394da916b4c1698aa569d6/action.yml) defines subject paths and the standard bundle output.
