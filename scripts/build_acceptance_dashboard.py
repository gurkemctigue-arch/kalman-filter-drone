"""Build a portable, read-only Chinese acceptance index from recorded evidence.

The generated HTML needs no server, network or JavaScript framework. This
script never launches tests, simulation or evaluation; missing records remain
incomplete. Engineering checks, physical identity and research are distinct.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import html
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
STATUS_ZH = {"PASS":"通过", "FAIL":"失败", "INCOMPLETE_EVIDENCE":"证据不足",
             "WRONG_PHYSICAL_ACTOR":"已观察到错误物理个体",
             "NO_OBSERVED_WRONG_MATCH":"已知帧未见错配（未知仍保留）"}
CHECK_NAMES = {
    "real_visual_flight":"真实机载视觉链路", "basic_flight":"基本飞行", "offline_occlusion":"离线遮挡验收",
    "armed_and_offboard_observed":"已记录解锁与 Offboard", "initial_explicit_box_confirmed_fresh":"初始框选以新鲜测量确认",
    "initial_box_matches_selected_track_snapshot":"框选与所选轨迹一致", "no_tracking_before_initial_selection":"初选前不跟随",
    "multiple_same_class_fresh_tracks_observed":"同帧观察到多个同类轨迹", "task_uuid_changes_require_explicit_selection":"任务变化需显式选择",
    "long_loss_cannot_reactivate_without_explicit_selection":"长失联后禁止自行恢复", "long_loss_cannot_control_before_explicit_selection":"重选前保持停止",
    "active_states_remain_fresh":"活动状态保持新鲜", "observed_ambiguities_suspend_control":"歧义时暂停控制",
    "selected_geometric_ambiguity_observed_if_required":"所要求的目标歧义已发生", "final_sustained_tracking":"末尾持续跟随",
    "final_sustained_hover":"末尾持续安全悬停", "terminal_hover_follows_selected_ambiguity":"悬停有实际目标歧义依据",
    "short_and_long_occlusion":"短时及长时遮挡", "required_short_and_long_occlusions_present":"所要求的短长遮挡记录齐全",
    "recorded_occlusions_pass":"录制的遮挡测试通过", "long_occlusion_braking_from_motion":"长遮挡从运动状态制动",
    "sustained_tracking_after_reselection":"重选后持续跟随", "three_encoder_joints_recorded":"三轴真实编码器反馈",
    "all_three_commands_recorded":"三轴命令已记录", "camera_tf_is_dynamic_feedback_only":"相机 TF 来自动态反馈",
    "physical_link_pose_matches_feedback_geometry":"物理相机姿态与反馈一致", "dynamic_tf_available_at_image_timestamps":"图像时刻动态 TF 可用",
    "all_three_real_joints_move":"三轴物理关节实际运动", "commands_and_encoders_have_physical_lag":"命令与反馈为独立通道",
    "exclusive_setpoint_fields":"位置/速度指令互斥", "full_recorded_trial_end":"保留完整录制末尾",
}


def esc(value):
    return html.escape(str(value), quote=True)


def relative_url(path, output):
    return quote(Path(os.path.relpath(path, output.parent)).as_posix(), safe="/")


def read_json(path, errors):
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError("JSON 顶层不是对象")
        return data
    except (OSError, ValueError) as error:
        errors.append(f"{path.name}: {type(error).__name__}: {error}")
        return None


def evidence_status(data):
    if not data:
        return "INCOMPLETE_EVIDENCE"
    raw = data.get("result", data.get("acceptance", {}).get("result"))
    checks = data.get("checks", data.get("acceptance", {}).get("checks", {}))
    if not isinstance(checks, dict):
        checks = {}
    if raw in {"FAIL", "FAIL_OR_INCOMPLETE"} or any(value is False for value in checks.values()):
        return "FAIL"
    if raw == "PASS" and checks and all(value is True for value in checks.values()):
        return "PASS"
    return "INCOMPLETE_EVIDENCE"


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def fraction(numerator, denominator):
    return f"{numerator}/{denominator} ({100*numerator/denominator:.1f}%)" if finite(numerator) and finite(denominator) and denominator > 0 else "未记录"


def identity_coverage(data):
    """All task opportunities are the denominator, including missing detections."""
    report = (data or {}).get("selected_physical_identity_all")
    report = report if isinstance(report,dict) else {}
    counts = report.get("counts")
    counts = counts if isinstance(counts,dict) else {}
    total = report.get("frames")
    correct, wrong = counts.get("CORRECT"), counts.get("WRONG_PHYSICAL_ACTOR")
    not_observed, geometry_unknown = counts.get("NOT_OBSERVED"), counts.get("UNKNOWN_GEOMETRY")
    initial_unknown = counts.get("UNKNOWN_TASK_INITIAL_ID")
    valid = (type(total) is int and total >= 0 and all(type(value) is int and value >= 0
             for value in (correct,wrong,not_observed,geometry_unknown,initial_unknown))
             and sum((correct,wrong,not_observed,geometry_unknown,initial_unknown)) == total)
    if not valid:
        return {"available":False,"status":"INCOMPLETE_EVIDENCE","reason":"缺少完整的全部任务机会分母或分类计数"}
    return {"available":True,"total":total,"known":correct+wrong,"correct":correct,"wrong":wrong,
            "status":"WRONG_PHYSICAL_ACTOR" if wrong else "NO_OBSERVED_WRONG_MATCH" if correct else "INCOMPLETE_EVIDENCE",
            "no_fresh":not_observed,"unknown":geometry_unknown+initial_unknown,
            "known_coverage":fraction(correct+wrong,total),"correct_lower_bound":fraction(correct,total),
            "wrong_fraction":fraction(wrong,total),"no_fresh_fraction":fraction(not_observed,total),
            "unknown_fraction":fraction(geometry_unknown+initial_unknown,total),
            "conditional_agreement":fraction(correct,correct+wrong),"raw_result":report.get("safety_result")}


def natural_key(value):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", str(value))]


def versioned_evaluation(directory, stem, max_schema, reports, errors):
    """Choose the newest supported contract, regardless of its outcome.

    Corrected bag decoders leave earlier parser reports in place. A PASS
    must never win over a newer supported FAIL just because it is positive.
    """
    candidates=[]
    for path in directory.glob(stem+"*.json"):
        if not re.fullmatch(re.escape(stem)+r"(?:_v\d+)?\.json",path.name):
            continue
        if path.name not in reports:
            reports[path.name]=read_json(path,errors)
        report=reports[path.name]
        if report is None:
            continue
        schema=report.get("schema_version",0)
        supported=type(schema) is int and 0<=schema<=max_schema
        candidates.append({"file":path.name,"report":report,"schema":schema,
                           "supported":supported,"status":evidence_status(report)})
    supported=[row for row in candidates if row["supported"]]
    selected=max(supported,key=lambda row:(row["schema"],row["file"]==stem+".json",natural_key(row["file"]))) if supported else None
    return selected,candidates


def collect_trial(directory):
    errors = []
    names = ("run_config.json", "summary.json", "offline_evaluation.json", "stage2_evaluation.json",
             "auto_unique_evaluation.json", "flight_evaluation.json", "gimbal_evaluation.json", "physical_identity.json")
    reports = {name:read_json(directory/name,errors) for name in names}
    gimbal_version,gimbal_history=versioned_evaluation(directory,"gimbal_evaluation",3,reports,errors)
    auto_version,auto_history=versioned_evaluation(directory,"auto_unique_evaluation",2,reports,errors)
    config, summary = reports["run_config.json"] or {}, reports["summary.json"] or {}
    match = re.match(r"stage([123])_", directory.name)
    stage = config["stage"] if type(config.get("stage")) is int and config["stage"] in {1,2,3} else int(match.group(1)) if match else 1
    category = config.get("target_class", summary.get("class_name", "未记录"))
    required = ["run_config.json", "summary.json", "onboard.mp4", "rosbag/metadata.yaml", "configuration/source_sha256.json"]
    missing = [name for name in required if not (directory/name).is_file()]
    if not any(path.is_file() for pattern in ("*.db3*","*.mcap*") for path in (directory/"rosbag").glob(pattern)):
        missing.append("rosbag 实际数据文件")
    if (directory/"onboard.mp4").is_file() and (directory/"onboard.mp4").stat().st_size <= 1024:
        missing.append("非空有效视频")
    dimensions = []
    if stage == 1:
        # Reuse the same strict, read-only engineering rules as the final
        # matrix; an old PASS label or basic_flight alone is insufficient.
        try:
            from summarize_stage1_acceptance import trial_report
            strict = trial_report(directory)
            result = "PASS" if strict.get("passed") is True else "INCOMPLETE_EVIDENCE" if strict.get("missing_artifacts") else "FAIL"
            dimensions.append({"name":"阶段一严格工程验收","status":result,"checks":strict.get("checks",{}),"file":"offline_evaluation.json"})
        except (OSError, ValueError, TypeError, KeyError) as error:
            errors.append(f"严格工程汇总: {type(error).__name__}: {error}")
            dimensions.append({"name":"阶段一严格工程验收","status":"INCOMPLETE_EVIDENCE","checks":{},"file":"offline_evaluation.json"})
    else:
        auto_unique = stage == 2 and not reports["stage2_evaluation.json"] and auto_version is not None
        chosen=auto_version if auto_unique else gimbal_version if stage==3 else None
        report_name = chosen["file"] if chosen else "stage2_evaluation.json" if stage == 2 else "gimbal_evaluation.json"
        report = chosen["report"] if chosen else (reports[report_name] or {}) if stage==2 else {}
        dimensions.append({"name":("唯一实例多候选歧义验收" if auto_unique else "指定目标安全验收") if stage == 2 else "三轴云台物理与几何验收",
                           "status":evidence_status(report),"checks":report.get("checks",{}),"file":report_name})
        if stage == 3:
            flight_name = "flight_evaluation.json" if reports["flight_evaluation.json"] is not None else "offline_evaluation.json"
            flight = reports[flight_name] or {}
            flight_checks={}
            if flight:
                from summarize_stage1_acceptance import offline_acceptance_evidence
                flight_checks=offline_acceptance_evidence(flight)
                flight_checks["offline_acceptance_result"] = flight.get("acceptance",{}).get("result") == "PASS"
            dimensions.append({"name":"独立跟随/遮挡验收","status":evidence_status({"result":flight.get("acceptance",{}).get("result"),"checks":flight_checks}),
                               "checks":flight_checks,"file":flight_name})
        dimensions.append({"name":"原始监控与飞行证据","status":"PASS" if summary.get("source") == "ONBOARD_RGBD_YOLO_PX4_FLIGHT"
                            and all(summary.get(key) is True for key in ("basic_flight_passed","armed_seen","offboard_seen"))
                            else "FAIL" if summary.get("basic_flight_passed") is False else "INCOMPLETE_EVIDENCE",
                           "checks":{key:summary.get(key) for key in ("basic_flight_passed","armed_seen","offboard_seen")},"file":"summary.json"})
    values = [row["status"] for row in dimensions]
    status = "FAIL" if "FAIL" in values else "INCOMPLETE_EVIDENCE" if missing or errors or "INCOMPLETE_EVIDENCE" in values else "PASS"
    failures = [f"{dimension['name']}: {CHECK_NAMES.get(key,key)}" for dimension in dimensions
                for key,value in dimension["checks"].items() if value is False]
    identity=identity_coverage(reports["physical_identity.json"])
    if identity.get("wrong",0):
        # Lifecycle safety can remain PASS while independent image/GT
        # evidence proves the wrong actor was followed. Never hide that
        # failure behind the safety result or a stable target UUID.
        status="FAIL"
        failures.append("独立物理身份评价观察到错误物理个体；不能用任务 UUID 保持掩盖")
    links = [directory/name for name in reports if (directory/name).is_file()]
    links += [directory/name for name in ("rosbag/metadata.yaml","configuration/source_sha256.json","ros.log","px4.log","telemetry.jsonl","physical_identity.frames.jsonl",
                                          "process_exit_codes.json","monitor.log","bag.log","offline_evaluation.log",
                                          "online_state_accuracy_v2.json","follow_dynamics.json",
                                          "identity_review/index.json","identity_review/visual_review.json","identity_review/assistant_screening.json") if (directory/name).is_file()]
    links += sorted({path for pattern in ("*.db3*", "*.mcap*") for path in (directory/"rosbag").glob(pattern) if path.is_file()})
    frames = sorted(directory.glob("frame_*.jpg"),key=natural_key)
    frames = [frames[index] for index in sorted({0,len(frames)//2,len(frames)-1})] if frames else []
    reviews = sorted((directory/"identity_review").glob("identity_review_*.jpg"),key=natural_key)
    return {"directory":directory,"stage":stage,"class":category,"config":config,"summary":summary,"reports":reports,
            "dimensions":dimensions,"status":status,"missing":missing,"errors":errors,"failures":failures,
            "links":links,"frames":frames,"reviews":reviews,"identity":identity,
            "evaluation_history":gimbal_history+auto_history}


def discover_trials(roots):
    directories = set()
    for root in roots:
        for marker in ("run_config.json","summary.json","stage2_evaluation.json","gimbal_evaluation.json","physical_identity.json"):
            directories.update(path.parent for path in root.rglob(marker) if re.match(r"stage[123]_",path.parent.name))
        # Resumable engineering matrices use prefixes such as stage23_...
        # and record the actual phase in run_config, rather than the name.
        for path in root.rglob("run_config.json"):
            if path.parent in directories:
                continue
            config=read_json(path,[])
            if config and type(config.get("stage")) is int and config["stage"] in {1,2,3}:
                directories.add(path.parent)
    return [collect_trial(directory) for directory in sorted(directories,key=lambda path:natural_key(path.as_posix()))]


def research_progress(data):
    """Execution completeness is distinct from successful/significant results."""
    if isinstance(data.get("recordings"),list) and "reviewed_aggregate" in data:
        reports=data["recordings"]
        return {"kind":"detection","complete":False,"state":"已复核子集" if data["reviewed_aggregate"] is not None else "PENDING_VISUAL_REVIEW",
                "sampled":sum(row.get("sampled_opportunities",0) for row in reports),
                "eligible":sum(row.get("geometric_eligible",0) for row in reports),
                "reviewed":sum(row.get("approved_eligible",0) for row in reports),
                "recording_states":[row.get("publication_status","未记录") for row in reports]}
    expected = next((data[key] for key in ("expected_trials","planned_trials","planned_count","total_planned") if type(data.get(key)) is int),None)
    rows = next((data[key] for key in ("trials","runs","jobs","conditions") if isinstance(data.get(key),list)),[])
    counts = Counter()
    for row in rows:
        if not isinstance(row,dict):
            continue
        label = str(row.get("status",row.get("state",row.get("result","")))).lower()
        if label in {"planned","pending","queued"}:
            counts["planned"] += 1
        elif label in {"started","running","in_progress","incomplete"}:
            counts["started"] += 1
        elif label in {"complete","completed","pass","fail","failed","done","incomplete_evidence"}:
            counts["complete"] += 1
            counts["failed"] += label in {"fail","failed","incomplete_evidence"}
        else:
            counts["unknown"] += 1
    recorded = data.get("recorded_trials")
    if expected is not None:
        # Unmaterialized planned entries remain in the denominator.
        counts["planned"] += max(0,expected-len(rows))
        complete = data.get("complete") is True and counts["complete"] == expected and not counts["started"] and not counts["unknown"]
        return {"kind":"matrix","expected":expected,"recorded":recorded,"counts":dict(counts),"complete":complete,
                "state":"complete" if complete else "started" if rows else "planned"}
    return {"kind":"offline_or_partial","expected":None,"counts":dict(counts),"complete":False,
            "state":"已有离线/局部结果；未声明完整独立飞行矩阵",
            "recorded_condition_repeats":data.get("recorded_condition_repeats"),
            "metric_records":data.get("metric_records"),"seed_count":data.get("seed_count_per_fault_condition")}


FLIGHT_TERMINAL = {"PASS", "FAIL", "INCOMPLETE", "INCOMPLETE_EVIDENCE", "INTERRUPTED"}
OFFLINE_TERMINAL = {"RECORDED", "INCOMPLETE_EVIDENCE", "INTERRUPTED", "NOT_APPLICABLE_NO_SELECTED_TASK"}


def slot_counts(rows, expected, *, offline=False):
    """Keep every planned slot, with unknown labels distinct from success."""
    raw = Counter(str(row.get("status", "UNKNOWN")) for row in rows)
    raw["PENDING"] += max(0, expected-len(rows))
    terminal = OFFLINE_TERMINAL if offline else FLIGHT_TERMINAL
    running = {"RUNNING_ANALYSIS"} if offline else {"RUNNING_FLIGHT", "RUNNING_EVALUATION"}
    return {"raw":dict(raw), "pending":raw["PENDING"],
            "running":sum(raw[key] for key in running),
            "terminal":sum(raw[key] for key in terminal),
            "failed":sum(raw[key] for key in ("FAIL", "INCOMPLETE", "INCOMPLETE_EVIDENCE", "INTERRUPTED")),
            "unknown":sum(value for key,value in raw.items() if key not in terminal|running|{"PENDING"}),
            "complete":len(rows)==expected and sum(raw[key] for key in terminal)==expected}


def collect_full_plan(path, data):
    """Map Linux provenance paths into this copied results tree, read-only.

    Child manifests are updated during each flight while the consolidated
    summary is only refreshed at an invocation boundary. Index both without
    letting an older summary hide a running or failed child slot.
    """
    errors=[];links=[path];expected=166
    trials=data.get("trials",[])
    trials=trials if isinstance(trials,list) else []
    names=[row.get("name") for row in trials if isinstance(row,dict)]
    valid=(len(names)==expected and all(isinstance(name,str) and name for name in names)
           and len(set(names))==expected)
    digest=hashlib.sha256(json.dumps({key:value for key,value in data.items() if key not in {"created_utc","plan_sha256"}},
                                  sort_keys=True,separators=(",", ":")).encode()).hexdigest()
    if not valid or data.get("plan_sha256")!=digest:
        errors.append("主计划必须保留166个不同任务名及匹配的计划摘要；当前计划不可认证")
    names=list(dict.fromkeys(name for name in names if isinstance(name,str) and name))
    flights={name:{"name":name,"status":"PENDING"} for name in names}

    def merge(rows, source):
        seen=set()
        for row in rows:
            if not isinstance(row,dict):
                errors.append(f"{source}: 无效任务记录");continue
            name=row.get("name")
            if name not in flights or name in seen:
                errors.append(f"{source}: 未登记或重复任务 {name}");continue
            seen.add(name)
            flights[name]={"name":name,"status":row.get("result",row.get("status","UNKNOWN"))}

    summary_path=path.parent/"summary.json"
    summary=read_json(summary_path,errors)
    if summary is not None:
        links.append(summary_path)
        if summary.get("plan_sha256")==data.get("plan_sha256") and summary.get("planned_flights")==expected:
            merge(summary.get("trials",[]),"主统计快照")
        else:
            errors.append("主统计快照与166计划不匹配，未采用其完成声明")
    results_root=path.parent.parent
    for matrix in data.get("matrices",[]):
        try:
            report_reference=PurePosixPath(matrix["report"])
            suffix=report_reference.relative_to(PurePosixPath(data["frozen_root"])/"results") if report_reference.is_absolute() else report_reference.relative_to("results")
            report_path=(results_root/Path(*suffix.parts)).resolve()
            if not report_path.is_relative_to(results_root.resolve()):
                raise ValueError("report escaped results root")
        except (KeyError,TypeError,ValueError):
            errors.append("子矩阵报告路径不属于冻结结果根，未读取");continue
        report=read_json(report_path,errors)
        if report is None:
            continue
        links.append(report_path)
        if matrix.get("kind")=="stage1":
            merge(report.get("trials",[]),report_path.name)
        else:
            merge([{"name":slot.get("trial",{}).get("name"),"status":slot.get("status","UNKNOWN")}
                   for slot in report.get("slots",[]) if isinstance(slot,dict)],report_path.name)
    offline_path=path.parent/"offline_manifest.json"
    offline=read_json(offline_path,errors);offline_rows=[]
    if offline is not None:
        links.append(offline_path)
        rows=offline.get("trials")
        if offline.get("plan_sha256")!=data.get("plan_sha256") or not isinstance(rows,dict):
            errors.append("离线清单不属于当前计划，未采用其完成声明")
        else:
            for name,row in rows.items():
                if name not in flights or not isinstance(row,dict) or row.get("name")!=name:
                    errors.append(f"离线清单含未登记或不一致任务 {name}")
                else:
                    offline_rows.append(row)
    flight_counts=slot_counts(list(flights.values()),expected)
    offline_counts=slot_counts(offline_rows,expected,offline=True)
    superseded_path=path.parent/"superseded.json"
    superseded=read_json(superseded_path,errors)
    if superseded is not None:
        links.append(superseded_path)
        if superseded.get("plan_sha256")!=data.get("plan_sha256"):
            errors.append("历史替代说明与当前计划摘要不匹配，未采用其替代声明")
            superseded=None
    progress={"kind":"full_plan","expected":expected,"flight_counts":flight_counts,"offline_counts":offline_counts,
              "complete":valid and not errors and flight_counts["complete"] and offline_counts["complete"],
              "all_flights_pass":valid and not errors and flight_counts["raw"].get("PASS",0)==expected,
              "flight_rows":list(flights.values()),"results_root":results_root,"superseded":superseded}
    return {"path":path,"data":data,"progress":progress,"errors":errors,"links":links}


def collect_extended(path, data):
    errors=[];plan=data.get("plan",{});slots=data.get("slots",[])
    plan=plan if isinstance(plan,dict) else {}
    slots=slots if isinstance(slots,list) else []
    trials=plan.get("trials",[]);names=[row.get("name") for row in trials if isinstance(row,dict)]
    slot_names=[row.get("trial",{}).get("name") for row in slots if isinstance(row,dict)]
    if (plan.get("expected_trials")!=16 or plan.get("primary_166_included") is not False or len(names)!=16
            or len(set(names))!=16 or slot_names!=names):
        errors.append("扩展工程清单需保留独立16槽及其原计划绑定")
    digest=hashlib.sha256(json.dumps(plan,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
    if data.get("plan_sha256")!=digest:
        errors.append("扩展工程计划摘要不匹配")
    counts=slot_counts([row for row in slots if isinstance(row,dict)],16)
    return {"path":path,"data":data,"errors":errors,"links":[path],
            "progress":{"kind":"extended_engineering","expected":16,"flight_counts":counts,
                        "complete":counts["complete"] and not errors,
                        "all_flights_pass":counts["raw"].get("PASS",0)==16 and not errors}}


def discover_research(roots):
    candidates = set()
    for root in roots:
        for pattern in ("plan.json","*manifest*.json","*repetition_report.json","*matrix*.json","research_report.json","detection_report.json","trackeval_comparison.json"):
            candidates.update(root.rglob(pattern))
    entries = []
    for path in sorted(candidates,key=lambda item:natural_key(item.as_posix())):
        errors=[]; data=read_json(path,errors)
        if data and path.name=="plan.json" and "frozen_root" in data and "matrices" in data:
            entries.append(collect_full_plan(path,data))
        elif data and data.get("source")=="EXTENDED_ENGINEERING_16_FLIGHTS":
            entries.append(collect_extended(path,data))
        elif data and path.name=="trackeval_comparison.json":
            entries.append({"path":path,"data":data,"progress":{"kind":"metric_reference","state":data.get("result","未记录"),"complete":False},"errors":errors})
        elif data and (any(key in data for key in ("expected_trials","planned_trials","planned_count","total_planned","metric_records","research_claim_boundary","recorded_condition_repeats"))
                       or path.name=="detection_report.json" and "reviewed_aggregate" in data):
            entries.append({"path":path,"data":data,"progress":research_progress(data),"errors":errors})
    return entries


def discover_research_figures(roots):
    """Index exported plots without treating a plot manifest as acceptance."""
    entries=[];seen=set()
    for root in roots:
        for path in sorted(root.rglob("manifest.json")):
            if path in seen:
                continue
            seen.add(path)
            errors=[];data=read_json(path,errors)
            if not data:
                continue
            names=data.get("figures");artifact_contract=False
            if not isinstance(names,list) and isinstance(data.get("artifacts_sha256"),dict) and "source_summary_sha256" in data:
                names=list(data["artifacts_sha256"]);artifact_contract=True
            if not isinstance(names,list):
                continue
            figures=[];missing=[];downloads=[]
            for name in names:
                if not isinstance(name,str):
                    continue
                candidate=(path.parent/name).resolve()
                if not candidate.is_relative_to(path.parent.resolve()) or candidate.suffix.lower() not in {".png",".jpg",".jpeg",".svg",".pdf",".csv",".json"}:
                    missing.append(name)
                elif candidate.is_file():
                    preview=candidate.suffix.lower() in ({".png",".jpg",".jpeg"} if artifact_contract else {".png",".jpg",".jpeg",".svg"})
                    (figures if preview else downloads).append(candidate)
                else:
                    missing.append(name)
            entries.append({"path":path,"figures":figures,"missing":missing,"downloads":downloads,
                            "boundary":data.get("claim_boundary",""),"errors":errors})
    return entries


def link(path, output, label=None):
    return f'<a href="{esc(relative_url(path,output))}">{esc(label or path.name)}</a>'


def badge(status):
    appearance={"WRONG_PHYSICAL_ACTOR":"FAIL","NO_OBSERVED_WRONG_MATCH":"INCOMPLETE_EVIDENCE"}.get(status,status)
    return f'<span class="badge {esc(appearance)}">{esc(STATUS_ZH.get(status,status))}</span>'


def check_table(checks):
    if not checks:
        return '<p class="muted">未记录可核对的逐项检查。</p>'
    rows=[]
    for key,value in checks.items():
        state="PASS" if value is True else "FAIL" if value is False else "INCOMPLETE_EVIDENCE"
        rows.append(f'<tr><td>{esc(CHECK_NAMES.get(key,key))}<small>{esc(key)}</small></td><td>{badge(state)}</td></tr>')
    return '<table><tbody>'+''.join(rows)+'</tbody></table>'


def study_progress_html(item, output):
    progress=item["progress"];expected=progress["expected"];counts=progress["flight_counts"]
    primary=progress["kind"]=="full_plan"
    body=[f'<h4>{"主研究166次飞行" if primary else "独立扩展16次工程录制"}</h4>',
          f'<p>执行状态：{"全部预定证据已尝试" if progress["complete"] else "未完成"}；计划分母 {expected}；'
          f'PENDING {counts["pending"]} / RUNNING {counts["running"]} / TERMINAL {counts["terminal"]}；'
          f'失败、不完整或中断 {counts["failed"]}；未知状态 {counts["unknown"]}。</p>',
          '<p>飞行原始状态：'+esc(json.dumps(counts["raw"],ensure_ascii=False,sort_keys=True))+'</p>',
          f'<p>全部飞行安全通过：{"是" if progress["all_flights_pass"] else "尚未成立"}。执行完成与安全通过分别判断，失败保留在原计划分母。</p>']
    if primary:
        superseded=progress.get("superseded")
        if superseded:
            body.append('<p class="notice">历史研究，已由 '+esc(superseded.get("replacement_prefix","未声明新版本"))+
                        ' 替代。此处保留原计划、原判定和所有未执行槽；已有飞行不计入替代研究分母，剩余槽不会标为完成。</p>')
            body.append('<p>替代原因：'+esc(superseded.get("reason","未说明"))+'</p>')
        offline=progress["offline_counts"]
        body.append(f'<p>离线分析分母 {expected}；PENDING {offline["pending"]} / RUNNING {offline["running"]} / TERMINAL {offline["terminal"]}；'
                    f'不完整或中断 {offline["failed"]}；未知状态 {offline["unknown"]}。</p>')
        body.append('<p>离线原始状态：'+esc(json.dumps(offline["raw"],ensure_ascii=False,sort_keys=True))+'</p>')
        body.append('<p class="muted">飞行优先采用当前子清单，主 summary 为调用结束时的快照；离线未登记槽仍为 PENDING。NOT_APPLICABLE_NO_SELECTED_TASK 仅表示该任务无需指定个体分析，不能代替飞行通过。</p>')
        body.append('<details><summary>全部166个预定飞行槽（包括未开始和失败）</summary><table><tr><th>任务名</th><th>飞行状态</th><th>已有录制</th></tr>')
        for row in progress["flight_rows"]:
            directory=progress["results_root"]/row["name"]
            artifacts=[]
            if directory.resolve().is_relative_to(progress["results_root"].resolve()):
                for name in ("run_config.json","summary.json","onboard.mp4","rosbag/metadata.yaml"):
                    if (directory/name).is_file():
                        artifacts.append(link(directory/name,output,name))
            body.append('<tr><td>'+esc(row["name"])+'</td><td>'+esc(row["status"])+'</td><td>'+(' · '.join(artifacts) or '尚无对应文件')+'</td></tr>')
        body.append('</table></details>')
    else:
        body.append('<p class="muted">扩展16次单列于主166次之外，每个工程条件单次录制；不能当作每条件10次重复。</p>')
    if item.get("links"):
        body.append('<p>源清单：'+' · '.join(link(path,output,str(path.relative_to(item["path"].parent)) if path.is_relative_to(item["path"].parent) else path.name) for path in item["links"])+'</p>')
    if item["errors"]:
        body.append('<p class="notice">清单问题：'+esc('；'.join(item["errors"]))+'</p>')
    return ''.join(body)


def trial_html(trial, output, index):
    directory=trial["directory"];config=trial["config"];identity=trial["identity"]
    # The common runner retains a gimbal_mode default even in fixed-camera
    # stage-two runs. It is a meaningful runtime choice only in stage three.
    meta=' · '.join(str(value) for value in (trial["class"],config.get("command_mode","未记录控制模式"),config.get("scenario_kind",""),
                         config.get("gimbal_mode","") if trial["stage"]==3 else "",config.get("estimator_method","")) if value)
    body=[f'<article class="trialcard" id="trial-{index}" data-stage="{trial["stage"]}" data-status="{trial["status"]}">',
          f'<h3>{esc(directory.name)} {badge(trial["status"])}</h3><p>{esc(meta)}</p>',
          '<p class="muted">本状态限于本次录制的工程证据；不等于整个阶段完成。</p>']
    for dimension in trial["dimensions"]:
        report_path=directory/dimension["file"]
        report_link=link(report_path,output) if report_path.is_file() else "报告未生成（"+esc(dimension["file"])+"）"
        body.append(f'<details><summary>{esc(dimension["name"])} {badge(dimension["status"])}</summary><p>采用报告：{report_link}</p>{check_table(dimension["checks"])}</details>')
    if len(trial.get("evaluation_history",[]))>1:
        body.append('<details><summary>评价器版本历史（保留旧报告结果）</summary><p class="muted">按受支持的最高 schema 选择当前报告，与结果正负无关；旧解析/评价结果保留。</p><table><tr><th>报告</th><th>Schema</th><th>状态</th></tr>')
        for row in trial["evaluation_history"]:
            body.append('<tr><td>'+link(directory/row["file"],output)+'</td><td>'+esc(row["schema"])+('</td><td>' if row["supported"] else '（未支持）</td><td>')+badge(row["status"])+'</td></tr>')
        body.append('</table></details>')
    auto_unique_only = trial["stage"] == 2 and any(row["file"].startswith("auto_unique_evaluation") for row in trial["dimensions"])
    if auto_unique_only:
        body.append('<p class="muted">本次唯一实例多候选测试未选定物理个体，指定目标身份评价不适用。</p>')
    elif trial["stage"] == 2 or trial["reports"]["physical_identity.json"]:
        body.append('<p>独立物理身份评价：'+badge(identity["status"])+"</p>")
        if identity["available"]:
            fields=(("已知物理身份覆盖率",identity["known_coverage"]),("全部任务机会中的正确比例下界",identity["correct_lower_bound"]),
                    ("错误物理个体/全部机会",identity["wrong_fraction"]),("无新鲜所选检测/全部机会",identity["no_fresh_fraction"]),
                    ("几何或初始身份未知/全部机会",identity["unknown_fraction"]),("已知帧中的条件正确率",identity["conditional_agreement"]))
            body.append('<details open><summary>独立物理身份覆盖：保留失联和 unknown 分母</summary><table>'+''.join(f'<tr><td>{esc(name)}</td><td>{esc(value)}</td></tr>' for name,value in fields)+'</table><p class="muted">已知帧正确率不能代替全程身份保持率。GT 为离线 amodal 投影，遮挡/交叉 unknown 仍须核验。</p></details>')
        else:
            body.append('<p class="notice">物理身份：证据不足。'+esc(identity["reason"])+'。任务 UUID 保持不证明物理身份。</p>')
    problems=trial["failures"]+["缺失："+value for value in trial["missing"]]+trial["errors"]
    if problems:
        body.append('<details open><summary>失败与缺失清单</summary><ul>'+''.join('<li>'+esc(value)+'</li>' for value in problems)+'</ul></details>')
    video=directory/"onboard.mp4"
    if video.is_file() and video.stat().st_size > 1024:
        body.append(f'<video controls preload="none" src="{esc(relative_url(video,output))}"></video><p>{link(video,output,"打开/下载原始视频")}</p>')
    else:
        body.append('<p class="notice">没有可播放的有效录制视频。</p>')
    if trial["frames"]:
        body.append('<div class="frames">'+''.join(f'<a href="{esc(relative_url(path,output))}"><img loading="lazy" src="{esc(relative_url(path,output))}" alt="{esc(path.name)}"><small>{esc(path.name)}（抽样帧，时间请以遥测核对）</small></a>' for path in trial["frames"])+'</div>')
    if trial["reviews"]:
        body.append('<p>采集时间对齐的独立身份接触表：'+ ' · '.join(link(path,output) for path in trial["reviews"])+'</p>')
    body.append('<details><summary>原始记录与评价 JSON</summary><ul>'+''.join('<li>'+link(path,output,str(path.relative_to(directory)))+'</li>' for path in trial["links"])+'</ul></details></article>')
    return ''.join(body)


def build_dashboard(roots, output, *, checkpoint_title=None, checkpoint_note=None, highlight_frames=()):
    roots=[Path(root).resolve() for root in roots];output=Path(output).resolve()
    trials=discover_trials(roots);research=discover_research(roots)
    research_figures=discover_research_figures(roots)
    title=checkpoint_title or "无人机目标跟踪与自主跟随 · 验收总览"
    highlights=[Path(path).resolve() for path in highlight_frames]
    if any(not path.is_file() or path.suffix.lower() not in {".jpg",".jpeg",".png"}
           or not any(path.is_relative_to(root) for root in roots) for path in highlights):
        raise ValueError("Checkpoint highlights must be existing images within the selected results roots")
    parts=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',f'<title>{esc(title)}</title>',
           '<style>body{margin:0;background:#f3f5f8;color:#172339;font:16px/1.6 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1200px;margin:auto;padding:28px}h1{font-size:28px}h2{margin-top:36px}a{color:#135ca9;overflow-wrap:anywhere}article,.panel{background:white;border:1px solid #d9e1eb;border-radius:10px;padding:20px;margin:18px 0}small{display:block;color:#5d6b80;font-size:12px}.muted{color:#5d6b80}.notice{background:#fff3cf;padding:12px;border-radius:6px}.badge{display:inline-block;font-size:13px;border-radius:4px;padding:1px 8px;background:#e9edf4}.PASS{color:#176d34;background:#e3f4e8}.FAIL{color:#a52929;background:#fbe5e5}.INCOMPLETE_EVIDENCE{color:#855c0b;background:#fff1cd}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border-bottom:1px solid #e2e7ef;padding:8px;text-align:left;vertical-align:top}video{width:100%;max-height:560px;background:#111;margin-top:14px}.frames{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.frames img{width:100%;border:1px solid #ddd}details{margin:12px 0}summary{cursor:pointer}select{padding:7px;margin-right:15px}.hidden{display:none}@media(max-width:700px){main{padding:14px}.frames{grid-template-columns:1fr}table{font-size:12px}}</style>',
           f'<main><h1>{esc(title)}</h1><p>生成时间（UTC）：{esc(datetime.now(timezone.utc).isoformat(timespec="seconds"))}</p>',
           '<p class="notice">此页面只索引已有录制证据。单元测试、仿真启动、监控 basic_flight 或单个 PASS 都不等于整阶段完成。工程功能、物理身份和论文研究统计分别列出；失败及未完成记录全部保留。</p>']
    formal_studies=[item for item in research if item["progress"]["kind"]=="full_plan"]
    if checkpoint_title:
        parts.append('<section class="panel" id="formal-checkpoint"><h2>正式计划检查点 · 未完成</h2>')
        if checkpoint_note:
            parts.append('<p class="notice">'+esc(checkpoint_note)+'</p>')
        for study in formal_studies:
            progress=study["progress"];counts=progress["flight_counts"];offline=progress["offline_counts"]
            names={row["name"] for row in progress["flight_rows"]}
            inside=sum(trial["directory"].name in names for trial in trials)
            parts.append(f'<p>正式飞行已终止：{counts["terminal"]} / {progress["expected"]}；'
                         f'PASS {counts["raw"].get("PASS",0)} / FAIL {counts["raw"].get("FAIL",0)} / '
                         f'PENDING {counts["pending"]} / RUNNING {counts["running"]}。</p>'
                         f'<p>离线分析：{offline["terminal"]} / {progress["expected"]}；PENDING {offline["pending"]}。</p>'
                         f'<p>页面录制卡片 {len(trials)}，其中正式计划内 {inside}、计划外 {len(trials)-inside}。'
                         '录制卡片数量与正式计划完成数分别统计，计划外探针不计入166次。</p>')
        if not formal_studies:
            parts.append('<p class="notice">未找到可核对的166次正式计划，当前不能声明正式完成数。</p>')
        parts.append('</section>')
    if highlights:
        parts.append('<section class="panel"><h2>已有机载抽样帧</h2><p class="muted">只链接已有图片，不重新检测或解码视频；抽样帧不能证明全程跟踪或物理身份正确。</p><div class="frames">')
        for path in highlights:
            parts.append(f'<a href="{esc(relative_url(path,output))}"><img loading="lazy" src="{esc(relative_url(path,output))}" alt="{esc(path.parent.name+" / "+path.name)}"><small>{esc(path.parent.name+" / "+path.name)}</small></a>')
        parts.append('</div></section>')
    parts.append('<div class="panel"><h2>工程证据覆盖</h2><table><tr><th>阶段</th><th>已发现录制</th><th>本次工程证据通过</th><th>失败</th><th>证据不足</th></tr>')
    for stage,name in ((1,"状态估计与单目标闭环"),(2,"多同类中的指定个体"),(3,"三轴云台协同")):
        counts=Counter(trial["status"] for trial in trials if trial["stage"]==stage)
        parts.append(f'<tr><td>阶段{stage}：{name}</td><td>{sum(counts.values())}</td><td>{counts["PASS"]}</td><td>{counts["FAIL"]}</td><td>{counts["INCOMPLETE_EVIDENCE"]}</td></tr>')
    parts.append('</table><p class="muted">这是已发现试验数量，不是预定场景矩阵的完成率；未执行的场景不能从本表中消失后被视为通过。</p></div><h2>研究矩阵与统计</h2>')
    if not research:
        parts.append('<p class="notice">未找到可验证的研究矩阵 manifest / 重复统计报告。研究工作保持未完成。</p>')
    for item in research:
        progress=item["progress"];data=item["data"]
        parts.append('<div class="panel"><h3>'+link(item["path"],output,str(item["path"].relative_to(next(root for root in roots if item["path"].is_relative_to(root)))))+'</h3>')
        if progress["kind"] in {"full_plan","extended_engineering"}:
            parts.append(study_progress_html(item,output))
        elif progress["kind"]=="matrix":
            counts=progress["counts"]
            parts.append(f'<p>状态：{esc(progress["state"])}；计划 {progress["expected"]}；planned {counts.get("planned",0)} / started {counts.get("started",0)} / complete {counts.get("complete",0)}；已完成记录中的失败/不完整 {counts.get("failed",0)}。</p>')
            parts.append('<p class="muted">complete 仅表示预定运行记录收齐，失败仍在分母中；不自动证明方法更优或论文统计显著。</p>')
        elif progress["kind"]=="detection":
            parts.append('<p>检测标注状态：'+esc(progress["state"])+f'；采样机会 {progress["sampled"]}；几何候选 {progress["eligible"]}；已视觉复核 {progress["reviewed"]}。</p>')
            parts.append('<p class="notice">proposed 几何投影指标不能当作已验收的正式 mAP；只可引用经过核验的可见子集，并保留排除原因。</p>')
            reviewed=data.get("reviewed_aggregate")
            if isinstance(reviewed,dict):
                parts.append('<p>已复核子集 mAP50:95：'+esc(reviewed.get("map50_95"))+'；仅适用于报告中明确保留的可见静态仿真子集。</p><table><tr><th>类别</th><th>运行阈值</th><th>Precision</th><th>Recall</th><th>漏检 FN</th></tr>')
                for category,metrics in reviewed.get("classes",{}).items():
                    parts.append('<tr>'+''.join('<td>'+esc(value)+'</td>' for value in (category,metrics.get("confidence_threshold"),metrics.get("precision"),metrics.get("recall"),metrics.get("fn")))+'</tr>')
                parts.append('</table><p class="muted">AP 使用置信度扫描；运行阈值处的 Recall 和漏检另列，不能用 AP 掩盖运行漏检。</p>')
        elif progress["kind"]=="metric_reference":
            parts.append('<p>指标公式参考对照：'+esc(progress["state"])+'。这是评价实现的正确性验证，不计入工程飞行或论文重复实验完成数。</p>')
        else:
            parts.append('<p>'+esc(progress["state"])+f'；独立录制条件重复次数：{esc(progress.get("recorded_condition_repeats"))}；离线噪声随机种子：{esc(progress.get("seed_count"))}；指标记录：{esc(progress.get("metric_records"))}。</p>')
        parts.append('<p>'+esc(data.get("scope",data.get("research_claim_boundary",data.get("claim_boundary",data.get("protocol",data.get("plan",{}).get("protocol","范围未记录"))))))+'</p></div>')
    if research_figures:
        parts.append('<h2>可直接查看的研究结果图</h2><p class="muted">图只展示已有报告中的结果；离线回放、独立飞行、条件子集和失败分母仍以源报告为准。</p>')
        for entry in research_figures:
            parts.append('<div class="panel"><p>'+link(entry["path"],output,"绘图来源与输入文件哈希")+'</p><div class="frames">')
            for path in entry["figures"]:
                parts.append(f'<a href="{esc(relative_url(path,output))}"><img loading="lazy" src="{esc(relative_url(path,output))}" alt="{esc(path.name)}"><small>{esc(path.name)}</small></a>')
            parts.append('</div>')
            vectors=[path.with_suffix(".svg") for path in entry["figures"] if path.suffix.lower()!=".svg" and path.with_suffix(".svg").is_file()]
            if vectors:
                parts.append('<p>矢量图：'+' · '.join(link(path,output) for path in vectors)+'</p>')
            if entry["downloads"]:
                parts.append('<p>矢量图、PDF、原始CSV及输入快照：'+' · '.join(link(path,output) for path in entry["downloads"])+'</p>')
            if entry["missing"]:
                parts.append('<p class="notice">未找到或无效的图文件：'+esc(', '.join(entry["missing"]))+'</p>')
            parts.append('<p>'+esc(entry["boundary"])+'</p></div>')
    parts.append('<h2>逐次工程录制</h2><p><label>阶段 <select id="stage-filter"><option value="all">全部</option><option value="1">阶段一</option><option value="2">阶段二</option><option value="3">阶段三</option></select></label><label>状态 <select id="status-filter"><option value="all">全部</option><option value="PASS">通过</option><option value="FAIL">失败</option><option value="INCOMPLETE_EVIDENCE">证据不足</option></select></label></p>')
    if not trials:
        parts.append('<p class="notice">尚无 stage1_/stage2_/stage3_ 实际试验目录；未完成。</p>')
    for index,trial in enumerate(trials):
        parts.append(trial_html(trial,output,index))
    parts.append('<p class="muted">页面为纯静态本地文件；视频不能播放时可打开原始 mp4。复制验收包时须保留 results 内相对目录和原始 JSON / 视频 / bag 数据。生成器未执行新试验，也未修改源记录。</p></main><script>function filterTrials(){const stage=document.getElementById("stage-filter").value,status=document.getElementById("status-filter").value;document.querySelectorAll(".trialcard").forEach(card=>card.classList.toggle("hidden",(stage!=="all"&&card.dataset.stage!==stage)||(status!=="all"&&card.dataset.status!==status)));}document.getElementById("stage-filter").addEventListener("change",filterTrials);document.getElementById("status-filter").addEventListener("change",filterTrials);</script></html>')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text('\n'.join(parts),encoding="utf-8")
    return {"output":str(output),"trials":len(trials),"research_reports":len(research),
            "research_figure_files":sum(len(entry["figures"]) for entry in research_figures),
            "formal_plan_counts":[{"expected":item["progress"]["expected"],"flight":item["progress"]["flight_counts"],
                                   "offline":item["progress"]["offline_counts"],"errors":item["errors"]} for item in formal_studies],
            "highlight_frame_count":len(highlights),
            "engineering_record_statuses":dict(Counter(trial["status"] for trial in trials))}


V4_JSON_LIMIT = 32 * 1024 * 1024
V4_COHORTS = {"core": (120, "FORMAL"), "extension": (160, "EXTENSION_FORMAL")}
V4_TERMINAL = {"PASS", "FAIL", "INCOMPLETE_EVIDENCE", "EVALUATION_PENDING",
               "INFRASTRUCTURE_ERROR", "INTERRUPTED"}
V4_ATTACHMENT_KINDS = {
    "detection": "PROSPECTIVE_ALL_ACTOR_DYNAMIC_DETECTION_REPORT_V1",
    "recovery": "PROSPECTIVE_PHYSICAL_RECOVERY_APPENDIX_V1",
    "timing": "OFFLINE_OBSERVED_PIPELINE_TIMING_NOT_CAUSAL_E2E",
}


def _v4_require(condition, message):
    if not condition:
        raise ValueError(message)


def _v4_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


class _V4Inputs:
    """Only bounded saved files; no evaluator imports or raw-data traversal."""

    def __init__(self):
        self.records = {}
        self.protected = set()
        self.deferred = []

    def protect(self, path):
        self.protected.add(Path(path).resolve())

    def pin(self, value):
        _v4_require(isinstance(value, dict) and isinstance(value.get("path"), str)
                    and bool(value["path"]) and isinstance(value.get("sha256"), str)
                    and re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is not None,
                    "缺少有效 path/SHA-256 绑定")
        if "bytes" in value:
            _v4_require(type(value["bytes"]) is int and value["bytes"] >= 0, "无效文件大小绑定")
        path = Path(value["path"]).resolve()
        self.protect(path.parent)
        return path

    def defer(self, value, role):
        self.pin(value)
        self.deferred.append({"role": role, "binding": value, "validation": "NOT_REREAD"})

    def read(self, path, role, *, binding=None, parse=True):
        path = Path(path).resolve()
        self.protect(path.parent)
        if binding is not None:
            _v4_require(self.pin(binding) == path, "绑定路径不一致：" + str(path))
        _v4_require(path.is_file() and path.stat().st_size <= V4_JSON_LIMIT,
                    "文件缺失或超过32 MiB读取上限：" + str(path))
        with path.open("rb") as stream:
            raw = stream.read(V4_JSON_LIMIT + 1)
        _v4_require(len(raw) <= V4_JSON_LIMIT, "文件读取期间超过大小上限：" + str(path))
        digest = hashlib.sha256(raw).hexdigest()
        if binding is not None:
            _v4_require(digest == binding["sha256"] and
                        ("bytes" not in binding or binding["bytes"] == len(raw)),
                        "绑定文件已改变：" + str(path))
        record = {"path": str(path), "sha256": digest, "bytes": len(raw)}
        previous = self.records.get(str(path))
        _v4_require(previous is None or all(previous[key] == record[key] for key in record),
                    "读取期间来源改变：" + str(path))
        record["roles"] = sorted(set((previous or {}).get("roles", [])) | {role})
        self.records[str(path)] = record
        if not parse:
            return None

        def pairs(items):
            result = {}
            for key, value in items:
                _v4_require(key not in result, "JSON重复键：" + key)
                result[key] = value
            return result

        def invalid(token):
            raise ValueError("JSON非有限数值：" + token)

        def floating(token):
            value = float(token)
            _v4_require(math.isfinite(value), "JSON非有限数值：" + token)
            return value

        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=pairs,
                           parse_constant=invalid, parse_float=floating)
        _v4_require(isinstance(value, dict), "JSON顶层必须是对象：" + str(path))
        return value

    def bound(self, binding, role):
        return self.read(self.pin(binding), role, binding=binding)

    def unchanged(self):
        for item in list(self.records.values()):
            self.read(item["path"], "final_small_file_check", binding=item, parse=False)


def _v4_source(package, requested, role):
    _v4_require(isinstance(requested, str) and bool(requested), "未提供绑定来源：" + role)
    matches = [item for item in package.get("sources", []) if isinstance(item, dict)
               and item.get("role") == role and item.get("path") == requested]
    _v4_require(len(matches) == 1 and matches[0].get("exists") is True,
                "来源索引缺失或重复：" + role)
    return matches[0]


def _v4_package(path, inputs):
    path = Path(path).resolve()
    if path.is_dir():
        path = path / "documents.json"
    package = inputs.read(path, "v4_documents")
    _v4_require(type(package.get("schema_version")) is int and package["schema_version"] == 1
                and package.get("kind") == "RELIABILITY_V4_DOCUMENT_PACKAGE",
                "不支持的v4文档包schema/kind")
    digest = _v4_digest({key: value for key, value in package.items() if key != "document_package_sha256"})
    _v4_require(package.get("document_package_sha256") == digest, "文档包结构摘要不一致")
    index = inputs.read(path.parent / "sources.json", "v4_document_sources")
    _v4_require(type(index.get("schema_version")) is int and index["schema_version"] == 1
                and index.get("kind") == "RELIABILITY_V4_REPORT_SOURCES"
                and index.get("sources") == package.get("sources")
                and index.get("document_package_sha256") == digest
                and index.get("mode") == package.get("mode")
                and index.get("scope") == package.get("scope"), "文档来源索引不一致")
    expected = {"plan.md", "report.md", "plan.html", "report.html", "documents.json"}
    outputs = index.get("outputs")
    _v4_require(isinstance(outputs, list) and len(outputs) == 5
                and all(isinstance(item, dict) for item in outputs)
                and {item.get("path") for item in outputs} == expected, "文档包输出索引不完整")
    for item in outputs:
        binding = {**item, "path": str(path.parent / item["path"])}
        inputs.read(binding["path"], "saved_document_output", binding=binding, parse=False)
    _v4_require(isinstance(package.get("sources"), list) and isinstance(package.get("request"), dict),
                "文档包缺少来源/请求结构")
    return path, package


def _v4_engineering(package, inputs):
    """Count saved statuses on the original plans; never compute a verdict."""
    request = package["request"]
    plans, bindings, expected = {}, {}, {}
    for cohort, (count, mode) in V4_COHORTS.items():
        binding = _v4_source(package, request.get(cohort + "_path"), "engineering_plan")
        plan = inputs.bound(binding, cohort + "_plan")
        _v4_require(type(plan.get("schema_version")) is int and plan["schema_version"] == 1
                    and plan.get("mode") == mode and len(plan.get("trials", [])) == count,
                    "正式分母需要原始core120+extension160；开发包不能代入正式280")
        _v4_require(plan.get("plan_sha256") == _v4_digest({key: value for key, value in plan.items()
                                                         if key != "plan_sha256"}),
                    "计划结构摘要已改变：" + cohort)
        for key in ("frozen_root", "output"):
            if isinstance(plan.get(key), str):
                inputs.protect(plan[key])
        ids = [trial.get("id") for trial in plan["trials"] if isinstance(trial, dict)]
        _v4_require(len(ids) == count and all(isinstance(value, str) and value for value in ids)
                    and len(set(ids)) == count and not (set(ids) & set(expected)), "计划槽ID缺失或重复")
        for trial in plan["trials"]:
            expected[trial["id"]] = (cohort, trial)
            if isinstance(trial.get("directory"), str):
                inputs.protect(trial["directory"])
        plans[cohort], bindings[cohort] = plan, binding
    _v4_require(plans["extension"].get("core_reference_binding", {}).get("plan_sha256")
                == plans["core"]["plan_sha256"], "扩展计划未引用该核心计划")
    summary_binding = _v4_source(package, request.get("summary_path"), "engineering_summary")
    summary = inputs.bound(summary_binding, "v4_engineering_summary")
    _v4_require(type(summary.get("schema_version")) is int and summary["schema_version"] == 1
                and isinstance(summary.get("trials"), list)
                and isinstance(summary.get("cohorts"), dict)
                and package.get("cohorts") == summary["cohorts"], "不支持或不一致的工程summary")
    for cohort, (count, _mode) in V4_COHORTS.items():
        item = summary["cohorts"].get(cohort, {})
        _v4_require(item.get("planned_slots") == count
                    and item.get("plan_sha256") == plans[cohort]["plan_sha256"], "summary计划分母/摘要不一致")
    rows = {}
    for row in summary["trials"]:
        _v4_require(isinstance(row, dict) and isinstance(row.get("slot_id"), str)
                    and row["slot_id"] in expected and row["slot_id"] not in rows, "summary出现额外/重复槽")
        cohort, trial = expected[row["slot_id"]]
        _v4_require(row.get("cohort") == cohort and isinstance(row.get("status"), str)
                    and row["status"] and all(row.get(key) == trial.get(key)
                    for key in ("target_class", "group", "seed")), "summary槽身份/状态不一致")
        rows[row["slot_id"]] = row
    complete_rows = []
    for slot_id, (cohort, trial) in expected.items():
        complete_rows.append(rows.get(slot_id, {"slot_id": slot_id, "cohort": cohort,
            "target_class": trial.get("target_class"), "group": trial.get("group"),
            "seed": trial.get("seed"), "status": "MISSING_SUMMARY_ROW", "metrics": {},
            "report_issues": [{"reason": "绑定summary中缺少原计划槽；不等于通过或零误差"}]}))
    return {"status": "SAVED_FORMAL_ROWS_BOUND_NOT_REEVALUATED", "rows": complete_rows,
            "plans": plans, "plan_bindings": bindings, "summary": summary,
            "slot_counts": dict(Counter(row["status"] for row in complete_rows))}


def _v4_same_plan(binding, engineering, cohort, inputs):
    inputs.pin(binding)
    expected = engineering["plan_bindings"][cohort]
    _v4_require(all(binding.get(key) == expected.get(key) for key in ("path", "sha256")),
                "附件绑定了不同的原始计划：" + cohort)


def _v4_attachment(path, kind, engineering, inputs):
    path = Path(path).resolve()
    result = {"type": kind, "path": str(path), "status": "REJECTED_OR_MISSING", "data": None}
    try:
        data = inputs.read(path, kind + "_saved_report")
        _v4_require(type(data.get("schema_version")) is int and data["schema_version"] == 1
                    and data.get("kind") == V4_ATTACHMENT_KINDS[kind], "不支持的附件schema/kind")
        _v4_require(engineering["status"] == "SAVED_FORMAL_ROWS_BOUND_NOT_REEVALUATED",
                    "没有可绑定的正式120+160计划，附件不能计入本入口")
        if kind == "detection":
            protocol = inputs.bound(data.get("protocol"), "prospective_detection_protocol")
            _v4_require(type(protocol.get("schema_version")) is int and protocol["schema_version"] == 1
                        and protocol.get("kind") == "PROSPECTIVE_ALL_ACTOR_DYNAMIC_CAMERA_DETECTION_V1"
                        and protocol.get("original_planned_slots") == data.get("original_planned_slots") == 280,
                        "检测协议schema/完整280分母不一致")
            for cohort in V4_COHORTS:
                _v4_same_plan(protocol.get("plans", {}).get(cohort), engineering, cohort, inputs)
            original_ids = {row["slot_id"] for row in engineering["rows"]}
            protocol_slots = protocol.get("slots", [])
            _v4_require(isinstance(protocol_slots, list) and all(isinstance(row, dict) for row in protocol_slots),
                        "检测协议槽必须是对象列表")
            protocol_ids = [row.get("slot_id") for row in protocol_slots]
            recordings = data.get("recordings")
            _v4_require(len(protocol_ids) == 280 and set(protocol_ids) == original_ids
                        and isinstance(recordings, list) and all(isinstance(row, dict) for row in recordings),
                        "检测协议/报告槽结构不完整")
            ids = [row.get("slot_id") for row in recordings]
            missing = data.get("missing_original_slot_ids")
            _v4_require(len(set(ids)) == len(ids) and set(ids) <= original_ids
                        and data.get("recording_slots_supplied") == len(ids)
                        and isinstance(missing, list) and len(set(missing)) == len(missing)
                        and set(missing) == original_ids - set(ids)
                        and data.get("all280_recordings_supplied") is (not missing), "检测缺失槽台账不一致")
            review_pin = data.get("review_file")
            if review_pin is not None:
                review = inputs.bound(review_pin, "independent_visible_label_review")
                _v4_require(type(review.get("schema_version")) is int and review["schema_version"] == 1
                            and review.get("kind") == "INDEPENDENT_ALL_ACTOR_VISIBLE_LABEL_REVIEW_V1",
                            "未知独立可见标签复核schema")
            for row in recordings:
                _v4_require(row.get("protocol") == data["protocol"], "逐槽检测协议绑定不一致")
                _v4_require(row.get("reviewed_metrics") is None or isinstance(row["reviewed_metrics"], dict),
                            "检测指标结构无效")
                inputs.defer(row.get("recording"), "detection_recording_not_reread")
                if row.get("prediction_cache") is not None:
                    inputs.defer(row["prediction_cache"], "detection_prediction_cache_not_reread")
                if row.get("reviewed_metrics") is not None:
                    _v4_require(review_pin is not None and row.get("independent_visible_label_review_valid") is True
                                and row.get("publication_status") == "REVIEWED_SUBSET_ONLY",
                                "已复核检测指标缺少独立复核绑定")
            _v4_require(data.get("reviewed_aggregate") is None or (isinstance(data["reviewed_aggregate"], dict)
                and review_pin is not None and any(row.get("reviewed_metrics") is not None for row in recordings)),
                "检测汇总缺少已复核子集")
            if isinstance(data.get("reviewed_aggregate"), dict):
                value = data["reviewed_aggregate"].get("map50_95")
                _v4_require(value is None or (finite(value) and 0 <= value <= 1), "检测mAP不是有效数值/null")
        elif kind == "recovery":
            _v4_require(data.get("scope") == "INDEPENDENT_PHYSICAL_RECOVERY_APPENDIX_NOT_ORIGINAL_VERDICTS"
                        and data.get("evaluation_status") == "DESCRIPTIVE_APPENDIX_WITH_EXPLICIT_UNKNOWN_AND_MISSING_OPPORTUNITIES",
                        "恢复附件范围不符；协议文件不能当作分析报告")
            protocol = inputs.bound(data.get("protocol_binding"), "physical_recovery_protocol")
            _v4_require(type(protocol.get("schema_version")) is int and protocol["schema_version"] == 1
                        and protocol.get("kind") == V4_ATTACHMENT_KINDS[kind]
                        and protocol.get("registered_slots") == 40
                        and protocol.get("registered_opportunities") == 80
                        and protocol.get("original_core_denominator") == 120, "恢复协议分母不完整")
            _v4_same_plan(protocol.get("core_plan"), engineering, "core", inputs)
            protocol_slots = protocol.get("slots", [])
            slots = data.get("slots", [])
            _v4_require(isinstance(protocol_slots, list) and isinstance(slots, list)
                        and all(isinstance(row, dict) for row in [*protocol_slots, *slots]), "恢复槽结构无效")
            registered = {row.get("slot_id") for row in protocol_slots}
            _v4_require(len(protocol_slots) == len(registered) == 40 and len(slots) == 40
                        and {row.get("slot_id") for row in slots} == registered
                        and registered <= {row["slot_id"] for row in engineering["rows"] if row["cohort"] == "core"},
                        "恢复原40槽台账不完整")
            for row in [*protocol_slots, *slots]:
                opportunities = row.get("opportunities", [])
                _v4_require(isinstance(opportunities, list) and len(opportunities) == 2
                            and all(isinstance(entry, dict) for entry in opportunities)
                            and {(entry.get("id"), entry.get("kind")) for entry in opportunities}
                            == {(row["slot_id"] + ":" + name, name) for name in ("short", "long_explicit_reselection")},
                            "恢复原两类机会有遗漏或重标")
            for name, count in (("short", 40), ("long_explicit_reselection", 40), ("all", 80)):
                entry = data.get("summary", {}).get(name, {})
                _v4_require(isinstance(entry, dict) and entry.get("registered_opportunities") == count
                            and isinstance(entry.get("original_confirmation_delay_s"), dict), "恢复机会分母/时延结构不一致")
                supported = entry.get("supported_original_without_observed_different")
                lower_bound = entry.get("descriptive_lower_bound")
                _v4_require(type(supported) is int and 0 <= supported <= count and finite(lower_bound)
                            and math.isclose(lower_bound, supported / count, abs_tol=1e-12), "恢复描述下界与完整机会计数不一致")
        else:
            _v4_require(data.get("scope") == "OBSERVABLE_TIMING_ONLY_NOT_ACCEPTANCE", "时延附件范围不符")
            context = inputs.bound(data.get("inputs", {}).get("context"), "timing_export_context")
            _v4_require(type(context.get("schema_version")) is int and context["schema_version"] == 1
                        and context.get("kind") == "NATIVE_PIPELINE_TIMING_EXPORT_CONTEXT_NOT_ACCEPTANCE"
                        and context.get("events") == data.get("inputs", {}).get("events"), "时延原始context/events绑定不一致")
            matches = [(cohort, trial) for cohort, plan in engineering["plans"].items()
                       for trial in plan["trials"] if context.get("source_root") == plan.get("frozen_root")
                       and isinstance(context.get("source_root"), str)
                       and context.get("trial") == trial.get("directory") and isinstance(context.get("trial"), str)]
            _v4_require(len(matches) == 1, "时延context不是本轮原始120+160计划中的唯一冻结来源/试验")
            result["bound_cohort"], matched_trial = matches[0]
            result["bound_slot_id"] = matched_trial["id"]
            inputs.defer(context.get("events"), "timing_events_not_reread")
            for name in ("source_root", "trial", "source_results_root"):
                if isinstance(context.get(name), str):
                    inputs.protect(context[name])
            for root in context.get("protected_roots", []):
                inputs.protect(root)
            for key in ("actual_worker_processed_wall_fps", "capture_to_controller_causal_source_s",
                        "capture_to_px4_setpoint_causal_source_s", "physical_capture_to_px4_effect_wall_s"):
                _v4_require(isinstance(data.get(key), dict) and data[key].get("status") == "NOT_OBSERVED",
                            "当前时延schema不能声称worker墙时FPS或因果端到端已观察")
            _v4_require(data["actual_worker_processed_wall_fps"].get("hz") is None,
                        "未观察到的墙时FPS不能有数值")
            for key in ("detector_acquisition_to_prepublication_source_s", "detector_processing_prefix_wall_s",
                        "completed_job_yolo_predict_wall_s", "controller_reported_measurement_age_source_s"):
                entry = data.get(key)
                _v4_require(isinstance(entry, dict) and isinstance(entry.get("statistics_s"), dict)
                            and all(type(entry.get(name)) is int and entry[name] >= 0 for name in ("known", "unknown", "total"))
                            and entry["known"] + entry["unknown"] == entry["total"], "时延机会计数/统计结构不一致")
                _v4_require(entry["known"] > 0 or all(value is None for value in entry["statistics_s"].values()),
                            "没有已知时延样本，不能展示非null统计")
        result.update(status="SAVED_REPORT_SMALL_BINDINGS_CHECKED_NOT_REVERIFIED", data=data)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        result["error"] = str(error)
    return result


def _v4_value(value):
    return "未知 / 缺失（null）" if value is None else esc(value)


def _v4_table(headers, rows):
    return "<table><tr>" + "".join("<th>" + esc(value) + "</th>" for value in headers) + "</tr>" + "".join(
        "<tr>" + "".join("<td>" + _v4_value(value) + "</td>" for value in row) + "</tr>" for row in rows) + "</table>"


def _v4_attachment_html(item, output):
    names = {"detection": "动态相机全物体检测附件", "recovery": "独立物理恢复描述附件", "timing": "可观测时序附件"}
    body = ['<section class="panel"><h2>' + names[item["type"]] + '</h2><p>' + esc(item["status"]) + '</p>']
    if item["data"] is None:
        return "".join(body + ['<p class="notice">缺失或拒绝：' + esc(item.get("error", "未提供")) + '</p></section>'])
    data = item["data"]
    body.append('<p>' + link(Path(item["path"]), output, "打开保存的原报告") + '</p><p class="notice">仅核对报告、协议及明确的小文件绑定；未重读全部原始数据，未重算指标，也未在本入口执行独立语义复验。</p>')
    if item["type"] == "detection":
        body.append(_v4_table(["原计划槽", "已提供录制槽", "缺失录制槽", "保存的采样机会数"],
            [[280, data.get("recording_slots_supplied"), len(data["missing_original_slot_ids"]), data.get("scheduled_opportunities")]]))
        counts = Counter(row.get("publication_status", "UNKNOWN") for row in data["recordings"])
        body.append(_v4_table(["保存的检测发布状态", "槽数"], sorted(counts.items())))
        aggregate = data.get("reviewed_aggregate")
        body.append('<p>保存报告中的独立批准可见子集 mAP50:95：' + _v4_value(aggregate.get("map50_95") if isinstance(aggregate, dict) else None)
                    + '。仅适用于已批准的可见仿真子集；缺图、遮挡及未复核机会仍保留，不能解释为全飞行准确率、在线FPS或原280槽全部验收通过。</p>')
    elif item["type"] == "recovery":
        body.append('<p class="notice">此工具没有 verify-report。这里只展示已保存的描述附件，不能声称已独立复验；显式重选是用户/脚本辅助，不是自动ReID。</p>')
        body.append(_v4_table(["机会类型", "完整分母", "支持原个体且未见不同个体", "描述下界", "右删失", "缺失/无效事件", "确认时延均值/s"], [
            [name, entry.get("registered_opportunities"), entry.get("supported_original_without_observed_different"),
             entry.get("descriptive_lower_bound"), entry.get("right_censored"), entry.get("missing_or_invalid_events"),
             entry.get("original_confirmation_delay_s", {}).get("mean")]
            for name, entry in data["summary"].items() if name in {"short", "long_explicit_reselection", "all"}]))
        body.append('<p>未知与未恢复机会保留在80机会分母中；未观察到确认的时延保持null。原个体恢复与重选后是否跟对新请求对象分开解释。</p>')
    else:
        body.append('<p>精确绑定原计划槽：' + esc(item["bound_cohort"] + " / " + item["bound_slot_id"]) + '</p>')
        body.append('<p class="notice">实际worker墙时FPS、图像到控制器/设定值的因果端到端时延、物理采集到PX4生效时延：NOT_OBSERVED（未观察）。不得跨时钟相减或按RTF换算。</p>')
        names = [("detector_acquisition_to_prepublication_source_s", "采集到发布前/source clock"),
                 ("detector_processing_prefix_wall_s", "检测处理及发布前缀/wall clock"),
                 ("completed_job_yolo_predict_wall_s", "已完成job的YOLO predict/wall clock"),
                 ("controller_reported_measurement_age_source_s", "控制器报告的测量年龄/source clock")]
        body.append(_v4_table(["保存的可观测量", "已知", "未知", "机会总数", "均值/s", "p95/s"], [
            [label, data.get(key, {}).get("known"), data.get(key, {}).get("unknown"),
             data.get(key, {}).get("total"), data.get(key, {}).get("statistics_s", {}).get("mean"),
             data.get(key, {}).get("statistics_s", {}).get("p95")] for key, label in names]))
        body.append('<p>source clock数值不能自动视为墙时；事件和job原日志未在此重读，尾部完整性未在此认证。</p>')
    return "".join(body + ['</section>'])


def build_v4_dashboard(package_path, output, *, prospective_detection=(), physical_recovery=(), timing=()):
    """Independent saved-v4 presentation; not the reporter's verify_package."""
    inputs = _V4Inputs()
    package_path, package = _v4_package(package_path, inputs)
    try:
        engineering = _v4_engineering(package, inputs)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        engineering = {"status": "MISSING_OR_REJECTED_FORMAL_ENGINEERING", "error": str(error),
                       "rows": [], "slot_counts": {"MISSING_FORMAL_EVIDENCE": 280}}
    attachments = []
    for kind, paths in (("detection", prospective_detection), ("recovery", physical_recovery), ("timing", timing)):
        attachments.extend(_v4_attachment(path, kind, engineering, inputs) for path in paths)
        if not paths:
            attachments.append({"type": kind, "status": "MISSING_NOT_PROVIDED", "data": None})
    requested_output = Path(output).absolute()
    for path in (requested_output, requested_output.with_suffix(".sources.json")):
        _v4_require(not path.exists() and not path.is_symlink(), "v4入口必须写入新的独立文件：" + str(path))
    output = requested_output.resolve()
    source_index = output.with_suffix(".sources.json")
    for path in (output, source_index):
        _v4_require(not path.exists() and not path.is_symlink(), "v4入口必须写入新的独立文件：" + str(path))
        _v4_require(not any(path.is_relative_to(root) for root in inputs.protected),
                    "禁止在输入/原始试验/冻结目录内输出：" + str(path))
    title = "v4独立交付入口 · 原计划280槽证据"
    body = ['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
            '<title>' + title + '</title><style>body{background:#f3f5f8;color:#172339;font:15px/1.65 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1280px;margin:auto;padding:24px}.panel{background:white;border:1px solid #d9e1eb;border-radius:10px;padding:18px;margin:18px 0}.notice{background:#fff3cf;padding:12px}table{border-collapse:collapse;width:100%;font-size:13px}td,th{border-bottom:1px solid #d9e1eb;padding:7px;text-align:left;overflow-wrap:anywhere}a{color:#135ca9;overflow-wrap:anywhere}.scroll{overflow-x:auto}details{margin:10px 0}</style><main>',
            '<h1>' + title + '</h1><p class="notice">这是保存证据的独立展示，不重新执行原reporter的verify_package/final_gate，不读取bag、模型或Gazebo，不借用历史166槽判定。终态登记、工程通过、身份已知覆盖与论文结论各有边界，页面不能授予项目整体验收。</p>',
            '<section class="panel"><h2>文档包与来源</h2><p>包模式：' + esc(package.get("mode")) + '；保存范围：' + esc(package.get("scope")) + '</p><p>已核对文档结构摘要及5个保存输出文件绑定；未按原请求重建原始验收。DOCX/PDF原生分页与逐页视觉验收不由本入口证明。</p><p>'
            + ' · '.join(link(package_path.parent / name, output, label) for name, label in
                         (("plan.html", "计划书HTML"), ("report.html", "研究报告HTML"), ("documents.json", "文档结构"), ("sources.json", "原包来源"))) + '</p></section>',
            '<section class="panel"><h2>工程执行覆盖</h2><p>原计划分母：280（core 120＋extension 160）。状态：' + esc(engineering["status"]) + '</p>']
    if engineering.get("error"):
        body.append('<p class="notice">正式证据不可用：' + esc(engineering["error"]) + '。280槽保留为缺失；开发试验不填入正式分母。</p>')
    body.append(_v4_table(["保存的原状态 / 明确缺失", "槽数（总分母280）"], sorted(engineering["slot_counts"].items())))
    body.append('<p>FAIL、证据不足、基础设施停止、中断、未知状态、未完成与缺失全部保留；不把有限误差或终态登记重新判成PASS。</p></section>')
    body.extend(_v4_attachment_html(item, output) for item in attachments)
    body.append('<section class="panel"><h2>原计划逐槽记录</h2><p>以下数值来自绑定summary，未重算；null不是0。身份已知覆盖与保持下界使用原完整任务时间格，不以已检测到的帧替换分母。</p><div class="scroll">')
    headers = ["队列 / 槽ID", "类别 / 组 / seed", "原状态", "距离RMSE/m", "高度RMSE/m", "完整任务身份已知覆盖", "完整任务保持下界", "错误样本", "未知样本", "报告问题"]
    rows = []
    for row in engineering["rows"]:
        metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
        rows.append([row["cohort"] + " / " + row["slot_id"], "/".join(str(row.get(key)) for key in ("target_class", "group", "seed")),
                     row["status"], *[metrics.get(key) for key in ("base_link_distance_rmse_m", "base_link_height_rmse_m",
                     "physical_task_time_known_coverage", "physical_task_time_retention_lower_bound",
                     "physical_task_time_wrong_samples", "physical_task_time_unknown_samples")],
                     json.dumps(row.get("report_issues", []), ensure_ascii=False)])
    body.append(_v4_table(headers, rows))
    body.append('</div></section><p>' + link(source_index, output, "本入口小文件核对记录与未重读绑定索引")
                + '</p><p>本页不运行模拟、不做标注、不重算统计。附件只补充展示，不改变原计划槽裁决；失败不能被删除或以新批次替换。</p></main></html>')
    inputs.unchanged()
    index = {"schema_version": 1, "kind": "RELIABILITY_V4_SAVED_DELIVERY_DASHBOARD",
             "generated_utc": datetime.now(timezone.utc).isoformat(), "original_planned_slots": 280,
             "validation": "SMALL_SAVED_FILES_CHECKED_NOT_ORIGINAL_EVALUATOR_RECONSTRUCTION",
             "project_acceptance_claimed": False, "engineering_status": engineering["status"],
             "slot_counts": engineering["slot_counts"], "displayed_slot_rows": len(engineering["rows"]),
             "attachments": [{key: value for key, value in item.items() if key != "data"} for item in attachments],
             "checked_small_files": list(inputs.records.values()), "deferred_bindings_not_reread": inputs.deferred,
             "original_evaluator_rerun": False, "ros_bag_reads": 0, "model_inference": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    with source_index.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(index, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(body))
    return {"output": str(output), "source_index": str(source_index), "original_planned_slots": 280,
            "engineering_status": engineering["status"], "slot_counts": engineering["slot_counts"],
            "attachment_statuses": [item["status"] for item in attachments], "project_acceptance_claimed": False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir",type=Path,default=ROOT/"results")
    parser.add_argument("--additional-results-dir",type=Path,action="append",default=[])
    parser.add_argument("--output",type=Path)
    parser.add_argument("--checkpoint-title")
    parser.add_argument("--checkpoint-note")
    parser.add_argument("--highlight-frame",type=Path,action="append",default=[])
    parser.add_argument("--v4-package", type=Path, help="显式v4 documents.json或包目录；独立于历史166槽入口")
    parser.add_argument("--v4-prospective-detection", type=Path, action="append", default=[])
    parser.add_argument("--v4-physical-recovery", type=Path, action="append", default=[])
    parser.add_argument("--v4-timing", type=Path, action="append", default=[])
    args=parser.parse_args()
    if args.v4_package is not None:
        if (args.output is None or args.results_dir != ROOT/"results" or args.additional_results_dir
                or args.checkpoint_title or args.checkpoint_note or args.highlight_frame):
            parser.error("v4分支需要显式--output，不能混用历史发现/检查点选项")
        result = build_v4_dashboard(args.v4_package, args.output,
                    prospective_detection=args.v4_prospective_detection,
                    physical_recovery=args.v4_physical_recovery, timing=args.v4_timing)
    else:
        if args.v4_prospective_detection or args.v4_physical_recovery or args.v4_timing:
            parser.error("v4附件需要--v4-package；不能交给历史166槽分支")
        result=build_dashboard([args.results_dir,*args.additional_results_dir],args.output or args.results_dir/"验收总览.html",
                               checkpoint_title=args.checkpoint_title,checkpoint_note=args.checkpoint_note,highlight_frames=args.highlight_frame)
    print(json.dumps(result,ensure_ascii=False))


if __name__=="__main__":
    main()
