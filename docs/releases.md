# Verify and prepare a release

Use a separately trusted checkout of the release tools. The verifier needs Python 3 and an independently installed, trusted GitHub CLI with the flags below. These are release tools, not Tailmux runtime dependencies. The release maintainer owns their updates. The reviewed CLI flag contract was checked with `gh 2.100.0`. That version observation does not establish patch status.

## Verify before installation

1. Obtain the exact version tag and full source commit through an independent reviewed channel. Do not derive the expected commit from the archive, its manifest, an adjacent checksum, or a mutable `latest` reference.
2. Download the versioned `tailmux-vVERSION.tar.gz` release asset. Keep it unopened.
3. From your trusted checkout, run the command below. Substitute the independently expected tag and 40-character lowercase source SHA. Use a current-user output directory without group or other write access.

```sh
python3 /trusted/tailmux/scripts/release/package.py verify \
  /downloads/tailmux-vVERSION.tar.gz \
  --tag vVERSION --source-sha EXPECTED_FULL_SOURCE_SHA \
  --output-parent /private/output
```

A successful command prints a new private `tailmux-verified-*` directory. Inspect its manifest and files. Then install explicitly with `bash /private/output/tailmux-verified-.../setup.sh install`. The verifier never installs, sources, or runs archive content. Never use a verifier from the downloaded package to authenticate that package. The package deliberately excludes release verification tools.

The trusted verifier copies at most 8 MiB into a private temporary snapshot and runs the standard verifier before any gzip or tar parsing:

```sh
gh attestation verify SNAPSHOT \
  --repo ddv1982/tailmux \
  --signer-workflow ddv1982/tailmux/.github/workflows/release.yml \
  --signer-digest EXPECTED_FULL_SOURCE_SHA \
  --source-ref refs/tags/EXPECTED_TAG \
  --source-digest EXPECTED_FULL_SOURCE_SHA \
  --deny-self-hosted-runners
```

Failure rejects the package. There is no checksum-only or unsigned fallback. Repository, signer, source, hosted-runner identity, and artifact digest are constrained through GitHub's standard SLSA attestation verification. The trusted checkout, installed `gh`, Python, host, and independent expected identity remain prerequisites.

After successful attestation verification, the tool accepts only the canonical `tailmux-portable-v1` USTAR layout. It bounds expanded bytes at 16 MiB, each payload at 2 MiB, and the manifest at 32 KiB. It requires exactly 15 regular members in a fixed order. It rejects extensions including PAX, GNU long names and sparse records, duplicate or colliding names, links, directories, devices, FIFOs, traversal, absolute paths, unsupported metadata, unexpected members, nonzero padding, and malformed terminators. It hashes every payload before creating the output stage or writing any payload. A new stage has mode `0700`. Existing output is never overwritten.

The canonical JSON manifest records `format`, `version`, `source_sha`, and `members`. Each member record contains its exact `size` and lowercase SHA-256 `sha256`. Duplicate keys, extra fields, unexpected paths, and noncanonical encodings fail. Paths and modes are fixed by this format. `bin/tailmux` alone has mode `0755`; every other regular member, including `setup.sh`, has mode `0644`. Run `setup.sh` through Bash.

The manifest is followed by these payloads in order:

```text
LICENSE
README.md
VERSION
bin/tailmux
docs/architecture.md
docs/releases.md
docs/troubleshooting.md
scripts/lib/cli.sh
scripts/lib/install.sh
scripts/lib/managed_blocks.sh
scripts/lib/platform.sh
scripts/lib/rc_blocks.sh
scripts/lib/uninstall.sh
setup.sh
```

## Prepare publication

Publication is not authorized by this guide. The checked-in workflow contains an unconditional acceptance refusal before build, attestation, and publication. PR-04 cannot publish even after an environment is configured. Parent integration must replace that refusal with the final PR-05 evidence gate before enabling a release. Local fake-verifier tests do not satisfy that gate.

The recommended PR-05 variable interface keeps `RELEASE_SOURCE_SHA` as the independently reviewed source and adds `RELEASE_ACCEPTANCE_SHA256` in the protected `release` environment. The operator sets the digest only after reviewing the exact acceptance evidence and its source. The parent-owned gate must check the retrieved evidence bytes against that digest before parsing, require their `source_sha` to equal `RELEASE_SOURCE_SHA`, and validate the acceptance schema, all required lanes, and referenced evidence digests. Missing or malformed expectations and incomplete or inconclusive evidence must reject. An immutable artifact ID may locate evidence, but it does not replace the reviewed digest. Run this gate after approval and repeated preflight, before build, attestation, or publication. This interface is a recommendation for parent integration. The current release workflow keeps an unconditional refusal in its place.

1. Review the exact source commit. Keep `VERSION`, the binary's literal `TAILMUX_VERSION`, and the installer's literal `TAILMUX_VERSION` equal to the tag without its leading `v`. The builder checks all three without executing them.
2. Have a repository administrator establish the existing `release` environment before running a tag workflow. Configure required reviewers, prevent self-review, disable administrator bypass, and permit only the `v*` tag deployment policy. No branch deployment policy is accepted.
3. Require active main rulesets for fresh independent PR approval, stale approval dismissal, last-push approval, and strict required status checks. Required contexts are `full-linux`, `full-macos`, and `workflow-policy`, bound to the GitHub Actions app, ID `15368`. Classic branch protection alone does not satisfy this read-only ruleset check.
4. Independently confirm the source was reviewed. Administrative custody must protect the repository variable `RELEASE_SOURCE_SHA`. Set it to that exact reviewed commit before pushing the version tag. Keep any environment override identical. The variable must never come from the event SHA, an archive, or a tag lookup. GitHub variable YAML does not itself establish restricted custody.
5. Confirm the environment's administrator-bypass setting and ruleset bypass actors manually. The environment GET API does not prove administrator-bypass configuration. Record that operator gate outside the workflow. Active rules and ancestry do not prove historical review of a commit.
6. Complete the separate acceptance checklist and review the final head before publication. No settings changes or publication were performed by this implementation.

The unprivileged `preflight` job has no environment and only contents/actions read. It uses GET requests for the environment, all deployment-policy pages, main, and all active main-rule pages. API failures, missing fields, absent reviewers, disabled self-review prevention, weak deployment restrictions, unprotected main, missing approval rules, and missing or wrongly attributed required checks reject the release. The last repository investigation found no environments and an unprotected main. Those settings must refuse publication.

The privileged job depends on successful preflight and protected environment approval. It has only contents write, attestations write, id-token write, and actions read for repeated protection checks. It repeats the checks after approval and refuses a changed main SHA or changed expected source. Naming an environment is not proof of protection. GitHub does not document environment-object creation timing relative to dependency evaluation, so this workflow cannot prove that no environment object is created during a rejected run. If that prohibition is required, an operator must run the read-only preflight before triggering the workflow.

Both jobs require a hosted runner and agreement among the independently expected source, event SHA, peeled tag commit, checkout HEAD, workflow SHA, and exact `release.yml@refs/tags/TAG` identity. The source must be an ancestor of the captured main SHA. The workflow runs from the version tag itself. It does not dispatch from main and then check out another ref.

The builder reads only the fixed payload paths from committed Git blobs. Working-tree changes cannot enter the package. File modes, manifest order, timestamps, ownership, USTAR headers, and gzip timestamp/name are fixed. The same Python/zlib implementation produces identical bytes for the same source. Cross-version zlib compression equivalence is not promised. The output archive is created exclusively and is attested before upload and publication. No custom signing, release hooks, runtime updater, registry upload, or storage record is added.

## Check the infrastructure locally

Use Python 3.11 through 3.14 for development dependency wheels. `requirements-dev.txt` pins PyYAML 6.0.3 with hashes for Linux and macOS wheels. Install it only in your development environment. Tailmux does not import it at runtime. The policy loader rejects duplicate keys, anchors, aliases, and merges. It preserves `on` as a string and resolves only true/false as booleans.

Run the local checks:

```sh
python3 scripts/release/check_workflows.py
actionlint -oneline .github/workflows/*.yml
python3 scripts/tests/suites/workflow_policy.py
python3 scripts/tests/suites/release_cli.py
python3 scripts/tests/suites/release_preflight.py
bash scripts/tests/run.sh full
```

CI runs the complete Linux and macOS suites as blocking jobs. Runner package owners install jq and ShellCheck. The Linux policy job installs hashed development wheels and verifies the pinned actionlint 1.7.12 distribution digest before execution. No `pull_request_target`, release token permissions, protected environment, or live-tailnet secrets are supplied to PR tests. Repository settings must separately make these job contexts required. Workflow YAML alone does not establish a merge gate.

Action updates use reviewed full SHA pins for Node 24 checkout, attestation, and artifact upload. Checkout disables credential persistence. Use hosted runners supporting the pinned checkout's runner requirements. Dependabot proposes weekly action and development dependency updates. Review new SHAs, Node runtime and runner compatibility, hashes, semantic policy, and actionlint before accepting an update. The policy deliberately rejects unreviewed pins until its reviewed registry is updated.

The tests use fake `gh` and API responses to prove invocation constraints, refusal behavior, sequencing, and output isolation. The controlled temporary Git fixture proves the real committed-object builder, modes, version agreement, and deterministic output. It does not create a release tag or commit in the project checkout. None of these tests proves real signature acceptance, protected publisher execution, fork-event isolation, Linux/macOS live installation, or platform performance. Those remain acceptance gates.

## Recover the first release

Withdraw or remove a failed candidate through its release owner. Stop using the installed candidate and disable connections. Use a reviewed checkout's uninstall path to remove the owned binary while preserving configuration. Do not change Tailscale identity, daemon state, packages, server settings, or policy as part of recovery.

There is no previous authenticated operational artifact yet. A separately authenticated test fixture can prove rollback mechanics, but it cannot supply a nonexistent published rollback. Restore an earlier artifact only when it actually exists, independently matches the expected source, and passes the same trusted verification. Otherwise keep connections disabled until an independently reviewed recovery build is ready. No recovery may restore raw SSH fallback, mounting, provisioning, or caller PATH transfer.

## Source contracts

The reviewed [GitHub CLI verification flags](https://cli.github.com/manual/gh_attestation_verify) define the standard verifier boundary. GitHub documents [environment reads](https://docs.github.com/en/rest/deployments/environments) and [active branch rule reads](https://docs.github.com/en/rest/repos/rules). The pinned [attestation action inputs](https://github.com/actions/attest/blob/1e69f48acb82d1966a394da916b4c1698aa569d6/action.yml) define the archive subject and disabled registry/storage behavior.
