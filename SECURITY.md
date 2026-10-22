# Security policy

Report Tailmux vulnerabilities through [GitHub private vulnerability reporting](https://github.com/ddv1982/tailmux/security/advisories/new) for `ddv1982/tailmux`.
Private reporting is enabled for this repository.
Use a private report for exploit details and sensitive reproductions.
Public issues can track ordinary bugs after sensitive details have been removed.

A useful report contains the affected Tailmux version or source commit, OS build, dependency versions, reproduction steps, expected behavior, and observed impact.
Redact credentials, private keys, auth tokens, personal peer identities, complete Tailscale prefs, and unrestricted environment dumps.
`tailmux doctor` includes local paths and version evidence, so review its output before sharing it.
Maintainers coordinate disclosure with the reporter and affected dependency owners.

## Supported scope

The [dependency policy](docs/dependencies.md) records the dated version baselines, ownership, and known advisory conditions.
The current baselines are Tailscale 1.104.2 and jq 1.8.2, reviewed on 2026-10-22.
Bash 3.2 is the accepted language baseline.
OS maintenance and vendor backports require separate evidence.
An older version does not prove compromise, and a supported version does not prove a safe deployment.

Tailmux is an outbound client with a fail-closed peer resolver and one Tailscale SSH transport.
Local package administration, daemon configuration, tailnet policy, remote tmux, and OS certificate maintenance belong to their operators.
Removed mounting helpers and Taildrive are outside the core client support scope.
An upstream dependency issue can still affect Tailmux users, and maintainers help identify the relevant owner.

There is no previous authenticated operational release available for rollback yet.
Fake-command tests and release-verifier fixtures establish local behavior only.
Real protected publication, cryptographic consumer acceptance, and platform SSH scenarios remain release acceptance gates.
This policy does not declare those gates passed.

## Response targets

The repository maintainers own triage and reporter communication.
The release maintainer owns fixes, release coordination, withdrawal, and rollback.
Severity reflects reachable impact and attacker preconditions, including the affected client or server role.

These are best-effort targets for the first substantive response and a mitigation decision after validation.
They are not guaranteed fix deadlines or a staffed incident-response service.

| Severity | First response target | Mitigation decision target |
| --- | --- | --- |
| Critical, such as reachable code execution or a release trust bypass | 1 business day | 2 business days after validation |
| High, such as a reachable authorization or credential exposure defect | 3 business days | 7 calendar days after validation |
| Medium, such as a bounded integrity or availability defect | 7 business days | 30 calendar days after validation |
| Low, such as a limited hardening gap | 14 business days | Next planned release review |

A mitigation decision can disable an affected feature or withdraw an artifact while a fix remains under review.
Maintainers communicate revised timing when investigation, vendor coordination, or available capacity changes the target.

## Emergency release and recovery

The release maintainer follows this procedure with an independent reviewer and the repository operator.
The operator owns protected publication approval.

1. Record the report, affected source commit, impact, and immediate containment decision privately.
2. Freeze the affected release candidate and preserve redacted evidence.
3. Prepare a minimal fix or disable the affected path. Add a regression that demonstrates the failure and the corrected behavior.
4. Review the exact source commit independently. Run the required local checks and relevant isolated live scenarios. Record missing evidence as unverified.
5. Verify release protections, source and workflow identity, pinned actions, and the final package manifest before protected publication.
6. Authenticate the resulting artifact with independently supplied repository, workflow, tag, and commit expectations before installation. Reject a failed verification before processing payloads.
7. Record the artifact digest, source commit, approval, consumer-verification result, and recovery result in the release evidence.
8. Notify the reporter and publish a coordinated advisory when disclosure is appropriate.

The release maintainer withdraws a faulty candidate and directs operators to disable affected connections or use an independently reviewed safe checkout.
After an authenticated safe release exists, rollback requires verification of that exact artifact and its source identity.
A colocated checksum alone does not authenticate it.
Rollback must preserve fail-closed resolution and must not restore raw SSH fallback, unsafe PATH transfer, mutable bootstrap downloads, or automatic machine provisioning.
Package rollback and daemon restarts remain with each machine's package and service owner.
Credential rotation requires established exposure and the credential owner's action.
No runtime auto-update, emergency timer, service change, or tailnet policy change is part of this procedure.

The procedure requires a recorded rehearsal before release acceptance.
A fake verifier or signed test fixture proves refusal or recovery mechanics only.
The first real publisher and consumer verification receipts remain required evidence.
