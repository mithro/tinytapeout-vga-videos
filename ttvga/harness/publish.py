# SPDX-License-Identifier: Apache-2.0
"""Publish a finished project directory into the frames subtree. Runs on the host.

A job builds `<scratch>` on the root volume. `install` checks it against an
allow-list, copies it to `<staging_dir>/<shuttle>_<macro>.new` on the bulk
volume (the same filesystem as `<frames_root>`), carries named entries over
from the published copy by hard link, and swaps the result into
`<frames_root>/<shuttle>/<macro>` with one `renameat2(RENAME_EXCHANGE)`: at no
instant is the published directory missing or half-copied. Each publish is
then appended to `<staging_dir>/changed.log`, which the root-owned upload
reads, and only after that is the old copy deleted. A per-project lock,
`<staging_dir>/<stem>.lock`, keeps two installs of one project apart.

The caller can hold signals (`defer_signals`, job.py's SIGTERM) over the swap,
the changed.log line and its own record of the publish (`on_published`), so a
stop never lands between a swap that happened and the records that say so.

Everything the job writes was produced by building and running third-party
Verilog, so nothing in scratch is trusted: only the names in `ALLOWED`, as
regular files and directories, are published (no symlinks, no devices). A
published directory is replaced only if it carries the `.ttvga-frames` marker
and holds nothing that looks like an archive clip directory's FPGA files
(`*.bin`, `fpga*`), so a wrong path never replaces a directory of the archive.

Standard library only: the host has no packages installed.
"""

from __future__ import annotations

import ctypes
import errno
import fcntl
import fnmatch
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import hostconf  # noqa: E402
from encode import stem_for  # noqa: E402

SAMPLERS = ("tb-v1", "centre-v1")

# The only paths a scratch directory may hold, relative to it.
ALLOWED = (
    "{stem}_trace.vgch.zst",
    "{sampler}/frames.txt",
    "{sampler}/frame_hashes.{method}.txt",
    "{sampler}/{stem}_{sampler}_frames.rgb6.zst",
    "{sampler}/index.html",
    "{sampler}/png/{NNNNNN}.png",
    "tb-v1/TRACE_SHA256",
)

PROJECT_MARKER = ".ttvga-frames"
# Names that belong to the archive's own <shuttle>/<macro>/ directories (Ruling AA).
FOREIGN_NAMES = ("*.bin", "fpga*")
CHANGED_LOG = "changed.log"

_PLACEHOLDERS = {
    # The methods vgacap's frames format has; the pre-XXH3 `sha256-rgb6` is not one of them.
    "method": r"(?:xxh3-128-rgb6|fnv1a64-tb2026-rgb888)",
    "NNNNNN": r"[0-9]{6}",
}
_SHUTTLE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]*")
_MACRO_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")

AT_FDCWD = -100
RENAME_EXCHANGE = 1 << 1
_libc = ctypes.CDLL(None, use_errno=True)


class PublishError(Exception):
    """Nothing was published: the scratch, the published copy or the names are unsafe."""


def _rules(stem: str) -> tuple[list[re.Pattern], set[str]]:
    """The allowed file regexes and the allowed directories for one stem."""
    files, dirs = [], set()
    for pattern in ALLOWED:
        for sampler in SAMPLERS if "{sampler}" in pattern else (None,):
            regex = ""
            for part in re.split(r"(\{\w+\})", pattern):
                key = part[1:-1] if part.startswith("{") else None
                if key == "stem":
                    regex += re.escape(stem)
                elif key == "sampler":
                    regex += re.escape(sampler)
                elif key in _PLACEHOLDERS:
                    regex += _PLACEHOLDERS[key]
                else:
                    regex += re.escape(part)
            files.append(re.compile(regex))
            parts = pattern.replace("{sampler}", sampler or "").split("/")[:-1]
            dirs.update("/".join(parts[: i + 1]) for i in range(len(parts)))
    return files, dirs


def _violations(top: Path, stem: str, extra_files: tuple[str, ...] = (), modes: bool = False) -> list[str]:
    """Entries of `top` outside the allow-list; with `modes`, also any file not 0644 or directory not 0755."""
    files, dirs = _rules(stem)
    out = []
    try:
        st = os.lstat(top)
    except FileNotFoundError:
        return [f"{top}: missing"]
    if not stat.S_ISDIR(st.st_mode):
        return [f"{top}: not a directory"]
    if modes and stat.S_IMODE(st.st_mode) != 0o755:
        out.append(f"{str(top)!r}: mode {stat.S_IMODE(st.st_mode):04o}, not 0755")

    def walk(path: Path, rel: str) -> None:
        with os.scandir(path) as it:
            entries = sorted(it, key=lambda e: e.name)
        for entry in entries:
            name = f"{rel}{entry.name}"
            mode = entry.stat(follow_symlinks=False).st_mode
            if stat.S_ISLNK(mode):
                out.append(f"{name!r}: symlink")
            elif stat.S_ISDIR(mode):
                if name not in dirs:
                    out.append(f"{name!r}: directory not allowed")
                    continue
                if modes and stat.S_IMODE(mode) != 0o755:
                    out.append(f"{name!r}: mode {stat.S_IMODE(mode):04o}, not 0755")
                walk(Path(entry.path), name + "/")
            elif not stat.S_ISREG(mode):
                out.append(f"{name!r}: not a regular file")
            elif name not in extra_files and not any(r.fullmatch(name) for r in files):
                out.append(f"{name!r}: name not allowed")
            elif modes and stat.S_IMODE(mode) != 0o644:
                out.append(f"{name!r}: mode {stat.S_IMODE(mode):04o}, not 0644")

    walk(top, "")
    return out


def check_allowed(scratch: Path, stem: str) -> list[str]:
    """The entries of `scratch` that may not be published (empty when it is all allowed)."""
    return _violations(Path(scratch), stem)


def exchange(a: Path, b: Path) -> bool:
    """Swap two paths atomically. False when the kernel or filesystem does not support it."""
    try:
        renameat2 = _libc.renameat2
    except AttributeError:  # a libc without the wrapper: the same as ENOSYS
        return False
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    if renameat2(AT_FDCWD, os.fsencode(a), AT_FDCWD, os.fsencode(b), RENAME_EXCHANGE) == 0:
        return True
    err = ctypes.get_errno()
    if err in (errno.ENOSYS, errno.EINVAL):
        return False
    raise OSError(err, os.strerror(err), str(a), None, str(b))


def _check_published(path: Path) -> None:
    """Refuse a directory that is not one of ours, or that holds the archive's FPGA files."""
    if not os.path.lexists(path):
        return
    if path.is_symlink() or not path.is_dir():
        raise PublishError(f"{path} is not a directory")
    if not (path / PROJECT_MARKER).is_file():
        raise PublishError(f"{path} has no {PROJECT_MARKER} marker: not a published frames directory")
    for dirpath, dirnames, filenames in os.walk(path):
        for name in dirnames + filenames:
            if any(fnmatch.fnmatch(name, p) for p in FOREIGN_NAMES):
                raise PublishError(f"{path} holds {Path(dirpath, name)}: an archive file, not frames")


def _remove(path: Path) -> None:
    if path.is_symlink() or (os.path.lexists(path) and not path.is_dir()):
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _note(log: Path, text: str) -> None:
    """Append a line to the job's log; never raises (stderr when the log cannot be written)."""
    try:
        with open(log, "ab") as f:
            f.write(f"{text}\n".encode())
    except OSError as e:
        print(f"publish: cannot write {log} ({e!r}): {text}", file=sys.stderr, flush=True)


def _run(cmd: list[str], log: Path) -> None:
    _note(log, f"$ {' '.join(cmd)}")
    with open(log, "ab") as f:
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    if result.returncode:
        raise PublishError(f"{cmd[0]} exited {result.returncode}; see {log}")


def _open_regular(path: Path, flags: int) -> int:
    """Open a regular file that is not a symlink, creating it 0644 if missing."""
    try:
        fd = os.open(path, flags | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o644)
    except OSError as e:
        raise PublishError(f"cannot open {path}: {e}") from e
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise PublishError(f"{path} is not a regular file")
    return fd


def _open_changed(conf) -> int:
    """The changed.log descriptor, opened and checked before anything is copied."""
    fd = _open_regular(conf.staging_dir / CHANGED_LOG, os.O_WRONLY | os.O_APPEND)
    try:
        os.fchmod(fd, 0o644)
    except OSError as e:
        os.close(fd)
        raise PublishError(f"cannot chmod {conf.staging_dir / CHANGED_LOG}: {e}") from e
    return fd


def _append_changed(fd: int, conf, shuttle: str, macro: str) -> None:
    """One whole line per publish, for the upload: one os.write on the O_APPEND descriptor."""
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {shuttle}/{macro}\n".encode()
    written = os.write(fd, line)
    if written != len(line):
        raise PublishError(f"{shuttle}/{macro} is published but {conf.staging_dir / CHANGED_LOG} "
                           f"got a short write: {written} of {len(line)} bytes")


def _remove_leftover(path: Path) -> None:
    try:
        _remove(path)
    except OSError as e:
        raise PublishError(f"cannot remove the leftover {path}: {e}; an operator must look") from e


def _check_name(label: str, name: str, pattern: re.Pattern) -> None:
    if not pattern.fullmatch(name):
        raise PublishError(f"bad {label} name {name!r}")


def install(scratch: Path, conf, shuttle: str, macro: str, log: Path, carry: list[str] = (), *,
            defer_signals: tuple[int, ...] = (), on_published: Callable[[], None] | None = None) -> None:
    """Publish `scratch` as `<frames_root>/<shuttle>/<macro>`, carrying `carry` over from the published copy.

    `defer_signals` are blocked from just before the swap until the changed.log line is
    written and `on_published` (the caller's record that the project is published) has
    run; a signal that arrived meanwhile is delivered then, before the old copy is deleted.
    """
    # A shuttle name has no "_", so <shuttle>_<macro> names exactly one project.
    _check_name("shuttle", shuttle, _SHUTTLE_NAME)
    _check_name("macro", macro, _MACRO_NAME)
    scratch, log = Path(scratch), Path(log)
    try:
        hostconf.check_paths(conf.frames_root, conf.staging_dir)
    except hostconf.ConfigError as e:
        raise PublishError(str(e)) from e
    stem = stem_for(shuttle, macro)
    shuttle_dir = conf.frames_root / shuttle
    dest = shuttle_dir / macro
    new, old, dele = (conf.staging_dir / f"{stem}.{suffix}" for suffix in ("new", "old", "del"))

    # Two installs of one project never overlap: the lock is held to the end.
    lock = _open_regular(conf.staging_dir / f"{stem}.lock", os.O_RDWR)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _install_locked(scratch, conf, shuttle, macro, log, list(carry), stem, shuttle_dir, dest, new, old, dele,
                        tuple(defer_signals), on_published)
    finally:
        os.close(lock)


def _install_locked(scratch, conf, shuttle, macro, log, carry, stem, shuttle_dir, dest, new, old, dele,
                    defer, on_published) -> None:
    # 1. Refuse anything unsafe before touching the filesystem.
    violations = check_allowed(scratch, stem)
    if violations:
        raise PublishError(f"{scratch} holds entries that may not be published: {'; '.join(violations)}")
    trace = f"{stem}_trace.vgch.zst"
    if not (scratch / trace).is_file():
        raise PublishError(f"{scratch} has no {trace}")
    if os.path.lexists(shuttle_dir) and (shuttle_dir.is_symlink() or not shuttle_dir.is_dir()):
        raise PublishError(f"{shuttle_dir} is not a directory")
    _check_published(dest)
    if not os.path.lexists(dest) and os.path.lexists(old):
        # Only a crash between the fallback's two renames leaves this: .old may be
        # the only copy of what was published, so it is neither restored nor deleted.
        raise PublishError(f"{dest} is missing and {old} exists: an install was interrupted mid-swap; an operator must look")
    top_names = {trace, *SAMPLERS}
    for name in carry:
        if name not in top_names:
            raise PublishError(f"cannot carry {name!r}: only {sorted(top_names)}")
        if os.path.lexists(scratch / name):
            raise PublishError(f"cannot carry {name!r}: {scratch} already holds it")
        if not os.path.lexists(dest / name):
            raise PublishError(f"cannot carry {name!r}: {dest} does not hold it")
    # changed.log is opened and checked now, so a bad one refuses the publish before
    # anything is copied; the line itself is written only after the swap.
    changed = _open_changed(conf)
    try:
        _install_checked(scratch, conf, shuttle, macro, log, carry, stem, shuttle_dir, dest, new, old, dele, changed,
                         defer, on_published)
    finally:
        os.close(changed)


def _install_checked(scratch, conf, shuttle, macro, log, carry, stem, shuttle_dir, dest, new, old, dele, changed,
                     defer, on_published) -> None:
    # 2. The shuttle directory.
    # Installs of other projects in the shuttle (other locks) may create it at the same time.
    try:
        shuttle_dir.mkdir()
    except FileExistsError:
        pass
    else:
        os.chmod(shuttle_dir, 0o755)
    if shuttle_dir.is_symlink() or not shuttle_dir.is_dir():
        raise PublishError(f"{shuttle_dir} is not a directory")

    # 3. Leftovers of an earlier install. With dest in place, .old is a finished swap's
    # old copy; it is moved to .del before deleting, so .old never holds a partial tree.
    _remove_leftover(new)
    _remove_leftover(dele)
    if os.path.lexists(old):
        try:
            os.rename(old, dele)
        except OSError as e:
            raise PublishError(f"cannot move the leftover {old} to {dele}: {e}; an operator must look") from e
        _remove_leftover(dele)

    try:
        # 4. The copy, with the marker.
        _run(["rsync", "-aH", "--delete", "--chmod=D0755,F0644", f"{scratch}/", f"{new}/"], log)
        (new / PROJECT_MARKER).write_bytes(b"")
        os.chmod(new / PROJECT_MARKER, 0o644)
        # 5. Carry-over by hard link: staging and frames_root are one filesystem.
        for name in carry:
            _run(["cp", "-al", str(dest / name), str(new / name)], log)
        # The whole new tree, as it will be published, names and modes.
        violations = _violations(new, stem, extra_files=(PROJECT_MARKER,), modes=True)
        if violations:
            raise PublishError(f"{new} may not be published: {'; '.join(violations)}")
    except BaseException:
        _remove(new)
        raise

    # 6 to 8, with `defer` held: the swap, the changed.log line, the caller's record.
    mask = signal.pthread_sigmask(signal.SIG_BLOCK, defer) if defer else None
    try:
        previous = _swap(new, dest, old)
        # The upload is told at once; deleting the old copy comes after and cannot undo the publish.
        _append_changed(changed, conf, shuttle, macro)
        if on_published is not None:
            on_published()
    finally:
        if mask is not None:
            signal.pthread_sigmask(signal.SIG_SETMASK, mask)   # a held signal is delivered here
    if previous is not None:
        try:
            os.rename(previous, dele)
            shutil.rmtree(dele)
        except OSError as e:
            _note(log, f"publish: could not delete the previous copy of {shuttle}/{macro}: {e!r}")


def _swap(new: Path, dest: Path, old: Path) -> Path | None:
    """Put `new` at `dest`; return where the previous copy now is (None when there was none)."""
    if not os.path.lexists(dest):
        os.rename(new, dest)
        return None
    if exchange(new, dest):
        return new
    os.rename(dest, old)
    try:
        os.rename(new, dest)
    except OSError as e:
        os.rename(old, dest)
        raise PublishError(f"cannot rename {new} to {dest}: {e}; the previous copy is back in place") from e
    return old
