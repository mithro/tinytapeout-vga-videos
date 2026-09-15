# SPDX-License-Identifier: Apache-2.0
"""`tt-vga`: one entry point, one sub-command per stage of the pipeline."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tt-vga", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    from ttvga import targets

    targets.add_parser(sub)

    args = parser.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
