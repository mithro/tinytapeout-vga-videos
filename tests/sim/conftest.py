# SPDX-License-Identifier: Apache-2.0
"""Fixtures shared by the simulation tests: the dev-tools paths and models built once a session."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.sim.build import build_model


@pytest.fixture(scope="session")
def dev():
    from ttvga import devtools

    d = devtools.paths()
    d.require("verilator", "ffmpeg_sink")
    return d


@pytest.fixture(scope="session")
def models(dev, tmp_path_factory):
    """Each model is built once per session, on first use."""
    root = tmp_path_factory.mktemp("models")
    cache: dict[tuple[str, bool, tuple[str, ...]], Path] = {}

    def get(design: str, test_hooks: bool = True, defines: tuple[str, ...] = ()) -> Path:
        key = (design, test_hooks, defines)
        if key not in cache:
            name = design + ("" if test_hooks else "-prod") + "".join("-" + d.lower() for d in defines)
            cache[key] = build_model(design, dev, root / name, test_hooks, defines)
        return cache[key]

    return get
