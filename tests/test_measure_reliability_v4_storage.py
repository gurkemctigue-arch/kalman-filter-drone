"""Synthetic original records; no flight, native bag decode or payload reads."""
from __future__ import annotations

from contextlib import redirect_stderr
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from tests import test_reliability_v4_runner as fixtures
from tests import test_reliability_v4_extensions as extensions

SPEC = importlib.util.spec_from_file_location(
    "storage_measurement_fixture", fixtures.ROOT / "tools/measure_reliability_v4_storage.py")
measurement = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(measurement)
guard, v4 = measurement.guard, fixtures.v4
STAMP = "2026-10-20T01:00:00+00:00"
FINISH = "2026-10-20T01:02:00+00:00"
EVAL_START = "2026-10-20T01:03:00+00:00"
EVAL_END = "2026-10-20T01:04:00+00:00"


def write(path, data):
    fixtures.write(path, data)
    return path


def fixture(base):
    root = Path(base).resolve() / "source"
    root.mkdir()
    extensions.extension_fixture(root)
    for relative in ("scripts/run_reliability_v4.py", "uav_tracking/research_failures.py"):
        shutil.copyfile(fixtures.ROOT / relative, root / relative)
    core = fixtures.make_fixture_plan(root, "results/core", "reliability_v4_fixture_core",
        seeds=[4], classes=list(v4.CLASSES), groups=list(v4.GROUPS))
    extension = extensions.make(root, output="results/extension", prefix="reliability_v4_fixture_extension", seeds=[4])
    plans = {"core": core, "extension": extension}
    paths, samples = {}, []
    for label, plan in plans.items():
        v4.persist_plan(plan)
        paths[label] = Path(plan["output"]) / "plan.json"
        for trial in plan["trials"]:
            directory = Path(trial["directory"])
            logdir = Path(plan["output"]) / "logs"
            logdir.mkdir(exist_ok=True)
            fake = fixtures.FakeCommands(surface="FAIL" if not samples else "PASS")
            flight = fake(trial["flight_command"], logdir / (trial["id"] + ".flight.log"), root, 1.)
            flight.update(started_utc=STAMP, finished_utc=FINISH)
            config = v4.load(directory / "run_config.json")
            config["no_bag"] = False
            write(directory / "run_config.json", config)
            snapshot = {name: digest for name, digest in plan["source_hashes"].items()
                        if name.startswith(("scripts/", "uav_tracking/", "ros2_ws/src/"))
                        and Path(name).suffix in {".py", ".sh", ".msg"}}
            snapshot[trial["model"]] = plan["model_hashes"][trial["model"]]
            write(directory / "configuration/source_sha256.json", snapshot)
            (directory / "telemetry.jsonl").write_bytes(b"inert synthetic telemetry; never read by size tool")
            (directory / "rosbag/data.db3.zstd").write_bytes(b"x" * 24)  # Inert size placeholder.
            metadata = directory / "rosbag/metadata.yaml"
            archive = {"schema_version": 1, "status": "PASS", "policy": measurement.budget.ARCHIVE_POLICY,
                "destination": str(directory / "rosbag"), "source_spool": "/historical/removed/fixture_spool",
                "recorder_exit_code": 0, "spool_retained": False,
                "raw_validation": {"status": "PASS", "message_count": 10, "topic_counts": {"/clock": 10},
                    "files": [{"path": "data.db3", "bytes": 240, "sha256": "1" * 64}]},
                "native_reader_validation": {"status": "PASS", "full_stream_read": True,
                    "message_count": 10, "topic_counts": {"/clock": 10}},
                "compressed_files": [{"path": "data.db3.zstd", "bytes": 24, "sha256": "2" * 64,
                    "raw_bytes": 240, "raw_sha256": "1" * 64, "zstd_test": "PASS"}],
                "published_metadata_sha256": v4.sha(metadata)}
            write(directory / "bag_integrity.json", archive)
            write(directory / "summary.json", {"termination_reason": "follow_duration_reached", "follow_start_s": 18.})
            write(directory / "recording_closure.json", {"schema_version": 1, "status": "PASS",
                "scope": "WORLD_PAUSE_ACK_AND_OBSERVED_FINAL_SOURCE_CORRESPONDENCE_BEFORE_RECORDER_CLOSE",
                "pause_request": {"command_pause": True, "returncode": 0, "response": "data: true"},
                "observer_cleanup_completed": True, "closed_streams_elapsed_wall_s": .1,
                "observations": [{"ready": True, "failures": [], "errors": [],
                    "missing_truth_frames_at_final_clock": [], "last_clock_ns": 94_000_000_000}]})
            entries = []
            for spec in trial["evaluations"]:
                execution = fake(spec["command"], logdir / (trial["id"] + "." + spec["kind"] + ".log"), root, 1.)
                execution.update(started_utc=EVAL_START, finished_utc=EVAL_END)
                entries.append(v4.read_evaluation(spec, execution, plan))
            record = {"status": "FAIL" if not samples else "PASS", "engineering_result": "FAIL" if not samples else "PASS",
                "execution_status": "COMPLETED", "flight_exit_code": 0, "infrastructure_stop": False,
                "runtime_configuration": {"errors": [], "run_config_sha256": v4.sha(directory / "run_config.json"),
                    "runtime_parameters_sha256": v4.sha(directory / "configuration/runtime_parameters.yaml")},
                "cleanup": {"residual_processes": []},
                "commands": [{"kind": "flight", **flight}], "evaluations": entries}
            v4.finalize(plan, trial, record)
            samples.append(SimpleNamespace(plan=plan, trial=trial, directory=directory,
                                           record=v4.load(v4.record_path(plan, trial))))
    return SimpleNamespace(root=root, results=root / "results", plans=plans, paths=paths, samples=samples,
                           output=root / "results/new_size_evidence")


def change_report(sample, relative, data, *, rebind=True):
    write(sample.directory / relative, data)
    if rebind:
        sample.record["artifact_hashes"][relative] = v4.sha(sample.directory / relative)
        for entry in sample.record["evaluations"]:
            if Path(entry["report"]).name == relative:
                entry["report_sha256"] = sample.record["artifact_hashes"][relative]
        sample.record["record_sha256"] = v4.digest(sample.record, ("record_sha256",))
        write(v4.record_path(sample.plan, sample.trial), sample.record)


class StorageMeasurementTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.f = fixture(self.temporary.name)

    def measure(self, **kwargs):
        return measurement.measure(self.f.paths["core"], self.f.paths["extension"], self.f.output, **kwargs)

    def test_all28_and_engineering_failure_preserved_and_budget_schema_consumable(self):
        originals = {str(v4.record_path(s.plan, s.trial)): v4.sha(v4.record_path(s.plan, s.trial)) for s in self.f.samples}
        original_names = {str(path.relative_to(self.f.root)) for path in self.f.root.rglob("*") if path.is_file()}
        summary = self.measure()
        self.assertEqual(summary["planned_count"], summary["measured_count"])
        self.assertEqual(summary["measured_count"], 28)
        self.assertEqual(summary["original_status_counts"], {"FAIL": 1, "PASS": 27})
        self.assertFalse(summary["capacity_admission_performed"])
        self.assertNotIn("status", summary)
        self.assertEqual({path.name for path in self.f.output.iterdir()},
                         {s.trial["name"] + ".json" for s in self.f.samples} | {"summary.json"})
        for label, plan in self.f.plans.items():
            for trial in plan["trials"]:
                condition = trial["group"] if label == "core" else trial["extension_condition"]
                paths = measurement.budget.sample_paths(plan, trial, self.f.output)
                sample = measurement.budget.read_sample((label, trial["target_class"], condition), plan, trial, paths, {})
                self.assertGreater(sample["total_bytes"], sample["compressed_bytes"])
        self.assertEqual(originals, {path: v4.sha(path) for path in originals})
        self.assertEqual(original_names, {str(path.relative_to(self.f.root)) for path in self.f.root.rglob("*")
                                          if path.is_file() and not path.is_relative_to(self.f.output)})
        receipt = v4.load(self.f.output / (self.f.samples[0].trial["name"] + ".json"))
        self.assertEqual(receipt["temporary_archive_evidence"]["archive_component_bound_without_growth_or_margin_bytes"], 768)
        self.assertFalse(receipt["temporary_archive_evidence"]["bound_is_measurement"])
        self.assertEqual(sum(receipt["component_bytes"].values()), receipt["total_trial_bytes"])

    def test_payload_and_model_bytes_never_opened_even_for_postchecks(self):
        original = Path.open
        def checked_open(path, *args, **kwargs):
            if path.suffix in {".pt", ".jsonl", ".db3", ".zstd", ".vhdx"}:
                self.fail("Payload/model content read: " + str(path))
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", checked_open):
            summary = self.measure()
        self.assertFalse(summary["payload_content_reads"])
        self.assertTrue(summary["source_validation"]["unread_source_assets"])

    def test_missing28th_terminal_refuses_without_creating_output(self):
        sample = self.f.samples[-1]
        v4.record_path(sample.plan, sample.trial).unlink()
        with self.assertRaises((guard.Refusal, FileNotFoundError)):
            self.measure()
        self.assertFalse(self.f.output.exists())

    def test_stale_original_report_sha_refuses(self):
        sample = self.f.samples[0]
        change_report(sample, "summary.json", {"termination_reason": "follow_duration_reached", "follow_start_s": 20.}, rebind=False)
        with self.assertRaisesRegex(guard.Refusal, "SHA changed"):
            self.measure()
        self.assertFalse(self.f.output.exists())

    def test_original_runtime_audit_cannot_detach_from_current_configuration(self):
        sample = self.f.samples[0]
        sample.record["runtime_configuration"]["run_config_sha256"] = "9" * 64
        sample.record["record_sha256"] = v4.digest(sample.record, ("record_sha256",))
        write(v4.record_path(sample.plan, sample.trial), sample.record)
        with self.assertRaisesRegex(guard.Refusal, "runtime receipt digests"):
            self.measure()
        self.assertFalse(self.f.output.exists())

    def test_invalid_native_report_cannot_be_laundered_by_rebinding_record(self):
        sample = self.f.samples[0]
        relative = "native_startup_report.json"
        data = v4.load(sample.directory / relative)
        data["checks"]["native_takeoff_command"] = False
        change_report(sample, relative, data)
        with self.assertRaisesRegex(guard.Refusal, "evaluator report"):
            self.measure()
        self.assertFalse(self.f.output.exists())

    def test_short_exposure_refuses(self):
        sample = self.f.samples[0]
        closure = v4.load(sample.directory / "recording_closure.json")
        closure["observations"][-1]["last_clock_ns"] = 92_000_000_000
        change_report(sample, "recording_closure.json", closure)
        with self.assertRaisesRegex(guard.Refusal, "Short/aborted"):
            self.measure()
        self.assertFalse(self.f.output.exists())

    def test_changed_current_compressed_size_refuses_without_reading_payload(self):
        (self.f.samples[0].directory / "rosbag/data.db3.zstd").write_bytes(b"larger corrupted inert fixture")
        with self.assertRaisesRegex(guard.Refusal, "mapping or current archive size"):
            self.measure()
        self.assertFalse(self.f.output.exists())

    def test_changed_current_text_source_refuses(self):
        path = self.f.root / "scripts/evaluate_px4_source_clock.py"
        path.write_text("# changed fixture source", encoding="utf-8")
        with self.assertRaisesRegex(guard.Refusal, "Frozen text source SHA"):
            self.measure()
        self.assertFalse(self.f.output.exists())

    def test_duplicate_cell_refuses(self):
        plan = self.f.plans["extension"]
        plan["trials"][-1] = deepcopy(plan["trials"][0])
        plan["plan_sha256"] = v4.digest(plan, ("plan_sha256",))
        write(self.f.paths["extension"], plan)
        with self.assertRaises(guard.Refusal):
            self.measure()
        self.assertFalse(self.f.output.exists())

    def test_declared_raw_compressed_correspondence_mismatch_refuses(self):
        sample = self.f.samples[0]
        data = v4.load(sample.directory / "bag_integrity.json")
        data["compressed_files"][0]["raw_sha256"] = "3" * 64
        change_report(sample, "bag_integrity.json", data)
        with self.assertRaisesRegex(guard.Refusal, "mapping or current archive size"):
            self.measure()
        self.assertFalse(self.f.output.exists())

    def test_stat_change_during_measurement_refuses_before_publishing_any_receipt(self):
        actual_inventory = measurement.inventory
        calls = 0
        def changing_inventory(directory):
            nonlocal calls
            calls += 1
            if calls == 29:
                (Path(directory) / "telemetry.jsonl").write_bytes(b"changed concurrent payload size")
            return actual_inventory(directory)
        with patch.object(measurement, "inventory", side_effect=changing_inventory):
            with self.assertRaisesRegex(guard.Refusal, "file sizes changed during measurement"):
                self.measure()
        self.assertFalse(self.f.output.exists())

    def test_output_inside_original_evidence_or_existing_output_refuses(self):
        for output in (self.f.samples[0].directory / "new_receipts", self.f.results, self.f.root / "new_receipts"):
            with self.subTest(output=output), self.assertRaises(guard.Refusal):
                measurement.measure(self.f.paths["core"], self.f.paths["extension"], output)

    def test_original_physical_snapshot_retains_actual_timestamp_without_admission(self):
        original = {"schema_version": 1, "kind": "RELIABILITY_V4_PHYSICAL_STORAGE_INVENTORY",
            "evidence_scope": "METADATA_ONLY_NOT_FORMAL_ADMISSION", "created_utc": STAMP,
            "volumes": [{"mount": "/mnt/d", "windows_volume_id": "fixture-volume", "free_bytes": 123456789}],
            "vhd_host": {"distribution": "FIXTURE", "path": "/fixture/ext4.vhdx"}}
        path = write(self.f.results / "original_inventory.json", original)
        result = self.measure(physical_inventory=path)
        self.assertEqual(result["original_physical_inventory"]["original_inventory"], original)
        self.assertIn("NOT_CURRENT_CAPACITY", result["original_physical_inventory"]["scope"])
        self.assertEqual(len(result["filesystem_free_snapshots"]), 2)
        self.assertTrue(all(type(row["free_bytes"]) is int for row in result["filesystem_free_snapshots"]))

    def test_cli_missing_cell_returns_refusal_and_preserves_trial(self):
        sample = self.f.samples[0]
        (sample.directory / "bag_integrity.json").unlink()
        stream = io.StringIO()
        with redirect_stderr(stream):
            code = measurement.main(["--core-development-plan", str(self.f.paths["core"]),
                "--extension-development-plan", str(self.f.paths["extension"]), "--output", str(self.f.output)])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stream.getvalue())["result"], "REFUSED_NOT_ADMISSION")
        self.assertTrue((sample.directory / "rosbag/data.db3.zstd").exists())
        self.assertFalse(self.f.output.exists())


if __name__ == "__main__":
    unittest.main()
