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
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from ttvga import HARNESS_DIR, RESULTS_DIR, ROOT, TARGETS_JSON
from ttvga.harness import hostconf
from ttvga.harness import verify as harness_verify

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
    """Check on the host that what is published is complete and playable.

    With `--server-stale URL`, list instead what the server at URL holds that the
    host's archive no longer has (verify.py's `stale_on_server`). Nothing is deleted.
    """
    host = resolve_host(args.host)
    cmd = (f"{host_python(tomllib.loads(TOOLS_TOML.read_text()))} ~/{REMOTE_ROOT}/harness/verify.py --videos ~/{REMOTE_VIDEOS} "
           f"--root ~/{REMOTE_ROOT} --decode {args.decode}")
    if args.server_stale:
        cmd += f" --server-stale {shlex.quote(args.server_stale)}"
    return ssh(host, cmd, check=False, timeout=7200).returncode


def collect(args: argparse.Namespace) -> int:
    """Bring each new result.json and its frames/ files from the host into data/results/.

    See `collect_filter` for what is taken and `remove_stale_frames` for what is removed.
    """
    host = resolve_host(args.host)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    found = host_listing(host)
    pulled = pull_results(f"{host.ssh}:{REMOTE_ROOT}/work/", RESULTS_DIR, found, host.ssh_cmd())
    for path in pulled.removed:
        print(f"removed {path.relative_to(RESULTS_DIR)} (not on the host)")
    if args.images:
        dest = Path(args.images)
        rsync_from(host, f"{REMOTE_VIDEOS}/", dest,
                   extra=["--include", "*/", "--include", "poster.png", "--include", "contact.png",
                          "--exclude", "*", "--prune-empty-dirs"])
    for e in found.errors:
        print(f"tt-vga collect: error: {_shown(e.get('id'))}: result.json does not parse: {_shown(e.get('error'))}",
              file=sys.stderr)
    for path in pulled.rejected:
        rel = path.relative_to(RESULTS_DIR).as_posix()
        done = "left in place (tb-v1: Ruling Z)" if _is_tb_v1(rel) else "deleted"
        print(f"tt-vga collect: error: {_shown(rel)} is a symlink or other non-regular file: {done}",
              file=sys.stderr)
    for x in pulled.oversized:
        kept = "local copy deleted" if _is_centre(x) else "local copy kept, it is stale"
        print(f"tt-vga collect: error: {_shown(x)} is over {MAX_SIZE} on the host: not collected, {kept}",
              file=sys.stderr)
    for x in pulled.changed:
        print(f"tt-vga collect: warning: {_shown(x)} changed or went on the host during collect: "
              "run collect again", file=sys.stderr)
    print(f"collected {len(_collected_ids(found))} new results into {RESULTS_DIR}")
    return 1 if found.errors or pulled.rejected or pulled.oversized else 0


# ---------------------------------------------------------------------------
# collect's pieces
# ---------------------------------------------------------------------------

LISTING_MARK = "--- frames"
TESTPATTERNS = "testpatterns"   # job.py's pseudo-shuttle, never published or committed
# The largest frames/ file collect takes. The largest real one is about
# 0.7 MB (7,159 frames, tt_um_spacewar's run, if every frame were distinct;
# its FNV file is 122,166 bytes), so 16 MiB is over 20 times that.
MAX_SIZE = "16M"
MAX_BYTES = 16 * 1024 * 1024    # rsync's 16M, checked against the listing's sizes first
# Every path that leaves the host is made of these bytes only (find -regex on the
# host, and _NAME again here).
_NAME = re.compile(r"[A-Za-z0-9_./-]+")
_ID = re.compile(r"[A-Za-z0-9_]+/[A-Za-z0-9_]+")
# The only frames/ files that come into git (WORK_FRAMES in job.py). Never
# tb-v1/TRACE_SHA256: the trace's SHA-256 stays out of git.
_FRAMES = (re.compile(r"[A-Za-z0-9_]+/[A-Za-z0-9_]+/frames/(centre-v1|tb-v1)/frames\.txt"),
           re.compile(r"[A-Za-z0-9_]+/[A-Za-z0-9_]+/frames/tb-v1/frame_hashes\.fnv1a64-tb2026-rgb888\.txt"))
_SAMPLERS = ("centre-v1", "tb-v1")


def _shown(text, limit: int = 200) -> str:
    """Host-supplied text for a message: repr, so control characters show, and cut to `limit`."""
    r = repr(text)
    return r if len(r) <= limit else r[:limit] + "..."


@dataclass
class HostListing:
    new_results: set[str]                 # ids whose host result.json has a `harness` key
    frames_files: dict[str, set[str]]     # id -> `<s>/<m>/frames/<sampler>/<file>` paths on the host
    dropped: set[str]                     # ids whose host result.json has `tb_v1.dropped`
    errors: list[dict] = field(default_factory=list)   # list_results.py's `{"id", "error"}` lines
    sizes: dict[str, int] = field(default_factory=dict)  # path -> bytes on the host, when listed


@dataclass
class Pulled:
    removed: list[Path]     # local frames/ files the host no longer has (remove_stale_frames)
    rejected: list[Path]    # collected paths that were not regular files afterwards, deleted
    oversized: list[str] = field(default_factory=list)  # listed over MAX_BYTES: not copied
    changed: list[str] = field(default_factory=list)    # not the listed size afterwards (changed or gone)


def listing_script(python: str, work: str, list_results: str) -> str:
    """The one script that lists the host's results (JSON lines), then LISTING_MARK, then its frames/ files.

    The results come first, so a job finishing in between can add frames/ files
    but never a result whose frames were missed. Each frames/ entry is
    `<size> <path>` and NUL terminated. Only paths made of `[A-Za-z0-9_./-]`
    are listed (`-regex` in the C locale), so no other byte leaves the host.
    """
    return f"""
set -e
{python} {list_results} {work}
echo {shlex.quote(LISTING_MARK)}
cd {work}
LC_ALL=C find . -mindepth 5 -maxdepth 5 -regextype posix-extended -regex '\\./[A-Za-z0-9_./-]+' \\
    -path '*/*/*/frames/*/*' -type f -printf '%s %P\\0'
"""


def parse_listing(text: str) -> HostListing:
    """Turn `listing_script`'s output into a HostListing. A missing LISTING_MARK is an error.

    Every path is checked against `_NAME` again here, and anything else dropped.
    """
    at = ("\n" + text).find(f"\n{LISTING_MARK}\n")
    if at < 0:
        raise RuntimeError(f"tt-vga collect: host listing has no {LISTING_MARK!r} line: the frames were not listed")
    head, tail = text[:at], text[at + len(LISTING_MARK) + 1:]
    found = HostListing(set(), {}, set())
    for line in head.splitlines():
        if not line:
            continue
        e = json.loads(line)
        if "error" in e:
            found.errors.append(e)
            continue
        if e["harness"] and _ID.fullmatch(e["id"]):
            found.new_results.add(e["id"])
            if e["dropped"]:
                found.dropped.add(e["id"])
            if isinstance(e.get("size"), int):
                found.sizes[f"{e['id']}/result.json"] = e["size"]
    for entry in tail.split("\0"):
        size, _, path = entry.partition(" ")
        if size.isdigit() and _NAME.fullmatch(path):
            found.frames_files.setdefault("/".join(path.split("/")[:2]), set()).add(path)
            found.sizes[path] = int(size)
    return found


def host_listing(host: Host) -> HostListing:
    """List the host's work tree in one SSH step (`listing_script`, with list_results.py sent first)."""
    tools = tomllib.loads(TOOLS_TOML.read_text())
    rsync(host, [str(HARNESS_DIR / "list_results.py")], f"{REMOTE_ROOT}/tools/")
    script = listing_script(host_python(tools), f"~/{REMOTE_ROOT}/work", f"~/{REMOTE_ROOT}/tools/list_results.py")
    return run_listing(host.ssh_cmd() + [host.ssh, "bash", "-s"], script)


def run_listing(cmd: list[str], script: str) -> HostListing:
    """Run `listing_script` through `cmd` (ssh ... bash -s) and parse it.

    Bytes, not text: the host's file names are not trusted to be UTF-8.
    """
    p = subprocess.run(cmd, input=script.encode(), capture_output=True, timeout=600)
    sys.stderr.write(p.stderr.decode(errors="backslashreplace"))
    if p.returncode != 0:
        raise RuntimeError(f"tt-vga collect: listing the host's work tree failed (exit {p.returncode})")
    return parse_listing(p.stdout.decode(errors="surrogateescape"))


def _testpatterns(ids: set[str]) -> set[str]:
    return {i for i in ids if i.split("/", 1)[0] == TESTPATTERNS}


def _collected_ids(listing: HostListing) -> set[str]:
    return {i for i in listing.new_results - _testpatterns(listing.new_results) if _ID.fullmatch(i)}


def collect_filter(listing: HostListing) -> list[str]:
    """The paths, relative to the host's work/, that collect copies (rsync's `--files-from`), sorted.

    - `<id>/result.json` only for ids in `new_results`: a host result.json from
      the old pipeline (full hash list, no `tb_v1`) never replaces a converted one;
    - the frames/ files of those ids that match `_FRAMES` exactly;
    - never testpatterns, `scratch/`, `kept/`, `repo/` or `build/`.
    """
    ids = _collected_ids(listing)
    paths = {f"{i}/result.json" for i in ids}
    for i in ids:
        paths |= {p for p in listing.frames_files.get(i, ()) if any(r.fullmatch(p) for r in _FRAMES)}
    return sorted(paths)


def _is_tb_v1(rel: str) -> bool:
    """Whether a path relative to data/results/ is under some `frames/tb-v1/`."""
    parts = rel.split("/")
    return any(a == "frames" and b == "tb-v1" for a, b in zip(parts, parts[1:]))


def _is_centre(rel: str) -> bool:
    return bool(_FRAMES[0].fullmatch(rel)) and rel.split("/")[3] == "centre-v1"


def _discard(results: Path, dest: Path) -> None:
    """Delete one collected path that is not tb-v1. The only deletion outside remove_stale_frames.

    Ruling Z: nothing under `frames/tb-v1/` is ever deleted except by
    remove_stale_frames, for an id whose parsed host result has `tb_v1.dropped`.
    """
    if _is_tb_v1(dest.relative_to(results).as_posix()):
        raise RuntimeError(f"tt-vga collect: refusing to delete {dest}: tb-v1 files go only through "
                           "remove_stale_frames (Ruling Z)")
    if dest.is_dir() and not dest.is_symlink():
        shutil.rmtree(dest)
    else:
        dest.unlink()


def remove_stale_frames(results: Path, listing: HostListing) -> list[Path]:
    """Delete the local frames/ files of new results that the host no longer has. Returns them.

    centre-v1 follows the host. tb-v1 is removed only for ids in `dropped`
    (Ruling Z): a default run has no tb-v1 on the host, and the converted file stays.
    A symlinked directory on the way is never followed.
    """
    have = set(collect_filter(listing))
    removed = []
    for i in sorted(_collected_ids(listing)):
        for sampler in _SAMPLERS:
            if sampler == "tb-v1" and i not in listing.dropped:
                continue
            d = results / i / "frames" / sampler
            if any(x.is_symlink() for x in (results / i, d.parent, d)) or not d.is_dir():
                continue
            for f in sorted(d.rglob("*")):
                if (f.is_file() or f.is_symlink()) and f.relative_to(results).as_posix() not in have:
                    f.unlink()
                    removed.append(f)
            for sub in sorted((p for p in d.rglob("*") if p.is_dir() and not p.is_symlink()), reverse=True) + [d, d.parent]:
                if sub.is_dir() and not any(sub.iterdir()):
                    sub.rmdir()
    return removed


def pull_results(source: str, results: Path, listing: HostListing, ssh_cmd: list[str] | None) -> Pulled:
    """Copy `collect_filter`'s paths from `source` (`host:ttvga/work/`, or a local directory) into
    `results`, then `remove_stale_frames`.

    The host is not trusted: symlinks and devices are not copied (`--no-links
    --no-D`). A file listed over MAX_BYTES is not copied and returned in
    `oversized`; rsync's `--max-size` covers one that grows after the listing,
    and any path not at its listed size afterwards is returned in `changed`.
    A collected path that is not a regular file afterwards is returned in
    `rejected`, and deleted unless it is tb-v1. A listed
    file that has gone by the time rsync looks (a job started and removed its
    result.json) is skipped with `--ignore-missing-args`; every other rsync
    error still stops collect.
    """
    listed = collect_filter(listing)
    oversized = [x for x in listed if listing.sizes.get(x, 0) > MAX_BYTES]
    paths = [x for x in listed if x not in oversized]
    rejected, changed = [], []
    for x in oversized:
        # A centre-v1 file follows the host, so the old copy goes. A result.json or
        # a tb-v1 file (Ruling Z, even for a dropped id) is kept and reported.
        dest = results / x
        if _is_centre(x) and (dest.is_file() or dest.is_symlink()):
            _discard(results, dest)
    if paths:
        cmd = ["rsync", "-a", "--no-links", "--no-D", f"--max-size={MAX_SIZE}", "--ignore-missing-args",
               "--from0", "--files-from=-"]
        if ssh_cmd:
            cmd += ["-e", " ".join(shlex.quote(c) for c in ssh_cmd)]
        cmd += [source, str(results)]
        p = subprocess.run(cmd, input="".join(f"{x}\0" for x in paths), text=True)
        # 24: a file vanished while copying (a job on the host replaced it); the rest came across.
        if p.returncode not in (0, 24):
            raise subprocess.CalledProcessError(p.returncode, cmd)
        for x in paths:
            dest = results / x
            if dest.is_symlink() or (dest.exists() and not dest.is_file()):
                if not _is_tb_v1(x):
                    _discard(results, dest)
                rejected.append(dest)
            elif x in listing.sizes and not (dest.is_file() and dest.stat().st_size == listing.sizes[x]):
                # Grown past MAX_SIZE (rsync skipped it), replaced, or gone since the listing.
                changed.append(x)
    return Pulled(remove_stale_frames(results, listing), rejected, oversized, changed)


# Files the published tree still holds from before the clips became
# browser-playable. They are superseded, no browser will play motion JPEG in an
# AVI, and a mirror that cannot unpublish must not carry them.
SUPERSEDED = ("60s.avi", "30s.avi", "10s.avi", "poster.png", "contact.png", "preview.gif",
              "rerender.log")


def mirror_excludes() -> list[str]:
    """rsync's anchored excludes: the FPGA session's files (verify.FOREIGN_PATTERNS) and the frames subtree."""
    return ["/" + p for p in harness_verify.FOREIGN_PATTERNS] + ["/frames/"]


def mirror_script(src: str, dest: str, dry_run: bool) -> str:
    """The script, run on the host, that copies the published clips in `src` into the archive `dest`.

    Never `--delete`: the archive is append-only downstream. It never writes over
    the FPGA session's files or the frames subtree (`mirror_excludes`), and it
    refuses a `dest` that holds the frames subtree's marker, `.ttvga-frames-root`.
    """
    excludes = "".join(f" --exclude {shlex.quote(name)}" for name in SUPERSEDED)
    excludes += "".join(f" --exclude {shlex.quote(p)}" for p in mirror_excludes())
    q_src, q_dest = shlex.quote(src), shlex.quote(dest)
    marker = shlex.quote(f"{dest}/{hostconf.ROOT_MARKER}")
    return f"""
set -e
if [ ! -d {q_src} ]; then echo "no published tree at {src}"; exit 1; fi
if [ -e {marker} ] || [ -L {marker} ]; then
  echo "refusing to mirror into {dest}: it holds {hostconf.ROOT_MARKER}, so it is the frames subtree, not the archive"
  exit 1
fi
mkdir -p {q_dest}
rsync -a --mkpath{excludes} {'--dry-run --stats' if dry_run else ''} \\
    {q_src} {q_dest}/
echo "---"
echo "clips:    $(find {q_dest} -name '*.mp4' -o -name '*.webm' | wc -l)"
echo "previews: $(find {q_dest} -name '*.png' -o -name '*.gif' | wc -l)"
echo "index:    $(ls {q_dest}/index.html {q_dest}/index.json 2>&1 | tr '\\n' ' ')"
du -sh {q_dest}
"""


# Only paths of this shape give an id; the host's file names are not trusted.
_FPGA_BIN = re.compile(r"[a-z0-9]+/tt_um_[A-Za-z0-9_]+/[^/]+\.bin")


def fpga_ids_script(dest: str) -> str:
    """The script that lists the archive's bitstreams, `<shuttle>/<macro>/<file>.bin`, NUL terminated."""
    return f"""
set -e
LC_ALL=C find {shlex.quote(dest)} -mindepth 3 -maxdepth 3 -name '*.bin' -printf '%P\\0'
"""


def parse_fpga_ids(raw: bytes) -> tuple[list[str], list[str]]:
    """(sorted unique `<shuttle>/<macro>` ids, dropped paths) from `fpga_ids_script`'s output.

    Bytes, decoded with surrogateescape: the names are not trusted to be UTF-8.
    A path that is not exactly `_FPGA_BIN` gives no id and is returned in `dropped`.
    """
    ids, dropped = set(), []
    for path in raw.decode("utf-8", errors="surrogateescape").split("\0"):
        if not path:
            continue
        if _FPGA_BIN.fullmatch(path):
            ids.add("/".join(path.split("/")[:2]))
        else:
            dropped.append(path)
    return sorted(ids), dropped


def write_fpga_ids(ssh_cmd: list[str], dest: str, out: Path) -> int:
    """Run `fpga_ids_script` through `ssh_cmd` and write the ids to `out`, one per line. Logs every path."""
    p = subprocess.run(ssh_cmd + ["bash", "-s"], input=fpga_ids_script(dest).encode(), capture_output=True,
                       timeout=600)
    sys.stderr.write(p.stderr.decode(errors="backslashreplace"))
    if p.returncode != 0:
        print(f"tt-vga mirror: listing the bitstreams under {dest} failed (exit {p.returncode})", file=sys.stderr)
        return 1
    ids, dropped = parse_fpga_ids(p.stdout)
    for path in p.stdout.decode("utf-8", errors="surrogateescape").split("\0"):
        if path:
            print(f"bitstream: {_shown(path)}")
    for path in dropped:
        print(f"tt-vga mirror: warning: {_shown(path)} is not <shuttle>/tt_um_<macro>/<file>.bin: no id taken",
              file=sys.stderr)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(f"{i}\n" for i in ids))
    print(f"{len(ids)} projects with a bitstream -> {out}")
    return 0


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
    # No --delete: a mirror of this kind is usually append-only downstream, and
    # deleting here would not unpublish there anyway.
    script = mirror_script(src, dest, args.dry_run)
    ssh_cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20"]
    if args.as_user is None and host.key:
        ssh_cmd += ["-o", "IdentitiesOnly=yes", "-i", os.path.expanduser(host.key)]
    print(f"mirroring {src} to {ssh_host}:{dest}/" + (" (dry run)" if args.dry_run else ""))
    rc = subprocess.run(ssh_cmd + [ssh_host, "bash", "-s"], input=script, text=True).returncode
    if rc != 0 or not args.fpga_ids_out:
        return rc
    return write_fpga_ids(ssh_cmd + [ssh_host], dest, Path(args.fpga_ids_out))


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
    p.add_argument("--server-stale", metavar="URL",
                   help="instead, list what the server at URL has that the archive no longer has (deletes nothing)")
    p.set_defaults(func=verify)
    p = sub.add_parser("collect", help="pull new result.json and frames/ files into data/results/")
    common(p)
    p.add_argument("--images", help="also pull poster and contact images into this local directory")
    p.set_defaults(func=collect)
    p = sub.add_parser("mirror", help="copy the published clips into a directory published onwards")
    common(p)
    p.add_argument("--dest", required=True,
                   help="destination directory on the host (not recorded in this repository)")
    p.add_argument("--as-user", help="account on the host to run the copy as, if not the simulation user")
    p.add_argument("--dry-run", action="store_true", help="list what would be copied and stop")
    p.add_argument("--fpga-ids-out", metavar="FILE",
                   help="also write the <shuttle>/<macro> ids that have a bitstream in --dest (for tt-vga index --fpga-ids)")
    p.set_defaults(func=mirror)
