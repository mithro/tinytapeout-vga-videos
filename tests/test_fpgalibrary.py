# SPDX-License-Identifier: Apache-2.0
"""Schema 1 checker for fpga-library.json (spec section 1)."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from ttvga import cli, fpgalibrary
from ttvga.fpgalibrary import DEMO_NAMES, check_bins, check_reserved, library_id, load, validate

FIXTURE = Path(__file__).parent / "fixtures" / "fpga-library"


@pytest.fixture
def doc() -> dict:
    return load(FIXTURE / "fpga-library.json")


@pytest.mark.parametrize(
    "shuttle, macro, want",
    [
        ("tt05", "tt_um_flappy_vga_cutout1", "tt05_flappy_vga_cutout1"),
        ("tt07", "tt_um_MichaelBell_rle_vga", "tt07_michaelbell_rle_vga"),
        ("ttsky25a", "tt_um_vga_example", "ttsky25a_vga_example"),
        ("ttihp25a", "tt_um_yuri_panchul_sea_battle_vga_game", "ttihp25a_yuri_panchul_sea_battl_09a2562b"),
        ("ttsky25a", "tt_um_rebeccargb_vga_timing_experiments", "ttsky25a_rebeccargb_vga_timing__4638a050"),
    ],
)
def test_library_id_examples(shuttle, macro, want):
    assert library_id(shuttle, macro) == want


def test_library_id_hashed_is_40_chars():
    got = library_id("ttsky25a", "tt_um_rebeccargb_vga_timing_experiments")
    assert got == "ttsky25a_rebeccargb_vga_timing__4638a050"
    assert len(got) == 40


def test_library_id_refuses_non_tt_um():
    with pytest.raises(ValueError):
        library_id("tt05", "flappy_vga")


def test_check_reserved():
    assert check_reserved("idle_display")
    assert len(DEMO_NAMES) == 5
    for name in DEMO_NAMES:
        assert check_reserved(name)
    assert check_reserved("ttsky25a_vga_example") is None


def test_fixture_is_valid(doc):
    assert validate(doc) == []
    assert check_bins(doc, FIXTURE) == []


def _set(path, value):
    def mutate(d):
        node = d
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value

    return mutate


def _delete(path):
    def mutate(d):
        node = d
        for key in path[:-1]:
            node = node[key]
        del node[path[-1]]

    return mutate


def _dup_id(d):
    d["designs"][1] = copy.deepcopy(d["designs"][0])


def _non_contiguous(d):
    extra = copy.deepcopy(d["designs"][1])
    extra["macro"] = "tt_um_other"
    extra["id"] = library_id(extra["shuttle"], extra["macro"])
    extra["bin"] = f"{extra['shuttle']}/{extra['macro']}/{extra['id']}-{extra['bin_sha256'][:12]}.bin"
    for key in ("poster", "preview_gif", "video_10s_webm"):
        extra[key] = None
    d["designs"].insert(3, extra)


def _unknown_top(d):
    d["future_key"] = {"anything": [1, 2]}


def _unknown_entry(d):
    d["designs"][0]["future_key"] = 1


D0 = ["designs", 0]
P0 = "ttsky25b/tt_um_lukasdragoste_vga_patterns"
CASES = [
    # (id, mutation, field prefix naming the violation)
    ("schema-2", _set(["schema"], 2), "schema"),
    ("schema-bool", _set(["schema"], True), "schema"),
    ("generated-no-z", _set(["generated"], "2026-11-26T03:00:00"), "generated"),
    ("generated-type", _set(["generated"], 5), "generated"),
    ("tthfv-short", _set(["tthfv_commit"], "abc"), "tthfv_commit"),
    ("videos-upper", _set(["videos_repo_commit"], "A" * 40), "videos_repo_commit"),
    ("designs-type", _set(["designs"], {}), "designs"),
    ("top-missing", _delete(["videos_repo_commit"]), "videos_repo_commit"),
    ("entry-not-object", _set(["designs", 0], 5), "designs[0]"),
    ("id-wrong", _set(D0 + ["id"], "ttsky25b_other"), "designs[0].id"),
    ("id-reserved", _set(D0 + ["id"], "idle_display"), "designs[0].id"),
    ("id-duplicate", _dup_id, "designs[1].id"),
    ("shuttle-bad", _set(D0 + ["shuttle"], "TT-SKY"), "designs[0].shuttle"),
    ("shuttle-noncontiguous", _non_contiguous, "designs[3].shuttle"),
    ("macro-no-prefix", _set(D0 + ["macro"], "vga_patterns"), "designs[0].macro"),
    ("title-empty", _set(D0 + ["title"], ""), "designs[0].title"),
    ("title-long", _set(D0 + ["title"], "x" * 201), "designs[0].title"),
    ("author-long", _set(D0 + ["author"], "x" * 201), "designs[0].author"),
    ("author-type", _set(D0 + ["author"], None), "designs[0].author"),
    ("description-long", _set(D0 + ["description"], "x" * 2001), "designs[0].description"),
    ("docs-http", _set(D0 + ["docs_url"], "http://example.com/"), "designs[0].docs_url"),
    ("repo-long", _set(D0 + ["repo_url"], "https://" + "x" * 500), "designs[0].repo_url"),
    ("commit-short", _set(D0 + ["commit"], "abc"), "designs[0].commit"),
    ("clock-zero", _set(D0 + ["clock_hz"], 0), "designs[0].clock_hz"),
    ("clock-big", _set(D0 + ["clock_hz"], 200000001), "designs[0].clock_hz"),
    ("clock-bool", _set(D0 + ["clock_hz"], True), "designs[0].clock_hz"),
    ("clock-float", _set(D0 + ["clock_hz"], 25175000.0), "designs[0].clock_hz"),
    ("pinout-type", _set(D0 + ["pinout"], []), "designs[0].pinout"),
    ("pinout-missing-key", _delete(D0 + ["pinout", "uio"]), "designs[0].pinout.uio"),
    ("pinout-7-labels", _set(D0 + ["pinout", "uo_out"], ["a"] * 7), "designs[0].pinout.uo_out"),
    ("pinout-label-long", _set(D0 + ["pinout", "ui_in"], ["x" * 65] + [""] * 7), "designs[0].pinout.ui_in"),
    ("pinout-label-type", _set(D0 + ["pinout", "uio"], [1] + [""] * 7), "designs[0].pinout.uio"),
    ("mask-256", _set(D0 + ["ui_in_mask"], 256), "designs[0].ui_in_mask"),
    ("mask-bool", _set(D0 + ["ui_in_mask"], True), "designs[0].ui_in_mask"),
    ("ui-in-bool", _set(D0 + ["ui_in"], True), "designs[0].ui_in"),
    ("ui-in-outside-mask", _set(D0 + ["ui_in"], 3), "designs[0].ui_in"),
    ("ui-in-null-mask-1", _set(D0 + ["ui_in"], None), "designs[0].ui_in"),
    ("ui-in-with-mask-0", _set(["designs", 1, "ui_in"], 1), "designs[1].ui_in"),
    ("ui-in-256", _set(D0 + ["ui_in"], 256), "designs[0].ui_in"),
    ("bin-differs", _set(D0 + ["bin"], f"{P0}/x-0123456789ab.bin"), "designs[0].bin"),
    ("bin-dotdot", _set(D0 + ["bin"], f"{P0}/../x.bin"), "designs[0].bin"),
    ("bin-bytes-bool", _set(D0 + ["bin_bytes"], True), "designs[0].bin_bytes"),
    ("fmax-bool", _set(D0 + ["fmax_hz"], True), "designs[0].fmax_hz"),
    ("clock-nan", _set(D0 + ["clock_hz"], float("nan")), "designs[0].clock_hz"),
    ("fmax-inf", _set(D0 + ["fmax_hz"], float("inf")), "designs[0].fmax_hz"),
    ("bin-absolute", _set(D0 + ["bin"], "/etc/passwd"), "designs[0].bin"),
    ("bin-bytes-0", _set(D0 + ["bin_bytes"], 0), "designs[0].bin_bytes"),
    ("bin-bytes-big", _set(D0 + ["bin_bytes"], 262145), "designs[0].bin_bytes"),
    ("sha-upper", _set(D0 + ["bin_sha256"], "A" * 64), "designs[0].bin_sha256"),
    ("build-status", _set(D0 + ["build_status"], "bad"), "designs[0].build_status"),
    ("fmax-float", _set(["designs", 4, "fmax_hz"], 17.5), "designs[4].fmax_hz"),
    ("fmax-zero", _set(D0 + ["fmax_hz"], 0), "designs[0].fmax_hz"),
    ("fmax-big", _set(D0 + ["fmax_hz"], 1000000001), "designs[0].fmax_hz"),
    ("validation-bad", _set(D0 + ["validation"], "partial"), "designs[0].validation"),
    ("verdict-upper", _set(D0 + ["verdict"], "Barely"), "designs[0].verdict"),
    ("verdict-long", _set(D0 + ["verdict"], "a" * 33), "designs[0].verdict"),
    ("qspi-bad", _set(D0 + ["qspi"], "real"), "designs[0].qspi"),
    ("poster-absolute-url", _set(D0 + ["poster"], "https://example.com/p.png"), "designs[0].poster"),
    ("poster-dotdot", _set(D0 + ["poster"], f"{P0}/../p.png"), "designs[0].poster"),
    ("poster-wrong-shuttle", _set(D0 + ["poster"], "ttsky25a/tt_um_lukasdragoste_vga_patterns/p.png"),
     "designs[0].poster"),
    ("poster-wrong-macro", _set(D0 + ["poster"], "ttsky25b/tt_um_vga_example/p.png"), "designs[0].poster"),
    ("poster-type", _set(D0 + ["poster"], 5), "designs[0].poster"),
    ("gif-bad-name", _set(D0 + ["preview_gif"], f"{P0}/.hidden"), "designs[0].preview_gif"),
    ("webm-two-segments", _set(D0 + ["video_10s_webm"], "ttsky25b/v.webm"), "designs[0].video_10s_webm"),
    ("entry-missing-key", _delete(D0 + ["qspi"]), "designs[0].qspi"),
]
ALLOWED = [("unknown-top-key", _unknown_top), ("unknown-entry-key", _unknown_entry)]


@pytest.mark.parametrize("mutate, prefix", [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_each_rule_is_enforced(doc, mutate, prefix):
    mutate(doc)
    got = validate(doc)
    assert len(got) == 1, got
    assert got[0].startswith(prefix + ":"), got


@pytest.mark.parametrize("mutate", [m for _, m in ALLOWED], ids=[n for n, _ in ALLOWED])
def test_unknown_keys_are_allowed(doc, mutate):
    mutate(doc)
    assert validate(doc) == []


def test_top_level_must_be_object():
    assert len(validate([])) == 1


def test_too_many_designs(doc):
    doc["designs"] = [doc["designs"][0]] * 2001
    assert any(v.startswith("designs:") for v in validate(doc))


def test_load_refuses_nan(tmp_path):
    for token in ("NaN", "Infinity", "-Infinity"):
        path = tmp_path / "x.json"
        path.write_text('{"schema": 1, "x": %s}' % token)
        with pytest.raises(ValueError):
            load(path)


def _bins_doc(tmp_path, doc):
    root = tmp_path / "bins"
    shutil.copytree(FIXTURE, root)
    return root


def test_check_bins_catches(tmp_path, doc):
    root = _bins_doc(tmp_path, doc)
    e = doc["designs"]
    # wrong size
    (root / e[0]["bin"]).write_bytes(b"\xff\x00\x00\xff\x7e\xaa\x99\x7e" + bytes(10))
    # wrong hash (same size, same preamble, different byte)
    p1 = root / e[1]["bin"]
    data = bytearray(p1.read_bytes())
    data[100] ^= 1
    p1.write_bytes(bytes(data))
    # no preamble, with the hash and size kept consistent
    p2 = root / e[2]["bin"]
    nopre = bytes(4096)
    p2.write_bytes(nopre)
    e[2]["bin_sha256"] = hashlib.sha256(nopre).hexdigest()
    e[2]["bin"] = f"{e[2]['shuttle']}/{e[2]['macro']}/{e[2]['id']}-{e[2]['bin_sha256'][:12]}.bin"
    p2.rename(root / e[2]["bin"])
    # missing file
    (root / e[3]["bin"]).unlink()
    got = check_bins(doc, root)
    assert len(got) == 4, got
    assert [g.split(":")[0] for g in got] == ["designs[0].bin", "designs[1].bin", "designs[2].bin", "designs[3].bin"]
    assert fpgalibrary.validate(doc) == []


def test_cli_exit_codes(tmp_path, capsys):
    src = FIXTURE / "fpga-library.json"
    assert cli.main(["fpga-library-check", str(src), "--bins", str(FIXTURE)]) == 0
    bad = json.loads(src.read_text())
    bad["designs"][0]["clock_hz"] = 0
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad))
    capsys.readouterr()
    assert cli.main(["fpga-library-check", str(path)]) == 1
    assert "designs[0].clock_hz" in capsys.readouterr().out
    path.write_text('{"schema": NaN}')
    assert cli.main(["fpga-library-check", str(path)]) == 1


def test_load_refuses_non_finite_float(tmp_path):
    path = tmp_path / "x.json"
    path.write_text('{"schema": 1, "x": 1e999}')
    with pytest.raises(ValueError):
        load(path)


def test_check_bins_skips_traversal_bin(doc):
    doc["designs"][0]["bin"] = f"{P0}/../x.bin"
    assert check_bins(doc, FIXTURE) == []


def test_check_bins_refuses_oversize_without_reading(tmp_path, doc):
    root = _bins_doc(tmp_path, doc)
    path = root / doc["designs"][0]["bin"]
    path.write_bytes(bytes(262145))
    got = check_bins(doc, root)
    assert len(got) == 1 and "over 262144" in got[0]


# Doubly-faulty entries: the dependent violation is deferred, but the entry still fails.
def _doubly_shuttle(d):
    d["designs"][0]["shuttle"] = "TT-SKY"
    d["designs"][0]["id"] = "wrong"


def _doubly_mask(d):
    d["designs"][0]["ui_in_mask"] = 256
    d["designs"][0]["ui_in"] = 3


def _doubly_sha(d):
    d["designs"][0]["bin_sha256"] = "A" * 64
    d["designs"][0]["bin"] = f"{P0}/wrong-0123456789ab.bin"


@pytest.mark.parametrize(
    "mutate, field",
    [(_doubly_shuttle, "shuttle"), (_doubly_mask, "ui_in_mask"), (_doubly_sha, "bin_sha256")],
)
def test_deferred_dependent_checks(doc, mutate, field, tmp_path, capsys):
    mutate(doc)
    got = validate(doc)
    assert got and any(v.startswith(f"designs[0].{field}:") for v in got)
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(doc))
    assert cli.main(["fpga-library-check", str(path)]) == 1
    out = capsys.readouterr().out
    assert f"designs[0].{field}:" in out
    assert "dependent checks deferred" in out


def test_cli_reports_non_finite_and_recursion(tmp_path, capsys):
    path = tmp_path / "x.json"
    path.write_text('{"schema": 1e999}')
    assert cli.main(["fpga-library-check", str(path)]) == 1
    assert "finite" in capsys.readouterr().out
    path.write_text("[" * 100000 + "]" * 100000)
    assert cli.main(["fpga-library-check", str(path)]) == 1
    assert "RecursionError" in capsys.readouterr().out
