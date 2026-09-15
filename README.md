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

## Decisions so far

- Phase 1 is RTL simulation with Verilator; gate-level simulation is phase 2.
- Videos, posters and contact sheets stay on the simulation host for now; a
  few examples are committed for documentation. Long-term hosting and
  YouTube (with title card and outro) come later.
- Static output counts as a success that may need more stimulus.
- Automated AI diagnosis of every failure is a late step and is only run
  after discussion; ad hoc diagnosis is used while developing.

## Licence

Apache 2.0. Project sources and documentation belong to their authors.
