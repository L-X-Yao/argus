"""Contract tests for the versioned parameter metadata and translation pack."""

import copy
import hashlib
import json
from pathlib import Path
from shutil import copytree
from unittest.mock import patch

import pytest

import backend.param_meta as pm

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "param_i18n"


@pytest.fixture(autouse=True)
def clear_merged_cache():
    pm._merged_cache.clear()
    pm._selection_cache.clear()
    pm._json_cache.clear()
    pm._validation_cache.clear()
    pm._active_pack = None
    yield
    pm._merged_cache.clear()
    pm._selection_cache.clear()
    pm._json_cache.clear()
    pm._validation_cache.clear()
    pm._active_pack = None


def metadata(vehicle="copter", **kwargs):
    with patch.object(pm, "PACK_DIR", FIXTURE):
        return pm.get_param_metadata(vehicle, **kwargs)


def test_manual_pack_aliases_overrides_and_translation_status():
    result = metadata(locale="zh", series="4.6.3")

    assert result["_meta"] == {
        "vehicle": "copter",
        "series": "4.6.3",
        "locale": "zh",
        "selection": "manual",
        "translation": "partial",
        "translated": 6,
        "total": 7,
        "available_series": ["4.6.3"],
        "data_version": "2026.11.1-fixture",
        "schema": 1,
    }
    assert result["RTL_ALT"]["tr"] == {
        "desc": "返航的最低高度",
        "human": "返航高度",
        "status": "machine",
    }
    assert result["OLD_ALT"]["desc"] == result["RTL_ALT"]["desc"]
    assert result["OLD_ALT"] is not result["RTL_ALT"]
    assert result["SIM_ACC_TRIM_X"]["source"] == "generated"
    assert result["SIM_ACC_TRIM_X"]["tr"] == {"status": "partial"}
    assert result["FLTMODE1"]["tr"]["values"] == {"0": "自稳", "1": "特技", "2": "定高"}
    assert result["LOG_BITMASK"]["tr"]["bitmask"] == {"0": "快速姿态", "1": "姿态", "2": "GPS"}


def test_english_source_does_not_need_a_translation_memory():
    result = metadata(locale="en", series="4.6.3")
    assert result["_meta"]["translation"] == "reviewed"
    assert result["_meta"]["translated"] == result["_meta"]["total"]
    assert all("tr" not in entry for name, entry in result.items() if name != "_meta")


def test_coverage_uses_live_names_and_firmware_breaks_ties(tmp_path):
    pack = tmp_path / "pack"
    for series, extra in (("4.5.7", {"ONLY_OLD": {"desc": "old"}}), ("4.7.1", {"ONLY_NEW": {"desc": "new"}})):
        target = pack / "meta" / "copter"
        target.mkdir(parents=True, exist_ok=True)
        (target / f"{series}.json").write_text(json.dumps({extra and next(iter(extra)): next(iter(extra.values()))}))
    (pack / "meta" / "copter" / "4.6.3.json").write_text((FIXTURE / "meta" / "copter" / "4.6.3.json").read_text())
    manifest = json.loads((FIXTURE / "manifest.json").read_text())
    manifest["sources"] += [
        {"vehicle": "copter", "series": series, "url": "", "sha256": "", "params": 1} for series in ("4.5.7", "4.7.1")
    ]
    pack.mkdir(exist_ok=True)
    (pack / "manifest.json").write_text(json.dumps(manifest))
    for name in ("aliases.json",):
        (pack / name).write_text((FIXTURE / name).read_text())

    with patch.object(pm, "PACK_DIR", pack):
        result = pm.get_param_metadata("copter", fw="v4.5.7", param_names=("ONLY_OLD", "ONLY_NEW"))
    assert result["_meta"]["series"] == "4.5.7"
    assert result["_meta"]["selection"] == "coverage"


def test_firmware_selection_exact_then_floor_then_highest():
    assert metadata(fw="v4.6.3")["_meta"]["selection"] == "fw"
    assert metadata(fw="v4.6.3")["_meta"]["series"] == "4.6.3"
    assert metadata(fw="v4.5.0")["_meta"]["series"] == "4.6.3"


def test_invalid_locale_is_english_and_explicitly_unavailable():
    result = metadata(locale="not-a-locale", series="4.6.3")
    assert result["_meta"]["locale"] == "en"
    assert result["_meta"]["translation"] == "unavailable"
    assert result["_meta"]["translated"] == 0
    assert "tr" not in result["RTL_ALT"]


def test_cached_series_still_reports_the_current_requests_selection():
    assert metadata(series="4.6.3")["_meta"]["selection"] == "manual"
    assert metadata(fw="v4.6.3")["_meta"]["selection"] == "fw"


def test_hot_request_does_not_walk_or_reread_the_pack():
    metadata(series="4.6.3", locale="zh")
    with (
        patch.object(Path, "rglob", side_effect=AssertionError("pack walked again")),
        patch("builtins.open", side_effect=AssertionError("pack read again")),
    ):
        result = metadata(series="4.6.3", locale="zh")
    assert result["RTL_ALT"]["tr"]["status"] == "machine"


def test_unknown_vehicle_and_bad_series_do_not_leak_paths():
    assert metadata(vehicle="unknown") == {}
    result = metadata(series="../../etc/passwd")
    assert result["_meta"]["series"] == "4.6.3"
    assert result["_meta"]["selection"] == "fw"


def test_pack_merge_does_not_mutate_legacy_or_cached_entries():
    legacy = {"RTL_ALT": {"desc": "legacy", "values": {"0": "zero"}}}
    before = copy.deepcopy(legacy)
    with patch.object(pm, "get_metadata", return_value=legacy):
        english = metadata(locale="en", series="4.6.3")
        translated = metadata(locale="zh", series="4.6.3")
        english_again = metadata(locale="en", series="4.6.3")
    assert legacy == before
    assert "tr" not in english["RTL_ALT"]
    assert translated["RTL_ALT"]["tr"]["human"] == "返航高度"
    assert "tr" not in english_again["RTL_ALT"]


def test_missing_or_bad_pack_falls_back_to_english_without_mutating_it(tmp_path):
    legacy = {"P": {"desc": "English", "values": {"0": "Zero"}}}
    before = copy.deepcopy(legacy)
    with patch.object(pm, "PACK_DIR", tmp_path / "missing"), patch.object(pm, "get_metadata", return_value=legacy):
        result = pm.get_param_metadata("copter", locale="zh")
    assert result["P"] == before["P"]
    assert result["_meta"]["translation"] == "unavailable"
    assert legacy == before

    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "manifest.json").write_text("not json")
    with patch.object(pm, "PACK_DIR", bad), patch.object(pm, "get_metadata", return_value=legacy):
        assert pm.get_param_metadata("copter", locale="zh")["P"]["desc"] == "English"


def test_translation_hash_is_exact_utf8_without_normalization():
    text = "Minimum altitude to return to launch"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    tm = json.loads((FIXTURE / "tm" / "zh.json").read_text())
    assert tm[digest]["t"] == "返航的最低高度"


def test_link_param_names_are_a_snapshot_and_firmware_does_not_survive_reset():
    from backend.drone_link import DroneLink

    link = DroneLink()
    link.param_mgr.params["B"] = {"name": "B"}
    link.param_mgr.params["A"] = {"name": "A"}
    assert link.param_names() == ("A", "B")
    assert link.param_mgr.names() == ("A", "B")
    snapshot = link.param_names()
    link.param_mgr.params.clear()
    assert snapshot == ("A", "B")

    link.vehicle.fw_version = "v4.6.3"
    link.vehicle.fw_git = "abc"
    link._reset_session_state()
    assert link.vehicle.fw_version == ""
    assert link.vehicle.fw_git == ""


def test_reviewed_translation_status(tmp_path):
    pack = tmp_path / "pack"
    copytree(FIXTURE, pack)
    tm_path = pack / "tm" / "zh.json"
    tm = json.loads(tm_path.read_text())
    for record in tm.values():
        record["r"] = 1
    tm_path.write_text(json.dumps(tm))
    (pack / "overrides" / "copter.json").write_text("{}")
    with patch.object(pm, "PACK_DIR", pack):
        result = pm.get_param_metadata("copter", locale="zh", series="4.6.3")
    assert result["_meta"]["translation"] == "reviewed"
    assert result["_meta"]["translated"] == result["_meta"]["total"]
    assert result["RTL_ALT"]["tr"]["status"] == "reviewed"


def test_generated_translation_status(tmp_path):
    pack = tmp_path / "pack"
    copytree(FIXTURE, pack)
    tm_path = pack / "tm" / "zh.json"
    tm = json.loads(tm_path.read_text())
    for text, translated in (
        ("Simulated accelerometer trim on the X axis", "模拟 X 轴加速度计配平"),
        ("Simulated accelerometer trim X", "模拟加速度计 X 轴配平"),
    ):
        tm[hashlib.sha256(text.encode()).hexdigest()] = {"t": translated, "r": 1, "s": "generated"}
    for record in tm.values():
        record["r"] = 1
    tm_path.write_text(json.dumps(tm))
    with patch.object(pm, "PACK_DIR", pack):
        result = pm.get_param_metadata("copter", locale="zh", series="4.6.3")
    assert result["SIM_ACC_TRIM_X"]["tr"]["status"] == "generated"
    assert result["_meta"]["translation"] == "generated"
    assert result["_meta"]["translated"] == result["_meta"]["total"]


def test_missing_or_bad_translation_memory_keeps_pack_english(tmp_path):
    for bad in (False, True):
        pack = tmp_path / f"pack-{bad}"
        copytree(FIXTURE, pack)
        tm_path = pack / "tm" / "zh.json"
        if bad:
            tm_path.write_text("bad json")
        else:
            tm_path.unlink()
        with (
            patch.object(pm, "PACK_DIR", pack),
            patch.object(pm, "get_metadata", side_effect=AssertionError("legacy fetch")),
        ):
            result = pm.get_param_metadata("copter", locale="zh", series="4.6.3")
        assert result["_meta"]["translation"] == "unavailable"
        assert result["RTL_ALT"]["desc"] == "Minimum altitude to return to launch"
        assert "tr" not in result["RTL_ALT"]


def test_manifest_change_invalidates_selection_and_merged_caches(tmp_path):
    pack = tmp_path / "pack"
    copytree(FIXTURE, pack)
    with patch.object(pm, "PACK_DIR", pack):
        assert pm.get_param_metadata("copter")["_meta"]["series"] == "4.6.3"
        meta = {"NEW_PARAM": {"desc": "New"}}
        (pack / "meta" / "copter" / "4.7.1.json").write_text(json.dumps(meta))
        manifest_path = pack / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["sources"].append({"vehicle": "copter", "series": "4.7.1", "url": "", "sha256": "", "params": 1})
        manifest_path.write_text(json.dumps(manifest))
        result = pm.get_param_metadata("copter", fw="v4.7.1")
    assert result["_meta"]["series"] == "4.7.1"
    assert result["_meta"]["available_series"] == ["4.6.3", "4.7.1"]
    assert result["NEW_PARAM"]["desc"] == "New"


def test_versioned_and_master_fallbacks(tmp_path):
    legacy = {"P": {"desc": "English"}}
    with (
        patch.object(pm, "PACK_DIR", tmp_path / "missing"),
        patch.object(pm, "_get_versioned_metadata", return_value=legacy) as versioned,
    ):
        result = pm.get_param_metadata("copter", locale="en", fw="v4.6.3")
    versioned.assert_called_once_with("copter", "4.6.3")
    assert result["_meta"]["series"] == "4.6.3"
    assert result["P"]["desc"] == "English"


def test_vehicle_without_pack_sources_uses_english_fallback(tmp_path):
    pack = tmp_path / "pack"
    copytree(FIXTURE, pack)
    manifest_path = pack / "manifest.json"
    manifest_path.write_text(json.dumps({"schema": 1, "data_version": "empty", "sources": []}))
    with patch.object(pm, "PACK_DIR", pack), patch.object(pm, "get_metadata", return_value={"P": {"desc": "E"}}):
        result = pm.get_param_metadata("copter")
    assert result["P"]["desc"] == "E"


def test_bad_legacy_metadata_is_not_returned(tmp_path):
    with (
        patch.object(pm, "PACK_DIR", tmp_path / "missing"),
        patch.object(pm, "get_metadata", return_value={"P": "bad"}),
    ):
        result = pm.get_param_metadata("copter")
    assert list(result) == ["_meta"]
    assert result["_meta"]["total"] == 0
