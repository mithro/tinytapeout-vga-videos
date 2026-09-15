# Host setup

Simulations run on a remote Linux host under a dedicated unprivileged user
named `ttvga`. The repository never records which host is used; pass it as
`--host ttvga@HOST` or set `TTVGA_HOST`. A local, uncommitted
`~/.config/tinytapeout-vga-videos/config.toml` can give hosts short names.

## Create the user (done once by an administrator)

```
sudo adduser --disabled-password --gecos "Tiny Tapeout VGA sims" ttvga
sudo install -d -m 700 -o ttvga -g ttvga /home/ttvga/.ssh
sudo install -m 600 -o ttvga -g ttvga /path/to/orchestrator_key.pub /home/ttvga/.ssh/authorized_keys
```

The user needs no sudo, no docker group and no extra packages. It needs
roughly 20 GB of disk per 100 projects (sources, build directories, frames
are deleted after encoding; the videos are about 50 to 150 MB per project
for all three clips in MJPEG).

`tmux` must be available on the host (it is in Debian by default) so the
queue survives SSH disconnects. If it is not, the runner falls back to
`setsid nohup`.

## Bootstrap (done by the orchestrator, idempotent)

```
uv run tt-vga bootstrap --host ttvga@HOST
```

Installs into `/home/ttvga/ttvga/tools/`:

- YosysHQ oss-cad-suite (Verilator, Icarus Verilog, Yosys, cocotb), the
  version pinned in `ttvga/tools.toml`, from the GitHub release tarball.
- A static ffmpeg build (pinned URL and checksum).
- `uv`, so the harness scripts run with a known Python.

Nothing is installed outside the `ttvga` home directory.

## Checking a host

```
uv run tt-vga host-check --host ttvga@HOST
```

Prints cores, memory, free disk, load and tool versions, and refuses to
run if the login user is `root`, `tim` or `ansible`.
