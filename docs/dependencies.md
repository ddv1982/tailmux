# Dependency policy reference

This policy was reviewed on 2026-10-22.
`bin/tailmux` remains one self-contained Bash executable with embedded jq filters and a bounded version-policy table.
Its runtime requires Bash, jq, Tailscale, OpenSSH, and standard OS file utilities.
Python and gh are direct-installer and release-verification tools. curl 8.4.0 or later and jq are direct-installer prerequisites. PyYAML and GitHub Actions belong to development and publication.
Taildrive, davfs2, WebDAV helpers, and local tmux are outside the client dependency set.

## Inventory records

`tailmux doctor` prints a tab-separated local inventory after three introductory lines.
Each row contains `name`, `role/owner`, `active path`, `CLI version`, `daemon version`, `policy classification`, `evidence date`, and `reason`.
Nonprintable characters in cells become `?`.
The evidence date identifies the embedded policy review, not a fresh advisory lookup.
`-` means that a version field does not apply.
`unknown` means that the evidence was not obtained.

Paths identify the command selected by the current PATH or the running Bash interpreter.
A symlink is reported as selected, without resolving its package ownership or authenticating its target.
The daemon path stays unknown because the local version response does not identify its executable path.
Tailscale CLI and daemon have separate rows and classifications.
Both rows retain both versions, so a mismatch stays visible even when the CLI meets the baseline.
A mismatch does not cause a restart.

The local probes are `jq --version`, `tailscale version --daemon --json`, and `ssh -V`.
A failed daemon query permits a separate `tailscale version --json` query for CLI identity only.
The daemon remains unknown after that failure.
The parser uses the documented `majorMinorPatch`, `short`, `long`, and `daemonLong` fields and build flags from the pinned [version command](https://raw.githubusercontent.com/tailscale/tailscale/v1.104.2/cmd/tailscale/cli/version.go) and [version metadata](https://raw.githubusercontent.com/tailscale/tailscale/v1.104.2/version/prop.go).
A failed, oversized, missing, conflicting, or unparseable response cannot establish a supported version for that probe.
Each captured command response is limited to 64 KiB plus one overflow byte.
There is no runtime Python parser fallback.

Doctor reads local version information, including one local daemon request.
It does not query upstream releases, inspect complete prefs, print environment variables, inspect the certificate store, or run remote tmux.
It neither updates packages nor changes services, policy, authentication, or daemon state.
Its exit status is zero when it completes the inventory, even when rows report missing prerequisites or policy concerns.
The classifications are diagnostic output, not an installation or connection gate.
`tailmux doctor <selector>` retains the resolver's JSON result and exact fail-closed errors.
It queries peer status without invoking SSH or these version probes.

## Classification meanings

| Classification | Meaning |
| --- | --- |
| `supported` | Meets the dated, reviewed version or Bash language baseline. It does not authenticate a binary, establish vendor maintenance, or prove platform compatibility. |
| `unsupported` | A required executable is missing, or the observed version is outside the reviewed baseline, such as older jq or an unstable Tailscale branch. This is not an exploit claim. |
| `advisory-affected` | An upstream-style Tailscale version falls below a reviewed advisory fix boundary. Each reason retains the condition. Feature use, certificate trust, vendor backports, and actual exposure remain unverified. |
| `unknown` | Missing or failed version evidence, an unreviewed newer release, a development or vendor build, or absent vendor patch evidence prevents a conclusion. |

The supported exact version baselines are Tailscale 1.104.2 and jq 1.8.2.
Newer versions require a policy refresh rather than automatic acceptance.
Tailscale release identifiers of the form `1.104.2-t<hex>` or `1.104.2-t<hex>-g<hex>` retain the numeric baseline.
A recognizable suffix is not publisher authentication.
Development, dirty, and other vendor suffixes remain unknown.
The parser's accepted numeric components are bounded to four digits and exclude leading zeroes.

Vendor backports require the vendor's advisory, exact OS or package build, affected features, and a dated maintainer decision.
Doctor has no vendor evidence registry and accepts no user-supplied support override.
For example, Apple OpenSSH 10.3p1 remains unknown without Apple build-specific patch evidence.
It is not labelled vulnerable by comparing its banner with portable OpenSSH.
A future supported vendor entry requires real evidence and a reviewed fixture.

## Runtime register

The following register describes policy, not an observed fleet inventory.
Active paths and installed versions come from doctor on each machine.
The release maintainer owns the embedded policy and its agreement with this register.

| Name | Role and owner | Active path | CLI version policy | Daemon version policy | Classification | Evidence date and reason |
| --- | --- | --- | --- | --- | --- | --- |
| Bash | Interpreter. OS or shell package owner. | Running `$BASH`. | Bash 3.2 or later is the accepted language baseline. | Not applicable. | Language baseline supported. OS security maintenance unknown. | 2026-10-22. Apple Bash 3.2.57 exercises the local fake-command suite. |
| jq | JSON parser. Package owner. | Selected `jq`. | Exact 1.8.2 baseline. Older versions unsupported. Newer versions unknown. | Not applicable. | Version evidence required. | 2026-10-22. [jq 1.8.2 security release](https://github.com/jqlang/jq/releases/tag/jq-1.8.2). |
| Tailscale CLI | Transport wrapper. Existing Tailscale package owner. | Selected `tailscale`. | Exact stable 1.104.2 baseline. | Reported separately. | Exact reviewed version supported. Older candidates retain advisory conditions. | 2026-10-22. [Tailscale release](https://github.com/tailscale/tailscale/releases/tag/v1.104.2) and pinned schema fixtures. |
| Tailscale daemon | Active local network service. Tailscale package and service owner. | Unknown from version metadata. | CLI identity is not daemon identity. | Exact 1.104.2 baseline. | Classified independently of CLI. | 2026-10-22. Local `daemonLong` response. No process-path or restart verification. |
| OpenSSH | SSH client used by Tailscale. OS or package owner. | Selected `ssh`. | Vendor and OS build evidence required. | Not applicable to the local client inventory. | Unknown until vendor evidence is reviewed. | 2026-10-22. [Apple security releases](https://support.apple.com/en-us/100100) and [portable OpenSSH notes](https://www.openssh.org/releasenotes.html) have distinct scope. |
| tmux | Remote session manager. Destination operator. | Remote-owned and unknown locally. | Remote version unknown. | Not applicable. | Unknown. | 2026-10-22. A local tmux version cannot establish the destination's version or patch status. |
| TLS trust | OS certificate store and Tailscale's bundled Go TLS implementation. OS and Tailscale owners. | Not inspected. | Bundled implementation is part of the Tailscale build. | Same ownership applies to the daemon build. | Trust exposure unknown. | 2026-10-22. Updating system Go does not patch an installed Tailscale binary. |

No broad platform range has been established by this policy.
The exact Tailscale 1.104.2 status fixture tests parsing and command construction.
It does not prove real SSH authentication, host-key behavior, macOS variant compatibility, Linux compatibility, or destination readiness.
Bash 3.2 acceptance is a language decision, not a promise that every OS shipping it receives security updates.
Standard utilities such as `head`, `mktemp`, `wc`, `tr`, `rm`, and `rmdir` remain OS-owned.
Their patch evidence and platform behavior belong to the OS review.

## Conditional advisory register

These historical fix boundaries come from the [Tailscale security bulletins](https://tailscale.com/security-bulletins), checked on 2026-10-22.
They are a bounded triage shortlist, not a complete vulnerability scanner.

| Advisory | Fixed boundary | Required condition |
| --- | --- | --- |
| TS-2026-013 | Tailscale 1.104.2 | Compromised certificates remain trusted by the host. WireGuard mesh encryption has a different trust boundary. |
| TS-2026-011 | Tailscale 1.102.3 | The affected router advertises 4via6 routes accessible to a peer. |
| TS-2026-010 | Tailscale 1.102.1 | The affected SSH server forwards secret values through `acceptEnv`. |
| TS-2026-009 and TS-2026-006 | Tailscale 1.98.9 | The affected SSH server relies on nonroot restrictions that special usernames bypass. |
| TS-2026-005 | Tailscale 1.98.9 | An affected nonroot Serve operator can proxy privileged Unix sockets. |
| TS-2026-012 | libtailscale 0.2.0 | Excluded from this client. Tailmux invokes the standard Tailscale executable. |

An older upstream version is an advisory candidate, not proof of compromise.
Doctor does not determine enabled server features or whether certificate trust has been corrected separately.
Destination server assessment belongs to its operator.
Tailscale's bundled Go and OS trust-store updates remain with their respective package owners.

## Development and release register

These tools are absent from the installed CLI dependency set.
The release maintainer owns their pins, source verification, review, and runner compatibility.
The project maintainer owns local test tooling.

| Tool | Reviewed version or pin | Scope and evidence |
| --- | --- | --- |
| Python | 3.11 or later for the installer; 3.11 through 3.14 for hashed development wheels. | Installer and verification tooling only. This support floor is separate from live platform acceptance. No runtime Python dependency. |
| PyYAML | `PyYAML==6.0.3`. | Workflow policy checker only. The release owner must retain approved distribution hashes in development requirements. No runtime YAML parser. |
| gh | 2.103.0 reviewed flag contract. | Installer and release verification. Constrains hostname, repository, signer workflow and digest, source ref and digest, and hosted runners. Explicit bundle mode uses successful JSON certificate publisher IDs. Source contract evidence is not cryptographic acceptance. |
| curl | 8.4.0 minimum for direct install. | HTTPS-only, bounded downloads with configuration disabled. Earlier versions cannot enforce the byte limit during unknown-length transfers. |
| actions/checkout | v7.0.1, `3d3c42e5aac5ba805825da76410c181273ba90b1`. | Reviewed full SHA. Node 24. Hosted runner compatibility and `persist-credentials: false` remain release-owner obligations. |
| actions/attest | v4.2.2, `1e69f48acb82d1966a394da916b4c1698aa569d6`. | Reviewed full SHA. Attests the final archive and exact committed installer. |
| actions/upload-artifact | v7.0.2, `cf430e030ddbb5b0abf93d22962f4752f3646cd9`. | Reviewed full SHA. CI evidence transport only. |
| ShellCheck and actionlint | ShellCheck 0.11.0 locally. actionlint 1.7.12 in parent release review. | Development checks. Syntax checks do not prove branch protection, publisher identity, or a secure deployment. |

The listed action pins are the reviewed PR-04 selections.
The release owner verifies that actual workflows use those exact pins before publication.
Checkout documents runner 2.327.1 or later and 2.329.0 or later for authenticated container Git operations in its [pinned README](https://raw.githubusercontent.com/actions/checkout/3d3c42e5aac5ba805825da76410c181273ba90b1/README.md).
The attestation verifier's contract is documented in the [gh manual](https://cli.github.com/manual/gh_attestation_verify).

## Review ownership

The release maintainer performs a human advisory review every week and refreshes this policy before every release.
The review covers Tailscale bulletins, jq releases, OS vendor advisories, destination tmux evidence, CI action pins, and release-tool contracts.
The maintainer records the date, exact build or source evidence, affected features, decision, and owner in the release evidence.
A changed baseline updates the embedded table, this register, and the literal doctor fixtures together.
Unknown vendor evidence remains unknown until reviewed.
Dependency-update proposals require review before adoption.
There is no timer, standing automation, runtime update check, or automatic package reconciliation in doctor.

The machine operator owns package updates, recovery access, and confirmation of the active daemon after an update.
The destination operator owns remote tmux, Tailscale SSH enablement, server policy, and server-side advisories.
The release maintainer owns Tailmux artifact withdrawal and rollback under [the security policy](../SECURITY.md).
