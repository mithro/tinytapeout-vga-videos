# Tiny Tapeout VGA videos

Simulate every Tiny Tapeout project that matches the Tiny VGA Pmod pinout,
decode the VGA output, and produce 10, 30 and 60 second videos of what the
design shows. Videos that come out wrong are examined by an AI agent to work
out whether the project, the stimulus or the harness is at fault.

Project list and metadata come from
[tinytapeout-project-search](https://github.com/mithro/tinytapeout-project-search);
the simulator conventions come from the
[Tiny Tapeout VGA Playground](https://github.com/TinyTapeout/vga-playground).

Status: design under review. See `PROGRESS.md` for the work log and
`docs/superpowers/specs/2026-09-15-vga-videos-design.md` for the design.

Simulations run on a remote host under a dedicated unprivileged user; see
`docs/host-setup.md`. The repository never names the host.

## Questions awaiting answers

1. Hosts for phase 1: only one candidate host lets the orchestrator create
   the `ttvga` user itself. For the others an administrator must create the
   user and install the orchestrator's public key (commands in
   `docs/host-setup.md`). Start on the one host, or wait for all?
2. One candidate host presents a changed SSH host key. Is that expected
   (reinstall) and should the new key be accepted?
3. Which SSH key should the orchestrator use for the `ttvga` user? Default
   plan: a new key pair generated for this purpose, stored in `~/.ssh` on the
   orchestrating laptop, never in the repository.
4. The AI diagnosis runs the local Claude Code CLI (`claude -p`) on the
   laptop, on the existing subscription. Is a cap of two automatic attempts
   per project acceptable, and is there a session or daily budget to respect?
5. Should `poster.png` and `contact.png` per project (a few hundred KB
   each, about 150 MB for all projects) be committed for review, or kept
   only on the host with the videos?
6. Repository settings: same as the project-search repo (merge commits only,
   tag format `vXX.ZZZ`, protected `main`)?

## Licence

Apache 2.0. Project sources and documentation belong to their authors.
