# Host setup

Simulations run on a remote Linux host under a dedicated unprivileged user
named `ttvga`. The repository never records which host is used, nor any path
on it; pass the host as `--host ttvga@HOST` or set `TTVGA_HOST`. A local,
uncommitted `~/.config/tinytapeout-vga-videos/config.toml` can give hosts short
names. Below, `ARCHIVE`, `FRAMES_ROOT` and `STAGING` are placeholders for
paths the administrator chooses.

## Create the user (done once by an administrator)

```
sudo adduser --disabled-password --gecos "Tiny Tapeout VGA sims" ttvga
sudo install -d -m 700 -o ttvga -g ttvga /home/ttvga/.ssh
sudo install -m 600 -o ttvga -g ttvga /path/to/orchestrator_key.pub /home/ttvga/.ssh/authorized_keys
```

The user needs no sudo and no docker group. It needs roughly 20 GB of disk per
100 projects (sources, build directories; frames are deleted after encoding;
the videos are about 50 to 150 MB per project for all three clips in both
codecs).

Packages the host must already have: [cmake](https://cmake.org/) and a C
compiler (bootstrap builds vgacap and `tracetool` with them), and
[tmux](https://github.com/tmux/tmux) so the queue survives SSH disconnects (it
is in Debian by default; without it the runner falls back to `setsid nohup`).

## Linger (done once by an administrator)

The queue runs in tmux and must outlive the SSH session, so the user needs
systemd linger:

```
sudo loginctl enable-linger ttvga
```

[`tt-vga host-check`](../ttvga/remote.py) prints `Linger=yes` when it is on,
and [`tt-vga queue start`](../ttvga/remote.py) refuses to start without it
unless given `--allow-no-linger`.

## Frames subtree and staging directory (done once by an administrator)

The published frames live in their own subtree of the archive, and copies are
made in a staging directory that is outside the archive but on the same
filesystem, so the final swap is a rename:

```
sudo install -d -o ttvga -g ttvga -m 755 STAGING
sudo install -d -o ttvga -g ttvga -m 755 FRAMES_ROOT
sudo -u ttvga touch FRAMES_ROOT/.ttvga-frames-root
```

`FRAMES_ROOT/.ttvga-frames-root` is the marker that tells
[`hostconf`](../ttvga/harness/hostconf.py) the directory is the frames subtree
and not the archive. `hostconf.load` refuses a `frames_root` that lacks the
marker, that holds `index.html` or `index.json` (the archive itself), that
contains or is contained in `STAGING`, or that is on a different filesystem
from `STAGING`. Create the subtree only once the main upload excludes it, so
that not even the empty directory and its marker reach the server.

## `host.toml`

As `ttvga`, write `~/ttvga/host.toml`; [`hostconf`](../ttvga/harness/hostconf.py)
reads it on the host:

```toml
frames_root = "FRAMES_ROOT"      # absolute path of the frames subtree
staging_dir = "STAGING"          # absolute path of the staging directory
min_free_root_gb = 100           # optional; default 100
```

Both directories must exist. Keep the real paths in a private note, not in this
repository.

## Bootstrap (done by the orchestrator, idempotent)

```
uv run tt-vga bootstrap --host ttvga@HOST
```

[`bootstrap`](../ttvga/remote.py) installs into `/home/ttvga/ttvga/tools/`, with
every version pinned in [`ttvga/tools.toml`](../ttvga/tools.toml):

- [YosysHQ oss-cad-suite](https://github.com/YosysHQ/oss-cad-suite-build)
  (Verilator, Icarus Verilog, Yosys, cocotb), from the GitHub release tarball.
- A static [ffmpeg](https://github.com/BtbN/FFmpeg-Builds) build, from a pinned
  URL.
- [uv](https://github.com/astral-sh/uv) and, through it, the pinned Python
  3.14, so the harness scripts run with a known interpreter.
- [vgacap](https://github.com/mithro/vgacap) at the pinned commit, built with
  cmake, and [`tracetool`](../ttvga/harness/tracetool.c) built against it.

Nothing is installed outside the `ttvga` home directory, and bootstrap does not
touch the `work/` tree.

## Checking a host

```
uv run tt-vga host-check --host ttvga@HOST
```

[`host-check`](../ttvga/remote.py) prints cores, memory, free disk, load, tool
versions, whether cmake is present, the linger state and whether `host.toml`
exists, and refuses to run if the login user is `root`, `tim` or `ansible`.
`host.toml` itself is only validated by `hostconf.load` once the frames subtree
exists.
