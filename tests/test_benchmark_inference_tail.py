"""Pure benchmark configuration/accounting checks; no model imports/inference."""
from contextlib import redirect_stderr
import io
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import benchmark_inference_tail as benchmark


class InferenceTailBenchmarkTests(unittest.TestCase):
    def argv(self, *extra):
        return ["--input-dir", "raw", "--model", "model.pt", "--output", "new", *extra]

    def test_parser_requires_complete_minimum_comparison_and_unique_supported_threads(self):
        args = benchmark.parse_args(self.argv())
        self.assertEqual((args.threads, args.warmup, args.repeats), ([1, 2, 4], 3, 3))
        for options in (("--threads", "1", "1"), ("--threads", "8"),
                        ("--warmup", "2"), ("--repeats", "1"), ("--limit-images", "0")):
            with self.subTest(options=options), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                benchmark.parse_args(self.argv(*options))

    def test_production_fixed_condition_requires_one_size_one_pool_and_cycles_are_full_passes(self):
        args = benchmark.parse_args(self.argv("--worker-mode", "production", "--fixed-condition",
                                              "--threads", "4", "--imgsz", "512", "--cycles", "84"))
        self.assertEqual((args.worker_mode, args.threads, args.imgsz, args.repeats, args.cycles),
                         ('production', [4], 512, 84, 84))
        for options in (("--worker-mode", "production"), ("--fixed-condition",),
                        ("--fixed-condition", "--threads", "4", "--include-512"),
                        ("--imgsz", "512"), ("--cycles", "84", "--repeats", "4")):
            with self.subTest(options=options), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                benchmark.parse_args(self.argv(*options))

    def test_production_runner_uses_one_actual_background_worker_and_propagates_original_error(self):
        main = threading.get_ident()
        seen = []
        expected = RuntimeError('private worker failure')
        def measure(condition, image):
            seen.append(threading.get_ident())
            if image == 'fail':
                raise expected
            return {'condition': condition, 'image': image, 'thread_name': threading.current_thread().name}
        runner = benchmark.ProductionRunner(measure)
        try:
            first = runner('one', 'a')
            runner('one', 'b')
            with self.assertRaises(RuntimeError) as caught:
                runner('one', 'fail')
            self.assertIs(caught.exception, expected)
            self.assertEqual(len(set(seen)), 1)
            self.assertNotEqual(seen[0], main)
            self.assertTrue(first['thread_name'].startswith('yolo_inference'))
        finally:
            runner.shutdown()

    def test_model_shape_observer_reads_forward_tensor_shape_without_guessing_from_imgsz(self):
        hooks = []
        handle = object()
        def register(hook):
            hooks.append(hook)
            return handle
        model = SimpleNamespace(predictor=SimpleNamespace(model=SimpleNamespace(
            backend=SimpleNamespace(model=SimpleNamespace(register_forward_pre_hook=register)))))
        evidence = {'actual_model_input_shape': None}
        self.assertIs(benchmark.observe_input_shape(model, evidence), handle)
        tensor = SimpleNamespace(shape=(1, 3, 384, 512))
        self.assertIsNone(hooks[0](object(), (tensor,)))
        self.assertEqual(evidence['actual_model_input_shape'], [1, 3, 384, 512])
        self.assertIsNone(benchmark.observe_input_shape(object(), evidence))

    def test_each_paired_order_has_all_conditions_and_changes_starting_condition(self):
        conditions = benchmark.conditions([1, 2, 4], True)
        self.assertEqual(len(conditions), 6)
        self.assertEqual({row["imgsz"] for row in conditions}, {512, 640})
        orders = [benchmark.paired_order(conditions, index) for index in range(12)]
        for order in orders:
            self.assertEqual({row["id"] for row in order}, {row["id"] for row in conditions})
            self.assertEqual(len(order), 6)
        self.assertEqual(len({order[0]["id"] for order in orders}), 6)
        self.assertEqual({row["imgsz"] for row in benchmark.conditions([4])}, {640})

    def test_summary_retains_unknowns_missing_opportunities_and_tail_quantiles(self):
        condition, = benchmark.conditions([4])
        rows = [{"condition_id": condition["id"], "predict_wall_s": value,
                 "speed_ms": {"inference": value * 1000 if value is not None else None}}
                for value in (.1, .2, None)]
        result = benchmark.summarize(rows, [condition], 2, 3)[condition["id"]]
        self.assertEqual((result["expected"], result["recorded"], result["unattempted_or_missing"]), (6, 3, 3))
        self.assertEqual(result["predict_wall_s"]["known"], 2)
        self.assertEqual(result["predict_wall_s"]["unknown"], 1)
        self.assertAlmostEqual(result["predict_wall_s"]["p95"], .195)
        self.assertIsNone(result["process_cpu_s"]["median"])
        self.assertEqual(result["ultralytics_speed_ms"]["postprocess"]["unknown"], 3)

    def test_psi_is_system_counter_delta_and_reset_or_missing_is_unknown(self):
        before = {"cpu": {"value": benchmark.parse_psi("some avg10=1.2 avg60=0.4 avg300=0.0 total=100\n")}}
        after = {"cpu": {"value": benchmark.parse_psi("some avg10=1.3 avg60=0.4 avg300=0.0 total=140\n")}}
        delta = benchmark.psi_delta(before, after)
        self.assertEqual(delta["cpu"]["some_stall_us"], 40)
        self.assertIsNone(delta["cpu"]["full_stall_us"])
        self.assertIsNone(delta["memory"]["some_stall_us"])
        after["cpu"]["value"]["some"]["total"] = 90
        self.assertIsNone(benchmark.psi_delta(before, after)["cpu"]["some_stall_us"])

    def test_model_initialization_and_start_callback_match_production_thread_guard(self):
        events, callbacks = [], {}
        torch = SimpleNamespace(set_num_threads=lambda value: events.append(("set", value)), get_num_threads=lambda: 4)
        class FakeYOLO:
            def __init__(self, path):
                events.append(("YOLO", path))
            def add_callback(self, name, callback):
                callbacks[name] = callback
        _, evidence = benchmark.new_production_model(Path("model.pt"), 4, torch, FakeYOLO)
        self.assertEqual(events, [("set", 4), ("YOLO", "model.pt")])
        callbacks["on_predict_start"](object())
        self.assertEqual(events[-1], ("set", 4))
        self.assertEqual((evidence["callback_count"], evidence["effective_threads"]), (1, 4))

    def test_existing_output_or_nested_output_is_refused_without_creating_directories(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve()
            raw = root / "raw"
            raw.mkdir()
            (raw / "frame.png").write_bytes(b"path-only fixture")
            model = root / "model.pt"
            model.write_bytes(b"path-only fixture")
            args = benchmark.parse_args(["--input-dir", str(raw), "--model", str(model), "--output", str(root / "new")])
            _, _, output, images = benchmark.validated_paths(args)
            self.assertFalse(output.exists())
            self.assertEqual([path.name for path in images], ["frame.png"])
            output.mkdir()
            with self.assertRaises(ValueError):
                benchmark.validated_paths(args)
            args.output = raw / "inside"
            with self.assertRaises(ValueError):
                benchmark.validated_paths(args)

    def test_failed_predict_retains_exact_pair_context_and_unknown_denominators(self):
        state = {"threads": 1, "calls": 0}
        torch = SimpleNamespace(set_num_threads=lambda value: state.update(threads=value),
                                get_num_threads=lambda: state["threads"], get_num_interop_threads=lambda: 1)
        class FakeImage:
            ndim, shape, nbytes = 3, (2, 2, 3), 12
            def tobytes(self):
                return b"fake pixels!"
        class FakeYOLO:
            def __init__(self, _path):
                self.callback = None
                self.predictor = SimpleNamespace(model=SimpleNamespace(format="pt", fp16=False, device="cpu"))
            def add_callback(self, _name, callback):
                self.callback = callback
            def predict(self, _image, **requested):
                self.callback(self.predictor)
                state["calls"] += 1
                if state["calls"] == 4:
                    raise RuntimeError("private fake failure")
                self.predictor.args = SimpleNamespace(**requested, quantize=None)
                return [SimpleNamespace(speed={"preprocess": 1., "inference": 2., "postprocess": 1.}, boxes=[])]
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve()
            raw = root / "raw"
            raw.mkdir()
            (raw / "frame.png").write_bytes(b"fake encoded png")
            (root / "model.pt").write_bytes(b"fake weight")
            args = benchmark.parse_args(["--input-dir", str(raw), "--model", str(root / "model.pt"),
                                         "--output", str(root / "new"), "--threads", "4"])
            modules = {"torch": torch, "cv2": SimpleNamespace(imread=lambda *_: FakeImage(),
                       IMREAD_COLOR=1, getNumThreads=lambda: 1), "ultralytics": SimpleNamespace(YOLO=FakeYOLO)}
            with patch.dict("sys.modules", modules), patch.dict(os.environ), self.assertRaisesRegex(RuntimeError, "private fake"):
                benchmark.run(args)
            failed = json.loads((root / "new/failed.json").read_text(encoding="utf-8"))
            self.assertEqual(failed["warmup_records"], 3)
            self.assertEqual(failed["failure_context"]["pair_id"], "repeat000_image000000")
            self.assertEqual(failed["failure_context"]["condition_id"], "pt_cpu_t4_img640")
            self.assertFalse((root / "new/summary.json").exists())
            result = failed["conditions"]["pt_cpu_t4_img640"]
            self.assertEqual((result["expected"], result["recorded"], result["unattempted_or_missing"]), (3, 0, 3))


if __name__ == "__main__":
    unittest.main()
