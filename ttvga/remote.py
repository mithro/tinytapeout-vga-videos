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
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from ttvga import HARNESS_DIR, RESULTS_DIR, ROOT, TARGETS_JSON, framehashes

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


def tarball_tools(tools: dict) -> dict:
    """The tools.toml entries installed from a tarball (those with a `url`)."""
    return {name: t for name, t in tools.items() if "url" in t}


def uv_env(runtime: bool = False) -> str:
    """uv environment assignments that keep the interpreter and cache under ~/ttvga/tools.

    At run time uv may only use that managed interpreter and never downloads one.
    """
    env = (f"UV_PYTHON_INSTALL_DIR=~/{REMOTE_ROOT}/tools/python UV_CACHE_DIR=~/{REMOTE_ROOT}/tools/uv-cache "
           f"UV_PYTHON_BIN_DIR=~/{REMOTE_ROOT}/tools/bin")
    if runtime:
        env += " UV_PYTHON_PREFERENCE=only-managed UV_PYTHON_DOWNLOADS=never"
    return env


def host_python(tools: dict) -> str:
    """The pinned interpreter every host script starts through."""
    return (f"{uv_env(runtime=True)} ~/{REMOTE_ROOT}/tools/uv/uv run --no-project "
            f"--python {tools['python']['version']} python")


def vgacap_build_commands(src: str, build: str, commit: str, url: str | None = None) -> list[str]:
    """Shell lines that fetch `commit` shallowly into `src` and build the vgacap tools in `build`.

    `url`, when given, sets up `src`'s origin first. The final PINNED file records
    the commit that was built, and is removed before a build starts, so a
    different pin or a failed build never looks current.
    """
    cmds = [f"[ -d {src}/.git ] || git init -q {src}"]
    if url:
        cmds.append(f"git -C {src} config --get remote.origin.url || git -C {src} remote add origin {shlex.quote(url)}")
    cmds += [
        f"git -C {src} cat-file -e {commit}^{{commit}} || git -C {src} fetch -q --depth 1 origin {commit}",
        f"git -C {src} checkout -q --detach {commit}",
        f"rm -f {build}/PINNED",
        f"cmake -S {src} -B {build} -DCMAKE_BUILD_TYPE=Release",
        f"cmake --build {build} -j 8 --target vgacap-sample vgacap-export vgacap-dump vgacap_trace vgacap_sample",
        f"echo {commit} > {build}/PINNED",
    ]
    return cmds


def tracetool_build_commands(src: str, build: str, source: str) -> list[str]:
    """Shell lines that compile `source` (tracetool.c) against the vgacap build into `build`/tracetool.

    The static libraries are found in the build tree, not guessed.
    """
    cmds = ["set -e", f"rm -f {build}/tracetool"]
    libs = []
    for i, lib in enumerate(("libvgacap_trace.a", "libvgacap_stream.a", "libvgacap_sha256.a", "libvgacap_zstd.a")):
        cmds += [f"L{i}=$(find {build} -name {lib} -print -quit)",
                 f'[ -n "$L{i}" ] || {{ echo "tracetool: {lib} not found under {build}" >&2; exit 1; }}']
        libs.append(f'"$L{i}"')
    cmds.append(f"cc -std=c99 -O2 -Wall -Wextra -Werror -I{src}/include -I{src}/third_party/sha256 "
                f"-I{src}/third_party/zstd/lib {source} {' '.join(libs)} -pthread -o {build}/tracetool")
    return cmds


def bootstrap_script(tools: dict) -> str:
    """The script that installs the pinned toolchain under ~/ttvga/tools on the host."""
    steps = []
    for name, t in tarball_tools(tools).items():
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
    py = tools["python"]["version"]
    vg = tools["vgacap"]
    build = "\n".join(vgacap_build_commands("vgacap-src", "vgacap-build", vg["commit"], vg["git"]))
    tracetool = "\n".join(tracetool_build_commands("vgacap-src", "vgacap-build", "tracetool.c"))
    return f"""
set -e
export {uv_env()}
mkdir -p ~/{REMOTE_ROOT}/tools/dl ~/{REMOTE_ROOT}/harness ~/{REMOTE_ROOT}/overrides ~/{REMOTE_ROOT}/work ~/{REMOTE_ROOT}/videos
cd ~/{REMOTE_ROOT}/tools
{''.join(steps)}
./oss-cad-suite/bin/verilator --version
./ffmpeg/bin/ffmpeg -version | head -1
./uv/uv --version
./uv/uv python install --no-bin {py}
if [ -f vgacap-build/PINNED ] && [ "$(cat vgacap-build/PINNED)" = "{vg['commit']}" ]; then
  echo "vgacap: present at {vg['commit']}"
else
  echo "building vgacap {vg['commit']}"
{build}
fi
echo "building tracetool"
({tracetool})
"""


def harness_version(repo: Path = ROOT) -> str:
    """A 16-hex key for the harness and tool pins; `-dirty` when either has uncommitted changes."""
    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                              text=True).stdout.strip()
    tree = git("rev-parse", "HEAD:ttvga/harness")
    blob = git("rev-parse", "HEAD:ttvga/tools.toml")
    key = hashlib.sha256(f"{tree}\n{blob}\n".encode()).hexdigest()[:16]
    if git("status", "--porcelain", "--", "ttvga/harness", "ttvga/tools.toml"):
        key += "-dirty"
    return key


def queue_command(args: argparse.Namespace, host: Host, tools: dict) -> str:
    """The command that starts the queue on the host, run under the pinned Python."""
    jobs = args.jobs or host.jobs
    q = (f"{host_python(tools)} ~/{REMOTE_ROOT}/harness/runqueue.py --root ~/{REMOTE_ROOT} --jobs {jobs} "
         f"--seconds {args.seconds} --timeout {args.timeout}")
    if args.only:
        q += f" --only {shlex.quote(args.only)}"
    if args.limit:
        q += f" --limit {args.limit}"
    if args.redo:
        q += " --redo"
    if args.redo_unless_harness:
        q += f" --redo-unless-harness {shlex.quote(args.redo_unless_harness)}"
    if args.rederive:
        q += " --rederive"
        if args.redo_unless_harness and not args.since:
            sys.exit("tt-vga: --rederive --redo-unless-harness needs --since ISO-TIMESTAMP, the start of the "
                     "re-derive campaign (reuse the same value when restarting it)")
    if args.since:
        q += f" --since {shlex.quote(args.since)}"
    if args.allow_no_linger:
        q += " --allow-no-linger"
    if args.drop_tb_v1 and not args.yes_drop_tb_v1:
        sys.exit("tt-vga: --drop-tb-v1 retires tb-v1 for every selected project: add --yes-drop-tb-v1 to confirm")
    if args.tb_v1:
        q += " --tb-v1"
    if args.drop_tb_v1:
        q += " --drop-tb-v1"
    if args.scope_memory:
        q += f" --scope-memory {shlex.quote(args.scope_memory)}"
    if args.scope_cpu:
        q += f" --scope-cpu {shlex.quote(args.scope_cpu)}"
    return q


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------

def host_check(args: argparse.Namespace) -> int:
    host = resolve_host(args.host)
    tools = tomllib.loads(TOOLS_TOML.read_text())
    script = f"""
set -e
echo "user: $(whoami)  host: $(hostname)"
echo "cores: $(nproc)  load: $(cut -d' ' -f1-3 /proc/loadavg)"
free -g | awk '/Mem:/ {{print "memory GB: total " $2 ", available " $7}}'
df -h ~ | awk 'NR==2 {{print "disk: " $4 " free of " $2}}'
for t in tmux git g++ make python3; do printf "%s: " $t; command -v $t || echo MISSING; done
printf "cmake: "; if command -v cmake > /dev/null; then cmake --version | head -1; else echo MISSING; fi
R=~/{REMOTE_ROOT}
[ -x $R/tools/uv/uv ] && $R/tools/uv/uv --version || echo "uv: not bootstrapped"
if [ -x $R/tools/uv/uv ] && P=$({uv_env(runtime=True)} $R/tools/uv/uv python find {tools['python']['version']}); then echo "python {tools['python']['version']}: $P"; else echo "python {tools['python']['version']}: MISSING"; fi
if [ -f $R/tools/vgacap-build/PINNED ]; then echo "vgacap pin built: $(cat $R/tools/vgacap-build/PINNED)  (want {tools['vgacap']['commit']})"; else echo "vgacap pin built: none  (want {tools['vgacap']['commit']})"; fi
L=$(loginctl show-user $(whoami) -p Linger 2>&1) || true; echo "${{L:-loginctl: no output}}"
[ -f $R/host.toml ] && echo "host.toml: present" || echo "host.toml: missing"
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
    script = bootstrap_script(tools)
    rsync(host, [str(HARNESS_DIR / "tracetool.c")], f"{REMOTE_ROOT}/tools/")
    return ssh(host, script, check=False, timeout=3600).returncode


def push_harness(host: Host) -> int:
    """Copy the harness, targets and compiled overrides to the host. Returns overrides sent."""
    from ttvga.overrides import COMPILED_DIR, compile_all

    n = compile_all()
    rsync(host, [str(HARNESS_DIR) + "/", str(TARGETS_JSON)], f"{REMOTE_ROOT}/harness/", delete=True,
          extra=["--exclude", "__pycache__"])
    rsync(host, [str(COMPILED_DIR) + "/"], f"{REMOTE_ROOT}/overrides/", delete=True)
    ssh(host, f"echo {shlex.quote(harness_version())} > ~/{REMOTE_ROOT}/harness/HARNESS_VERSION")
    return n


def sync(args: argparse.Namespace) -> int:
    """Copy the harness, targets and compiled overrides to the host."""
    host = resolve_host(args.host)
    n = push_harness(host)
    print(f"synced harness, targets and {n} overrides to {host.ssh}:{REMOTE_ROOT}/")
    return 0


def queue(args: argparse.Namespace) -> int:
    """Start, stop or inspect the job queue, which runs inside a tmux session on the host."""
    host = resolve_host(args.host)
    if args.action == "start":
        # The host keeps whatever harness it was last given, and a run says
        # nothing about which one it used. A fix committed here but never sent
        # cost a clip its correct audio rate, and the file played perfectly, so
        # nothing downstream noticed. Send it every time instead: the queue
        # refuses to start while another is running, so this cannot disturb one.
        if not args.no_sync:
            n = push_harness(host)
            print(f"synced harness, targets and {n} overrides before starting")
        q = queue_command(args, host, tomllib.loads(TOOLS_TOML.read_text()))
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


def rerender(args: argparse.Namespace) -> int:
    """Rebuild the published clips and previews on the host, migrating any old AVIs."""
    host = resolve_host(args.host)
    cmd = (f"{host_python(tomllib.loads(TOOLS_TOML.read_text()))} ~/{REMOTE_ROOT}/harness/rerender.py --videos ~/{REMOTE_VIDEOS} "
           f"--root ~/{REMOTE_ROOT} --jobs {args.jobs or host.jobs}")
    if args.only:
        cmd += f" --only {shlex.quote(args.only)}"
    if args.drop_legacy:
        cmd += " --drop-legacy"
    if args.previews_only:
        cmd += " --previews-only"
    if args.rewrite_webm:
        cmd += " --rewrite-webm"
    if args.background:
        script = f"""
set -e
if tmux has-session -t ttvga-rerender 2>/dev/null; then echo "rerender already running"; exit 1; fi
tmux new-session -d -s ttvga-rerender {shlex.quote(cmd + f" > ~/{REMOTE_ROOT}/rerender.log 2>&1; echo RERENDER-DONE >> ~/{REMOTE_ROOT}/rerender.log")}
echo "started in tmux session ttvga-rerender; watch ~/{REMOTE_ROOT}/rerender.log"
"""
        return ssh(host, script, check=False).returncode
    return ssh(host, cmd, check=False, timeout=14400).returncode


def verify(args: argparse.Namespace) -> int:
    """Check on the host that what is published is complete and playable."""
    host = resolve_host(args.host)
    cmd = (f"{host_python(tomllib.loads(TOOLS_TOML.read_text()))} ~/{REMOTE_ROOT}/harness/verify.py --videos ~/{REMOTE_VIDEOS} "
           f"--root ~/{REMOTE_ROOT} --decode {args.decode}")
    return ssh(host, cmd, check=False, timeout=7200).returncode


def collect(args: argparse.Namespace) -> int:
    """Pull every result.json (and timing.json) from the host into data/results/."""
    host = resolve_host(args.host)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    rsync_from(host, f"{REMOTE_ROOT}/work/", RESULTS_DIR,
               extra=["--include", "*/", "--include", "result.json", "--exclude", "*", "--prune-empty-dirs"])
    # The per-frame hashes move out of result.json into frame_hashes.txt beside it.
    for path in RESULTS_DIR.glob("*/*/result.json"):
        framehashes.export(path)
    if args.images:
        dest = Path(args.images)
        rsync_from(host, f"{REMOTE_VIDEOS}/", dest,
                   extra=["--include", "*/", "--include", "poster.png", "--include", "contact.png",
                          "--exclude", "*", "--prune-empty-dirs"])
    n = sum(1 for _ in RESULTS_DIR.glob("*/*/result.json"))
    print(f"collected {n} results into {RESULTS_DIR}")
    return 0


# Files the published tree still holds from before the clips became
# browser-playable. They are superseded, no browser will play motion JPEG in an
# AVI, and a mirror that cannot unpublish must not carry them.
SUPERSEDED = ("60s.avi", "30s.avi", "10s.avi", "poster.png", "contact.png", "preview.gif",
              "rerender.log")


def mirror(args: argparse.Namespace) -> int:
    """Copy the published clips into a directory that is itself published onwards.

    Both sides live on the simulation host, so the copy runs there and nothing
    crosses the network twice. It usually needs a different account from the one
    that runs the simulations, because the destination belongs to whoever owns
    the onward publishing; `--as-user` says which.

    Nothing about the destination is recorded in the repository: pass `--dest`.
    """
    host = resolve_host(args.host)
    ssh_host = f"{args.as_user}@{host.ssh.split('@', 1)[1]}" if args.as_user else host.ssh
    dest = args.dest.rstrip("/")
    src = f"/home/{host.user}/{REMOTE_VIDEOS}/"
    excludes = "".join(f" --exclude {shlex.quote(name)}" for name in SUPERSEDED)
    # No --delete: a mirror of this kind is usually append-only downstream, and
    # deleting here would not unpublish there anyway.
    script = f"""
set -e
if [ ! -d {shlex.quote(src)} ]; then echo "no published tree at {src}"; exit 1; fi
mkdir -p {shlex.quote(dest)}
rsync -a --mkpath{excludes} {'--dry-run --stats' if args.dry_run else ''} \\
    {shlex.quote(src)} {shlex.quote(dest)}/
echo "---"
echo "clips:    $(find {shlex.quote(dest)} -name '*.mp4' -o -name '*.webm' | wc -l)"
echo "previews: $(find {shlex.quote(dest)} -name '*.png' -o -name '*.gif' | wc -l)"
echo "index:    $(ls {shlex.quote(dest)}/index.html {shlex.quote(dest)}/index.json 2>&1 | tr '\\n' ' ')"
du -sh {shlex.quote(dest)}
"""
    ssh_cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20"]
    if args.as_user is None and host.key:
        ssh_cmd += ["-o", "IdentitiesOnly=yes", "-i", os.path.expanduser(host.key)]
    print(f"mirroring {src} to {ssh_host}:{dest}/" + (" (dry run)" if args.dry_run else ""))
    return subprocess.run(ssh_cmd + [ssh_host, "bash", "-s"], input=script, text=True).returncode


class _RefuseTestHooks(argparse.Action):
    """`tt-vga queue --test-hooks` exits 2: only job.py's own tests build tb.cpp's test hooks."""

    def __call__(self, parser, namespace, values, option_string=None):
        parser.error("--test-hooks is for job.py's own tests: the queue never builds tb.cpp's test hooks")


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
    redo = p.add_mutually_exclusive_group()
    redo.add_argument("--redo", action="store_true")
    redo.add_argument("--redo-unless-harness", metavar="VERSION",
                      help="rerun unless the project's result already comes from this HARNESS_VERSION")
    p.add_argument("--rederive", action="store_true",
                   help="derive the published traces again instead of simulating (job.py --rederive)")
    p.add_argument("--since", metavar="ISO-TIMESTAMP",
                   help="with --rederive --redo-unless-harness: when this re-derive campaign started")
    p.add_argument("--allow-no-linger", action="store_true",
                   help="start the queue even though the host user has no linger")
    tb = p.add_mutually_exclusive_group()
    tb.add_argument("--tb-v1", action="store_true", help="also run the legacy tb-v1 sampler in every job")
    tb.add_argument("--drop-tb-v1", action="store_true",
                    help="retire tb-v1 in every selected project (needs --yes-drop-tb-v1)")
    p.add_argument("--yes-drop-tb-v1", action="store_true", help="confirm --drop-tb-v1")
    p.add_argument("--scope-memory", help="each job scope's MemoryMax (runqueue's default 6G)")
    p.add_argument("--scope-cpu", help="each job scope's CPUQuota (runqueue's default 200%%)")
    p.add_argument("--test-hooks", action=_RefuseTestHooks, nargs=0, help=argparse.SUPPRESS)
    p.add_argument("--seconds", type=float, default=60.0)
    p.add_argument("--timeout", type=float, default=1800.0)
    p.add_argument("--no-sync", action="store_true",
                   help="start without first sending this repository's harness to the host")
    p.add_argument("--lines", type=int, default=20, help="log lines to show for status")
    p.set_defaults(func=queue)
    p = sub.add_parser("rerender", help="rebuild the clips and previews on the host (also migrates old AVIs)")
    common(p)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--only", default="", help="comma separated shuttles or <shuttle>/<macro> ids")
    p.add_argument("--background", action="store_true", help="run in a tmux session instead of waiting")
    p.add_argument("--drop-legacy", action="store_true",
                   help="delete the superseded AVIs and unprefixed previews once the clips are written")
    p.add_argument("--previews-only", action="store_true", help="re-render previews without transcoding")
    p.add_argument("--rewrite-webm", action="store_true",
                   help="rebuild the WebM clips from the published MP4")
    p.set_defaults(func=rerender)
    p = sub.add_parser("verify", help="check the published clips are complete and playable")
    common(p)
    p.add_argument("--decode", type=int, default=40,
                   help="how many projects to decode in full (0 to skip)")
    p.set_defaults(func=verify)
    p = sub.add_parser("collect", help="pull result.json files into data/results/")
    common(p)
    p.add_argument("--images", help="also pull poster and contact images into this local directory")
    p.set_defaults(func=collect)
    p = sub.add_parser("mirror", help="copy the published clips into a directory published onwards")
    common(p)
    p.add_argument("--dest", required=True,
                   help="destination directory on the host (not recorded in this repository)")
    p.add_argument("--as-user", help="account on the host to run the copy as, if not the simulation user")
    p.add_argument("--dry-run", action="store_true", help="list what would be copied and stop")
    p.set_defaults(func=mirror)
