# SPDX-License-Identifier: Apache-2.0
"""Simulate Tiny VGA compatible Tiny Tapeout projects and record videos."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OVERRIDES_DIR = ROOT / "overrides"
TARGETS_JSON = DATA_DIR / "targets.json"
RESULTS_DIR = DATA_DIR / "results"
HARNESS_DIR = Path(__file__).resolve().parent / "harness"
