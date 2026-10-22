# Acceptance compatibility reference

No platform has real acceptance evidence at the final security stack head yet.
Every row below is NOT VERIFIED. Hosted runner tests establish offline tooling behavior only.

| Client | Destination | Intended coverage | Current evidence |
| --- | --- | --- | --- |
| Linux | Linux | `linux-linux` | No real SSH, host-key, terminal, or authenticated release evidence |
| macOS with a wrapper-capable Tailscale build | Linux | `macos-linux` | No real SSH, host-key, terminal, or authenticated release evidence |
| Linux | macOS with the open-source Tailscale CLI variant | `linux-macos` | No real SSH, host-key, terminal, or authenticated release evidence |

A reachable ordinary macOS sshd does not establish Tailscale SSH server support.
Upstream supports the server on Linux and the macOS open-source CLI variant. See [Tailscale SSH prerequisites](https://tailscale.com/docs/features/tailscale-ssh).
That upstream capability does not establish Tailmux acceptance for this row.
The acceptance validator still requires all three pairs. The separate publisher selector permits an explicit live-only waiver for v0.2.0 at one independently expected source. It leaves these rows NOT VERIFIED and waives no authentication, source, CI, or code-review requirement.

App Store and TestFlight Tailscale builds without `tailscale ssh` are incompatible with the selected transport.
Tailmux must report this limitation. It must not replace the app, weaken host-key checks, or fall back to raw SSH.
Windows, WSL, mounting, and Taildrive have no acceptance claim in this redesign.
Bash and Zsh launch the same executable; generated legacy functions must not shadow it.

The runtime needs Bash, jq, local Tailscale, and OpenSSH. tmux belongs on the destination.
The direct installer and release-package verifier need trusted Python 3.11 or later. Direct installation also needs trusted gh 2.103.0 or later, jq, and curl 8.4.0 or later. The optional acceptance smoke driver needs Python 3.10 or later with its standard library.
The smoke driver uses POSIX PTY control on Linux and macOS.
It supplies terminal bytes, resize propagation, bounded output, and child exit status.
It supplies no native screenshots or video. Such evidence still needs an independently available native recorder.

Each accepted platform inventory records OS builds, Bash, jq, OpenSSH vendor build and patch evidence,
Tailscale CLI and daemon versions, destination tmux, and the approved policy fixture.
Version banners alone do not prove vendor patch status.
Refresh the dated [dependency policy](dependencies.md) through the package owners before testing.
No package upgrade, policy change, credential creation, or host operation is part of these tools.

Offline tests use invented `work` and `TEST_USER` labels and synthetic evidence files.
A structurally complete test fixture does not establish that any real test ran.
There are no actual platform VERIFIED entries, performance measurements, or native recording receipts.
See [the acceptance procedure](acceptance.md) for the laptop handoff and release gates.
