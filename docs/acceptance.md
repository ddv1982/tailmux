# Run isolated acceptance after the laptop update

Live work is deferred until the operator updates the laptop through its existing package owners.
Live host checks are deferred at the operator’s request. This change runs no live-host operations.
No real platform, authentication, host-key, native recording, or performance gate is complete.

Use the [compatibility reference](compatibility.md) to select the intended platform pairs.
Use disposable isolated clients and destinations for fault tests.
A normal workstation is not disposable merely because it can reach a test host.
Keep recovery access under the operator's control.

## Inspect the reviewed checkout first

Fetch `security/05-release-acceptance` and use the reviewed full SHA supplied with the PR stack.
Do not infer acceptance from a moving branch name.
The following commands are a future operator procedure, not a record of commands already run.

```sh
git fetch origin security/05-release-acceptance
git switch --detach REVIEWED_FULL_SOURCE_SHA
git rev-parse HEAD
git status --short
bash bin/tailmux --help
bash setup.sh --help
bash bin/tailmux doctor
```

Replace `REVIEWED_FULL_SOURCE_SHA` with the exact reviewed commit before running the commands.
Stop if the checkout is dirty or differs from that commit.
Local `doctor` reports dependency inventory; review its output privately.
`doctor work` additionally reads peer status. It is optional and can reveal private peer identifiers.
Use the explicit checkout path so an old shell function cannot shadow the client.

Authenticate through your usual Tailscale path after the update.
Never put an auth key in chat, the command line, a committed fixture, or a terminal recording.
Check CLI and running daemon versions separately through the package owner's normal read-only checks.
Do not enable a server, grant an operator, change policy, or replace the Tailscale app for this procedure.
The operator must separately prepare an approved isolated test environment if prerequisites are missing.

After help and local doctor succeed, installation is optional.
Review the local installer and its destination first, then use the local checkout.

```sh
bash setup.sh install
```

This changes Tailmux-owned files. It is unnecessary for the first smoke test.
Migration, uninstall, and recovery tests belong in a disposable account with backed-up test dotfiles.

## Run the opt-in PTY smoke test

Approve one disposable destination, an explicit nonroot user, and the exact source commit.
`work` below is an operator-provided test selector. `TEST_USER` is a placeholder.
Neither is a real address or tailnet domain.
Prepare a private output parent outside the checkout before invoking the driver.

```sh
python3 scripts/acceptance/smoke.py \
	  --expected-commit REVIEWED_FULL_SOURCE_SHA \
	  --target work --user TEST_USER --platform macos \
	  --consent disposable-pty-smoke \
	  --timeout 120 --output "$HOME/private-tailmux-smoke"
```

For a Linux client, use `--platform linux`.
The output directory must not already exist. Keep its parent private and free of symlinks.
The reviewed checkout must be clean, including untracked files.
The driver refuses a missing terminal, wrong platform, root user, malformed target, or different source commit.
It invokes only `/bin/bash`, the checked-out `bin/tailmux`, and the explicit `TEST_USER@work` operand.
It uses argument arrays and never accepts arbitrary remote commands or SSH flags.
The runtime owns peer selection and the maintained `tailscale ssh` transport.
Local SSH configuration and the operator's local account remain trusted.

The driver passes terminal input to the real PTY and copies its output to your terminal and a private log.
It does not separately log keystrokes. Remote echo can still expose what you type.
Do not type secrets or run commands that print them during capture.
Resize your terminal to propagate its size. Detach with tmux's normal detach keys to finish an attach test.
Ctrl-C is terminal input for the foreground remote application; it does not necessarily end tmux.
The driver accepts at most 180 seconds of session time or 1 MiB of terminal output, followed by bounded local child cleanup.
It records the child's actual exit code, raw wait status, cancellation or timeout outcome, and observed resize events.
Timeout exits 124, cancellation exits 130, output overflow exits 125, and I/O failure exits 74.
Ordinary completion preserves the child's exit code or maps a signal to `128 + signal`.

`terminal.log` and `smoke.json` are private, unreviewed receipts with mode restricted by umask 077.
A timeout or local child cleanup does not prove that a remote tmux session was removed.
Inspect and clean up only the disposable sessions owned by this run, then save a cleanup receipt.
The driver does not remove sessions automatically, mutate policy or keys, perform mounts, or run sudo.
It cannot prove identity or successful tmux attachment from terminal text alone.
Its verdict is always NOT VERIFIED.

The driver provides native PTY control, not native screenshots or video recording.
Detect and use an actual terminal recorder separately for the required screenshots and 30 to 60 second video.
Never render a transcript into an image or generate video to fill that gap.
Without actual terminal control and native recording evidence, release interaction review remains NOT VERIFIED.

## Complete the manual scenarios

Run all ten scenario groups on every required platform pair in the approved request.
Record each subcase separately inside the group's command list and supporting state receipts.
A PASS covers all subcases in its group. A missing subcase is incomplete even if the JSON has the right fields.
The structural validator cannot determine whether observations are true or the subcases actually ran.
The protected operator review owns that judgment.

1. Resume an existing tmux session, then create one when none exists. Confirm the selected peer identity and advertised host key. Exercise the Linux to Linux, macOS to Linux, and investigated Linux to macOS lanes from PR05. Use current supported builds and record before, after, and cleanup state.
2. Use an operator-owned disposable destination fixture without tmux. Expect the missing-tmux diagnostic and remote exit 127. Do not remove tmux from a workstation to create the fixture.
3. Use separately prepared logged-out, stopped, and unavailable-daemon client fixtures. Expect distinct failures before transport. Do not log out or stop the working laptop. Save evidence that no alternate DNS or SSH path started.
4. Exercise invalid and malformed status snapshots through the offline fixtures. Repeat through an operator-owned isolated producer fixture if claiming a live boundary check. Never inject fabricated daemon responses into a workstation. Identify synthetic input explicitly.
5. Use isolated duplicate canonical-name and advertised-address fixtures, plus duplicate reported HostName values. Expect ambiguity rejection or canonical selection according to the contract. Status schemas that cannot produce a case remain offline-only coverage. They cannot become a claimed live pass.
6. Use a real shared-device FQDN and an IPv6-only test peer. With system MagicDNS acceptance disabled in the prepared fixture, confirm the intended peer still works through the maintained wrapper. Reject unknown selectors, external addresses, and misleading short names without fallback. Do not publish the private FQDN or addresses.
7. Use a separately provisioned identity denied by the test policy. Confirm access fails without another user or transport retry. Include a permitted nonroot control, an unauthorized root request, and forwarded-environment checks with harmless markers. Do not edit policy during the run or use real secrets as markers.
8. Use operator-owned missing-advertised-key and unadvertised-mismatch fixtures. Expect refusal. Separately observe a legitimate rotation through the trusted coordination channel and confirm it works. Retain the fixture identity and trust receipt. The driver does not synthesize rotation or key faults.
9. Drive a real terminal through resize, Ctrl-C, network disconnect, nonzero remote exit, and normal detach. Record exact outcomes, local child cleanup, and remote session state. Network loss belongs in an isolated fixture. Do not disconnect the working laptop to create it.
10. Test clean local install, recognized legacy migration through a dotfiles symlink, repeated install, uninstall, and first-release recovery in a disposable account. Preserve user files and Tailscale identity. Test a genuinely authenticated artifact and an invalid artifact rejected before execution. Follow the release owner's consumer-verification procedure. A fake verifier or signed test fixture proves only its stated mechanics, never an existing operational rollback release.

For each run, record the exact head and merge base, UTC times, OS builds, vendor patch evidence,
CLI and daemon versions, remote tmux version, approved policy fixture, exact argv, exit status,
expected and observed behavior, before and after state, native captures, cleanup, and operator review.
Retain originals privately. Produce redacted copies and bind their digests to the originals through protected operator custody.
Do not commit private hostnames or full peer snapshots as public fixtures.
Offline fixture success remains separate from real platform coverage.

## Supply the evidence contract

The release owner calls this stdlib-only interface without network access.
The independently approved request is separate from the bundle.

```sh
python3 scripts/acceptance/verify.py \
	  --request PRIVATE_APPROVED_REQUEST_JSON \
	  --bundle PRIVATE_REDACTED_BUNDLE_DIRECTORY \
	  --expected-sha REVIEWED_FULL_SOURCE_SHA \
	  --expected-merge-base REVIEWED_FULL_MERGE_BASE_SHA
```

Exit 0 means structural completeness only. The JSON output contains `structure: COMPLETE` and `verdict: NOT_VERIFIED`.
Exit 2 means rejected evidence and also contains `verdict: NOT_VERIFIED`.
Command-line parse errors use argparse's exit 2.
Do not turn exit 0 into VERIFIED, a release authorization, or proof that a test ran.
Never execute `argv` values read from evidence. This verifier does not launch subprocesses.

`AcceptanceRequest` has exactly these fields. Extra fields are rejected.

| Field | Shape |
| --- | --- |
| `schema` | Integer 1 |
| `source_sha`, `merge_base_sha` | Full lowercase 40-character SHAs matching independent CLI expectations |
| `approved_by`, `approved_at` | Operator identifier and UTC ISO time ending in `Z` |
| `platforms` | Exactly `linux-linux`, `macos-linux`, `linux-macos` |
| Each platform value | `target`, `user`, `isolated: true`, `scope: disposable-acceptance` |

`Evidence` is `evidence.json` inside the bundle. Extra fields are rejected at every defined record boundary.

| Field | Shape |
| --- | --- |
| `schema`, `source_sha`, `merge_base_sha` | Same schema and source binding as the request |
| `origin` | `kind: protected-operator`, `operator`, `custody_ref` |
| `redaction` | `reviewer`, `reviewed_at`, `status: PASS` |
| `files` | Entries with relative `path`, lowercase `sha256`, and `kind` |
| `scenarios` | Exactly one entry per scenario ID and required platform pair |
| `gates` | Exactly `unit-static`, `performance`, `audit-security`, `audit-release`, `operator-review` |

Allowed file kinds are UTF-8 `text`, PNG `native-screenshot`, and MP4 `native-video`.
PNG and MP4 header checks are format screening only. They cannot authenticate the capture or its contents.
All files must exist, be regular, and match their digest. Symlinks, hard links, traversal, duplicate paths,
unlisted files, duplicate JSON keys, and JSON constants such as NaN are rejected.
The limits are 1 MiB per JSON document, 256 referenced files, 32 MiB per file, and 128 MiB of evidence bytes.
The verifier accepts a directory and performs no archive extraction. The manual workflow uses the separate bounded ZIP intake tool. Keep it immutable during verification.
Use a bounded, isolated process when reading evidence from another principal.

Each scenario contains these fields:

- `platform`, `scenario`, `target`, `user`, `source_sha`, and `merge_base_sha` bind the run to the approved request.
- `status` is `PASS`. Error, skipped, and inconclusive results reject completeness.
- `started_at` and `finished_at` are UTC ISO times after request approval and in order.
- `inventory` contains nonempty `client_os`, `destination_os`, `bash`, `jq`, `openssh`, `tailscale_cli`, `tailscale_daemon`, `tmux`, `vendor_patch`, and `policy_fixture`. OS values start with `linux ` or `macos ` according to the pair. Include the full build after that prefix.
- `commands` is a nonempty list of records containing string-array `argv`, integer `expected_exit`, integer `exit_code`, `outcome: exited`, and a text-file `transcript` reference. Exit codes must match their expectations. An expected denial or exit 127 can be a successful test.
- `expected` and `observed` describe the complete group's subcases.
- `evidence` lists referenced files and includes text, a native screenshot, and native video.
- `operator_review` contains `reviewer`, `source_sha`, `reviewed_at`, `status: PASS`, and a text `receipt` reference. Review cannot predate completion.

Scenario IDs in checklist order are `attach-create`, `missing-tmux`, `backend-state`, `invalid-snapshot`,
`duplicate-identity`, `shared-ipv6-dns`, `denied-policy`, `host-keys`, `terminal-lifecycle`, and `install-recovery`.
The matrix currently requires 30 scenario records. These are ten groups per platform, not a claim that 30 real runs exist.
Each gate contains `status: PASS`, `source_sha`, `reviewer`, `reviewed_at`, and text `evidence` references.
A missing performance or independent audit lane rejects completeness.

The redaction gate rejects common Tailscale keys, GitHub tokens, private-key headers, and secret-assignment patterns.
It scans metadata and referenced bytes. It is not a complete secret detector.
The operator must inspect text, images, video, and metadata for secrets and private identifiers before sharing.
Do not replace secret markers with usable credentials to test the gate.
Fixture tests use invented strings and deliberately synthetic media headers, solely to test structural handling.

## Keep release approval independent

A manifest's `protected-operator` string cannot establish its origin.
Neither JSON, matching digests, a PASS field, nor a green hosted job proves that an operator performed a test.
The release owner must obtain the request and evidence through an authenticated protected operator channel,
review the exact source SHA and request digest independently, inspect raw-to-redacted custody receipts,
and bind the accepted manifest digest to the operator's external approval.
Reject evidence acquired only from the candidate checkout as untrusted for release approval.

The parent owns runner registration, required CI checks, and the final release gate.
The gate must combine structural success with trusted origin, real Linux and macOS coverage,
completed native interaction review, measured performance, independent security and release audits,
and the exact final head. Any missing, failed, or inconclusive lane keeps the result NOT VERIFIED.
A patch-changing fix invalidates affected receipts. Recheck the final merge base and head after rebases.
This acceptance tool never emits VERIFIED.

Performance remains unmeasured and deferred.
Before recording a baseline, follow the plan's benchmark checklist on identical isolated peers, builds, and policy.
Record trunk first and 20 interleaved setup samples, separating daemon startup and interactive login.
Investigate median noninteractive setup growth above both 20 percent and 100 milliseconds.
Noisy or authentication-skipped samples remain inconclusive.
There are no custom performance metrics or speed claims in this change.

## Bind protected release approval before building

The parent inserts this gate before package build, attestation, or publication in the protected release job.
The release owner supplies the expected source and captured merge base independently.

```sh
python3 scripts/acceptance/release_gate.py \
	  --expected-sha REVIEWED_FULL_SOURCE_SHA \
	  --expected-merge-base REVIEWED_FULL_MERGE_BASE_SHA
```

The protected environment supplies four independently reviewed expectations:

- `ACCEPTANCE_SOURCE_SHA` is the same full source SHA as the CLI expectation, checkout HEAD, `GITHUB_SHA`, and `GITHUB_WORKFLOW_SHA`.
- `ACCEPTANCE_ARTIFACT_ID` is an existing numeric evidence artifact ID in `ddv1982/tailmux`.
- `ACCEPTANCE_ARCHIVE_SHA256` is the independently approved digest of that artifact's downloaded ZIP bytes.
- `ACCEPTANCE_REQUEST_SHA256` is the independently approved digest of its `request.json`.

The job also needs the ordinary read-only Actions token for `gh api`, the fixed repository identity,
and GitHub-hosted runner identity. No new credential is created by this interface.
The captured merge base must equal `git merge-base HEAD origin/main`. Fetch the required main history first.
Tracked source changes, missing expectations, malformed values, stale source identity, wrong digests,
failed download, malformed archive, or incomplete evidence reject the gate with exit 2 and no success report.
The download is bounded to two minutes and 128 MiB. Temporary evidence is private and removed after verification.
The gate reuses `unpack.py` and `verify.py`; it never executes an evidence command.
After every control succeeds, exit 0 emits the structural JSON report with source, merge base,
artifact ID, archive digest, request digest, manifest digest, and `verdict: NOT_VERIFIED`.

The protected environment approver is the trust root.
Before approval, that person must independently inspect authenticated operator custody,
real Linux and macOS evidence, all ten scenario groups and subcases, native screenshots and video,
performance baseline and head samples, independent audits, and the exact-head operator review.
They must independently bind the four expectation values to that reviewed evidence.
A repository variable, self-declared JSON origin, artifact digest, or fake test fixture cannot replace that approval.
The parent publisher preflight must establish actual environment protections and reviewed tag identity first.
This script cannot observe a human approval merely from environment variables.
Its structural report alone never authorizes publication or certifies live execution.

## Review the manual workflow prerequisites

`.github/workflows/acceptance.yml` runs only by manual dispatch at the reviewed current main workflow commit.
Manual laptop checks can use the reviewed stack branch before integration; hosted acceptance dispatch cannot.
It runs no SSH, provisions no credentials, and contacts no test host.
Its hosted Linux and macOS jobs test the offline CLI and validate independently produced redacted evidence.
They upload only the structural report, never the raw evidence or private request.
No publication occurs.

The acceptance workflow calls its own dispatch preflight:

```sh
python3 scripts/acceptance/preflight.py --expected-sha REVIEWED_FULL_SOURCE_SHA
```

Exit 0 must mean successful authenticated read-only policy inspection.
The script rejects API failures, absent environment, absent required reviewers, missing self-review prevention,
inappropriate deployment restrictions, and an unreviewed commit under the required branch rules.
Dispatch must use `refs/heads/main`, the current protected main head, the expected repository, the acceptance workflow,
and equal checkout, dispatch, and workflow SHAs on a GitHub-hosted runner.
The acceptance environment must have exactly one custom deployment rule for branch `main`.
A `v*` tag rule belongs to the publisher environment and is rejected here.
Use read-only `contents` and `actions` token permissions, with no environment attached to preflight.
The script loads `scripts/release/preflight.py` through a fixed repository-relative import.
It reuses the release owner's `api`, `git`, and `validate_main` helpers for read-only API and protected-main checks.
It does not call the publisher's tag-specific CLI or environment validator.
The release helpers must be integrated before this workflow can run. Missing helpers fail closed.
The environment job requires successful preflight with `needs`; it has no bypass condition.

The operator must already have configured and independently inspected the protected `acceptance` environment.
Naming it in YAML does not establish protection and can create an unprotected environment.
If even environment-object creation must be prevented before rejection, complete preflight before dispatch as well.
Repository required-check settings and administrator bypass behavior need separate operator proof.
An unavailable policy read is a blocker, not an assumed pass.

Dispatch requires the exact source SHA, merge base, an evidence artifact ID in this repository, and independently approved ZIP and request digests.
The source SHA must equal checkout HEAD, `GITHUB_SHA`, and `GITHUB_WORKFLOW_SHA`.
The merge base must match the fetched main history.
After environment approval, the workflow downloads the independently produced artifact through read-only `gh api`.
The download has a two-minute timeout and a 128 MiB file-size limit.
`unpack.py` checks the approved ZIP digest before extracting only bounded regular files into a new private directory.
The ZIP contains `request.json` and `bundle/evidence.json` with all referenced files.
It rejects duplicate paths, traversal, links, special files, unsupported compression, encryption, and excessive sizes.
Partial output from a failed extraction is untrusted and must not be reused.
Artifact upload and operator authentication remain separate operator-owned steps. No SSH credential flow is created.
An artifact identifier and digest establish bytes, not real test execution or protected operator origin.
Do not commit self-referential evidence into the source checkout.
If the independent artifact cannot be safely redacted for this repository, keep dispatch blocked
and run verification privately through the parent release gate instead.

Fork PR tests stay in unprivileged CI with no acceptance environment or secrets.
This workflow has no PR trigger, no write token, and no secret-bearing live job.
Future secret-bearing work needs separate protected design and private secret entry.
Do not request or create credentials now.
External actions are pinned to the reviewed full checkout and upload SHAs, with checkout credential persistence disabled.
