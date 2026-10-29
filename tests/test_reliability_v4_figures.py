"""Small synthetic JSON specifications; one tiny figure, never research results."""
from collections import Counter
from copy import deepcopy
import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests import test_replay_evidence as replay_fixtures

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("v4_figure_fixture",ROOT/"scripts/build_reliability_v4_figures.py")
figures = importlib.util.module_from_spec(spec);spec.loader.exec_module(figures)


def write(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,allow_nan=False),encoding="utf-8")


def trial(cohort="core",category="person",group="stage1_velocity",seed=4,condition="clean",status="PASS",value=.4,censored=False):
    identifier = (f"{category}_{group}_seed{seed:03d}" if cohort == "core" else f"{category}_extension_{condition}_seed{seed:03d}")
    return {"cohort":cohort,"slot_id":identifier,"target_class":category,"group":group,"condition":condition,"seed":seed,"status":status,
        "metrics":{"base_link_distance_rmse_m":value,"base_link_height_rmse_m":.1,"navigation_valid_coverage":.8,
                   "physical_follow_truth_coverage":.9,"base_link_distance_settling_s":None if censored else .2,
                   "base_link_height_settling_s":None if censored else .3},
        "settling":{dimension:"RIGHT_CENSORED" if censored else "SETTLED" for dimension in ("distance","height")},
        "required_evaluator_kinds":["source_clock","native_startup","surface_flight","navigation"]}


def summary(rows,*,formal=False,pairs=None):
    cohorts = {}
    for cohort in dict.fromkeys(row["cohort"] for row in rows):
        selected = [row for row in rows if row["cohort"] == cohort]
        counts = dict(Counter(row["status"] for row in selected))
        cohorts[cohort] = {"mode":("EXTENSION_" if cohort == "extension" else "")+("FORMAL" if formal else "PROBE"),
            "planned_slots":len(selected),"terminal_slots":sum(value for state,value in counts.items() if state in figures.TERMINAL),
            "status_counts":counts,"all_engineering_pass":all(row["status"] == "PASS" for row in selected)}
    return {"schema_version":1,"evidence_scope":"FIXTURE_ONLY","cohorts":cohorts,"trials":rows,"paired_comparisons":pairs or [],
            "implementation_sources":{"fixture":"PURE_FIXTURE_ONLY_NOT_A_REAL_RESULT"}}


def paired(rows):
    by_id = {row["slot_id"]:row for row in rows};pairs = []
    for seed in (4,5):
        left_id,right_id = f"person_stage1_position_seed{seed:03d}",f"person_stage1_velocity_seed{seed:03d}"
        left,right = by_id[left_id],by_id[right_id]
        a,b = left["metrics"]["base_link_distance_rmse_m"],right["metrics"]["base_link_distance_rmse_m"]
        pairs.append({"seed":seed,"left_id":left_id,"right_id":right_id,"left_status":left["status"],"right_status":right["status"],
                      "difference":a-b if a is not None and b is not None else None,"both_engineering_pass":left["status"] == right["status"] == "PASS"})
    stats = {}
    for subset in ("all_finite_pairs","both_pass_pairs"):
        values = [pair["difference"] for pair in pairs if pair["difference"] is not None and (subset == "all_finite_pairs" or pair["both_engineering_pass"])]
        stats[subset] = {"n_slots":2,"n":len(values),"n_missing":2-len(values),"mean":figures.statistics.mean(values) if values else None,
                         "ci95":[min(values),max(values)] if len(values)>1 else None,"ci_status":"FIXTURE_ONLY"}
    return {"comparison":"stage1_position_minus_stage1_velocity","target_class":"person","difference_direction":"left_minus_right",
            "planned_pairs_in_matrix":2,"formal_pairs_per_condition":10,"metrics":{"base_link_distance_rmse_m":{**stats,"pairs":pairs}}}


def replay_bundle(root):
    """Twenty tiny synthetic file/source-audited reports; no real data/choices."""
    replay = replay_fixtures.replay
    config,source_root = None,None
    reports,artifacts = [],[]
    for category in replay.CLASSES:
        for seed in replay.SEEDS:
            config,source_root,path,array,_ = replay_fixtures.fixture(root,config=config,source_root=source_root,cls=category,seed=seed)
            receipt = replay_fixtures.cli.verify_export_evidence(path,array,config,source_root=source_root)
            report = replay.replay_trial(array,config,export_evidence=receipt)
            report_path = root/(report["slot_id"]+".json");write(report_path,report)
            reports.append(report);artifacts.append({"slot_id":report["slot_id"],"path":report_path.name,"sha256":figures.sha(report_path)})
    result = replay.paired_trial_summary(reports,config)
    config_path = root/"registered_configuration.json";write(config_path,config)
    result.update(trial_report_artifacts=artifacts,registered_configuration_artifact={"path":config_path.name,"sha256":figures.sha(config_path)},
                  evaluation_source={"configuration_sha256":replay.configuration_digest(config)},missing_or_invalid_inputs=[])
    path = root/"summary.json";write(path,result)
    return path,result


class FigureTests(unittest.TestCase):
    def test_complete_formal_denominators_keep_all_120_plus_160_slots_and_failures(self):
        rows = []
        for category in figures.CLASSES:
            for group in figures.GROUPS:
                for index,seed in enumerate(range(1000,1010)):
                    rows.append(trial(category=category,group=group,seed=seed,status=figures.STATUSES[index%8]))
            for condition in figures.CONDITIONS:
                group = "stage1_position" if condition == "speed_changes_position" else "stage1_velocity"
                for index,seed in enumerate(range(1000,1010)):
                    rows.append(trial("extension",category,group,seed,condition,figures.STATUSES[index%8]))
        data = figures.validate_summary(summary(rows,formal=True));specs,pending = figures.make_specs(data)
        for cohort,total in (("core",120),("extension",160)):
            spec = next(item for item in specs if item["figure_id"] == cohort+"_verdicts")
            self.assertEqual(sum(row["count"] for row in spec["rows"]),total)
            self.assertTrue(any(row["category"] == "FAIL" and row["count"] for row in spec["rows"]))
            self.assertTrue(any(row["category"] == "PENDING" and row["count"] for row in spec["rows"]))
        self.assertTrue(any(item["figure_id"] == "replay_four_methods" for item in pending))
        bad = deepcopy(data);bad["trials"].pop()
        with self.assertRaises(ValueError):figures.validate_summary(bad)

    def test_zero_failure_missing_and_right_censoring_are_separate_and_sample_n_is_not_trial_n(self):
        rows = [trial(seed=4,status="FAIL",value=0.,censored=True),trial(seed=5,status="PENDING",value=None)]
        rows[0]["metric_sample_counts"] = {"base_link_distance_rmse_m":75}
        data = figures.validate_summary(summary(rows));specs,_ = figures.make_specs(data)
        error = next(item for item in specs if item["figure_id"] == "core_navigation_errors")
        values = [row for row in error["rows"] if row["metric"] == "base_link_distance_rmse_m"]
        self.assertEqual([row["value"] for row in values],[0.,None])
        self.assertEqual([row["source_error_samples"] for row in values],[75,None])
        self.assertEqual(values[0]["status"],"FAIL")
        censor = next(item for item in specs if item["figure_id"] == "core_settling_censoring")
        self.assertEqual(sum(row["count"] for row in censor["rows"] if row["category"] == "RIGHT_CENSORED"),2)
        rows[0]["metrics"]["base_link_distance_settling_s"] = 0.
        with self.assertRaisesRegex(ValueError,"Censored"):figures.validate_summary(summary(rows))

    def test_pair_directions_failure_subset_missing_n_and_ci_are_not_reestimated(self):
        rows = [trial(group=group,seed=seed,status="FAIL" if group == "stage1_position" and seed == 5 else "PASS",value=value)
                for group,seed,value in (("stage1_position",4,.8),("stage1_velocity",4,.4),("stage1_position",5,1.1),("stage1_velocity",5,.5))]
        contrast = paired(rows);data = figures.validate_summary(summary(rows,pairs=[contrast]));specs,_ = figures.make_specs(data)
        result = next(item for item in specs if item["figure_id"] == "core_paired_navigation_errors")
        estimates = result["rows"]
        self.assertEqual([item["n_finite_trial_pairs"] for item in estimates],[2,1])
        self.assertEqual([item["formal_planned_pairs"] for item in estimates],[10,10])
        self.assertEqual([item["n_planned_trial_pairs"] for item in estimates],[2,2])
        self.assertIsNone(estimates[1]["ci_low"])
        self.assertEqual(result["raw_rows"][1]["left_status"],"FAIL")
        for field in ("difference","left_id","left_status"):
            bad = deepcopy(data);pair = bad["paired_comparisons"][0]["metrics"]["base_link_distance_rmse_m"]["pairs"][0]
            pair[field] = 9 if field == "difference" else "substituted"
            with self.subTest(field=field),self.assertRaises(ValueError):figures.validate_summary(bad)

    def test_malformed_metrics_counts_and_repeated_trial_cannot_create_a_figure(self):
        original = summary([trial()])
        for defect in ("bool","negative","coverage","duplicate","count","class","nan"):
            bad = deepcopy(original)
            if defect == "bool":bad["trials"][0]["metrics"]["base_link_distance_rmse_m"] = True
            elif defect == "negative":bad["trials"][0]["metrics"]["base_link_distance_rmse_m"] = -1.
            elif defect == "coverage":bad["trials"][0]["metrics"]["navigation_valid_coverage"] = 2.
            elif defect == "duplicate":bad["trials"].append(deepcopy(bad["trials"][0]))
            elif defect == "count":bad["cohorts"]["core"]["status_counts"]["PASS"] = 0
            elif defect == "class":bad["trials"][0]["target_class"] = "truth_actor"
            else:bad["trials"][0]["metrics"]["base_link_distance_rmse_m"] = float("nan")
            with self.subTest(defect=defect),self.assertRaises(ValueError):figures.validate_summary(bad)

    def test_new_navigation_latency_center_jitter_and_requested_shutter_fields_keep_their_units_and_sample_counts(self):
        row = trial(status="FAIL")
        row["metrics"].update(velocity_command_jitter_rms_mps2=0.,yaw_command_jitter_rms_radps2=.3,
            image_center_rmse_px=4.,image_center_normalized_rmse=.1,image_center_observed_coverage=.7,
            image_to_first_command_sim_mean_s=.12,image_to_first_command_sim_p95_s=.2,
            short_requested_shutter_prediction_position_rmse_m=.6,short_requested_shutter_valid_prediction_coverage=.4)
        row["metric_sample_counts"] = {"velocity_command_jitter_rms_mps2":0,"image_center_rmse_px":45,
                                      "short_requested_shutter_prediction_position_rmse_m":None}
        data = figures.validate_summary(summary([row]));specs,_ = figures.make_specs(data)
        by_id = {item["figure_id"]:item for item in specs}
        self.assertIn("core_control_jitter",by_id);self.assertIn("core_image_center",by_id)
        self.assertIn("m/s^2",by_id["core_control_jitter"]["metrics"][0][1])
        jitter = next(item for item in by_id["core_control_jitter"]["rows"] if item["metric"] == "velocity_command_jitter_rms_mps2")
        self.assertEqual((jitter["value"],jitter["source_error_samples"]),(0.,0))
        center = next(item for item in by_id["core_image_center"]["rows"] if item["metric"] == "image_center_rmse_px")
        self.assertEqual(center["source_error_samples"],45)
        self.assertIn("do not independently establish pixel-level occlusion",by_id["core_shutter_prediction"]["caption"])

    def test_pending_replay_never_opens_unbound_trial_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"summary.json";write(path,{"evaluation_status":"PENDING_EXPORT_AND_ONLINE_EQUIVALENCE","complete_verified_matrix":False})
            with patch.object(figures,"verified_file",side_effect=AssertionError("pending cannot open trials")):
                with self.assertRaisesRegex(ValueError,"pending"):figures.load_replay(path)

    def test_verified_replay_plots_position_velocity_with_common_error_counts_and_original_failed_trials(self):
        with tempfile.TemporaryDirectory() as tmp:
            path,data = replay_bundle(Path(tmp))
            result,reports,sources = figures.load_replay(path)
            self.assertEqual(len(reports),20);self.assertEqual(len(sources),21)
            specs,pending = figures.make_specs(summary([trial()]),replay=(result,reports))
            spec = next(item for item in specs if item["figure_id"] == "replay_four_methods")
            self.assertEqual(len(spec["rows"]),20*4*2)
            self.assertEqual({row["status"] for row in spec["rows"]},{"FAIL"})
            self.assertTrue(all(row["source_error_samples"] > 0 for row in spec["rows"]))
            self.assertTrue(any(item["figure_id"] == "replay_velocity_paired_ci" for item in pending))
            for defect in ("missing_manifest","changed_report","traversal","missing_receipt"):
                with self.subTest(defect=defect):
                    bad = deepcopy(data)
                    if defect == "missing_manifest":bad.pop("trial_report_artifacts")
                    elif defect == "changed_report":bad["trial_report_artifacts"][0]["sha256"] = "0"*64
                    elif defect == "traversal":bad["trial_report_artifacts"][0]["path"] = "../outside.json"
                    else:
                        artifact = bad["trial_report_artifacts"][0];report_path = Path(tmp)/artifact["path"]
                        row = figures.load(report_path);row["export_evidence"] = None;write(report_path,row)
                        artifact["sha256"] = figures.sha(report_path)
                    write(path,bad)
                    with self.assertRaises(ValueError):figures.load_replay(path)

    def test_build_manifest_and_csv_survive_pending_replay_without_rendering_any_fake_conclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);path = root/"summary.json";write(path,summary([trial(status="FAIL",value=None,censored=True)]))
            replay = root/"replay.json";write(replay,{"complete_verified_matrix":False})
            with patch.object(figures,"render",return_value=[]):
                manifest = figures.build(path,root/"out",replay_summary_path=replay,only=["core_verdicts"])
            self.assertEqual(manifest["kind"],"RELIABILITY_V4_FIGURES")
            self.assertEqual(manifest["scope"],"FIXTURE_ONLY")
            self.assertEqual(manifest["summary_sha256"],figures.sha(path))
            self.assertEqual(manifest["figures"],[])
            self.assertTrue(any("PENDING_OR_INVALID_REPLAY" in item["reason"] for item in manifest["pending"]))
            for artifact in manifest["csv"]:self.assertEqual(artifact["sha256"],figures.sha(root/"out"/artifact["path"]))
            with (root/"out"/"all_trial_metrics.csv").open(encoding="utf-8-sig") as stream:rows = list(csv.DictReader(stream))
            self.assertTrue(any(row["value"] == "" and row["status"] == "FAIL" for row in rows))
            with self.assertRaises(FileExistsError):figures.build(path,root/"out",only=["core_verdicts"])

    def test_source_change_during_render_aborts_without_publishing_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);path = root/"summary.json";data = summary([trial()]);write(path,data)
            def changed(*args):
                data["trials"][0]["status"] = "FAIL";write(path,data);return []
            with patch.object(figures,"render",side_effect=changed),self.assertRaisesRegex(ValueError,"changed"):
                figures.build(path,root/"out",only=["core_verdicts"])
            self.assertFalse((root/"out"/"manifest.json").exists())

    def test_one_tiny_fixture_exports_png_pdf_svg_with_explicit_fixture_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);path = root/"summary.json"
            write(path,summary([trial(seed=4,status="PASS"),trial(seed=5,status="FAIL"),trial(seed=6,status="PENDING",value=None)]))
            manifest = figures.build(path,root/"out",only=["core_verdicts"],fixture_only=True)
            self.assertEqual({item["format"] for item in manifest["figures"]},{"png","pdf","svg"})
            for item in manifest["figures"]:
                file = root/"out"/item["path"]
                self.assertEqual(item["sha256"],figures.sha(file));self.assertGreater(item["bytes"],500)
                self.assertEqual(item["scope"],"FIXTURE_ONLY")
            self.assertTrue((root/"out"/"core_verdicts.png").read_bytes().startswith(b"\x89PNG"))
            self.assertTrue((root/"out"/"core_verdicts.pdf").read_bytes().startswith(b"%PDF"))
            self.assertIn("FIXTURE_ONLY",(root/"out"/"core_verdicts.svg").read_text(encoding="utf-8"))

    def test_tiny_numeric_and_pair_renderers_keep_failed_and_zero_pair_subsets_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [trial(group=group,seed=seed,status="FAIL",value=value) for group,seed,value in
                    (("stage1_position",4,.8),("stage1_velocity",4,.4),("stage1_position",5,1.1),("stage1_velocity",5,.5))]
            data = summary(rows,pairs=[paired(rows)])
            specs,_ = figures.make_specs(figures.validate_summary(data))
            selected = [item for item in specs if item["figure_id"] in {"core_navigation_errors","core_paired_navigation_errors"}]
            self.assertEqual(len(selected),2)
            for item in selected:
                paths = figures.render(item,root)
                self.assertEqual(len(paths),3)
                svg = next(path for path in paths if path.suffix == ".svg").read_text(encoding="utf-8")
                self.assertIn("FIXTURE_ONLY",svg)
                if item["kind"] == "paired":
                    self.assertIn("n=0/10",svg)
                    self.assertIn("CI absent",svg)


if __name__ == "__main__":unittest.main()
