# SPDX-License-Identifier: Apache-2.0
"""Publish a finished project directory into the frames subtree. Runs on the host.

A job builds `<scratch>` on the root volume. `install` checks it against an
allow-list, copies it to `<staging_dir>/<shuttle>_<macro>.new` on the bulk
volume (the same filesystem as `<frames_root>`), carries named entries over
from the published copy by hard link, and swaps the result into
`<frames_root>/<shuttle>/<macro>` with one `renameat2(RENAME_EXCHANGE)`: at no
instant is the published directory missing or half-copied, and the old one is
deleted only after the swap. Each publish is appended to
`<staging_dir>/changed.log`, which the root-owned upload reads.

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
import fnmatch
import os
import re
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

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
    "method": r"[a-z0-9]+(?:-[a-z0-9]+)*",
    "NNNNNN": r"[0-9]{6}",
}
_PROJECT_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")

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


def _violations(top: Path, stem: str, extra_files: tuple[str, ...] = ()) -> list[str]:
    files, dirs = _rules(stem)
    out = []
    try:
        st = os.lstat(top)
    except FileNotFoundError:
        return [f"{top}: missing"]
    if not stat.S_ISDIR(st.st_mode):
        return [f"{top}: not a directory"]

    def walk(path: Path, rel: str) -> None:
        with os.scandir(path) as it:
            entries = sorted(it, key=lambda e: e.name)
        for entry in entries:
            name = f"{rel}{entry.name}"
            mode = entry.stat(follow_symlinks=False).st_mode
            if stat.S_ISLNK(mode):
                out.append(f"{name!r}: symlink")
            elif stat.S_ISDIR(mode):
                if name in dirs:
                    walk(Path(entry.path), name + "/")
                else:
                    out.append(f"{name!r}: directory not allowed")
            elif not stat.S_ISREG(mode):
                out.append(f"{name!r}: not a regular file")
            elif name not in extra_files and not any(r.fullmatch(name) for r in files):
                out.append(f"{name!r}: name not allowed")

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


def _run(cmd: list[str], log: Path) -> None:
    with open(log, "ab") as f:
        f.write(f"$ {' '.join(cmd)}\n".encode())
        f.flush()
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    if result.returncode:
        raise PublishError(f"{cmd[0]} exited {result.returncode}; see {log}")


def install(scratch: Path, conf, shuttle: str, macro: str, log: Path, carry: list[str] = ()) -> None:
    """Publish `scratch` as `<frames_root>/<shuttle>/<macro>`, carrying `carry` over from the published copy."""
    for label, name in (("shuttle", shuttle), ("macro", macro)):
        if not _PROJECT_NAME.fullmatch(name):
            raise PublishError(f"bad {label} name {name!r}")
    scratch, log = Path(scratch), Path(log)
    stem = stem_for(shuttle, macro)
    shuttle_dir = conf.frames_root / shuttle
    dest = shuttle_dir / macro
    new = conf.staging_dir / f"{stem}.new"
    old = conf.staging_dir / f"{stem}.old"

    # 1. Refuse anything unsafe before touching the filesystem.
    violations = check_allowed(scratch, stem)
    if violations:
        raise PublishError(f"{scratch} holds entries that may not be published: {'; '.join(violations)}")
    if os.path.lexists(shuttle_dir) and (shuttle_dir.is_symlink() or not shuttle_dir.is_dir()):
        raise PublishError(f"{shuttle_dir} is not a directory")
    _check_published(dest)
    # A crash between the fallback's two renames leaves the published copy at .old.
    restore = not os.path.lexists(dest) and os.path.lexists(old)
    if restore:
        _check_published(old)
    source = old if restore else dest
    top_names = {f"{stem}_trace.vgch.zst", *SAMPLERS}
    carry = list(carry)
    for name in carry:
        if name not in top_names:
            raise PublishError(f"cannot carry {name!r}: only {sorted(top_names)}")
        if os.path.lexists(scratch / name):
            raise PublishError(f"cannot carry {name!r}: {scratch} already holds it")
        if not os.path.lexists(source / name):
            raise PublishError(f"cannot carry {name!r}: {dest} does not hold it")

    # 2. Permissions, and the shuttle directory.
    os.umask(0o022)
    shuttle_dir.mkdir(mode=0o755, exist_ok=True)

    # 3. Leftovers of an earlier, interrupted install.
    _remove(new)
    if restore:
        os.rename(old, dest)
    else:
        _remove(old)

    try:
        # 4. The copy, with the marker.
        _run(["rsync", "-aH", "--delete", "--chmod=D0755,F0644", f"{scratch}/", f"{new}/"], log)
        (new / PROJECT_MARKER).write_bytes(b"")
        # 5. Carry-over by hard link: staging and frames_root are one filesystem.
        for name in carry:
            _run(["cp", "-al", str(dest / name), str(new / name)], log)
        # The whole new tree, as it will be published, is checked once more.
        violations = _violations(new, stem, extra_files=(PROJECT_MARKER,))
        if violations:
            raise PublishError(f"{new} holds entries that may not be published: {'; '.join(violations)}")
    except BaseException:
        _remove(new)
        raise

    # 6 and 7. The swap; the old copy is deleted only once the new one is in place.
    if not os.path.lexists(dest):
        os.rename(new, dest)
    elif exchange(new, dest):
        shutil.rmtree(new)
    else:
        os.rename(dest, old)
        os.rename(new, dest)
        shutil.rmtree(old)

    # 8. One whole line per publish, for the upload.
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {shuttle}/{macro}\n".encode()
    fd = os.open(conf.staging_dir / CHANGED_LOG, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_CLOEXEC, 0o644)
    try:
        written = os.write(fd, line)
    finally:
        os.close(fd)
    if written != len(line):
        raise PublishError(f"short write to {conf.staging_dir / CHANGED_LOG}: {written} of {len(line)} bytes")
