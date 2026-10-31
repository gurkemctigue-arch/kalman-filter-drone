"""Named prospective scales; inert plans only, never ROS/model execution."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests import test_reliability_v4_runner as fixtures
from tests import test_reliability_v4_extensions as extensions

v4 = fixtures.v4
FIELD = "car_input_scale_registration"


class CarInputScaleRegistrationTests(unittest.TestCase):
    SIZE = 640
    REGISTRATION = "CAR_INPUT_SCALE_REGISTRATION_TRAIN04_640"

    def registration(self):
        return deepcopy(getattr(v4, self.REGISTRATION))

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def current_protocol(self):
        protocol = v4.load(fixtures.ROOT / v4.PROTOCOL_PATH)
        protocol[FIELD] = self.registration()
        protocol["resources"]["car"]["inference_image_size"] = self.SIZE
        return protocol

    def enable_inert_plan(self):
        fixtures.fixture(self.root)
        adaptation = deepcopy(v4.CAR_MODEL_ADAPTATION_TRAIN04)
        weight = self.root / adaptation["model"]
        weight.write_bytes(b"ORCHESTRATION_FIXTURE_ONLY: not a trained model")
        adaptation["model_sha256"] = v4.sha(weight)
        for key in ("training_receipt", "dataset_manifest"):
            path = self.root / adaptation[key]["path"]
            fixtures.write(path, {"evidence_scope": "ORCHESTRATION_FIXTURE_ONLY", "artifact": key})
            adaptation[key]["sha256"] = v4.sha(path)
        replacement = patch.object(v4, "CAR_MODEL_ADAPTATION_TRAIN04", adaptation)
        replacement.start()
        self.addCleanup(replacement.stop)
        registration = self.registration()
        receipt_path = registration["receipt"]["path"]
        (self.root / receipt_path).write_bytes((fixtures.ROOT / receipt_path).read_bytes())
        protocol = v4.load(self.root / v4.PROTOCOL_PATH)
        protocol["resources"]["car"].update(model=adaptation["model"], inference_image_size=self.SIZE)
        protocol.update(model_adaptation=adaptation, **{FIELD: registration})
        fixtures.write(self.root / v4.PROTOCOL_PATH, protocol)
        return protocol, receipt_path

    def make(self, suffix):
        return fixtures.plan(self.root, classes=["car"], groups=["stage1_velocity"],
                             seeds=[4], suffix=suffix, persist=False)

    def test_640_registration_and_all_previous960_histories_remain_distinct(self):
        protocol = self.current_protocol()
        v4.validate_protocol(protocol)
        self.assertEqual(protocol[FIELD], self.registration())
        for adaptation in (None, v4.CAR_MODEL_ADAPTATION, v4.CAR_MODEL_ADAPTATION_TRAIN04):
            with self.subTest(model=adaptation and adaptation["model"]):
                previous = deepcopy(protocol)
                previous.pop(FIELD)
                previous["resources"]["car"]["inference_image_size"] = 960
                if adaptation is None:
                    previous["resources"]["car"]["model"] = "models/yolo11m.pt"
                    previous.pop("model_adaptation")
                else:
                    previous["resources"]["car"]["model"] = adaptation["model"]
                    previous["model_adaptation"] = deepcopy(adaptation)
                v4.validate_protocol(previous)
        receipt = protocol[FIELD]["receipt"]
        self.assertEqual(v4.sha(fixtures.ROOT / receipt["path"]), receipt["sha256"])
        evidence = v4.load(fixtures.ROOT / receipt["path"])
        self.assertEqual(evidence["scope"], self.registration()["scope"])
        self.assertFalse(evidence["complete_development_readiness"])
        self.assertEqual(evidence["resource"]["precision"], "CPU native PT FP32")
        self.assertEqual(evidence["quality"]["summary_sha256"],
                         "570775127105dab3138ecc001b1815b05994763306546504fee1cfe6e9cca0e4")

    def test_missing_or_changed_registration_and_unreviewed_resources_reject(self):
        defects = ("missing", "null", "revision", "receipt_path", "receipt_sha", "scope",
                   "other_model", "train01", "other_size", "size960", "threads2", "float_threads", "float_size")
        for defect in defects:
            with self.subTest(defect=defect):
                protocol = self.current_protocol()
                resource = protocol["resources"]["car"]
                if defect == "missing": protocol.pop(FIELD)
                elif defect == "null": protocol[FIELD] = None
                elif defect == "revision": protocol[FIELD]["revision"] = "unreviewed"
                elif defect == "receipt_path": protocol[FIELD]["receipt"]["path"] = "config/other.json"
                elif defect == "receipt_sha": protocol[FIELD]["receipt"]["sha256"] = "0" * 64
                elif defect == "scope": protocol[FIELD]["scope"] = "COMPLETE_READINESS"
                elif defect == "other_model": resource["model"] = "models/other.pt"
                elif defect == "train01": resource["model"] = v4.CAR_ADAPTED_MODEL
                elif defect == "other_size": resource["inference_image_size"] = 512 if self.SIZE == 640 else 640
                elif defect == "size960": resource["inference_image_size"] = 960
                elif defect == "threads2": resource["inference_threads"] = 2
                elif defect == "float_threads": resource["inference_threads"] = 4.
                elif defect == "float_size": resource["inference_image_size"] = float(self.SIZE)
                with self.assertRaises(ValueError):
                    v4.validate_protocol(protocol)

    def test_actual_receipt_is_required_and_bound_in_source_and_config_maps(self):
        _protocol, relative = self.enable_inert_plan()
        receipt = self.root / relative
        original = receipt.read_bytes()
        receipt.unlink()
        with self.assertRaisesRegex(ValueError, "resource receipt"):
            self.make("missing_scale_receipt")
        receipt.write_bytes(original)
        frozen = self.make("scale")
        expected = self.registration()["receipt"]["sha256"]
        self.assertEqual(frozen["source_hashes"][relative], expected)
        self.assertEqual(frozen["config_hashes"][relative], expected)
        for mapping in ("source_hashes", "config_hashes"):
            for defect in ("missing", "wrong_sha"):
                with self.subTest(mapping=mapping, defect=defect):
                    changed = deepcopy(frozen)
                    if defect == "missing": changed[mapping].pop(relative)
                    else: changed[mapping][relative] = "0" * 64
                    changed["plan_sha256"] = v4.digest(changed, ("plan_sha256",))
                    with self.assertRaises(ValueError):
                        v4.validate_plan(changed)
        receipt.write_bytes(original + b"\nchanged evidence\n")
        with self.assertRaisesRegex(ValueError, "resource receipt"):
            self.make("changed_scale_receipt")
        with patch.object(v4, "verify_external_runtime", side_effect=AssertionError("must reject first")), \
                self.assertRaisesRegex(ValueError, "Frozen source"):
            v4.verify_sources(frozen)

    def test_extensions_inherit640_and_cannot_change_one_condition_resource(self):
        self.enable_inert_plan()
        fixtures.write(self.root / v4.EXTENSION_PROTOCOL_PATH,
                       v4.load(fixtures.ROOT / v4.EXTENSION_PROTOCOL_PATH))
        frozen = extensions.make(self.root, classes=["car"], seeds=[4])
        self.assertEqual(len(frozen["trials"]), 8)
        for trial in frozen["trials"]:
            command = trial["flight_command"]
            self.assertEqual(trial["model"], v4.CAR_ADAPTED_MODEL_TRAIN04)
            self.assertEqual(trial["inference_image_size"], self.SIZE)
            self.assertEqual(trial["inference_threads"], 4)
            self.assertEqual(command[command.index("--inference-image-size") + 1], str(self.SIZE))
        trial = frozen["trials"][0]
        trial["inference_image_size"] = 512 if self.SIZE == 640 else 640
        command = trial["flight_command"]
        command[command.index("--inference-image-size") + 1] = str(trial["inference_image_size"])
        frozen["plan_sha256"] = v4.digest(frozen, ("plan_sha256",))
        with self.assertRaisesRegex(ValueError, "trial commands"):
            v4.validate_plan(frozen)

    def test_960_probe_cannot_certify640_with_the_same_file_pool(self):
        protocol, _relative = self.enable_inert_plan()
        previous_protocol = deepcopy(protocol)
        previous_protocol.pop(FIELD)
        previous_protocol["resources"]["car"]["inference_image_size"] = 960
        fixtures.write(self.root / v4.PROTOCOL_PATH, previous_protocol)
        previous = self.make("scale_previous960")
        v4.persist_plan(previous)
        fixtures.write(self.root / v4.PROTOCOL_PATH, protocol)
        current = self.make("scale_current640")
        self.assertEqual(previous["source_hashes"], current["source_hashes"])
        evidence = {"schema_version": 2, "result": "PASS", "ready_for_formal_reliability_v4": True,
                    "checks": {key: True for key in v4.PROBE_CHECKS},
                    "bindings": {"flight_source_hashes": v4.flight_source_hashes(current["source_hashes"]),
                        "evaluation_source_hashes": v4.offline_source_hashes(current["source_hashes"]),
                        "model_hashes": current["model_hashes"],
                        "magnetic_runtime_manifest_sha256": current["magnetic_runtime_binding"]["manifest_sha256"],
                        "magnetic_library_registration_sha256": current["magnetic_library_binding"]["registration_sha256"],
                        "navigation_acceptance_sha256": v4.digest(current["protocol"]["navigation_acceptance"])},
                    "probe_slots": [{"plan_path": str(Path(previous["output"]) / "plan.json"),
                                     "plan_file_sha256": v4.sha(Path(previous["output"]) / "plan.json"),
                                     "slot_id": previous["trials"][0]["id"], "record_file_sha256": "0" * 64}]}
        path = self.root / "scale_probe_gate.json"
        fixtures.write(path, evidence)
        current["development_probe_gate"] = {"path": str(path), "sha256": v4.sha(path), "evidence": evidence}
        with patch.object(v4, "read_slots", side_effect=AssertionError("must reject before records")), \
                self.assertRaisesRegex(ValueError, "selected model/adaptation/resource revision"):
            v4.validate_probe_gate(current)


class Car512InputScaleRegistrationTests(CarInputScaleRegistrationTests):
    SIZE = 512
    REGISTRATION = "CAR_INPUT_SCALE_REGISTRATION_TRAIN04_512"

    def test_640_registration_cannot_authorize512_or_share_its_evidence(self):
        protocol = self.current_protocol()
        protocol[FIELD] = deepcopy(v4.CAR_INPUT_SCALE_REGISTRATION_TRAIN04_640)
        with self.assertRaisesRegex(ValueError, "Frozen resource"):
            v4.validate_protocol(protocol)
        receipt = v4.load(fixtures.ROOT / self.registration()["receipt"]["path"])
        self.assertFalse(receipt["closed_loop_validated"])
        self.assertFalse(receipt["timing"]["maximum_latency_improved"])
        self.assertEqual(receipt["quality"]["candidate_id"], "train20_04_best_m512")
        self.assertEqual([c["inference_image_size"] for c in receipt["timing"]["configurations"]], [640, 512])


if __name__ == "__main__":
    unittest.main()
