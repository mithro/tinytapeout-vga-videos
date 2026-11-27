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

The user needs no sudo and no docker group. Disk, per project:

- the work directory (sources, build, scratch): up to 2 GB while a job runs
  ([measurements](reports/2026-11-pilot/measurements.md#root-volume-peak-per-job));
- the published frames subtree (trace, stores, hash files, PNGs, pages): 1 to
  611 MB in the pilot
  ([measurements](reports/2026-11-pilot/measurements.md#sizes)), kept, not
  deleted after encoding;
- the videos: about 50 to 150 MB for all three clips in both codecs.

Packages the host must already have, each printed by
[`tt-vga host-check`](../ttvga/remote.py):

| package | used by |
|---|---|
| [cmake](https://cmake.org/) | bootstrap, to build vgacap |
| a C compiler (`cc`) | bootstrap, to build vgacap and [`tracetool`](../ttvga/harness/tracetool.c) |
| [g++](https://gcc.gnu.org/) | every job, to compile the [Verilator](https://verilator.org) model |
| [GNU make](https://www.gnu.org/software/make/) | every job, to run Verilator's generated makefile |
| [git](https://git-scm.com/) | every job, to fetch the project's source |
| [tmux](https://github.com/tmux/tmux) | the queue, to survive SSH disconnects |

Without tmux the runner falls back to
[`setsid`](https://man7.org/linux/man-pages/man1/setsid.1.html) and
[`nohup`](https://man7.org/linux/man-pages/man1/nohup.1.html).

## Linger (done once by an administrator)

The queue runs each job in its own
[systemd](https://systemd.io/) user scope, which must outlive the SSH session,
so the user needs linger
([`loginctl`](https://man7.org/linux/man-pages/man1/loginctl.1.html)):

```
sudo loginctl enable-linger ttvga
```

[`tt-vga host-check`](../ttvga/remote.py) prints `Linger=yes` when it is on,
and the queue runner, [`runqueue.py`](../ttvga/harness/runqueue.py)
(`linger_problem`), refuses to start without it unless
[`tt-vga queue start`](../ttvga/remote.py) is given `--allow-no-linger`.

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
from `STAGING`. The archive's normal upload carries the subtree to the server
with everything else ([publishing](publishing.md#frames-upload)).

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
  ([Verilator](https://verilator.org),
  [Icarus Verilog](https://steveicarus.github.io/iverilog/),
  [Yosys](https://yosyshq.net/yosys/), [cocotb](https://www.cocotb.org/)), from
  the GitHub release tarball.
- A static [ffmpeg](https://github.com/BtbN/FFmpeg-Builds) build, from a pinned
  URL.
- [uv](https://github.com/astral-sh/uv) and, through it, the pinned Python
  3.14, so the harness scripts run with a known interpreter.
- [vgacap](https://github.com/mithro/vgacap) at the pinned commit, built with
  cmake, and [`tracetool`](../ttvga/harness/tracetool.c) built against it.
- [xxhash](https://pypi.org/project/xxhash/) at the pinned version, into uv's
  cache, for the host scripts' `uv run --with`.

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
