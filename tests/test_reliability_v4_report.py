"""Synthetic immutable JSON fixtures only; no formal results, bags or DOCX files."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests import test_reliability_v4_runner as fixtures
from tests import test_reliability_v4_extensions as extensions
from tests.test_reliability_v4_summary import summarizer, terminal
from tests.test_replay_comparison import cli_fixture, write
from tests.test_replay_evidence import fixture as evidence_fixture
from tests import test_detection_recording_provenance as detection_fixtures

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v4_document_report_fixture", ROOT / "scripts/build_reliability_v4_report.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)
NODE_DOCX_AVAILABLE = bool(shutil.which("node")) and subprocess.run(
    [shutil.which("node"), "-e", "require.resolve('docx')"], cwd=ROOT,
    capture_output=True, check=False).returncode == 0


class ReliabilityReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        extensions.extension_fixture(self.root)
        self.core = fixtures.plan(self.root, groups=["stage1_velocity"], classes=["person"], seeds=[4, 5], suffix="report_fixture")
        terminal(self.core, self.core["trials"][0], "FAIL", distance=0., censored=True)
        self.plan_path = Path(self.core["output"]) / "plan.json"
        self.summary_path = self.root / "engineering_summary.json"
        self.summary = summarizer.summary(self.plan_path, resamples=128, seed=42)
        write(self.summary_path, self.summary)

    def build(self, **options):
        return builder.build(self.summary_path, self.plan_path, **options)

    def detection_fixture(self, *, bound=True):
        fixture = detection_fixtures.DetectionRecordingProvenanceTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.source["frames"][0].update(eligible_geometric_subset=True, exclusion_reason=None,
            gt=[{"id": "fixture-gt", "class_name": "car", "bbox": [1., 1., 10., 10.]}])
        write(fixture.recording, fixture.source)
        config, evidence = detection_fixtures.evaluator.inference_configuration(fixture.source, fixture.args(), root=fixture.root)
        provenance = detection_fixtures.evaluator.input_provenance(fixture.recording, fixture.source, config, evidence, root=fixture.root)
        folder = fixture.root / "detection_output" / "trial_car"
        folder.mkdir(parents=True)
        predictions = {"1.000000": [{"id": "0", "class_name": "car", "bbox": [1., 1., 10., 10.], "confidence": .8}]}
        cache = folder / "low_confidence_predictions.json"
        write(cache, {"schema_version": 2, "provenance": provenance, "predictions": predictions})
        review = {"approved_frames": {"trial_car": ["1.000000"]}, "cache_provenance_sha256": {"trial_car": builder.canonical_sha256(provenance)} if bound else {}}
        review_path = fixture.root / "actual_review.json"
        write(review_path, review)
        frames = [dict(fixture.source["frames"][0], pred=predictions["1.000000"], review_status="APPROVED" if bound else "PENDING")]
        metrics = builder.detection_metrics(frames) if bound else None
        child = {"source_trial": fixture.source["source_trial"], "target_class": "car", "sampled_opportunities": 2,
            "recording_manifest_sha256": builder.sha(fixture.recording), "prediction_cache_sha256": builder.sha(cache),
            "prediction_cache_schema_version": 2, "input_provenance": provenance, "cache_provenance_sha256": builder.canonical_sha256(provenance),
            "review_binding_status": "BOUND" if bound else "PENDING_INPUT_BINDING", "geometric_eligible": 1,
            "approved_eligible": int(bound), "excluded": [{"time_s": 2., "reason": "selected source RGB image not recorded"}],
            "all_eligible_proposed_metrics": builder.detection_metrics(frames), "reviewed_metrics": metrics,
            "publication_status": "REVIEWED_SUBSET_ONLY" if bound else "PENDING_VISUAL_REVIEW",
            "checkpoint": config["checkpoint"], "checkpoint_sha256": config["checkpoint_sha256"],
            "inference": {**config, "executed_during_this_command": False, "wall_latency_median_s": None},
            "labels": "FIXTURE_ONLY: no images decoded or models inferred", "frames": frames}
        write(folder / "detection_report.json", child)
        report_path = folder.parent / "detection_report.json"
        write(report_path, {"schema_version": 1, "recordings": [{key: value for key, value in child.items() if key != "frames"}],
            "reviewed_aggregate": metrics, "review_file": str(review_path), "review_file_sha256": builder.sha(review_path),
            "claim_boundary": "FIXTURE_ONLY"})
        return fixture, report_path, review_path, cache

    def test_draft_preserves_failure_pending_zero_censoring_and_no_acceptance_claim(self):
        package, sources = self.build()
        self.assertEqual(package["scope"], "DEVELOPMENT_ONLY")
        self.assertFalse(package["completion"]["all_280_slots_terminal"])
        self.assertFalse(package["completion"]["project_acceptance_claimed"])
        report = builder.render_markdown(package["documents"]["report"])
        for text in ("FAIL", "PENDING", "RIGHT_CENSORED", "DEVELOPMENT_ONLY", "R_geometry+R_pose", "退化"):
            self.assertIn(text, report)
        self.assertIn("| 1/2 | 0 |", report)
        self.assertTrue(sources.records)

    def test_edited_summary_metrics_or_counts_cannot_bypass_sources(self):
        for change in (lambda value: value["cohorts"]["core"].update(terminal_slots=2),
                       lambda value: value["trials"][0]["metrics"].update(base_link_distance_rmse_m=999.)):
            bad = deepcopy(self.summary)
            change(bad)
            write(self.summary_path, bad)
            with self.assertRaisesRegex(ValueError, "differs"):
                self.build()

    def test_changed_plan_or_original_evaluator_is_rejected(self):
        report_path = Path(self.core["trials"][0]["evaluations"][0]["report"])
        with report_path.open("a") as stream:
            stream.write(" ")
        with self.assertRaises(ValueError):
            self.build()

    def test_final_rejects_development_or_partial_matrix(self):
        with self.assertRaisesRegex(ValueError, "FINAL requires"):
            self.build(mode="final")

    def test_new_outputs_bind_structure_markdown_html_and_sources(self):
        package, sources = self.build()
        output = self.root / "new_document_package"
        builder.write_package(package, sources, output)
        self.assertEqual(builder.verify_package(output / "documents.json")["mode"], "draft")
        self.assertEqual({path.name for path in output.iterdir()}, {"plan.md", "report.md", "plan.html", "report.html", "documents.json", "sources.json"})
        with self.assertRaises(FileExistsError):
            builder.write_package(package, sources, output)

    def test_resealed_content_tampering_and_relabelled_final_are_rejected(self):
        for field in ("text", "mode"):
            package, sources = self.build()
            output = self.root / ("tamper_" + field)
            builder.write_package(package, sources, output)
            path = output / "documents.json"
            value = builder.strict_json(path)
            if field == "text":
                value["documents"]["report"]["blocks"][1]["text"] = "所有算法均通过验收"
            else:
                value["mode"] = "final"
                value["completion"]["all_280_slots_terminal"] = True
            value["document_package_sha256"] = builder.canonical_sha256({key: item for key, item in value.items() if key != "document_package_sha256"})
            write(path, value)
            with self.assertRaisesRegex(ValueError, "original bound evidence"):
                builder.verify_package(path)

    def test_changed_markdown_with_resealed_output_index_is_rejected(self):
        package, sources = self.build()
        output = self.root / "tamper_markdown"
        builder.write_package(package, sources, output)
        path = output / "report.md"
        path.write_text("# 伪造正式完成\n", encoding="utf-8")
        index = builder.strict_json(output / "sources.json")
        record = next(item for item in index["outputs"] if item["path"] == "report.md")
        record.update(sha256=builder.sha(path), bytes=path.stat().st_size)
        write(output / "sources.json", index)
        with self.assertRaisesRegex(ValueError, "Markdown/HTML"):
            builder.verify_package(output / "documents.json")

    def test_source_changes_during_publication_prevent_completion_index(self):
        package, sources = self.build()
        self.summary_path.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed during"):
            builder.write_package(package, sources, self.root / "not_published")
        self.assertFalse((self.root / "not_published").exists())

    def test_plan_is_current_humble_scope_and_same_measurement_boundary(self):
        package, _ = self.build()
        text = builder.render_markdown(package["documents"]["plan"])
        for phrase in ("Ubuntu 22.04", "ROS 2 Humble", "120槽", "160槽", "20条", "R_pose", "闭环控制或安全优越性"):
            self.assertIn(phrase, text)
        self.assertNotIn("80次独立飞行", text)
        self.assertNotIn("Jazzy作为仿真基线", text)

    def test_new_control_fields_keep_units_and_requested_shutter_semantics(self):
        package, _ = self.build()
        text = builder.render_markdown(package["documents"]["report"])
        for phrase in ("m/s²", "rad/s²", "仿真s", "short_requested_shutter请求时间窗", "不能单独证明", "没有适用组"):
            self.assertIn(phrase, text)
        for phrase in ("物理距离95%绝对误差分位数", "物理高度反向超调", "导航速度误差p95", "位置设定值二阶差分",
                       "操作层恢复", "检查已知分母", "右删失不是失败", "初始选择和重新选择",
                       "身份unknown样本数", "不是机体实测速度/加速度"):
            self.assertIn(phrase, text)

    def test_detection_review_cache_and_static_subset_metrics_are_source_bound(self):
        fixture, report, review, _ = self.detection_fixture()
        package, _ = self.build(detection_report=report, detection_review=review, detection_source_root=fixture.root)
        self.assertEqual(package["detection_status"], "REVIEWED_STATIC_SUBSET_ONLY")
        text = builder.render_markdown(package["documents"]["report"])
        for phrase in ("不代表全部280次飞行", "子集mAP50", "批准子集帧数", "0.45置信度", "trial_car/car"):
            self.assertIn(phrase, text)
        self.assertIn("| trial_car/car | 1 | 1 | 1 | 1 | 1 |", text)

    def test_detection_without_input_or_without_bound_review_remains_pending(self):
        package, _ = self.build()
        self.assertEqual(package["detection_status"], "PENDING_NOT_PROVIDED")
        fixture, report, review, _ = self.detection_fixture(bound=False)
        package, _ = self.build(detection_report=report, detection_review=review, detection_source_root=fixture.root)
        self.assertEqual(package["detection_status"], "PENDING_VISUAL_REVIEW")
        with self.assertRaisesRegex(ValueError, "required together"):
            self.build(detection_report=report)

    def test_detection_changed_review_cache_and_source_images_are_rejected(self):
        for artifact in ("review", "cache", "image"):
            fixture, report, review, cache = self.detection_fixture()
            path = review if artifact == "review" else cache if artifact == "cache" else fixture.recording.parent / "frame.png"
            with path.open("ab") as stream:
                stream.write(b" ")
            with self.assertRaises(ValueError):
                self.build(detection_report=report, detection_review=review, detection_source_root=fixture.root)

    def test_detection_resealed_metric_or_approval_count_cannot_bypass_inputs(self):
        for field in ("metric", "approval"):
            fixture, report, review, _ = self.detection_fixture()
            child_path = report.parent / "trial_car/detection_report.json"
            child = builder.strict_json(child_path)
            if field == "metric":
                child["reviewed_metrics"]["classes"]["car"]["precision"] = .123
            else:
                child["approved_eligible"] = 999
            write(child_path, child)
            parent = builder.strict_json(report)
            parent["recordings"] = [{key: value for key, value in child.items() if key != "frames"}]
            write(report, parent)
            with self.assertRaisesRegex(ValueError, "reviewed metrics/frames"):
                self.build(detection_report=report, detection_review=review, detection_source_root=fixture.root)

    def test_html_escapes_text_and_plan_rejects_active_content(self):
        document = {"title": "<script>", "status_label": "<unsafe>", "blocks": [builder.paragraph("<img onerror=bad>"), builder.table(["<a>"], [["<b>"]])]}
        html = builder.render_html(document)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img onerror", html)
        self.assertIn("&lt;img", html)
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            builder.markdown_blocks("# title\n<img src='http://example'>")

    def test_figures_require_exact_summary_hash_local_path_and_file_hash(self):
        image = self.root / "figure.png"
        image.write_bytes(b"EXPLICIT_FAKE_PNG_FIXTURE_NOT_RENDERED")
        manifest = self.root / "figures.json"
        data = {"schema_version": 1, "kind": "RELIABILITY_V4_FIGURES", "summary_sha256": builder.sha(self.summary_path),
                "source_hashes": {"scripts/build_reliability_v4_figures.py": builder.sha(ROOT / "scripts/build_reliability_v4_figures.py")},
                "scope": "FIXTURE_ONLY", "figures": [{"path": image.name, "sha256": builder.sha(image), "bytes": image.stat().st_size,
                "caption": "Synthetic fixture", "scope": "FIXTURE_ONLY", "source_role": "engineering_summary"}], "csv": [], "pending": ["No real figure"]}
        write(manifest, data)
        package, _ = self.build(figures_manifest=manifest)
        self.assertEqual(package["documents"]["report"]["blocks"][-4]["type"], "figure")
        for mutation in (lambda value: value.update(summary_sha256="0" * 64),
                         lambda value: value["figures"][0].update(path="../escape.png"),
                         lambda value: value["figures"][0].update(sha256="0" * 64),
                         lambda value: value["figures"][0].update(source_role="verified_estimator_replay"),
                         lambda value: value["figures"][0].update(source_role="wrong_role"),
                         lambda value: value.update(source_hashes={})):
            bad = deepcopy(data)
            mutation(bad)
            write(manifest, bad)
            with self.assertRaises(ValueError):
                self.build(figures_manifest=manifest)

    def test_replay_missing_declarations_account_for_all_twenty_without_inventing_metrics(self):
        directory = self.root / "missing_replay"
        directory.mkdir()
        config, source_root, manifest = cli_fixture(directory)
        output = directory / "saved_run"
        builder.replay_cli.run(config, manifest, output, source_root=source_root)
        sources = builder.Sources()
        summary, _, outcomes = builder.verify_replay(output / "summary.json", manifest, output / "registered_configuration.json", sources, source_root=source_root)
        self.assertEqual(len(outcomes), 20)
        self.assertTrue(all(row["status"] == "MISSING_DECLARED" for row in outcomes))
        self.assertFalse(summary["complete_verified_matrix"])
        self.assertTrue(all(group["available_trial_reports"] == 0 for group in summary["classes"].values()))
        bad = builder.strict_json(output / "summary.json")
        bad["missing_or_invalid_inputs"].pop()
        write(output / "summary.json", bad)
        with self.assertRaisesRegex(ValueError, "unattempted"):
            builder.verify_replay(output / "summary.json", manifest, output / "registered_configuration.json", builder.Sources(), source_root=source_root)

    def test_replay_real_file_fixture_reproduces_saved_values_and_rejects_metric_edits(self):
        directory = self.root / "one_array_replay"
        directory.mkdir()
        config, source_root, array_path, trial, _ = evidence_fixture(directory)
        manifest = directory / "inputs.json"
        slots = {slot: None for slot in builder.scheduled_slots()}
        slots[trial["slot_id"]] = {"path": str(array_path), "sha256": builder.sha(array_path)}
        write(manifest, {"schema_version": 1, "slots": slots})
        output = directory / "saved_run"
        builder.replay_cli.run(config, manifest, output, source_root=source_root)
        summary, _, outcomes = builder.verify_replay(output / "summary.json", manifest, output / "registered_configuration.json", builder.Sources(), source_root=source_root)
        self.assertEqual(summary["available_trial_reports"], 1)
        self.assertEqual(len(outcomes), 20)
        report_path = output / (trial["slot_id"] + ".json")
        bad = builder.strict_json(report_path)
        bad["metrics"]["methods"]["raw"]["position_rmse_m"] = 0.
        write(report_path, bad)
        with self.assertRaisesRegex(ValueError, "Saved replay result differs"):
            builder.verify_replay(output / "summary.json", manifest, output / "registered_configuration.json", builder.Sources(), source_root=source_root)

    def test_draft_replay_registration_is_rejected_before_opening_arrays(self):
        path = self.root / "draft_replay.json"
        write(path, {"schema_version": 1, "status": "DRAFT"})
        with self.assertRaises((ValueError, KeyError)):
            builder.verify_replay(self.summary_path, self.root / "never_opened_manifest.json", path, builder.Sources())

    def test_final_terminal_gate_accepts_failures_and_missing_replay_as_negative_report(self):
        cohorts, rows = {}, []
        for name, mode, count in (("core", "FORMAL", 120), ("extension", "EXTENSION_FORMAL", 160)):
            cohorts[name] = {"mode": mode, "planned_slots": count, "terminal_slots": count,
                             "all_slots_terminal": True, "plan_sha256": "a" * 64}
            rows += [{"cohort": name, "slot_id": str(i), "status": "FAIL"} for i in range(count)]
        summary = {"cohorts": cohorts, "trials": rows, "bootstrap": {"resamples": 10000, "rng_seed": 20261029}}
        config = {"freeze_requirements": {"final_engineering_plan_path": str(self.plan_path),
                  "final_engineering_plan_file_sha256": builder.sha(self.plan_path), "final_engineering_plan_digest": "a" * 64}}
        outcomes = [{"slot_id": slot, "status": "MISSING_DECLARED"} for slot in builder.scheduled_slots()]
        builder.final_gate(summary, {}, config, outcomes, self.plan_path)
        summary["trials"][0]["status"] = "RUNNING"
        with self.assertRaisesRegex(ValueError, "FINAL requires"):
            builder.final_gate(summary, {}, config, outcomes, self.plan_path)

    @unittest.skipUnless(NODE_DOCX_AVAILABLE, "Node.js and npm docx are required for the source-only renderer gate")
    def test_node_gate_verifies_python_sources_without_rendering_docx(self):
        package, sources = self.build()
        output = self.root / "node_checked_package"
        builder.write_package(package, sources, output)
        result = subprocess.run([shutil.which("node"), str(ROOT / "scripts/build_reliability_v4_documents.cjs"),
            "--input", str(output / "documents.json"), "--python", sys.executable, "--validate-only"], capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("NO_RENDERING", result.stdout)
        self.assertFalse(any(output.glob("*.docx")))


if __name__ == "__main__":
    unittest.main()
