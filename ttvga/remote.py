# SPDX-License-Identifier: Apache-2.0
"""Talk to the simulation host over SSH: bootstrap tools, sync the harness, run the queue, collect results.

The host is never recorded in the repository. It comes from `--host user@name`,
the `TTVGA_HOST` environment variable, or a short name looked up in
`~/.config/tinytapeout-vga-videos/config.toml`:

    [hosts.big]
    ssh = "ttvga@example.org"
    key = "~/.ssh/ttvga_ed25519"
    jobs = 40

Everything on the host lives under `~/ttvga/` of the dedicated user.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from ttvga import HARNESS_DIR, OVERRIDES_DIR, RESULTS_DIR, TARGETS_JSON

CONFIG_PATH = Path.home() / ".config" / "tinytapeout-vga-videos" / "config.toml"
FORBIDDEN_USERS = {"root", "tim", "ansible"}
REMOTE_ROOT = "ttvga"          # working files, relative to the remote user's home
REMOTE_VIDEOS = "public_html"  # published clips, served at https://<host>/~<user>/
TOOLS_TOML = Path(__file__).resolve().parent / "tools.toml"


@dataclass
class Host:
    ssh: str                    # user@host
    key: str | None = None
    jobs: int = 8

    @property
    def user(self) -> str:
        return self.ssh.split("@", 1)[0] if "@" in self.ssh else os.environ.get("USER", "")

    def ssh_cmd(self) -> list[str]:
        cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20"]
        if self.key:
            cmd += ["-o", "IdentitiesOnly=yes", "-i", os.path.expanduser(self.key)]
        return cmd


def resolve_host(spec: str | None) -> Host:
    """Turn --host / TTVGA_HOST / a config short name into a Host, refusing privileged users."""
    spec = spec or os.environ.get("TTVGA_HOST")
    if not spec:
        sys.exit("tt-vga: no host given: use --host user@host, TTVGA_HOST, or a name from the config file")
    host = Host(ssh=spec)
    if CONFIG_PATH.exists():
        cfg = tomllib.loads(CONFIG_PATH.read_text())
        entry = cfg.get("hosts", {}).get(spec)
        if entry:
            host = Host(ssh=entry["ssh"], key=entry.get("key"), jobs=int(entry.get("jobs", 8)))
        elif "@" not in spec:
            sys.exit(f"tt-vga: {spec!r} is not user@host and not a name in {CONFIG_PATH}")
    if host.user in FORBIDDEN_USERS or not host.user:
        sys.exit(f"tt-vga: refusing to run as user {host.user!r}; use the dedicated unprivileged user")
    return host


def ssh(host: Host, script: str, check: bool = True, capture: bool = False, timeout: float | None = None) -> subprocess.CompletedProcess:
    """Run a shell script on the host through `bash -s` so quoting stays local."""
    cmd = host.ssh_cmd() + [host.ssh, "bash", "-s"]
    return subprocess.run(cmd, input=script, text=True, check=check, timeout=timeout,
                          capture_output=capture)


def rsync(host: Host, sources: list[str], dest: str, delete: bool = False, extra: list[str] | None = None) -> None:
    cmd = ["rsync", "-a", "--mkpath", "-e", " ".join(shlex.quote(c) for c in host.ssh_cmd())]
    if delete:
        cmd.append("--delete")
    cmd += extra or []
    cmd += sources + [f"{host.ssh}:{dest}"]
    subprocess.run(cmd, check=True)


def rsync_from(host: Host, source: str, dest: Path, extra: list[str] | None = None) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    cmd = ["rsync", "-a", "--mkpath", "-e", " ".join(shlex.quote(c) for c in host.ssh_cmd())]
    cmd += extra or []
    cmd += [f"{host.ssh}:{source}", str(dest)]
    p = subprocess.run(cmd)
    # 24 means a file disappeared while copying: a job on the host rewrote its
    # result. Everything else came across, so collecting during a run is fine.
    if p.returncode not in (0, 24):
        raise subprocess.CalledProcessError(p.returncode, cmd)


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------

def host_check(args: argparse.Namespace) -> int:
    host = resolve_host(args.host)
    script = f"""
set -e
echo "user: $(whoami)  host: $(hostname)"
echo "cores: $(nproc)  load: $(cut -d' ' -f1-3 /proc/loadavg)"
free -g | awk '/Mem:/ {{print "memory GB: total " $2 ", available " $7}}'
df -h ~ | awk 'NR==2 {{print "disk: " $4 " free of " $2}}'
for t in tmux git g++ make python3; do printf "%s: " $t; command -v $t || echo MISSING; done
R=~/{REMOTE_ROOT}
[ -x $R/tools/oss-cad-suite/bin/verilator ] && $R/tools/oss-cad-suite/bin/verilator --version || echo "verilator: not bootstrapped"
[ -x $R/tools/ffmpeg/bin/ffmpeg ] && $R/tools/ffmpeg/bin/ffmpeg -version | head -1 || echo "ffmpeg: not bootstrapped"
[ -f $R/queue-state.json ] && python3 -c "import json;s=json.load(open('$R/queue-state.json'));print('queue:', 'running' if not s['finished'] else 'finished', s['done'], 'done', s['failed'], 'failed', len(s['running']), 'active')" || echo "queue: never run"
ls $R/work 2>/dev/null | wc -l | sed 's/^/shuttles with work: /'
find $R/work -name result.json 2>/dev/null | wc -l | sed 's/^/results: /'
du -sh ~/{REMOTE_VIDEOS} 2>/dev/null || echo "published videos: none"
curl -s -o /dev/null -w "published index: HTTP %{{http_code}}\\n" "https://$(hostname -f)/~$(whoami)/index.html" || true
"""
    return ssh(host, script, check=False).returncode


def bootstrap(args: argparse.Namespace) -> int:
    """Install the pinned toolchain under ~/ttvga/tools on the host. Idempotent."""
    host = resolve_host(args.host)
    tools = tomllib.loads(TOOLS_TOML.read_text())
    steps = []
    for name, t in tools.items():
        strip = f"--strip-components={t['strip']}" if t.get("strip") else ""
        mkdir = f"mkdir -p {t['dir']}" if t.get("strip") else "true"
        into = f"-C {t['dir']}" if t.get("strip") else ""
        steps.append(f"""
if [ ! -x {t['check']} ]; then
  echo "installing {name} {t['version']}"
  {mkdir}
  curl -sSL -o dl/{name}.tar {shlex.quote(t['url'])}
  tar xf dl/{name}.tar {into} {strip}
  rm -f dl/{name}.tar
else
  echo "{name}: present"
fi""")
    script = f"""
set -e
mkdir -p ~/{REMOTE_ROOT}/tools/dl ~/{REMOTE_ROOT}/harness ~/{REMOTE_ROOT}/overrides ~/{REMOTE_ROOT}/work ~/{REMOTE_ROOT}/videos
cd ~/{REMOTE_ROOT}/tools
{''.join(steps)}
./oss-cad-suite/bin/verilator --version
./ffmpeg/bin/ffmpeg -version | head -1
"""
    return ssh(host, script, check=False, timeout=3600).returncode


def sync(args: argparse.Namespace) -> int:
    """Copy the harness, targets and compiled overrides to the host."""
    from ttvga.overrides import COMPILED_DIR, compile_all

    host = resolve_host(args.host)
    n = compile_all()
    rsync(host, [str(HARNESS_DIR) + "/", str(TARGETS_JSON)], f"{REMOTE_ROOT}/harness/", delete=True,
          extra=["--exclude", "__pycache__"])
    rsync(host, [str(COMPILED_DIR) + "/"], f"{REMOTE_ROOT}/overrides/", delete=True)
    print(f"synced harness, targets and {n} overrides to {host.ssh}:{REMOTE_ROOT}/")
    return 0


def queue(args: argparse.Namespace) -> int:
    """Start, stop or inspect the job queue, which runs inside a tmux session on the host."""
    host = resolve_host(args.host)
    if args.action == "start":
        jobs = args.jobs or host.jobs
        q = (f"python3 ~/{REMOTE_ROOT}/harness/runqueue.py --root ~/{REMOTE_ROOT} --jobs {jobs} "
             f"--seconds {args.seconds} --timeout {args.timeout}")
        if args.only:
            q += f" --only {shlex.quote(args.only)}"
        if args.limit:
            q += f" --limit {args.limit}"
        if args.redo:
            q += " --redo"
        script = f"""
set -e
if tmux has-session -t ttvga 2>/dev/null; then echo "queue already running (tmux session ttvga)"; exit 1; fi
tmux new-session -d -s ttvga {shlex.quote(q + f" 2>>~/{REMOTE_ROOT}/queue-stderr.log; echo QUEUE-EXITED; sleep 60")}
sleep 2
tail -n 3 ~/{REMOTE_ROOT}/queue.log
"""
        return ssh(host, script, check=False).returncode
    if args.action == "stop":
        # SIGTERM lets the queue finish running jobs and start no more.
        script = f"""
if [ -f ~/{REMOTE_ROOT}/queue-state.json ]; then
  PID=$(python3 -c "import json;print(json.load(open('$HOME/{REMOTE_ROOT}/queue-state.json'))['pid'])")
  kill -TERM $PID 2>/dev/null && echo "sent SIGTERM to queue $PID" || echo "queue not running"
fi
"""
        return ssh(host, script, check=False).returncode
    if args.action == "status":
        script = f"""
tmux has-session -t ttvga 2>/dev/null && echo "tmux session: running" || echo "tmux session: none"
[ -f ~/{REMOTE_ROOT}/queue-state.json ] && cat ~/{REMOTE_ROOT}/queue-state.json
echo "--- last log lines"
tail -n {args.lines} ~/{REMOTE_ROOT}/queue.log 2>/dev/null || true
"""
        return ssh(host, script, check=False).returncode
    if args.action == "kill":
        return ssh(host, "tmux kill-session -t ttvga 2>/dev/null && echo killed || echo 'no session'", check=False).returncode
    return 2


def collect(args: argparse.Namespace) -> int:
    """Pull every result.json (and timing.json) from the host into data/results/."""
    host = resolve_host(args.host)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    rsync_from(host, f"{REMOTE_ROOT}/work/", RESULTS_DIR,
               extra=["--include", "*/", "--include", "result.json", "--exclude", "*", "--prune-empty-dirs"])
    # The per-frame hash list is only useful on the host; keep the committed results small.
    for path in RESULTS_DIR.glob("*/*/result.json"):
        result = json.loads(path.read_text())
        timing = result.get("timing") or {}
        if "frame_hashes" in timing:
            timing["frame_hashes_count"] = len(timing.pop("frame_hashes"))
            path.write_text(json.dumps(result, indent=2) + "\n")
    if args.images:
        dest = Path(args.images)
        rsync_from(host, f"{REMOTE_VIDEOS}/", dest,
                   extra=["--include", "*/", "--include", "poster.png", "--include", "contact.png",
                          "--exclude", "*", "--prune-empty-dirs"])
    n = sum(1 for _ in RESULTS_DIR.glob("*/*/result.json"))
    print(f"collected {n} results into {RESULTS_DIR}")
    return 0


def add_parsers(sub: argparse._SubParsersAction) -> None:
    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--host", help="user@host, or a name from ~/.config/tinytapeout-vga-videos/config.toml")

    p = sub.add_parser("host-check", help="print cores, memory, disk, tool versions and queue state")
    common(p); p.set_defaults(func=host_check)
    p = sub.add_parser("bootstrap", help="install the pinned toolchain into the host user's home")
    common(p); p.set_defaults(func=bootstrap)
    p = sub.add_parser("sync", help="copy harness, targets and overrides to the host")
    common(p); p.set_defaults(func=sync)
    p = sub.add_parser("queue", help="start|stop|status|kill the job queue on the host")
    common(p)
    p.add_argument("action", choices=["start", "stop", "status", "kill"])
    p.add_argument("--jobs", type=int, default=0, help="parallel jobs (default from config or 8)")
    p.add_argument("--only", default="", help="comma separated shuttles or <shuttle>/<macro> ids")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--redo", action="store_true")
    p.add_argument("--seconds", type=float, default=60.0)
    p.add_argument("--timeout", type=float, default=1800.0)
    p.add_argument("--lines", type=int, default=20, help="log lines to show for status")
    p.set_defaults(func=queue)
    p = sub.add_parser("collect", help="pull result.json files into data/results/")
    common(p)
    p.add_argument("--images", help="also pull poster and contact images into this local directory")
    p.set_defaults(func=collect)
