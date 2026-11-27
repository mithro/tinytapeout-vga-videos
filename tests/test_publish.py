# SPDX-License-Identifier: Apache-2.0
"""hostconf.load checks host.toml; publish.install swaps a project into the frames subtree."""

import os
import re
import signal
import stat
import sys
import threading
import time
from pathlib import Path

import pytest

from ttvga import HARNESS_DIR

sys.path.insert(0, str(HARNESS_DIR))

import hostconf  # noqa: E402
import publish  # noqa: E402

SHUTTLE, MACRO = "tt06", "tt_um_demo"
STEM = f"{SHUTTLE}_{MACRO}"


def make_host(tmp_path: Path, extra: str = "") -> hostconf.HostConfig:
    frames_root, staging = tmp_path / "archive" / "frames", tmp_path / "staging"
    frames_root.mkdir(parents=True)
    staging.mkdir()
    (frames_root / ".ttvga-frames-root").write_bytes(b"")
    (tmp_path / "host.toml").write_text(f'frames_root = "{frames_root}"\nstaging_dir = "{staging}"\n{extra}')
    return hostconf.load(tmp_path)


def make_scratch(path: Path, files: dict[str, bytes]) -> Path:
    for name, data in files.items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_bytes(data)
    return path


def basic_files(tag: bytes) -> dict[str, bytes]:
    return {
        f"{STEM}_trace.vgch.zst": b"trace " + tag,
        "centre-v1/frames.txt": b"frames " + tag,
        "centre-v1/frame_hashes.xxh3-128-rgb6.txt": b"hashes " + tag,
        f"centre-v1/{STEM}_centre-v1_frames.rgb6.zst": b"store " + tag,
        "centre-v1/index.html": b"<html>" + tag,
        "centre-v1/png/000000.png": b"png " + tag,
    }


def tree(path: Path) -> dict[str, bytes]:
    return {str(p.relative_to(path)): p.read_bytes() for p in sorted(path.rglob("*")) if p.is_file()}


def published(conf: hostconf.HostConfig) -> Path:
    return conf.frames_root / SHUTTLE / MACRO


STAGING_CLEAN = ["changed.log", f"{STEM}.lock"]


def staging_names(conf: hostconf.HostConfig) -> list[str]:
    return sorted(p.name for p in conf.staging_dir.iterdir())


def state(conf: hostconf.HostConfig) -> dict:
    """Everything under frames_root and staging (contents by name), to check that nothing changed."""
    return {"frames": tree(conf.frames_root), "staging": tree(conf.staging_dir),
            "staging_names": staging_names(conf)}


def install(tmp_path: Path, conf: hostconf.HostConfig, scratch: Path, **kw) -> None:
    publish.install(scratch, conf, SHUTTLE, MACRO, tmp_path / "publish.log", **kw)


# --- hostconf --------------------------------------------------------------


def test_load_requires_paths(tmp_path):
    with pytest.raises(hostconf.ConfigError, match="host.toml"):
        hostconf.load(tmp_path)
    conf = make_host(tmp_path)
    assert conf.min_free_root_gb == 100.0
    assert conf.frames_root == tmp_path / "archive" / "frames"
    assert conf.staging_dir == tmp_path / "staging"
    text = (tmp_path / "host.toml").read_text()
    for key in ("frames_root", "staging_dir"):
        lines = [line for line in text.splitlines() if not line.startswith(key)]
        (tmp_path / "host.toml").write_text("\n".join(lines) + "\n")
        with pytest.raises(hostconf.ConfigError, match=key):
            hostconf.load(tmp_path)
    (tmp_path / "host.toml").write_text(text + "min_free_root_gb = 250\n")
    assert hostconf.load(tmp_path).min_free_root_gb == 250.0
    (tmp_path / "host.toml").write_text(text + 'min_free_root_gb = "lots"\n')
    with pytest.raises(hostconf.ConfigError, match="min_free_root_gb"):
        hostconf.load(tmp_path)
    (tmp_path / "host.toml").write_text(text.replace(str(tmp_path / "staging"), "staging"))
    with pytest.raises(hostconf.ConfigError, match="staging_dir"):
        hostconf.load(tmp_path)
    (tmp_path / "host.toml").write_text(text.replace(str(tmp_path / "staging"), str(tmp_path / "absent")))
    with pytest.raises(hostconf.ConfigError, match="staging_dir"):
        hostconf.load(tmp_path)


@pytest.mark.parametrize("name", ["index.json", "index.html"])
def test_load_refuses_archive_root(tmp_path, name):
    conf = make_host(tmp_path)
    (conf.frames_root / name).write_text("{}")
    with pytest.raises(hostconf.ConfigError, match=name):
        hostconf.load(tmp_path)


def test_load_refuses_unmarked_root(tmp_path):
    conf = make_host(tmp_path)
    (conf.frames_root / ".ttvga-frames-root").unlink()
    with pytest.raises(hostconf.ConfigError, match=r"\.ttvga-frames-root"):
        hostconf.load(tmp_path)


def test_load_refuses_staging_inside_root(tmp_path):
    conf = make_host(tmp_path)
    inner = conf.frames_root / "staging"
    inner.mkdir()
    text = (tmp_path / "host.toml").read_text()
    (tmp_path / "host.toml").write_text(text.replace(str(conf.staging_dir), str(inner)))
    with pytest.raises(hostconf.ConfigError, match="inside"):
        hostconf.load(tmp_path)
    (tmp_path / "host.toml").write_text(text.replace(str(conf.staging_dir), str(conf.frames_root)))
    with pytest.raises(hostconf.ConfigError, match="inside"):
        hostconf.load(tmp_path)


def test_load_refuses_root_inside_staging(tmp_path):
    conf = make_host(tmp_path)
    inner = conf.staging_dir / "frames"
    inner.mkdir()
    (inner / ".ttvga-frames-root").write_bytes(b"")
    text = (tmp_path / "host.toml").read_text()
    (tmp_path / "host.toml").write_text(text.replace(str(conf.frames_root), str(inner)))
    with pytest.raises(hostconf.ConfigError, match="frames_root .* is inside staging_dir"):
        hostconf.load(tmp_path)


def test_load_refuses_two_filesystems(tmp_path, monkeypatch):
    conf = make_host(tmp_path)
    real_stat = os.stat

    def fake_stat(path, *args, **kwargs):
        st = real_stat(path, *args, **kwargs)
        if Path(path) == conf.staging_dir:
            fields = list(st)
            fields[stat.ST_DEV] += 1
            return os.stat_result(fields)
        return st

    monkeypatch.setattr(os, "stat", fake_stat)
    with pytest.raises(hostconf.ConfigError, match="filesystem"):
        hostconf.load(tmp_path)


# --- publish ---------------------------------------------------------------


def test_install_new_project(tmp_path):
    conf = make_host(tmp_path)
    scratch = make_scratch(tmp_path / "scratch", basic_files(b"A"))
    install(tmp_path, conf, scratch)
    dest = published(conf)
    assert tree(dest) == {**basic_files(b"A"), ".ttvga-frames": b""}
    assert staging_names(conf) == STAGING_CLEAN


def test_install_replaces_with_exchange(tmp_path, monkeypatch):
    conf = make_host(tmp_path)
    install(tmp_path, conf, make_scratch(tmp_path / "s1", basic_files(b"A") | {"tb-v1/frames.txt": b"tb"}))
    calls = []
    real = publish.exchange

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(publish, "exchange", spy)
    install(tmp_path, conf, make_scratch(tmp_path / "s2", basic_files(b"B")))
    assert len(calls) == 1
    assert tree(published(conf)) == {**basic_files(b"B"), ".ttvga-frames": b""}
    assert staging_names(conf) == STAGING_CLEAN


def test_install_keeps_hard_links(tmp_path):
    conf = make_host(tmp_path)
    scratch = make_scratch(tmp_path / "scratch", basic_files(b"A"))
    os.link(scratch / "centre-v1/png/000000.png", scratch / "centre-v1/png/000001.png")
    install(tmp_path, conf, scratch)
    png = published(conf) / "centre-v1" / "png"
    assert (png / "000000.png").stat().st_ino == (png / "000001.png").stat().st_ino


def test_install_fallback_two_renames(tmp_path, monkeypatch):
    conf = make_host(tmp_path)
    install(tmp_path, conf, make_scratch(tmp_path / "s1", basic_files(b"A")))
    monkeypatch.setattr(publish, "exchange", lambda a, b: False)
    renames = []
    real_rename = os.rename

    def spy(a, b):
        renames.append((Path(a), Path(b)))
        return real_rename(a, b)

    monkeypatch.setattr(os, "rename", spy)
    install(tmp_path, conf, make_scratch(tmp_path / "s2", basic_files(b"B")))
    sd = conf.staging_dir
    assert renames == [
        (published(conf), sd / f"{STEM}.old"),
        (sd / f"{STEM}.new", published(conf)),
        (sd / f"{STEM}.old", sd / f"{STEM}.del"),
    ]
    assert tree(published(conf)) == {**basic_files(b"B"), ".ttvga-frames": b""}
    assert staging_names(conf) == STAGING_CLEAN


def test_install_fallback_rolls_back_a_failed_second_rename(tmp_path, monkeypatch):
    conf = make_host(tmp_path)
    install(tmp_path, conf, make_scratch(tmp_path / "s1", basic_files(b"A")))
    log_before = (conf.staging_dir / "changed.log").read_bytes()
    monkeypatch.setattr(publish, "exchange", lambda a, b: False)
    real_rename = os.rename

    def failing(a, b):
        if Path(a) == conf.staging_dir / f"{STEM}.new":
            raise OSError(5, "injected")
        return real_rename(a, b)

    monkeypatch.setattr(os, "rename", failing)
    with pytest.raises(publish.PublishError, match="back in place"):
        install(tmp_path, conf, make_scratch(tmp_path / "s2", basic_files(b"B")))
    assert tree(published(conf)) == {**basic_files(b"A"), ".ttvga-frames": b""}
    assert (conf.staging_dir / "changed.log").read_bytes() == log_before
    assert not (conf.staging_dir / f"{STEM}.old").exists()


def test_install_refuses_missing_dest_with_leftover_old(tmp_path):
    conf = make_host(tmp_path)
    install(tmp_path, conf, make_scratch(tmp_path / "s1", basic_files(b"A") | {"tb-v1/frames.txt": b"tb"}))
    # A crash between the fallback's two renames: the published copy sits at .old.
    old = conf.staging_dir / f"{STEM}.old"
    os.rename(published(conf), old)
    make_scratch(conf.staging_dir / f"{STEM}.new", {"partial": b"x"})
    before = state(conf)
    with pytest.raises(publish.PublishError, match="operator") as info:
        install(tmp_path, conf, make_scratch(tmp_path / "s2", basic_files(b"B")))
    assert str(published(conf)) in str(info.value) and str(old) in str(info.value)
    assert state(conf) == before


def test_install_removes_leftovers_when_published(tmp_path):
    conf = make_host(tmp_path)
    install(tmp_path, conf, make_scratch(tmp_path / "s1", basic_files(b"A")))
    for suffix in ("old", "new", "del"):
        make_scratch(conf.staging_dir / f"{STEM}.{suffix}", {"stale": b"x"})
    install(tmp_path, conf, make_scratch(tmp_path / "s2", basic_files(b"B")))
    assert tree(published(conf)) == {**basic_files(b"B"), ".ttvga-frames": b""}
    assert staging_names(conf) == STAGING_CLEAN


def test_install_logs_a_failed_delete_and_publishes(tmp_path, monkeypatch):
    conf = make_host(tmp_path)
    install(tmp_path, conf, make_scratch(tmp_path / "s1", basic_files(b"A")))
    real_rmtree = publish.shutil.rmtree

    def failing(path, *args, **kwargs):
        if Path(path).name == f"{STEM}.del":
            raise OSError(5, "injected")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(publish.shutil, "rmtree", failing)
    install(tmp_path, conf, make_scratch(tmp_path / "s2", basic_files(b"B")))
    monkeypatch.setattr(publish.shutil, "rmtree", real_rmtree)
    assert tree(published(conf)) == {**basic_files(b"B"), ".ttvga-frames": b""}
    assert len((conf.staging_dir / "changed.log").read_text().splitlines()) == 2
    assert "could not delete the previous copy" in (tmp_path / "publish.log").read_text()
    # The next install clears the .del leftover.
    install(tmp_path, conf, make_scratch(tmp_path / "s3", basic_files(b"C")))
    assert staging_names(conf) == STAGING_CLEAN


def test_install_lock_serialises_one_project(tmp_path, monkeypatch):
    conf = make_host(tmp_path)
    install(tmp_path, conf, make_scratch(tmp_path / "s0", basic_files(b"0")))
    spans, errors = [], []
    real_run = publish._run

    def slow_run(cmd, log):
        start = time.monotonic()
        real_run(cmd, log)
        time.sleep(0.2)
        spans.append((threading.current_thread().name, start, time.monotonic()))

    monkeypatch.setattr(publish, "_run", slow_run)
    scratches = {tag: make_scratch(tmp_path / f"s{tag}", basic_files(tag.encode())) for tag in "AB"}
    barrier = threading.Barrier(2)

    def run(tag):
        try:
            barrier.wait()
            install(tmp_path, conf, scratches[tag])
        except Exception as e:  # reported below
            errors.append(repr(e))

    threads = [threading.Thread(target=run, args=(tag,), name=tag) for tag in "AB"]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    (a,), (b,) = ([s for s in spans if s[0] == tag] for tag in "AB")
    assert a[2] <= b[1] or b[2] <= a[1], spans
    assert tree(published(conf)) in [{**basic_files(t.encode()), ".ttvga-frames": b""} for t in "AB"]
    assert len((conf.staging_dir / "changed.log").read_text().splitlines()) == 3
    assert staging_names(conf) == STAGING_CLEAN


@pytest.mark.parametrize("earlier", [False, True])
@pytest.mark.parametrize("name", [f"{STEM}.lock", "changed.log"])
def test_install_refuses_symlinked_lock_and_log(tmp_path, name, earlier):
    conf = make_host(tmp_path)
    if earlier:
        install(tmp_path, conf, make_scratch(tmp_path / "s0", basic_files(b"0")))
        (conf.staging_dir / name).unlink()
    target = tmp_path / "elsewhere"
    target.write_bytes(b"")
    (conf.staging_dir / name).symlink_to(target)
    before = tree(conf.frames_root)
    with pytest.raises(publish.PublishError):
        install(tmp_path, conf, make_scratch(tmp_path / "s", basic_files(b"A")))
    assert target.read_bytes() == b""
    # Nothing was published: absent on a first install, unchanged otherwise.
    assert tree(conf.frames_root) == before
    assert published(conf).exists() == earlier
    assert not (conf.staging_dir / f"{STEM}.new").exists()


def test_install_names_an_undeletable_del_leftover(tmp_path, monkeypatch):
    conf = make_host(tmp_path)
    install(tmp_path, conf, make_scratch(tmp_path / "s1", basic_files(b"A")))
    dele = make_scratch(conf.staging_dir / f"{STEM}.del", {"stale": b"x"})
    real_rmtree = publish.shutil.rmtree

    def failing(path, *args, **kwargs):
        if Path(path) == dele:
            raise OSError(13, "injected")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(publish.shutil, "rmtree", failing)
    before = tree(conf.frames_root)
    with pytest.raises(publish.PublishError, match=re.escape(str(dele))):
        install(tmp_path, conf, make_scratch(tmp_path / "s2", basic_files(b"B")))
    assert tree(conf.frames_root) == before


def test_note_never_raises(tmp_path, capsys):
    publish._note(tmp_path / "absent-dir" / "log", "hello")
    assert "hello" in capsys.readouterr().err


@pytest.mark.parametrize("breakage", ["marker", "index.json", "filesystem"])
def test_install_rechecks_frames_root(tmp_path, monkeypatch, breakage):
    conf = make_host(tmp_path)
    install(tmp_path, conf, make_scratch(tmp_path / "s1", basic_files(b"A")))
    if breakage == "marker":
        (conf.frames_root / ".ttvga-frames-root").unlink()
    elif breakage == "index.json":
        (conf.frames_root / "index.json").write_text("{}")
    before = state(conf)
    if breakage == "filesystem":
        real_stat = os.stat

        def fake_stat(path, *args, **kwargs):
            st = real_stat(path, *args, **kwargs)
            if Path(path) == conf.staging_dir:
                fields = list(st)
                fields[stat.ST_DEV] += 1
                return os.stat_result(fields)
            return st

        monkeypatch.setattr(os, "stat", fake_stat)
    with pytest.raises(publish.PublishError):
        install(tmp_path, conf, make_scratch(tmp_path / "s2", basic_files(b"B")))
    monkeypatch.undo()
    assert state(conf) == before


def test_install_requires_trace(tmp_path):
    conf = make_host(tmp_path)
    files = basic_files(b"A")
    del files[f"{STEM}_trace.vgch.zst"]
    with pytest.raises(publish.PublishError, match="_trace.vgch.zst"):
        install(tmp_path, conf, make_scratch(tmp_path / "s", files))
    assert not published(conf).exists()


def test_install_carries_tb_v1(tmp_path):
    conf = make_host(tmp_path)
    tb = {"tb-v1/frames.txt": b"tb", "tb-v1/TRACE_SHA256": b"ab" * 32, "tb-v1/png/000000.png": b"p"}
    install(tmp_path, conf, make_scratch(tmp_path / "s1", basic_files(b"A") | tb))
    inodes = {name: (published(conf) / name).stat().st_ino for name in tb}
    install(tmp_path, conf, make_scratch(tmp_path / "s2", basic_files(b"B")), carry=["tb-v1"])
    assert tree(published(conf)) == {**basic_files(b"B"), **tb, ".ttvga-frames": b""}
    assert {name: (published(conf) / name).stat().st_ino for name in tb} == inodes
    # A carry the scratch already holds, one not published, or not a top-level name, is refused.
    for n, (scratch_files, carry) in enumerate((
        (basic_files(b"C") | tb, ["tb-v1"]),
        (basic_files(b"C"), ["centre-v1", "missing-v1"]),
        (basic_files(b"C"), ["tb-v1/png"]),
        (basic_files(b"C"), [".."]),
    )):
        with pytest.raises(publish.PublishError):
            install(tmp_path, conf, make_scratch(tmp_path / f"refused-{n}", scratch_files), carry=carry)
        assert tree(published(conf)) == {**basic_files(b"B"), **tb, ".ttvga-frames": b""}
    # Carried files pass the same mode check as copied ones.
    (published(conf) / "tb-v1" / "frames.txt").chmod(0o600)
    before = state(conf)
    with pytest.raises(publish.PublishError, match="0644"):
        install(tmp_path, conf, make_scratch(tmp_path / "s-mode", basic_files(b"D")), carry=["tb-v1"])
    assert state(conf) == before


def test_swap_never_exposes_partial_directory(tmp_path, monkeypatch):
    conf = make_host(tmp_path)
    sets = []
    scratches = []
    for k in range(2):
        files = {f"centre-v1/png/{k * 200 + i:06d}.png": b"%d" % i for i in range(200)}
        files[f"{STEM}_trace.vgch.zst"] = b"t"
        scratches.append(make_scratch(tmp_path / f"s{k}", files))
        sets.append(frozenset(f"{k * 200 + i:06d}.png" for i in range(200)))
    install(tmp_path, conf, scratches[0])
    exchanges, listings = [], []
    real_exchange = publish.exchange

    def timed_exchange(a, b):
        start = time.monotonic_ns()
        result = real_exchange(a, b)
        exchanges.append((start, time.monotonic_ns()))
        return result

    dest = published(conf)
    top = {".ttvga-frames", "centre-v1", f"{STEM}_trace.vgch.zst"}
    stop = threading.Event()
    seen, bad = [], []
    swapped_out = 0

    def watch():
        # Each listing reads one directory, through one descriptor. A listing whose
        # directory was swapped out while it was read is of the old copy, which is
        # being deleted; only listings of the directory published throughout count.
        nonlocal swapped_out
        while not stop.is_set():
            began = time.monotonic_ns()
            try:
                fd = os.open(dest, os.O_RDONLY | os.O_DIRECTORY)
            except OSError as e:
                bad.append(f"published path: {e!r}")
                continue
            try:
                top_listing = set(os.listdir(fd))
                png_fd = os.open("centre-v1/png", os.O_RDONLY | os.O_DIRECTORY, dir_fd=fd)
                try:
                    listing = frozenset(os.listdir(png_fd))
                finally:
                    os.close(png_fd)
                error = None
            except OSError as e:
                error = repr(e)
            try:
                still = os.stat(dest).st_ino == os.fstat(fd).st_ino
            except OSError as e:
                bad.append(f"published path: {e!r}")
                continue
            finally:
                os.close(fd)
            listings.append((began, time.monotonic_ns()))
            if not still:
                swapped_out += 1
                continue
            if error:
                bad.append(error)
                continue
            seen.append(listing)
            if listing not in sets:
                bad.append(f"png listing of {len(listing)} names")
            if top_listing != top:
                bad.append(f"top listing {sorted(top_listing)}")

    monkeypatch.setattr(publish, "exchange", timed_exchange)
    thread = threading.Thread(target=watch)
    thread.start()
    try:
        for n in range(50):
            install(tmp_path, conf, scratches[(n + 1) % 2])
    finally:
        stop.set()
        thread.join()
    assert bad == []
    assert set(seen) == set(sets)
    assert len(exchanges) == 50
    overlapped = sum(any(ls <= xe and xs <= le for ls, le in listings) for xs, xe in exchanges)
    assert overlapped >= 10, (overlapped, len(listings), swapped_out)


def test_modes_are_0644_0755(tmp_path):
    conf = make_host(tmp_path)
    old = os.umask(0o077)
    try:
        scratch = make_scratch(tmp_path / "scratch", basic_files(b"A"))
        for p in scratch.rglob("*"):
            p.chmod(0o700 if p.is_dir() else 0o600)
        (scratch / "centre-v1" / "index.html").chmod(0o775)
        install(tmp_path, conf, scratch)
    finally:
        os.umask(old)
    dest = published(conf)
    modes = {str(p.relative_to(dest)): stat.S_IMODE(p.stat().st_mode) for p in [dest, *dest.rglob("*")]}
    assert modes == {name: (0o755 if (dest / name).is_dir() else 0o644) for name in modes}
    assert stat.S_IMODE((conf.frames_root / SHUTTLE).stat().st_mode) == 0o755
    assert stat.S_IMODE((conf.staging_dir / "changed.log").stat().st_mode) == 0o644


@pytest.mark.parametrize("planted", [None, "x.bin", "centre-v1/x.bin", "fpga-library.json", "fpga"])
def test_install_refuses_unmarked_directory(tmp_path, planted):
    conf = make_host(tmp_path)
    dest = published(conf)
    if planted is None:
        # An archive clips directory: no marker.
        make_scratch(dest, {f"{STEM}.mp4": b"clip"})
    else:
        install(tmp_path, conf, make_scratch(tmp_path / "s1", basic_files(b"A")))
        make_scratch(dest, {planted: b"bitstream"})
    before = tree(dest)
    log = conf.staging_dir / "changed.log"
    log_before = log.read_bytes() if log.exists() else None
    with pytest.raises(publish.PublishError):
        install(tmp_path, conf, make_scratch(tmp_path / "s2", basic_files(b"B")))
    assert tree(dest) == before
    assert (log.read_bytes() if log.exists() else None) == log_before
    assert not (conf.staging_dir / f"{STEM}.new").exists()


def test_install_refuses_symlinked_published_directory(tmp_path):
    conf = make_host(tmp_path)
    elsewhere = make_scratch(tmp_path / "elsewhere", {".ttvga-frames": b""})
    (conf.frames_root / SHUTTLE).mkdir()
    published(conf).symlink_to(elsewhere)
    with pytest.raises(publish.PublishError):
        install(tmp_path, conf, make_scratch(tmp_path / "s", basic_files(b"B")))
    assert published(conf).is_symlink()


@pytest.mark.parametrize("shuttle, macro", [("..", MACRO), (SHUTTLE, "a/b"), (SHUTTLE, "x\ny"), ("", MACRO), ("tt_06", "um_x"), (".tt06", MACRO)])
def test_install_refuses_bad_project_names(tmp_path, shuttle, macro):
    conf = make_host(tmp_path)
    # The scratch is otherwise valid for this stem, so only the name check can refuse it.
    scratch = tmp_path / "s"
    scratch.mkdir()
    if "/" not in f"{shuttle}_{macro}":
        (scratch / f"{shuttle}_{macro}_trace.vgch.zst").write_bytes(b"t")
    with pytest.raises(publish.PublishError, match="bad (shuttle|macro) name"):
        publish.install(scratch, conf, shuttle, macro, tmp_path / "log")
    assert sorted(p.name for p in conf.frames_root.iterdir()) == [".ttvga-frames-root"]


def test_install_refuses_disallowed_file(tmp_path):
    conf = make_host(tmp_path)
    cases = {
        "hidden": lambda s: (s / ".hidden").write_bytes(b""),
        "notes": lambda s: (s / "notes.txt").write_bytes(b""),
        "symlink": lambda s: (s / "centre-v1" / "png" / "000001.png").symlink_to(s / "centre-v1" / "png" / "000000.png"),
        "dirlink": lambda s: (s / "tb-v1").symlink_to(s / "centre-v1"),
        "fifo": lambda s: os.mkfifo(s / "centre-v1" / "frames.txt.fifo"),
        "bad-png": lambda s: (s / "centre-v1" / "png" / "1.png").write_bytes(b""),
        "other-stem": lambda s: (s / "tt07_x_trace.vgch.zst").write_bytes(b""),
        "unknown-sampler": lambda s: make_scratch(s, {"edge-v1/frames.txt": b""}),
        "sha-in-centre": lambda s: (s / "centre-v1" / "TRACE_SHA256").write_bytes(b""),
        "marker": lambda s: (s / ".ttvga-frames").write_bytes(b""),
        # The pre-XXH3 method file is refused, never published beside the new format.
        "sha256-method": lambda s: (s / "centre-v1" / "frame_hashes.sha256-rgb6.txt").write_bytes(b""),
        "bin": lambda s: (s / "x.bin").write_bytes(b""),
    }
    for name, plant in cases.items():
        scratch = make_scratch(tmp_path / f"s-{name}", basic_files(b"A"))
        plant(scratch)
        violations = publish.check_allowed(scratch, STEM)
        assert len(violations) == 1, (name, violations)
        with pytest.raises(publish.PublishError):
            install(tmp_path, conf, scratch)
        assert not published(conf).exists()
    assert publish.check_allowed(make_scratch(tmp_path / "ok", basic_files(b"A") | {
        "tb-v1/TRACE_SHA256": b"",
        "tb-v1/frame_hashes.fnv1a64-tb2026-rgb888.txt": b"",
        f"tb-v1/{STEM}_tb-v1_frames.rgb6.zst": b"",
    }), STEM) == []


def test_changed_log_lines_are_whole(tmp_path):
    conf = make_host(tmp_path)
    macros = [f"tt_um_m{i:02d}" for i in range(16)]
    errors = []

    def run(macro):
        try:
            for n in range(5):
                files = {f"{SHUTTLE}_{macro}_trace.vgch.zst": b"%d" % n}
                scratch = make_scratch(tmp_path / f"s-{macro}-{n}", files)
                publish.install(scratch, conf, SHUTTLE, macro, tmp_path / f"{macro}.log")
        except Exception as e:  # reported below
            errors.append(repr(e))

    threads = [threading.Thread(target=run, args=(m,)) for m in macros]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    data = (conf.staging_dir / "changed.log").read_text()
    assert data.endswith("\n")
    lines = data.splitlines()
    assert len(lines) == 16 * 5
    pattern = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?\+00:00 tt06/(tt_um_m\d\d)")
    assert all(pattern.fullmatch(line) for line in lines), lines
    assert sorted(pattern.fullmatch(line).group(2) for line in lines) == sorted(macros * 5)


def test_exchange_swaps_and_reports_errors(tmp_path):
    a, b = make_scratch(tmp_path / "a", {"x": b"a"}), make_scratch(tmp_path / "b", {"x": b"b"})
    assert publish.exchange(a, b) is True
    assert (a / "x").read_bytes() == b"b" and (b / "x").read_bytes() == b"a"
    with pytest.raises(FileNotFoundError):
        publish.exchange(a, tmp_path / "absent")


class _Stop(Exception):
    pass


def _sigterm_mid_swap(monkeypatch, events: list) -> None:
    """Make the swap send this process SIGTERM, as a queue stop or the scope would."""
    real = publish.exchange

    def exchange(a, b):
        os.kill(os.getpid(), signal.SIGTERM)
        events.append("sigterm sent")
        return real(a, b)

    monkeypatch.setattr(publish, "exchange", exchange)


@pytest.fixture
def sigterm_raises():
    """SIGTERM raises _Stop, as job.py's handler raises Terminated."""
    events: list[str] = []

    def handler(signum, frame):
        events.append("handler")
        raise _Stop

    previous = signal.signal(signal.SIGTERM, handler)
    try:
        yield events
    finally:
        signal.signal(signal.SIGTERM, previous)


def test_install_defers_sigterm_over_swap_and_record(tmp_path, monkeypatch, sigterm_raises):
    events = sigterm_raises
    conf = make_host(tmp_path)
    install(tmp_path, conf, make_scratch(tmp_path / "s1", basic_files(b"A")))
    _sigterm_mid_swap(monkeypatch, events)
    with pytest.raises(_Stop):
        install(tmp_path, conf, make_scratch(tmp_path / "s2", basic_files(b"B")),
                defer_signals=(signal.SIGTERM,), on_published=lambda: events.append("recorded"))
    # The stop arrived mid-swap and was held until the swap, changed.log and the job's record were done.
    assert events == ["sigterm sent", "recorded", "handler"]
    assert tree(published(conf)) == {**basic_files(b"B"), ".ttvga-frames": b""}
    assert len((conf.staging_dir / "changed.log").read_text().splitlines()) == 2
    assert signal.SIGTERM not in signal.pthread_sigmask(signal.SIG_BLOCK, [])
    # The previous copy was not deleted (the stop came first); the next install clears it.
    monkeypatch.undo()
    install(tmp_path, conf, make_scratch(tmp_path / "s3", basic_files(b"C")))
    assert staging_names(conf) == STAGING_CLEAN


def test_install_without_defer_can_stop_before_the_record(tmp_path, monkeypatch, sigterm_raises):
    """The gap deferring closes: undeferred, the stop lands inside the swap step and nothing is recorded."""
    events = sigterm_raises
    conf = make_host(tmp_path)
    install(tmp_path, conf, make_scratch(tmp_path / "s1", basic_files(b"A")))
    _sigterm_mid_swap(monkeypatch, events)
    with pytest.raises(_Stop):
        install(tmp_path, conf, make_scratch(tmp_path / "s2", basic_files(b"B")),
                on_published=lambda: events.append("recorded"))
    assert "recorded" not in events
    assert len((conf.staging_dir / "changed.log").read_text().splitlines()) == 1


def test_install_restores_the_signal_mask_on_failure(tmp_path, monkeypatch):
    conf = make_host(tmp_path)
    install(tmp_path, conf, make_scratch(tmp_path / "s1", basic_files(b"A")))

    def broken(a, b):
        raise OSError(5, "I/O error")

    monkeypatch.setattr(publish, "exchange", broken)
    with pytest.raises(OSError):
        install(tmp_path, conf, make_scratch(tmp_path / "s2", basic_files(b"B")), defer_signals=(signal.SIGTERM,))
    assert signal.SIGTERM not in signal.pthread_sigmask(signal.SIG_BLOCK, [])
