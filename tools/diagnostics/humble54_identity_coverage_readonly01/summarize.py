"""Copy existing small closed-trial identity evidence; never rescore or relabel."""
from collections import Counter
from datetime import datetime, timezone
import ast
import hashlib
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[3]
ROOT = PROJECT / "results/frozen_fullplan_v4_humble54"
OUT = PROJECT / "results/diagnostics/humble54_identity_coverage_readonly01"
LIMIT = 2 * 1024 * 1024
INPUTS = []


def read(path, expected=None, parse=True):
    path = Path(path)
    before = path.stat()
    if before.st_size > LIMIT:
        raise ValueError("refusing metadata over 2 MiB: " + str(path))
    with path.open("rb") as stream:
        raw = stream.read(LIMIT + 1)
    after = path.stat()
    if len(raw) > LIMIT or (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError("metadata changed during read")
    digest = hashlib.sha256(raw).hexdigest()
    if expected is not None and digest != expected:
        raise ValueError("original small binding differs: " + str(path))
    INPUTS.append({"path": path.relative_to(PROJECT).as_posix(), "bytes": len(raw), "sha256": digest,
                   "matches_original_binding": True if expected else None})
    return json.loads(raw) if parse else raw


def local(path):
    marker = "/results/frozen_fullplan_v4_humble54/"
    if marker not in path:
        raise ValueError("source path outside known result root")
    result = (ROOT / path.split(marker, 1)[1]).resolve()
    if not result.is_relative_to(ROOT.resolve()):
        raise ValueError("source path leaves result root")
    return result


def pick(value, keys):
    return {key: value[key] for key in keys}


def main():
    manifest_path = ROOT / "full28_storage_measurement_probe02_after07_01/summary.json"
    manifest = read(manifest_path, "cac0d6bf42920dce4e59b9bb490e3bacc96cd8aaf57d4b50fc5b9b27dc459403")
    cells, multi = [], []
    for binding in manifest["receipts"]:
        accounting = read(local(binding["path"]), binding["sha256"])
        terminal_binding = accounting["original_terminal"]
        terminal = read(local(terminal_binding["path"]), terminal_binding["sha256"])
        if terminal["status"] != accounting["original_status"]:
            raise ValueError("original status disagreement")
        evidence = terminal.get("engineering_evidence", {})
        physical = evidence.get("physical_identity")
        cells.append({"id": terminal["id"], "original_status": terminal["status"], "cell": accounting["cell"],
                      "terminal": terminal_binding, "has_saved_physical_identity_summary": physical is not None})
        if physical is None:
            continue
        report_binding = accounting["original_report_bindings"]["physical_identity"]
        report_path = local(report_binding["path"])
        reports = accounting["original_report_bindings"]
        run_config = read(local(reports["run_config.json"]["path"]), reports["run_config.json"]["sha256"])
        parameters = reports["configuration/runtime_parameters.yaml"]
        read(local(parameters["path"]), parameters["sha256"], parse=False)
        arguments = terminal["runtime_configuration"]["arguments"]
        original_eval = next(row for row in terminal["evaluations"] if row["kind"] == "physical_identity")
        row = {"id": terminal["id"], "original_status": terminal["status"], "terminal": terminal_binding,
               "evaluation_status": original_eval["result"], "time_grid": physical,
               "diagnostic_frame_identity": evidence["diagnostic_frame_identity"],
               "saved_parameters": {"run_config": reports["run_config.json"], "runtime_parameters": parameters,
                                     "arguments": pick(arguments, ("target_class", "stage", "seed", "gimbal_mode", "target_mode",
                                         "association_mode", "initial_select", "initial_min_candidates", "scenario_kind", "condition",
                                         "estimator_method", "duration", "max_inference_rate_hz", "occlusions", "reselect_after_loss"))},
               "physical_report": {**report_binding, "bytes_from_stat": report_path.stat().st_size,
                                   "content_read_in_this_diagnostic": report_path.stat().st_size <= LIMIT},
               "time_grid_unknown_reason_counts": None, "diagnostic_frame_unknown_reason_counts": None,
               "state_phase_stratification": "NOT_AVAILABLE_IN_ORIGINAL_SMALL_SUMMARIES"}
        if physical["correct"] + physical["wrong"] + physical["unknown"] != physical["scheduled_samples"]:
            raise ValueError("saved time-grid count inconsistency")
        if report_path.stat().st_size <= LIMIT:
            report = read(report_path, report_binding["sha256"])
            saved_grid = report["conservative_task_time_identity"]
            for key, value in physical.items():
                if saved_grid[key] != value:
                    raise ValueError("small terminal/report identity aggregate differs")
            row["time_grid_unknown_reason_counts"] = saved_grid["unknown_reason_counts"]
            row["time_grid_semantics"] = saved_grid["semantics"]
            row["diagnostic_frame_unknown_reason_counts"] = dict(Counter(
                item["reason"] for item in report["conservative_selected_identity"]["outcomes"] if item["outcome"] == "unknown"))
            row["diagnostic_frame_outcome_counts"] = report["selected_physical_identity_all"]["counts"]
            row["camera_geometry_status_counts"] = report["camera_geometry_status_counts"]
        else:
            # Only the tiny original evaluator stdout is read for car category
            # counts; the >2 MiB physical-identity documents are not hashed/read.
            log_path = local(terminal_binding["path"]).parent.parent / "logs" / (terminal["id"] + ".physical_identity.log")
            text = read(log_path, parse=False).decode("utf-8")
            line = next(line for line in text.splitlines() if line.startswith("Physical identity: "))
            recorded = ast.literal_eval(line.split("; ", 1)[1])
            frame = row["diagnostic_frame_identity"]
            if recorded["frames"] != frame["frames"] or recorded["counts"]["CORRECT"] != frame["correct"]:
                raise ValueError("small evaluator stdout/terminal aggregate differs")
            row["diagnostic_frame_outcome_counts"] = recorded["counts"]
            row["diagnostic_frame_category_source"] = log_path.relative_to(PROJECT).as_posix()
            row["time_grid_reason_limitation"] = "Not present in bound small terminal; >2 MiB physical report intentionally not read. Existing report can answer later without a new experiment."
        multi.append(row)
    if len(cells) != 28 or len(multi) != 4:
        raise ValueError("unexpected closed development scope")
    totals = {key: sum(row["time_grid"][key] for row in multi) for key in ("scheduled_samples", "correct", "wrong", "unknown")}
    result = {"created_utc": datetime.now(timezone.utc).isoformat(), "scope": "READ_ONLY_COPY_AND_AGGREGATION_OF_EXISTING_CLOSED_DEVELOPMENT_IDENTITY_EVIDENCE_NOT_RESCORING",
              "development_status_counts": dict(Counter(row["original_status"] for row in cells)),
              "closed_development_cells": 28, "cells_with_saved_designated_identity_summary": 4,
              "cells_without_saved_designated_identity_summary": 24,
              "missing_designated_identity_summary_is_not_24_identity_failures": True,
              "multi_target_slots": multi, "descriptive_pooled_time_grid_counts": totals,
              "pooled_counts_are_not_independent_trials_or_formal_success_rate": True,
              "time_grid_basis": "Fixed 0.1 s cells from first explicit REQUEST to last recorded /clock, final partial cell retained. No FOLLOW-only selection. Pre-confirmation, CLEAR/RESET, task boundaries and missing independent evidence remain UNKNOWN.",
              "takeoff_and_phase_boundary": "Recording before first REQUEST is outside this specific denominator. Any takeoff/non-FOLLOW/loss/hover/reselection time after REQUEST stays inside. Original small summaries do not split grid outcomes by flight phase; no phase counts are inferred.",
              "zero_known_wrong_boundary": "Zero observed wrong labels does not prove zero true identity switches or no wrong target during UNKNOWN cells. Stable UUID and engineering PASS do not certify physical identity.",
              "existing_data_can_answer_without_new_experiment": [
                  "Car exact per-time-cell unknown reasons may be extracted from the existing larger physical_identity reports in a separately bounded read; not needed to rerun simulations.",
                  "Visible-label review may annotate existing images/video when independent visibility evidence exists; absence of evidence cannot be filled by UUID/nearest actor/highest IoU.",
                  "Any new secondary analysis must preserve original FAIL/UNKNOWN and create a separately named report with its own protocol."],
              "requires_new_formal_batch": [
                  "Generalized designated-identity coverage, wrong-target risk and comparison between midpoint/active gimbal across repeated independent seeds and failure cases.",
                  "Estimator baseline/adaptive-KF causal performance claims under paired identical scenes, seeds and control parameters.",
                  "Evidence removed or never recorded: only additional independent recording/labels can close it; a new experiment cannot retroactively prove old UNKNOWN cells.",
                  "Confidence intervals and formal admission across the planned 280 slots; these four seed004 development runs do not supply that evidence."],
              "does_not_conflate_with_dds_latency_unknown": True, "formal_progress": "0/280_UNCHANGED", "native_started": False,
              "bag_model_large_trace_reads": False, "large_physical_report_content_reads": False,
              "source_binding": {"path": Path(__file__).relative_to(PROJECT).as_posix(), "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
              "small_inputs": INPUTS}
    OUT.mkdir(parents=True, exist_ok=False)
    path = OUT / "identity_coverage.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    table = ["| 开发槽 | 正确 | 已知错 | 未知 | 0.1秒时间格总数 | 已知覆盖 |", "|---|---:|---:|---:|---:|---:|"]
    for row in sorted(multi, key=lambda item: item["id"]):
        value = row["time_grid"]
        table.append(f"| {row['id']} | {value['correct']} | {value['wrong']} | {value['unknown']} | {value['scheduled_samples']} | {value['known_coverage']:.2%} |")
    markdown = """# 已闭合开发槽的物理身份覆盖核查

仅复制原结果并汇总，不重新评分，不改变原 FAIL/UNKNOWN。28槽仍为23 PASS、4 FAIL、1 INCOMPLETE_EVIDENCE；其中4个指定个体多目标槽有物理身份评价，另24槽没有这项指定身份摘要，不能据此当成24次身份失败。

""" + "\n".join(table) + """

四槽仅作描述性合并：3014格中2551正确、0已知错、463未知。全部为seed004开发数据，不能作为正式成功率、独立重复次数或算法统计结论。原工程PASS与身份覆盖是不同指标；未知区间可能仍发生跟错，0已知错不能推出0真实ID switch。

分母是首个显式REQUEST至末个记录/clock的固定10Hz时间格，含不足0.1秒的尾格；REQUEST前的起飞时段不在这一分母。REQUEST后尚未确认、CLEAR/RESET后、任务切换、长时丢失/悬停和无独立新证据的格均保留，不按FOLLOW剔除。原摘要没有按飞行状态分层，不能拆出各状态的未知数。四槽原始终态、run_config和runtime_parameters哈希都列入JSON。

行人stage2的104个未知时间格：101格原身份证据未知，另未确认、任务边界、无证据各1格。行人stage3的106格：103格原身份证据未知，另三类各1格。这是时间格原因，不能和逐检测帧计数相加。

逐检测帧的具体原因：行人stage2为71帧无新鲜选中目标检测、30帧已知或未能排除外部遮挡；行人stage3为71帧无新鲜检测、31帧外部遮挡、1帧多个物理个体均可匹配。汽车原小stdout分别保留NOT_OBSERVED 73/70帧、UNKNOWN_GEOMETRY 26/25帧；其114/139个时间格的进一步原因不在小终态中。两份汽车物理身份报告为3,066,769/7,660,044字节，本次只取stat与原声明SHA，未读内容；以后可从原报告取细分，无需为了这一项重飞。

固定时间格与原诊断帧是两个分母。身份覆盖也不同于相机TF覆盖：例如行人主动云台的相机几何922/922 KNOWN，仍有106/754身份时间格UNKNOWN。物理身份UNKNOWN与DDS软件时延UNKNOWN是两套证据，不能互相补齐。

现有图像/录像可供独立可见性复核；缺少可见证据不能凭稳定UUID、最近真值或最大IoU补标签。正式结论仍需要新冻结批次、独立随机种子、保留失败，并在相同条件下比较控制、云台和滤波方案。新实验也不能反向证明旧UNKNOWN。详细路径、哈希、原协议和未解问题见 [identity_coverage.json](identity_coverage.json)。
"""
    (OUT / "README.md").write_text(markdown, encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                      "multi_slots": len(multi), "totals": totals, "small_inputs": len(INPUTS)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
