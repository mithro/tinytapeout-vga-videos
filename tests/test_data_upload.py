# SPDX-License-Identifier: Apache-2.0
"""host/data-upload: the main upload's frames exclusion and data-upload-frames-sync.

Every test renders the templates with sandbox values (all paths under tmp_path)
and runs the rendered scripts as the host would: data-upload-sync with /bin/sh,
data-upload-frames-sync through its own #!/usr/bin/python3, so the host's system
Python is the one exercised.  `rsync` on PATH is tests/data_upload_fake_rsync.py,
which records each call and runs the real rsync into a local directory that
stands for the write-only server.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

from ttvga import HARNESS_DIR

REPO = Path(__file__).resolve().parent.parent
HOST_DIR = REPO / "host" / "data-upload"
FAKE_RSYNC = Path(__file__).resolve().parent / "data_upload_fake_rsync.py"
SUBTREE = "tinytapeout-vga-videos/frames"
REMOTE = "acct@dest.invalid:/"
REAL_RSYNC = shutil.which("rsync")

pytestmark = pytest.mark.skipif(REAL_RSYNC is None, reason="needs rsync")


def _load(name: str, path: Path):
    # The installed scripts have no .py suffix, so name the loader explicitly.
    spec = importlib.util.spec_from_file_location(name, path, loader=SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


render = _load("data_upload_render", HOST_DIR / "render.py")


@dataclass
class Box:
    tmp: Path
    publish: Path      # the publish root as the scripts see it: a symlink, as on the host
    real: Path         # what it points at
    frames: Path       # <publish>/<SUBTREE>
    etc: Path
    state: Path        # the main upload's state dir
    fstate: Path       # the frames upload's state dir
    staging: Path
    dest: Path         # stands for the server
    rendered: Path
    record: Path
    env: dict

    @property
    def changed(self) -> Path:
        return self.staging / "changed.log"

    @property
    def offset_file(self) -> Path:
        return self.fstate / "offset"

    def project(self, pid: str, files=("a.txt",)) -> Path:
        d = self.frames / pid
        d.mkdir(parents=True)
        for f in files:
            (d / f).write_text(f"{pid} {f}\n")
        return d

    def calls(self) -> list[dict]:
        if not self.record.exists():
            return []
        return [json.loads(line) for line in self.record.read_text().splitlines()]

    def sent(self) -> list[str]:
        """Every path under the destination's frames subtree, relative to it."""
        root = self.dest / SUBTREE
        if not root.exists():
            return []
        return sorted(str(p.relative_to(root)) for p in root.rglob("*"))

    def frames_sync(self, *args, **env) -> subprocess.CompletedProcess:
        return subprocess.run([str(self.rendered / "data-upload-frames-sync"), *args],
                              env={**self.env, **env}, capture_output=True, text=True)

    def main_sync(self, **env) -> subprocess.CompletedProcess:
        return subprocess.run(["/bin/sh", str(self.rendered / "data-upload-sync")],
                              env={**self.env, **env}, capture_output=True, text=True)


def values(box_dirs: dict) -> dict:
    return {
        "HOST": "testhost",
        "PUBLISH_ROOT": str(box_dirs["publish"]),
        "PUBLIC_URL": "https://example.invalid/testhost",
        "DEST_ACCOUNT": "acct",
        "DEST_HOST": "dest.invalid",
        "DEST_DIR": "/srv/data/testhost",
        "PEER_JOB": "peer",
        "CONF_DIR": str(box_dirs["etc"]),
        "STATE_DIR": str(box_dirs["state"]),
        "FRAMES_STATE_DIR": str(box_dirs["fstate"]),
        "FRAMES_SUBTREE": SUBTREE,
        "STAGING_DIR": str(box_dirs["staging"]),
        "MOUNTS": "/",
    }


@pytest.fixture
def box(tmp_path: Path) -> Box:
    dirs = {name: tmp_path / name for name in ("real", "etc", "state", "fstate", "staging", "dest", "bin")}
    for d in dirs.values():
        d.mkdir()
    dirs["publish"] = tmp_path / "publish"
    dirs["publish"].symlink_to(dirs["real"])
    (dirs["real"] / "README.md").write_text("published\n")
    (dirs["real"] / "tinytapeout-vga-videos").mkdir()
    (dirs["real"] / "tinytapeout-vga-videos" / "index.html").write_text("<html></html>\n")
    frames = dirs["publish"] / SUBTREE
    frames.mkdir()
    (frames / ".ttvga-frames-root").write_bytes(b"")
    (dirs["etc"] / "exclusions").write_text("*.key\n")

    rendered = tmp_path / "rendered"
    render.render(values(dirs), rendered)
    shutil.copy(rendered / "frames.conf", dirs["etc"] / "frames.conf")

    record = tmp_path / "rsync-calls.jsonl"
    fake = dirs["bin"] / "rsync"
    fake.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE_RSYNC}" "$@"\n')
    fake.chmod(0o755)
    env = {
        "PATH": f"{dirs['bin']}:{os.environ['PATH']}",
        "LC_ALL": "C",
        "FAKE_RSYNC_REAL": REAL_RSYNC,
        "FAKE_RSYNC_RECORD": str(record),
        "FAKE_RSYNC_REMOTE": REMOTE,
        "FAKE_RSYNC_DEST": str(dirs["dest"]),
    }
    return Box(tmp_path, dirs["publish"], dirs["real"], frames, dirs["etc"], dirs["state"], dirs["fstate"],
               dirs["staging"], dirs["dest"], rendered, record, env)


def line(pid: str) -> str:
    return f"2026-11-27T01:02:03+00:00 {pid}\n"


# ---------------------------------------------------------------- render.py


def test_render_refuses_a_placeholder_without_value(tmp_path, box):
    v = values({"publish": box.publish, "etc": box.etc, "state": box.state, "fstate": box.fstate,
                "staging": box.staging})
    del v["DEST_HOST"]
    with pytest.raises(render.RenderError, match="DEST_HOST"):
        render.render(v, tmp_path / "out1")


def test_render_refuses_an_unused_value_and_an_unsafe_one(tmp_path, box):
    v = values({"publish": box.publish, "etc": box.etc, "state": box.state, "fstate": box.fstate,
                "staging": box.staging})
    with pytest.raises(render.RenderError, match="never used: EXTRA"):
        render.render({**v, "EXTRA": "x"}, tmp_path / "out2")
    with pytest.raises(render.RenderError, match="HOST"):
        render.render({**v, "HOST": 'a"; rm -rf /'}, tmp_path / "out3")


def test_rendered_files_hold_no_placeholder(box):
    for f in box.rendered.iterdir():
        assert "{{" not in f.read_text(), f.name
    assert os.access(box.rendered / "data-upload-frames-sync", os.X_OK)


# ---------------------------------------------------------- data-upload-sync


@pytest.mark.skipif(shutil.which("patch") is None, reason="needs patch")
def test_the_diff_is_the_template_against_the_live_script(tmp_path):
    """data-upload-sync.diff, reversed, applies exactly to the current template (it is not stale)."""
    copy = tmp_path / "data-upload-sync"
    shutil.copy(HOST_DIR / "data-upload-sync", copy)
    r = subprocess.run(["patch", "-R", "--dry-run", str(copy), str(HOST_DIR / "data-upload-sync.diff")],
                       capture_output=True, text=True)
    assert r.returncode == 0 and "FAILED" not in r.stdout and "fuzz" not in r.stdout, r.stdout + r.stderr


def test_main_upload_excludes_the_frames_subtree(box):
    box.project("tt06/tt_um_demo")
    r = box.main_sync()
    assert r.returncode == 0, r.stderr
    (call,) = box.calls()
    assert f"--exclude=/{SUBTREE}/" in call["argv"]
    assert not any(a.startswith("--delete") for a in call["argv"])
    assert f"(excluding /{SUBTREE}/)" in r.stdout
    assert (box.dest / "README.md").exists()
    assert (box.dest / "tinytapeout-vga-videos" / "index.html").exists()
    # Not even the empty subtree or its marker reaches the server.
    assert not (box.dest / SUBTREE).exists()


def test_main_upload_dry_run_adds_dry_run(box):
    r = box.main_sync(DATA_UPLOAD_DRY_RUN="1")
    assert r.returncode == 0, r.stderr
    (call,) = box.calls()
    assert "--dry-run" in call["argv"] and f"--exclude=/{SUBTREE}/" in call["argv"]
    assert not (box.dest / "README.md").exists()


def test_main_upload_fails_closed_without_frames_conf(box):
    (box.etc / "frames.conf").unlink()
    r = box.main_sync()
    assert r.returncode == 1
    assert "refusing to upload without the frames exclusion" in r.stderr
    assert box.calls() == []


@pytest.mark.parametrize("text", [
    "",                                            # no FRAMES_SUBTREE at all
    f"FRAMES_SUBTREE={SUBTREE}\nFRAMES_SUBTREE=x\n",  # twice
    "FRAMES_SUBTREE=\n",
    "FRAMES_SUBTREE=/abs/frames\n",
    "FRAMES_SUBTREE=frames/\n",
    "FRAMES_SUBTREE=a//b\n",
    "FRAMES_SUBTREE=a/../b\n",
    "FRAMES_SUBTREE=..\n",
    "FRAMES_SUBTREE=a/*\n",
    "FRAMES_SUBTREE=a b\n",
])
def test_main_upload_refuses_a_bad_frames_subtree(box, text):
    (box.etc / "frames.conf").write_text(text)
    r = box.main_sync()
    assert r.returncode == 1, r.stdout
    assert "refusing to run" in r.stderr
    assert box.calls() == []


# --------------------------------------------------- data-upload-frames-sync


def test_publish_py_lines_match_the_upload_regex(box):
    """changed.log as publish.py writes it (one os.write per line) is what the upload accepts."""
    sys.path.insert(0, str(HARNESS_DIR))
    import publish

    fd = os.open(box.changed, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        publish._append_changed(fd, None, "tt06", "tt_um_demo")
    finally:
        os.close(fd)
    frames_sync = _load("data_upload_frames_sync", box.rendered / "data-upload-frames-sync")
    (text,) = box.changed.read_text().splitlines()
    assert frames_sync.LINE_RE.match(text), text


def test_one_valid_line_is_sent_and_the_offset_stored(box):
    box.project("tt06/tt_um_demo")
    box.changed.write_text(line("tt06/tt_um_demo"))
    r = box.frames_sync()
    assert r.returncode == 0, r.stderr
    assert box.sent() == ["tt06", "tt06/tt_um_demo", "tt06/tt_um_demo/a.txt"]
    (call,) = box.calls()
    assert call["stdin"] == f"{SUBTREE}/tt06/tt_um_demo\n"
    assert box.offset_file.read_text() == f"{box.changed.stat().st_size}\n"
    assert "post-transfer re-check passed for 1 project(s)" in r.stderr
    # Nothing new: no rsync at all.
    r = box.frames_sync()
    assert r.returncode == 0 and len(box.calls()) == 1


def test_options_are_the_main_uploads_plus_the_frames_guards(box):
    box.project("tt06/tt_um_demo")
    box.changed.write_text(line("tt06/tt_um_demo"))
    assert box.main_sync().returncode == 0
    assert box.frames_sync().returncode == 0
    main, frames = (c["argv"] for c in box.calls())
    expected = [a for a in main if a != f"--exclude=/{SUBTREE}/"]
    expected = [f"--log-file={box.fstate}/rsync.log" if a.startswith("--log-file=") else a for a in expected]
    extras = ["-r", "--files-from=-", "--safe-links", "--no-implied-dirs"]
    assert frames == expected[:-3] + extras + expected[-3:]
    assert not any(a.startswith("--delete") for a in frames)


def test_invalid_lines_are_logged_and_skipped(box):
    box.project("tt06/tt_um_demo")
    bad = ["not a line\n", "2026-11-27T01:02:03+00:00 ../etc\n", "2026-11-27T01:02:03+00:00 tt06/x/y\n",
           "2026-11-27T01:02:03+00:00 tt.06/tt_um_demo\n", "2026-11-27T01:02:03+00:00 tt06/tt_um_demo \n",
           "2026-11-27T01:02:03+00:00 tt06/\xe9\n"]
    box.changed.write_text("".join(bad) + line("tt06/tt_um_demo"))
    r = box.frames_sync()
    assert r.returncode == 0, r.stderr
    assert r.stderr.count("skipping invalid changed.log line") == len(bad)
    assert box.calls()[0]["stdin"] == f"{SUBTREE}/tt06/tt_um_demo\n"
    assert box.offset_file.read_text() == f"{box.changed.stat().st_size}\n"


def test_only_invalid_lines_advance_the_offset_without_rsync(box):
    box.changed.write_text("garbage\n")
    r = box.frames_sync()
    assert r.returncode == 0, r.stderr
    assert box.calls() == []
    assert box.offset_file.read_text() == "8\n"


def test_partial_last_line_is_left_for_the_next_run(box):
    box.project("tt06/one")
    box.project("tt06/two")
    first = line("tt06/one")
    box.changed.write_text(first + "2026-11-27T01:02:03+00:00 tt06/tw")
    r = box.frames_sync()
    assert r.returncode == 0, r.stderr
    assert "partial last line" in r.stderr
    assert box.calls()[0]["stdin"] == f"{SUBTREE}/tt06/one\n"
    assert box.offset_file.read_text() == f"{len(first)}\n"
    with open(box.changed, "a") as f:
        f.write("o\n")
    r = box.frames_sync()
    assert r.returncode == 0, r.stderr
    assert box.calls()[1]["stdin"] == f"{SUBTREE}/tt06/two\n"
    assert box.offset_file.read_text() == f"{box.changed.stat().st_size}\n"


def test_symlinked_project_and_shuttle_are_refused(box):
    outside = box.tmp / "outside"
    (outside / "proj").mkdir(parents=True)
    (outside / "secret.txt").write_text("secret\n")
    (outside / "proj" / "secret.txt").write_text("secret\n")
    (box.frames / "test").mkdir()
    (box.frames / "test" / "link").symlink_to(outside)       # the brief's <frames>/test/link -> /etc
    (box.frames / "shlink").symlink_to(outside)               # a symlinked shuttle directory
    box.project("tt06/ok")
    box.changed.write_text(line("test/link") + line("shlink/proj") + line("tt06/ok"))
    r = box.frames_sync()
    assert r.returncode == 0, r.stderr
    assert "skipping test/link: project directory" in r.stderr and "is a symlink" in r.stderr
    assert "skipping shlink/proj: shuttle directory" in r.stderr
    assert box.calls()[0]["stdin"] == f"{SUBTREE}/tt06/ok\n"
    assert "secret" not in " ".join(box.sent())


def test_project_containing_a_symlink_is_refused_with_find_output(box):
    d = box.project("tt06/withlink")
    (d / "sub").mkdir()
    (d / "sub" / "evil").symlink_to("/etc/passwd")
    box.project("tt06/ok")
    box.changed.write_text(line("tt06/withlink") + line("tt06/ok"))
    r = box.frames_sync()
    assert r.returncode == 0, r.stderr
    assert "skipping tt06/withlink: find -P" in r.stderr
    assert f"{d}/sub/evil" in r.stderr                     # find's output, in full
    assert box.calls()[0]["stdin"] == f"{SUBTREE}/tt06/ok\n"
    assert not any("withlink" in p for p in box.sent())


def test_missing_project_is_skipped(box):
    box.changed.write_text(line("tt06/gone"))
    r = box.frames_sync()
    assert r.returncode == 0, r.stderr
    assert "skipping tt06/gone: shuttle directory" in r.stderr and "does not exist" in r.stderr
    assert box.calls() == []


def test_offset_past_the_end_restarts_from_zero(box):
    box.project("tt06/tt_um_demo")
    box.changed.write_text(line("tt06/tt_um_demo"))
    box.offset_file.write_text("100000\n")
    r = box.frames_sync()
    assert r.returncode == 0, r.stderr
    assert "past the end" in r.stderr and "starting from 0" in r.stderr
    assert box.calls()[0]["stdin"] == f"{SUBTREE}/tt06/tt_um_demo\n"
    assert box.offset_file.read_text() == f"{box.changed.stat().st_size}\n"


def test_a_corrupt_offset_is_fatal(box):
    box.changed.write_text(line("tt06/tt_um_demo"))
    box.offset_file.write_text("twelve\n")
    r = box.frames_sync()
    assert r.returncode == 1 and "not a byte offset" in r.stderr
    assert box.calls() == []


@pytest.mark.parametrize("rc, stored, exit_code", [(23, True, 0), (24, False, 0), (12, False, 12)])
def test_rsync_exit_code_decides_the_offset(box, rc, stored, exit_code):
    box.project("tt06/tt_um_demo")
    box.changed.write_text(line("tt06/tt_um_demo"))
    r = box.frames_sync(FAKE_RSYNC_RC=str(rc))
    assert r.returncode == exit_code, r.stderr
    assert f"rsync exit {rc}" in r.stderr
    if stored:
        assert box.offset_file.read_text() == f"{box.changed.stat().st_size}\n"
    else:
        assert not box.offset_file.exists()
        # Retried: the next run names the same project again.
        assert box.frames_sync().returncode == 0
        assert box.calls()[1]["stdin"] == f"{SUBTREE}/tt06/tt_um_demo\n"


def test_swap_during_transfer_is_caught_by_the_recheck(box):
    """The residual risk: a checked component swapped for a symlink before rsync opens it."""
    box.project("tt06/tt_um_demo")
    outside = box.tmp / "outside"
    (outside / "tt_um_demo").mkdir(parents=True)
    (outside / "tt_um_demo" / "stolen.txt").write_text("not for publishing\n")
    hook = f'mv "{box.frames}/tt06" "{box.tmp}/tt06.moved" && ln -s "{outside}" "{box.frames}/tt06"'
    box.changed.write_text(line("tt06/tt_um_demo"))
    r = box.frames_sync(FAKE_RSYNC_HOOK=hook)
    assert r.returncode == 1, r.stderr
    assert "realpath changed during transfer: tt06/tt_um_demo" in r.stderr
    # rsync did follow the swapped component: that is the risk the re-check reports.
    assert "tt06/tt_um_demo/stolen.txt" in box.sent()
    # rsync itself succeeded, so the offset is stored; the person reading the log deletes by hand.
    assert box.offset_file.read_text() == f"{box.changed.stat().st_size}\n"


def test_safe_links_drop_a_symlink_added_during_transfer(box):
    """A symlink that appears inside a project after the find check is not followed or sent as unsafe."""
    d = box.project("tt06/tt_um_demo")
    hook = f'ln -s /etc/passwd "{d}/late"'
    box.changed.write_text(line("tt06/tt_um_demo"))
    r = box.frames_sync(FAKE_RSYNC_HOOK=hook)
    assert r.returncode == 1                                   # the re-check sees the new symlink
    assert "realpath changed during transfer: tt06/tt_um_demo" in r.stderr
    assert not (box.dest / SUBTREE / "tt06/tt_um_demo/late").exists()


def test_dry_run_like_step_3(box):
    """The runbook's Step 3, in the sandbox: exactly the valid, symlink-free project is listed."""
    outside = box.tmp / "outside"
    outside.mkdir()
    (box.frames / "test").mkdir()
    (box.frames / "test" / "link").symlink_to(outside)
    box.project("test/t19_ok")
    d = box.project("test/t19_withlink")
    (d / "evil").symlink_to("/etc")
    box.changed.write_text("invalid line\n" + line("test/link") + line("test/t19_withlink")
                           + line("test/t19_ok") + "2026-11-27T01:02:03+00:00 test/t19_par")
    r = box.frames_sync(DATA_UPLOAD_DRY_RUN="1")
    assert r.returncode == 0, r.stderr
    (call,) = box.calls()
    assert "--dry-run" in call["argv"]
    assert call["stdin"] == f"{SUBTREE}/test/t19_ok\n"
    assert "post-transfer re-check passed for 1 project(s)" in r.stderr
    assert "dry run: offset not stored" in r.stderr
    assert not box.offset_file.exists()
    assert box.sent() == []


def test_full_sends_the_whole_subtree_and_keeps_the_offset(box):
    box.project("tt06/one")
    box.project("tt07/two")
    box.offset_file.write_text("7\n")
    r = box.frames_sync("--full")
    assert r.returncode == 0, r.stderr
    (call,) = box.calls()
    assert call["stdin"] == f"{SUBTREE}\n"
    assert {"tt06/one/a.txt", "tt07/two/a.txt", ".ttvga-frames-root"} <= set(box.sent())
    assert box.offset_file.read_text() == "7\n"


def test_full_does_not_follow_or_send_unsafe_symlinks(box):
    (box.frames / "evil").symlink_to("/etc")
    d = box.project("tt06/one")
    (d / "pw").symlink_to("/etc/passwd")
    r = box.frames_sync("--full")
    assert r.returncode == 0, r.stderr
    assert not os.path.lexists(box.dest / SUBTREE / "evil")
    assert not os.path.lexists(box.dest / SUBTREE / "tt06/one/pw")
    assert (box.dest / SUBTREE / "tt06/one/a.txt").exists()


def test_frames_root_must_be_real_and_marked(box):
    box.changed.write_text(line("tt06/tt_um_demo"))
    (box.frames / ".ttvga-frames-root").unlink()
    r = box.frames_sync()
    assert r.returncode == 1 and "has no .ttvga-frames-root marker" in r.stderr
    # A frames subtree that is itself a symlink to a marked directory elsewhere.
    elsewhere = box.tmp / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / ".ttvga-frames-root").write_bytes(b"")
    shutil.rmtree(box.frames)
    box.frames.symlink_to(elsewhere)
    r = box.frames_sync()
    assert r.returncode == 1 and "is not a directory (or is a symlink)" in r.stderr
    assert box.calls() == []


def test_missing_changed_log_is_nothing_to_do(box):
    r = box.frames_sync()
    assert r.returncode == 0 and "does not exist yet" in r.stderr
    assert box.calls() == []


def test_symlinked_changed_log_is_fatal(box):
    target = box.tmp / "other.log"
    target.write_text(line("tt06/tt_um_demo"))
    box.changed.symlink_to(target)
    r = box.frames_sync()
    assert r.returncode == 1 and "is a symlink" in r.stderr
    assert box.calls() == []


def test_bad_frames_conf_is_fatal(box):
    (box.etc / "frames.conf").write_text(f"FRAMES_SUBTREE={SUBTREE}\nSTAGING_DIR={box.staging}\nOTHER=1\n")
    r = box.frames_sync()
    assert r.returncode == 1 and "not a FRAMES_SUBTREE/STAGING_DIR=VALUE line" in r.stderr
    (box.etc / "frames.conf").write_text(f"FRAMES_SUBTREE=../x\nSTAGING_DIR={box.staging}\n")
    r = box.frames_sync()
    assert r.returncode == 1 and "not a plain relative path" in r.stderr
    assert box.calls() == []


def test_a_held_lock_skips_the_run(box):
    import fcntl

    box.project("tt06/tt_um_demo")
    box.changed.write_text(line("tt06/tt_um_demo"))
    fd = os.open(box.fstate / "lock", os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        r = box.frames_sync()
    finally:
        os.close(fd)
    assert r.returncode == 0 and "another frames upload is running" in r.stderr
    assert box.calls() == [] and not box.offset_file.exists()
