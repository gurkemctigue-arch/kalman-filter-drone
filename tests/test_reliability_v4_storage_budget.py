"""Synthetic metadata/accounting fixtures; never real archives or admission.

These tests are intentionally independent from ROS/PX4/Gazebo. Files with bag
suffixes contain inert size placeholders, and their contents must not be read.
"""
from copy import deepcopy
from contextlib import redirect_stderr
import importlib.util
import io
import json
import math
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("storage_budget_fixture", ROOT / "tools/reliability_v4_storage_budget.py")
budget = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(budget)
guard = budget.guard


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, allow_nan=False), encoding="utf-8")
    return path


def seal(data, field):
    data[field] = guard.sealed(data, field)
    return data


class FakeStorage:
    """Metadata backend double; cannot certify actual volumes or a VHD."""
    def __init__(self, vhd):
        self.vhd = vhd
        self.free = 10**15
        self.logical = 10**16
        self.queries = []

    def volume(self, specification):
        self.queries.append(specification["id"])
        return {"mount": specification["mount"], "windows_volume_id": specification["windows_volume_id"],
                "free_bytes": self.free}

    def vhd_path(self, distribution):
        return self.vhd.resolve(strict=True)

    def logical_free(self, root):
        return self.logical


def fixture(temporary, *, split=False):
    base = Path(temporary).resolve()
    mounts = {name: base / name for name in (("D", "E") if split else ("D",))}
    for mount in mounts.values():
        mount.mkdir()
    root = mounts["D"] / "source"
    results = root / "results"
    sizes = results / "freeze_validation/artifact_storage"
    sizes.mkdir(parents=True)
    vhd = mounts["E" if split else "D"] / "ext4.vhdx"
    vhd.write_bytes(b"fixture placeholder, not a virtual disk")
    plans, plan_paths, samples = {}, {}, []
    for label, groups in (("core", guard.GROUPS), ("extension", guard.CONDITIONS)):
        output = results / (label + "_matrix")
        plan = {"schema_version": 1, "study_kind": "POST_REPAIR_ENGINEERING_VALIDATION",
                "mode": "PROBE" if label == "core" else "EXTENSION_PROBE", "selected_seeds": [4],
                "selected_classes": list(guard.CLASSES), "selected_groups": list(guard.GROUPS),
                "selected_extension_conditions": list(guard.CONDITIONS), "frozen_root": str(root),
                "results_root": str(results), "output": str(output),
                "source_hashes": {"fixture.py": "1" * 64}, "model_hashes": {"fixture.pt": "2" * 64}, "trials": []}
        for cls in guard.CLASSES:
            for group in groups:
                name = f"{label}_{cls}_{group}_seed004"
                trial = {"id": name, "name": name, "seed": 4, "target_class": cls,
                         "group": group, "extension_condition": group, "duration_s": 45.,
                         "directory": str(results / name)}
                plan["trials"].append(trial)
        write(output / "plan.json", seal(plan, "plan_sha256"))
        plans[label], plan_paths[label] = plan, output / "plan.json"
        for trial in plan["trials"]:
            directory = Path(trial["directory"])
            (directory / "rosbag").mkdir(parents=True)
            count = 10 + len(samples)
            compressed = directory / "rosbag/data.db3.zstd"
            compressed.write_bytes(b"x" * count)
            (directory / "telemetry.jsonl").write_bytes(b"inert fixture")
            archive = {"status": "PASS", "policy": budget.ARCHIVE_POLICY,
                       "raw_validation": {"status": "PASS", "files": [{"path": "data.db3", "bytes": count * 3}]},
                       "compressed_files": [{"path": "data.db3.zstd", "bytes": count, "raw_bytes": count * 3}],
                       "native_reader_validation": {"full_stream_read": True}}
            summary = {"termination_reason": "follow_duration_reached", "follow_start_s": 18., "end_sim_s": 62.98}
            closure = {"status": "PASS", "observations": [{"last_clock_ns": 64_000_000_000}]}
            for relative, data in (("bag_integrity.json", archive), ("summary.json", summary),
                                   ("recording_closure.json", closure)):
                write(directory / relative, data)
            paths = budget.sample_paths(plan, trial, sizes)
            record = {"id": trial["id"], "plan_sha256": plan["plan_sha256"], "infrastructure_stop": False,
                      "execution_status": "COMPLETED", "flight_exit_code": 0,
                      "status": "FAIL" if not samples else "EVALUATION_PENDING",
                      "artifact_hashes": {name: guard.sha(directory / name) for name in
                                          ("bag_integrity.json", "summary.json", "recording_closure.json")}}
            write(paths["terminal"], seal(record, "record_sha256"))
            files = {name: (directory / name).stat().st_size for name in
                     ("bag_integrity.json", "summary.json", "recording_closure.json", "rosbag/data.db3.zstd", "telemetry.jsonl")}
            size = {"scope": "FILE_SIZE_ACCOUNTING_ONLY_NO_VERDICT_CHANGE", "trial": trial["directory"],
                    "files": files, "total_trial_bytes": sum(files.values())}
            write(paths["size"], size)
            samples.append({"trial": trial, "paths": paths, "size": size, "archive": archive,
                            "summary": summary, "record": record, "count": count})
    inventory = {"schema_version": 1, "kind": "RELIABILITY_V4_PHYSICAL_STORAGE_INVENTORY",
                 "created_utc": "2026-10-20T00:00:00+00:00", "evidence_scope": "METADATA_ONLY_NOT_FORMAL_ADMISSION",
                 "volumes": [{"mount": str(mount), "windows_volume_id": "fixture-" + name, "free_bytes": 1}
                             for name, mount in mounts.items()],
                 "vhd_host": {"distribution": "FIXTURE", "path": str(vhd)}}
    identifiers = {"drive_" + name for name in mounts}
    amounts = lambda value: {name: value for name in identifiers}
    assumptions = {"schema_version": 1, "kind": budget.ASSUMPTIONS_KIND,
        "basis": "Synthetic fixture assumptions, never real capacity evidence",
        "persistent_growth_factor": 1.25, "raw_growth_factor": 1.1, "compressed_growth_factor": 1.2,
        "persistent_extra_bytes_by_volume": amounts(0), "temporary_extra_bytes_by_volume": amounts(4096),
        "additional_remaining_bytes": amounts(20), "additional_remaining_basis": "Explicit fixture build budget",
        "persistent_basis": "Explicit fixture persistent margin", "temporary_basis": "Declared bound, not measured peak",
        "delivery_reservations": {purpose: {"bytes_by_volume": amounts(100), "basis": "Explicit fixture task"}
                                  for purpose in guard.DELIVERIES}}
    inventory_path = write(base / "inventory.json", inventory)
    assumptions_path = write(base / "assumptions.json", assumptions)
    backend = FakeStorage(vhd)
    arguments = {"core_path": plan_paths["core"], "extension_path": plan_paths["extension"],
                 "size_directory": sizes, "inventory_path": inventory_path, "assumptions_path": assumptions_path}
    return SimpleNamespace(root=root, results=results, plans=plans, paths=plan_paths, samples=samples,
        inventory=inventory, inventory_path=inventory_path, assumptions=assumptions,
        assumptions_path=assumptions_path, backend=backend, arguments=arguments)


def update_named_sample(sample, name, data):
    """Keep a synthetic record/size receipt consistent with a changed JSON."""
    path = sample["paths"][name]
    write(path, data)
    relative = path.name
    sample["record"]["artifact_hashes"][relative] = guard.sha(path)
    write(sample["paths"]["terminal"], seal(sample["record"], "record_sha256"))
    sample["size"]["files"][relative] = path.stat().st_size
    sample["size"]["total_trial_bytes"] = sum(sample["size"]["files"].values())
    write(sample["paths"]["size"], sample["size"])


class StorageBudgetTests(unittest.TestCase):
    def test_complete28_preserves_failures_and_has_no_acceptance_claim(self):
        with tempfile.TemporaryDirectory() as temporary:
            f = fixture(temporary)
            result = budget.assemble(**f.arguments, backend=f.backend)
            self.assertEqual(result["kind"], budget.KIND)
            self.assertFalse(result["admission_performed"])
            self.assertNotIn("status", result)
            self.assertNotIn("result", result)
            self.assertEqual(len(result["storage"]["cells"]), 28)
            self.assertEqual(result["storage_sha256"], guard.canonical(result["storage"]))
            statuses = result["provenance"]["original_development_statuses"]
            self.assertEqual(sum(s["status"] == "FAIL" for s in statuses), 1)
            self.assertEqual(sum(s["status"] == "EVALUATION_PENDING" for s in statuses), 27)
            self.assertEqual(f.backend.queries, ["drive_D"])

    def test_same_volume_aggregates280_once_and_uses_largest_archive_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            f = fixture(temporary)
            result = budget.assemble(**f.arguments, backend=f.backend)
            actual = result["capacity_preview"]["volumes"]["drive_D"]
            expected = 10 * sum(math.ceil(s["size"]["total_trial_bytes"] * 1.25) for s in f.samples)
            self.assertEqual(actual["full_280_persistent_bytes"], expected)
            bound = max(3 * math.ceil(s["count"] * 3 * 1.1) + 2 * math.ceil(s["count"] * 1.2) for s in f.samples) + 4096
            self.assertEqual(result["storage"]["temporary_peak_bytes"], {"drive_D": bound})
            self.assertEqual(actual["temporary_reserve_bytes"], guard.MIN_RESERVE)
            self.assertEqual(actual["remaining_build_delivery_bytes"], 520)

    def test_split_volume_explicit_zero_persistent_keeps_full_temporary_bound_on_each(self):
        with tempfile.TemporaryDirectory() as temporary:
            f = fixture(temporary, split=True)
            result = budget.assemble(**f.arguments, backend=f.backend)
            storage = result["storage"]
            self.assertEqual(storage["vhd_host"]["volume"], "drive_E")
            self.assertEqual(storage["temporary_peak_bytes"]["drive_D"], storage["temporary_peak_bytes"]["drive_E"])
            self.assertTrue(all(cell["persistent_bytes_by_volume"]["drive_E"] == 0 for cell in storage["cells"]))
            self.assertEqual(result["capacity_preview"]["volumes"]["drive_E"]["temporary_reserve_bytes"], guard.MIN_RESERVE)

    def test_missing_receipt_reports_original_cell_without_substitution(self):
        with tempfile.TemporaryDirectory() as temporary:
            f = fixture(temporary)
            sample = f.samples[-1]
            sample["paths"]["size"].unlink()
            with self.assertRaises(budget.MissingEvidence) as caught:
                budget.assemble(**f.arguments, backend=f.backend)
            self.assertEqual(caught.exception.missing[0]["condition"], sample["trial"]["extension_condition"])
            self.assertEqual(caught.exception.missing[0]["missing_evidence"], "size")
            self.assertEqual(f.backend.queries, [])

    def test_bag_vhd_and_telemetry_contents_are_never_opened(self):
        with tempfile.TemporaryDirectory() as temporary:
            f = fixture(temporary)
            original = Path.open
            def checked_open(path, *args, **kwargs):
                if "rosbag" in path.parts or path.suffix in {".vhdx", ".jsonl", ".db3", ".zstd", ".zst"}:
                    self.fail("Forbidden data contents read: " + str(path))
                return original(path, *args, **kwargs)
            with patch.object(Path, "open", checked_open):
                result = budget.assemble(**f.arguments, backend=f.backend)
            self.assertEqual(len(result["storage"]["cells"]), 28)

    def test_recorded_size_change_refuses_without_hashing_the_changed_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            f = fixture(temporary)
            data = Path(f.samples[0]["trial"]["directory"]) / "telemetry.jsonl"
            data.write_bytes(b"longer synthetic placeholder")
            with self.assertRaisesRegex(guard.Refusal, "accounting size changed"):
                budget.assemble(**f.arguments, backend=f.backend)

    def test_source_mismatch_and_duplicate_cell_refuse(self):
        for mutation in ("source", "duplicate"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                f = fixture(temporary)
                plan = f.plans["extension"]
                if mutation == "source":
                    plan["source_hashes"] = {"different.py": "3" * 64}
                else:
                    plan["trials"][-1] = deepcopy(plan["trials"][0])
                write(f.paths["extension"], seal(plan, "plan_sha256"))
                with self.assertRaises(guard.Refusal):
                    budget.assemble(**f.arguments, backend=f.backend)

    def test_short_or_aborted_recording_cannot_be_used_for_full_exposure(self):
        for field in ("termination", "clock"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                f = fixture(temporary)
                sample = f.samples[0]
                if field == "termination":
                    update_named_sample(sample, "summary", {**sample["summary"], "termination_reason": "flight_aborted"})
                else:
                    update_named_sample(sample, "closure", {"status": "PASS", "observations": [{"last_clock_ns": 62_000_000_000}]})
                with self.assertRaises(guard.Refusal):
                    budget.assemble(**f.arguments, backend=f.backend)

    def test_forged_terminal_without_completed_zero_exit_is_rejected(self):
        for field, value in (("execution_status", "RUNNING"), ("flight_exit_code", 2), ("flight_exit_code", False)):
            with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as temporary:
                f = fixture(temporary)
                sample = f.samples[0]
                sample["record"][field] = value
                write(sample["paths"]["terminal"], seal(sample["record"], "record_sha256"))
                with self.assertRaisesRegex(guard.Refusal, "Incomplete/infrastructure"):
                    budget.assemble(**f.arguments, backend=f.backend)

    def test_invalid_growth_and_missing_delivery_source_refuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            f = fixture(temporary)
            for value in (True, .99, float("nan"), float("inf")):
                data = {**f.assumptions, "raw_growth_factor": value}
                with self.subTest(value=value), self.assertRaises(guard.Refusal):
                    budget.assumptions_contract(data, {"drive_D"})
            data = deepcopy(f.assumptions)
            data["delivery_reservations"]["videos12"]["bytes_by_volume"]["drive_D"] = 0
            with self.assertRaisesRegex(guard.Refusal, "Unbudgeted"):
                budget.assumptions_contract(data, {"drive_D"})
            data = {**f.assumptions, "status": "REGISTERED"}
            with self.assertRaises(guard.Refusal):
                budget.assumptions_contract(data, {"drive_D"})

    def test_current_physical_free_overrides_old_inventory_and_logical_free(self):
        with tempfile.TemporaryDirectory() as temporary:
            f = fixture(temporary)
            f.backend.free = 1
            f.backend.logical = 10**18
            result = budget.assemble(**f.arguments, backend=f.backend)
            physical = result["capacity_preview"]["volumes"]["drive_D"]
            self.assertFalse(physical["fits_declared_physical_budget"])
            self.assertLess(physical["remaining_after_budget_bytes"], 0)
            self.assertTrue(result["capacity_preview"]["fits_declared_logical_budget"])
            self.assertFalse(result["admission_performed"])

    def test_duplicate_host_identity_and_changed_registry_vhd_refuse(self):
        for mutation in ("alias", "vhd"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                f = fixture(temporary, split=True)
                if mutation == "alias":
                    f.inventory["volumes"][1]["windows_volume_id"] = f.inventory["volumes"][0]["windows_volume_id"]
                    write(f.inventory_path, f.inventory)
                else:
                    other = f.root.parent / "other.vhdx"
                    other.write_bytes(b"not a real VHD")
                    f.backend.vhd = other
                with self.assertRaises(guard.Refusal):
                    budget.assemble(**f.arguments, backend=f.backend)

    def test_consumer_guard_accepts_assembled_storage_shape_and_arithmetic(self):
        with tempfile.TemporaryDirectory() as temporary:
            f = fixture(temporary)
            result = budget.assemble(**f.arguments, backend=f.backend)
            formal, rows = {}, {}
            for label in ("core", "extension"):
                formal[label] = {"results_root": str(f.results), "trials": []}
                references = [{"plan_path": str(f.paths[label]), "slot_id": t["id"]} for t in f.plans[label]["trials"]]
                if label == "core":
                    formal[label]["development_probe_gate"] = {"evidence": {"probe_slots": references}}
                else:
                    formal["core"]["extension_protocol_binding"] = {"protocol": {"development_readiness": {"evidence": {"probe_slots": references}}}}
                rows[label] = {}
                for trial in f.plans[label]["trials"]:
                    for seed in range(1000, 1010):
                        item = {**trial, "id": trial["id"] + str(seed)}
                        formal[label]["trials"].append(item)
                        rows[label][item["id"]] = {"status": "PENDING"}
            context = SimpleNamespace(root=f.root, **formal)
            runtime = SimpleNamespace(v4=SimpleNamespace(load=guard.load))
            checked = guard.validate_storage({"storage": result["storage"]}, context, runtime, rows, f.backend)
            self.assertEqual(checked["pending_slots"], 280)
            self.assertEqual(checked["volumes"]["drive_D"]["required_bytes"],
                             result["capacity_preview"]["volumes"]["drive_D"]["required_bytes"])

    def test_cli_missing_cell_creates_no_output_and_never_calls_backend(self):
        with tempfile.TemporaryDirectory() as temporary:
            f = fixture(temporary)
            f.samples[-1]["paths"]["size"].unlink()
            output = Path(temporary) / "new-budget.json"
            args = ["--core-development-plan", str(f.paths["core"]), "--extension-development-plan", str(f.paths["extension"]),
                    "--size-evidence-dir", str(f.arguments["size_directory"]), "--physical-inventory", str(f.inventory_path),
                    "--assumptions", str(f.assumptions_path), "--output", str(output)]
            with patch.object(guard, "NativeStorage", side_effect=AssertionError("Backend must not be called")), redirect_stderr(io.StringIO()) as stream:
                code = budget.main(args)
            self.assertEqual(code, 2)
            self.assertFalse(output.exists())
            self.assertEqual(json.loads(stream.getvalue())["result"], "REFUSED_NOT_ADMISSION")

    def test_output_rejects_source_build_trial_plan_and_receipt_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            f = fixture(temporary)
            result = budget.assemble(**f.arguments, backend=f.backend)
            forbidden = [f.root / "config/new-budget.json", f.root / "ros2_ws/build/new-budget.json",
                         f.root / "ros2_ws/install/new-budget.json", ROOT / "config/new-budget.json",
                         Path(f.samples[0]["trial"]["directory"]) / "new/budget.json",
                         f.paths["core"].parent / "new/budget.json",
                         f.arguments["size_directory"] / "new/budget.json"]
            for output in forbidden:
                with self.subTest(output=output), self.assertRaises(guard.Refusal):
                    budget.require_independent_output(output, result)
            budget.require_independent_output(f.results / "independent-new-budget/budget.json", result)
            budget.require_independent_output(Path(temporary) / "outside-project/budget.json", result)
            self.assertFalse((f.results / "independent-new-budget").exists())

    def test_cli_existing_output_is_preserved_before_any_input_is_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "old.json"
            output.write_bytes(b"preserved")
            args = []
            for name in ("core-development-plan", "extension-development-plan", "size-evidence-dir", "physical-inventory", "assumptions"):
                args += ["--" + name, "absent"]
            args += ["--output", str(output)]
            with patch.object(budget, "assemble", side_effect=AssertionError("No assembly permitted")), redirect_stderr(io.StringIO()):
                self.assertEqual(budget.main(args), 2)
            self.assertEqual(output.read_bytes(), b"preserved")


if __name__ == "__main__":
    unittest.main()
