"""Small offline fixtures; no YOLO weights, real images, bag reader or ROS."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("detection_recording_evaluator", ROOT / "scripts/evaluate_detection_recordings.py")
evaluator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluator)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")
    return path


class DetectionRecordingProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for category, name in (("person", "yolo11n.pt"), ("car", "yolo11s.pt")):
            path = self.root / "models" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("FAKE_WEIGHTS_" + category).encode())
        for name in ("scripts/evaluate_detection_recordings.py", "uav_tracking/research_metrics.py"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("FIXTURE_SOURCE " + name).encode())
        self.trial = self.root / "trial_car"
        self.source = {"target_class": "car", "source_trial": str(self.trial), "frames": [
            {"time_s": 1., "image_file": "frame.png", "eligible_geometric_subset": False,
             "exclusion_reason": "FIXTURE_INELIGIBLE", "gt": [], "pred": []},
            {"time_s": 2., "image_file": None, "eligible_geometric_subset": False,
             "exclusion_reason": "IMAGE_MISSING", "gt": [], "pred": []}]}
        self.recording = write_json(self.root / "extraction/recording.json", self.source)
        (self.recording.parent / "frame.png").write_bytes(b"FAKE_ENCODED_IMAGE")

    def args(self, *extra):
        return evaluator.build_parser().parse_args([str(self.recording), "--output", str(self.root / "output"), *map(str, extra)])

    def recorded(self):
        detector = {"class_name": "car", "class_id": 2, "model_path": "models/yolo11s.pt",
                    "inference_image_size": 640, "inference_threads": 4, "inference_device": "cpu",
                    "confidence_threshold": .45}
        write_json(self.trial / "run_config.json", {"target_class": "car", "model_path": None,
                   "inference_image_size": 640, "inference_threads": 4})
        runtime = self.trial / "configuration/runtime_parameters.yaml"
        runtime.parent.mkdir(parents=True, exist_ok=True)
        runtime.write_text(yaml.safe_dump({"uav_tracking_detection": {"ros__parameters": detector}}), encoding="utf-8")
        write_json(self.trial / "configuration/source_sha256.json", {
            "models/yolo11s.pt": evaluator.file_sha256(self.root / "models/yolo11s.pt")})

    def provenance(self):
        configuration, evidence = evaluator.inference_configuration(self.source, self.args(), root=self.root)
        return evaluator.input_provenance(self.recording, self.source, configuration, evidence, root=self.root)

    def cache(self, provenance=None, predictions=None):
        provenance = provenance if provenance is not None else self.provenance()
        predictions = {"1.000000": []} if predictions is None else predictions
        return write_json(self.root / "cache.json", {"schema_version": 2, "provenance": provenance, "predictions": predictions})

    def test_historical_defaults_are_unchanged_and_explicitly_labelled(self):
        for category, size in (("person", 320), ("car", 480)):
            source = dict(self.source, target_class=category)
            config, evidence = evaluator.inference_configuration(source, self.args(), root=self.root)
            self.assertEqual((config["image_size"], config["threads"], config["confidence_floor"], config["iou_nms"]), (size, 2, .001, .7))
            self.assertEqual(config["settings_source"], "historical")
            self.assertEqual(evidence, {})

    def test_recorded_car_uses_640_four_threads_and_saved_model_hash(self):
        self.recorded()
        config, evidence = evaluator.inference_configuration(self.source, self.args("--settings-source", "recorded"), root=self.root)
        self.assertEqual((config["image_size"], config["threads"]), (640, 4))
        self.assertEqual(config["checkpoint_sha256"], evidence["saved_model"]["sha256"])
        self.assertEqual(evidence["recorded_online_confidence_threshold"], .45)
        self.assertEqual(config["confidence_floor"], .001)

    def test_recorded_missing_binding_and_conflicting_run_override_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            evaluator.inference_configuration(self.source, self.args("--settings-source", "recorded"), root=self.root)
        self.recorded()
        write_json(self.trial / "run_config.json", {"target_class": "car", "inference_image_size": 480})
        with self.assertRaisesRegex(ValueError, "disagree"):
            evaluator.inference_configuration(self.source, self.args("--settings-source", "recorded"), root=self.root)

    def test_recorded_model_relocation_requires_identical_bytes(self):
        self.recorded()
        relocated = self.root / "relocated.pt"
        relocated.write_bytes((self.root / "models/yolo11s.pt").read_bytes())
        args = self.args("--settings-source", "recorded", "--car-model-path", relocated)
        evaluator.inference_configuration(self.source, args, root=self.root)
        relocated.write_bytes(b"OTHER_MODEL")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            evaluator.inference_configuration(self.source, args, root=self.root)

    def test_recorded_size_override_and_missing_model_manifest_are_rejected(self):
        self.recorded()
        with self.assertRaisesRegex(ValueError, "cannot be changed"):
            evaluator.inference_configuration(self.source, self.args("--settings-source", "recorded", "--car-image-size", "480"), root=self.root)
        write_json(self.trial / "configuration/source_sha256.json", {})
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            evaluator.inference_configuration(self.source, self.args("--settings-source", "recorded"), root=self.root)

    def test_explicit_settings_require_complete_declaration_and_actual_file(self):
        with self.assertRaisesRegex(ValueError, "require model"):
            evaluator.inference_configuration(self.source, self.args("--settings-source", "explicit"), root=self.root)
        args = self.args("--settings-source", "explicit", "--car-model-path", self.root / "models/yolo11s.pt",
                         "--car-image-size", "640", "--car-threads", "4")
        config, _ = evaluator.inference_configuration(self.source, args, root=self.root)
        self.assertEqual((config["image_size"], config["threads"]), (640, 4))
        args.car_model_path = self.root / "MISSING.pt"
        with self.assertRaisesRegex(ValueError, "auto-download"):
            evaluator.inference_configuration(self.source, args, root=self.root)

    def test_invalid_values_are_rejected(self):
        for attr, value in (("car_threads", 0), ("car_image_size", 641), ("confidence_floor", float("nan")),
                            ("confidence_floor", True), ("iou_nms", 0)):
            with self.subTest(attr=attr, value=value):
                args = self.args()
                setattr(args, attr, value)
                with self.assertRaises(ValueError):
                    evaluator.inference_configuration(self.source, args, root=self.root)

    def test_cache_keeps_missing_images_and_empty_predictions(self):
        provenance = self.provenance()
        self.assertEqual([row["status"] for row in provenance["input_images"]], ["PRESENT", "MISSING"])
        self.assertEqual(evaluator.load_prediction_cache(self.cache(provenance), provenance), {"1.000000": []})

    def test_legacy_cache_missing_rows_and_foreign_rows_are_rejected(self):
        provenance = self.provenance()
        with self.assertRaisesRegex(ValueError, "Legacy/unbound"):
            evaluator.load_prediction_cache(write_json(self.root / "old.json", {"1.000000": []}), provenance)
        for predictions in ({}, {"1.000000": [], "2.000000": []}):
            with self.subTest(predictions=predictions), self.assertRaisesRegex(ValueError, "every present"):
                evaluator.load_prediction_cache(self.cache(provenance, predictions), provenance)

    def test_model_and_every_inference_setting_are_bound(self):
        provenance = self.provenance()
        for key, value in (("checkpoint_sha256", "f" * 64), ("image_size", 640), ("threads", 4),
                           ("confidence_floor", .01), ("iou_nms", .5), ("class_id", 0), ("device", "cuda")):
            with self.subTest(key=key):
                changed = deepcopy(provenance)
                changed["inference"][key] = value
                with self.assertRaisesRegex(ValueError, "provenance differs"):
                    evaluator.load_prediction_cache(self.cache(changed), provenance)

    def test_boolean_cannot_masquerade_as_numeric_configuration(self):
        provenance = self.provenance()
        provenance["inference"]["threads"] = 1
        changed = deepcopy(provenance)
        changed["inference"]["threads"] = True
        with self.assertRaisesRegex(ValueError, "provenance differs"):
            evaluator.load_prediction_cache(self.cache(changed), provenance)

    def test_changed_image_recording_and_evaluator_sources_reject_old_cache(self):
        provenance = self.provenance()
        cache = self.cache(provenance)
        targets = [self.recording.parent / "frame.png", self.recording,
                   self.root / "scripts/evaluate_detection_recordings.py", self.root / "uav_tracking/research_metrics.py"]
        for path in targets:
            with self.subTest(path=path.name):
                original = path.read_bytes()
                path.write_bytes(original + b" ")
                with self.assertRaisesRegex(ValueError, "provenance differs"):
                    evaluator.load_prediction_cache(cache, self.provenance())
                path.write_bytes(original)

    def test_newly_available_image_and_alias_timestamps_cannot_reuse_cache(self):
        provenance = self.provenance()
        cache = self.cache(provenance)
        changed = deepcopy(self.source)
        changed["frames"][1]["image_file"] = "new.png"
        (self.recording.parent / "new.png").write_bytes(b"NEW_IMAGE")
        config, evidence = evaluator.inference_configuration(changed, self.args(), root=self.root)
        with self.assertRaisesRegex(ValueError, "provenance differs"):
            evaluator.load_prediction_cache(cache, evaluator.input_provenance(self.recording, changed, config, evidence, root=self.root))
        changed["frames"][1]["time_s"] = 1.00000001
        with self.assertRaisesRegex(ValueError, "alias"):
            evaluator.input_provenance(self.recording, changed, config, evidence, root=self.root)

    def test_invalid_prediction_payload_is_rejected(self):
        provenance = self.provenance()
        good = {"id": "0", "class_name": "car", "bbox": [0, 0, 4, 4], "confidence": .9}
        for change in ({"confidence": True}, {"bbox": [0, 0, -1, 4]}, {"class_name": "person"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                evaluator.load_prediction_cache(self.cache(provenance, {"1.000000": [dict(good, **change)]}), provenance)

    def test_timestamp_only_visual_review_stays_pending(self):
        provenance = self.provenance()
        review = {"approved_frames": {"trial_car": ["1.000000"]}}
        self.assertEqual(evaluator.review_binding_status(review, "trial_car", provenance), "PENDING_INPUT_BINDING")
        review["cache_provenance_sha256"] = {"trial_car": evaluator.canonical_sha256(provenance)}
        self.assertEqual(evaluator.review_binding_status(review, "trial_car", provenance), "BOUND")

    def test_bound_review_cannot_use_string_membership_or_approve_missing_images(self):
        provenance = self.provenance()
        for approved in ("1.000000", ["2.000000"], ["1.000000", "1.000000"]):
            review = {"approved_frames": {"trial_car": approved},
                      "cache_provenance_sha256": {"trial_car": evaluator.canonical_sha256(provenance)}}
            with self.subTest(approved=approved), self.assertRaisesRegex(ValueError, "unique present"):
                evaluator.review_binding_status(review, "trial_car", provenance)

    def test_main_passes_declared_settings_and_reuse_never_imports_yolo(self):
        calls = []
        thread_calls = []
        empty = types.SimpleNamespace(cpu=lambda: types.SimpleNamespace(tolist=lambda: []))

        class FakeYOLO:
            def __init__(self, path):
                calls.append(("model", path))
                self.callback = None

            def add_callback(self, name, callback):
                self.callback = callback

            def predict(self, image, **kwargs):
                self.callback(None)
                calls.append(("predict", kwargs))
                return [types.SimpleNamespace(boxes=types.SimpleNamespace(xyxy=empty, conf=empty))]

        fake_cv2 = types.SimpleNamespace(IMREAD_COLOR=1, imdecode=lambda _data, _flag: np.zeros((8, 8, 3), dtype=np.uint8))
        argv = [str(self.recording), "--output", str(self.root / "main_output"), "--settings-source", "explicit",
                "--car-model-path", str(self.root / "models/yolo11s.pt"), "--car-image-size", "640", "--car-threads", "4"]
        with patch.dict("sys.modules", {"cv2": fake_cv2, "torch": types.SimpleNamespace(set_num_threads=thread_calls.append),
                                       "ultralytics": types.SimpleNamespace(YOLO=FakeYOLO)}):
            evaluator.main(argv)
        predict = [row[1] for row in calls if row[0] == "predict"]
        self.assertEqual(predict, [{"imgsz": 640, "conf": .001, "iou": .7, "classes": [2], "device": "cpu", "verbose": False}])
        self.assertEqual(thread_calls, [4, 4])
        cache = self.root / "main_output/trial_car/low_confidence_predictions.json"
        before = cache.read_bytes()
        with patch.dict("sys.modules", {"cv2": fake_cv2, "torch": None, "ultralytics": None}):
            evaluator.main([*argv, "--reuse-predictions"])
        self.assertEqual(cache.read_bytes(), before)
        report = evaluator.read_json(self.root / "main_output/trial_car/detection_report.json")
        self.assertFalse(report["inference"]["executed_during_this_command"])
        self.assertEqual(report["sampled_opportunities"], 2)
        self.assertEqual(report["publication_status"], "PENDING_VISUAL_REVIEW")


if __name__ == "__main__":
    unittest.main()
