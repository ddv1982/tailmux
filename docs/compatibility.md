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
The verifier currently requires all three pairs and cannot silently waive one.

App Store and TestFlight Tailscale builds without `tailscale ssh` are incompatible with the selected transport.
Tailmux must report this limitation. It must not replace the app, weaken host-key checks, or fall back to raw SSH.
Windows, WSL, mounting, and Taildrive have no acceptance claim in this redesign.
Bash and Zsh launch the same executable; generated legacy functions must not shadow it.

The runtime needs Bash, jq, local Tailscale, and OpenSSH. tmux belongs on the destination.
The offline verifier and optional smoke driver need Python 3.10 or later with its standard library.
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
