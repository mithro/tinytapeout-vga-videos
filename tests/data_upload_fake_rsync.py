# SPDX-License-Identifier: Apache-2.0
"""A stand-in for `rsync` on PATH in tests/test_data_upload.py.

It records its argv and stdin, runs an optional hook, then runs the real rsync
with the remote destination `FAKE_RSYNC_REMOTE` swapped for the local directory
`FAKE_RSYNC_DEST` (and `--rsh=` dropped), and exits with the real rsync's code
or `FAKE_RSYNC_RC` when that is set.

    FAKE_RSYNC_REAL    the real rsync
    FAKE_RSYNC_RECORD  a JSON-lines file: {"argv": [...], "stdin": "..."} per call
    FAKE_RSYNC_REMOTE  the remote destination argument the script passes ("acct@host:/")
    FAKE_RSYNC_DEST    the local directory that stands for it
    FAKE_RSYNC_HOOK    optional: a /bin/sh command run before the real rsync
    FAKE_RSYNC_RC      optional: the exit code to return instead
"""

import json
import os
import subprocess
import sys


def main() -> int:
    argv = sys.argv[1:]
    stdin = sys.stdin.buffer.read()
    with open(os.environ["FAKE_RSYNC_RECORD"], "a") as f:
        f.write(json.dumps({"argv": argv, "stdin": stdin.decode()}) + "\n")
    hook = os.environ.get("FAKE_RSYNC_HOOK")
    if hook:
        subprocess.run(["/bin/sh", "-c", hook], check=True)
    remote, dest = os.environ["FAKE_RSYNC_REMOTE"], os.environ["FAKE_RSYNC_DEST"]
    if argv[-1] != remote:
        print(f"fake rsync: last argument {argv[-1]!r} is not {remote!r}", file=sys.stderr)
        return 99
    real = [a for a in argv[:-1] if not a.startswith("--rsh=")] + [dest.rstrip("/") + "/"]
    rc = subprocess.run([os.environ["FAKE_RSYNC_REAL"], *real], input=stdin).returncode
    forced = os.environ.get("FAKE_RSYNC_RC")
    return int(forced) if forced else rc


if __name__ == "__main__":
    sys.exit(main())
