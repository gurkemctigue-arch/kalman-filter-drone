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
from tests import test_reliability_v4_summary as summary_fixtures

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
    category=rows[0]["target_class"]
    by_id = {row["slot_id"]:row for row in rows};pairs = []
    for seed in (4,5):
        left_id,right_id = f"{category}_stage1_position_seed{seed:03d}",f"{category}_stage1_velocity_seed{seed:03d}"
        left,right = by_id[left_id],by_id[right_id]
        a,b = left["metrics"]["base_link_distance_rmse_m"],right["metrics"]["base_link_distance_rmse_m"]
        pairs.append({"seed":seed,"left_id":left_id,"right_id":right_id,"left_status":left["status"],"right_status":right["status"],
                      "difference":a-b if a is not None and b is not None else None,"both_engineering_pass":left["status"] == right["status"] == "PASS"})
    stats = {}
    for subset in ("all_finite_pairs","both_pass_pairs"):
        values = [pair["difference"] for pair in pairs if pair["difference"] is not None and (subset == "all_finite_pairs" or pair["both_engineering_pass"])]
        stats[subset] = {"n_slots":2,"n":len(values),"n_missing":2-len(values),"mean":figures.statistics.mean(values) if values else None,
                         "ci95":[min(values),max(values)] if len(values)>1 else None,"ci_status":"FIXTURE_ONLY"}
    return {"comparison":"stage1_position_minus_stage1_velocity","target_class":category,"difference_direction":"left_minus_right",
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


def recovery_trial(*, invalid_timing=False):
    row = trial(status="FAIL")
    windows = [{"kind":"short","start_s":index,"end_s":index+.2,"recovery_after_open_s":latency,
                "checks":{"identity_preserved_on_observed_recovery":identity}}
               for index,(latency,identity) in enumerate(((.2,True),(.4,False),(.5,None),(None,None)))]
    if invalid_timing:windows.append({"kind":"short","start_s":5.,"end_s":5.2})
    reports = {"surface_flight":{"occlusions":windows},"navigation":{"windows":[
        {"kind":"explicit_selection","start_s":0.,"end_s":1.,"first_measured_confirmation_after_request_s":.1,"confirmation_censored":False},
        {"kind":"explicit_selection","start_s":1.,"end_s":2.,"first_measured_confirmation_after_request_s":None,"confirmation_censored":True},
        {"kind":"explicit_selection","start_s":2.,"end_s":3.}]}}
    metrics,row["recovery_evidence"] = summary_fixtures.summarizer.recovery_evidence(reports)
    row["metrics"].update(metrics)
    counts = summary_fixtures.summarizer.metric_sample_counts(reports)
    row["metric_sample_counts"] = {name:counts[name] for name in metrics}
    return row


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
            short_requested_shutter_prediction_position_rmse_m=.6,short_requested_shutter_valid_prediction_coverage=.4,
            detector_inference_wall_mean_s=.63,detector_inference_wall_p95_s=.8)
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
        performance = by_id["core_performance"]
        self.assertIn("Detector processing-chain mean (wall s)",dict(performance["metrics"]).values())
        self.assertIn("not pure network inference",performance["caption"])
        self.assertEqual({item["metric"]:item["value"] for item in performance["rows"]
                          if item["metric"].startswith("detector_inference_wall_")},
            {"detector_inference_wall_mean_s":.63,"detector_inference_wall_p95_s":.8})

    def test_p95_overshoot_position_commands_and_operational_events_keep_units_denominators_and_original_failure(self):
        row = recovery_trial()
        row["metrics"].update(base_link_distance_p95_m=.8,base_link_height_p95_m=.3,kf_position_p95_m=.4,kf_velocity_p95_mps=.2,
            base_link_distance_overshoot_m=0.,base_link_height_overshoot_m=.1,position_command_rate_rms_mps=.5,
            position_command_second_difference_rms_mps2=.7)
        data = figures.validate_summary(summary([row,trial(seed=5,status="PENDING",value=None)]))
        specs,_ = figures.make_specs(data);by_id = {item["figure_id"]:item for item in specs}
        self.assertIn("absolute-error",by_id["core_navigation_p95"]["metrics"][0][1])
        self.assertIn("opposite-side",by_id["core_overshoot"]["metrics"][0][1])
        self.assertIn("m/s)",by_id["core_position_command_variation"]["metrics"][0][1])
        self.assertIn("m/s^2",by_id["core_position_command_variation"]["metrics"][1][1])
        self.assertIn("not measured vehicle motion",by_id["core_position_command_variation"]["caption"])
        rates = by_id["core_operational_recovery_fractions"]
        selected = next(item for item in rates["rows"] if item["metric"] == "short_same_track_task_observed_recovery_fraction" and item["seed"] == 4)
        self.assertEqual((selected["value"],selected["operational_fraction_numerator"],selected["operational_fraction_denominator"]),(.25,1,4))
        self.assertEqual(selected["status"],"FAIL")
        timing = by_id["core_operational_recovery_time"]["rows"][0]
        self.assertEqual((timing["source_error_samples"],timing["source_window_samples"]),(None,1))
        self.assertIn("not independent physical identity or ReID",rates["caption"])
        self.assertEqual(sum(item["count"] for item in by_id["core_short_requested_shutter_outcomes"]["rows"]),4)
        self.assertEqual(sum(item["count"] for item in by_id["core_explicit_selection_outcomes"]["rows"]),3)
        self.assertEqual(sum(item["count"] for item in by_id["core_recovery_source_status"]["rows"] if item["category"] == "NOT_IN_INPUT_SUMMARY"),2)
        self.assertTrue(all(item["trials_with_missing_source"] == 1 for item in by_id["core_explicit_selection_outcomes"]["rows"]))

    def test_recovery_missing_timing_censoring_and_fraction_denominators_cannot_turn_into_zero_or_trial_counts(self):
        row = recovery_trial(invalid_timing=True)
        self.assertIsNone(row["metrics"]["short_post_open_measured_recovery_observed_fraction"])
        self.assertEqual(row["recovery_evidence"]["short_requested_shutter"]["missing_or_invalid_timing_windows"],1)
        data = figures.validate_summary(summary([row]));specs,_ = figures.make_specs(data)
        recovery = next(item for item in specs if item["figure_id"] == "core_operational_recovery_fractions")
        self.assertEqual(len(recovery["metrics"]),1)
        self.assertEqual(recovery["metrics"][0][0],"short_same_track_task_recovery_fraction_given_known_recovery")
        for defect in ("fill_missing_fraction","wrong_window_denominator","time_sample_is_trial_n","fraction_over_one","censored_time_as_zero"):
            bad = deepcopy(row)
            if defect == "fill_missing_fraction":bad["metrics"]["short_post_open_measured_recovery_observed_fraction"] = 0.
            elif defect == "wrong_window_denominator":bad["recovery_evidence"]["explicit_selection"]["classified_confirmation_windows"] = 3
            elif defect == "time_sample_is_trial_n":bad["metric_sample_counts"]["short_same_track_task_recovery_mean_s"] = 10
            elif defect == "fraction_over_one":bad["metrics"]["explicit_selection_observed_confirmation_fraction"] = 1.2
            else:
                metric = "explicit_selection_observed_confirmation_mean_s"
                bad["recovery_evidence"]["explicit_selection"].update(observed_confirmation_windows=0,
                    confirmation_right_censored_windows=2,classified_confirmation_windows=2)
                bad["metrics"].update(explicit_selection_observed_confirmation_fraction=0.,explicit_selection_observed_confirmation_p95_s=None)
                bad["metrics"][metric] = 0.
            with self.subTest(defect=defect),self.assertRaises(ValueError):figures.validate_summary(summary([bad]))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);row = trial();row["metrics"]["base_link_distance_p95_m"] = .7
            data = summary([row]);data.pop("evidence_scope");data["implementation_sources"] = {"scripts/summarize_reliability_v4.py":"0"*64}
            path = root/"old_summary.json";write(path,data)
            with self.assertRaisesRegex(ValueError,"older signed-p95"):
                figures.build(path,root/"out",only=["core_navigation_p95"])
            self.assertFalse((root/"out").exists())

    def test_tiny_operational_window_chart_and_csv_retain_missing_source_censoring_and_all_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);path = root/"summary.json";write(path,summary([recovery_trial(),trial(seed=5,status="PENDING",value=None)]))
            manifest = figures.build(path,root/"out",only=["core_short_requested_shutter_outcomes"],fixture_only=True)
            self.assertEqual(len(manifest["figures"]),3)
            svg = (root/"out/core_short_requested_shutter_outcomes.svg").read_text(encoding="utf-8")
            self.assertIn("FIXTURE_ONLY",svg);self.assertIn("not independent trials",svg)
            with (root/"out/all_operational_recovery_evidence.csv").open(encoding="utf-8-sig") as stream:evidence = list(csv.DictReader(stream))
            with (root/"out/all_operational_recovery_windows.csv").open(encoding="utf-8-sig") as stream:windows = list(csv.DictReader(stream))
            self.assertEqual(len(evidence),4);self.assertEqual(len(windows),7)
            self.assertTrue(any(item["source_status"] == "NOT_IN_INPUT_SUMMARY" and item["requested_windows"] == "" for item in evidence))
            self.assertTrue(any(item["window_status"] == "RIGHT_CENSORED_NOT_FAILURE" and item["status"] == "FAIL" for item in windows))

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
        from matplotlib.figure import Figure
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [trial(group=group,seed=seed,status="FAIL",value=value) for group,seed,value in
                    (("stage1_position",4,.8),("stage1_velocity",4,.4),("stage1_position",5,1.1),("stage1_velocity",5,.5))]
            passing = [trial(category="car",group=group,seed=seed,status="PASS",value=value)
                       for group,seed,value in (("stage1_position",4,.6),("stage1_velocity",4,.3),
                                               ("stage1_position",5,.7),("stage1_velocity",5,.4))]
            contrast=paired(passing)
            data = summary(rows+passing,pairs=[paired(rows),contrast])
            specs,_ = figures.make_specs(figures.validate_summary(data))
            selected = [item for item in specs if item["figure_id"] in {"core_navigation_errors","core_paired_navigation_errors"}]
            self.assertEqual(len(selected),2)
            original_save=Figure.savefig;inspected=[]
            def inspect_and_save(fig,path,**kwargs):
                if Path(path).suffix==".png":
                    fig.canvas.draw()
                    for axis in fig.axes:
                        if not axis.get_visible():continue
                        for collection in axis.collections:
                            radius=max(collection.get_sizes(),default=0.)**.5*fig.dpi/144
                            for _,y in axis.transData.transform(collection.get_offsets()):
                                self.assertGreater(y-radius,axis.bbox.y0)
                                self.assertLess(y+radius,axis.bbox.y1)
                    inspected.append(Path(path).name)
                return original_save(fig,path,**kwargs)
            for item in selected:
                with patch.object(Figure,"savefig",autospec=True,side_effect=inspect_and_save):
                    paths = figures.render(item,root)
                self.assertEqual(len(paths),3)
                svg = next(path for path in paths if path.suffix == ".svg").read_text(encoding="utf-8")
                self.assertIn("FIXTURE_ONLY",svg)
                if item["kind"] == "paired":
                    self.assertIn("n=0/10",svg)
                    self.assertIn("CI absent",svg)
            self.assertEqual(len(inspected),2)


if __name__ == "__main__":unittest.main()
