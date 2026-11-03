"""Explicit exception for exactly two pinned car identity JSONs, <=8 MiB each."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[3]
ROOT = PROJECT / "results/frozen_fullplan_v4_humble54"
OUT = PROJECT / "results/diagnostics/humble54_identity_coverage_readonly01"
OLD_SHA = "efe1443ee7bd3501d57631c50beb215f1ca5a5d2dd614b690a3239b11818ce4d"
ALLOWED = {
    "car_stage2_crossing_seed004": (3066769, "0c2d32eec9e5017852e8f079fa01914cfbb2e8a812b3fe3d2c6fa2e04d671d28"),
    "car_stage3_multi_active_seed004": (7660044, "58aab55dea538bf9120bddc6015e16ca237f3a241929877fc547900179692521"),
}
BINDINGS = []


def read_bound(path, digest, size=None, *, large=False):
    path = Path(path)
    maximum = 8 * 1024 * 1024 if large else 2 * 1024 * 1024
    before = path.stat()
    expected = before.st_size if size is None else size
    if before.st_size != expected or expected > maximum:
        raise ValueError("exact size or hard bound differs")
    pieces, hasher, total = [], hashlib.sha256(), 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(min(1024 * 1024, expected - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > expected or total > maximum:
                raise ValueError("input grew during bounded read")
            hasher.update(chunk)
            pieces.append(chunk)
    after = path.stat()
    fields = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    if fields(before) != fields(after) or total != expected or hasher.hexdigest() != digest:
        raise ValueError("before/after stat, original bytes or SHA binding differs")
    BINDINGS.append({"path": path.relative_to(PROJECT).as_posix(), "bytes": total, "sha256": digest,
                     "hard_limit_bytes": maximum, "before_after_stat_unchanged": True,
                     "explicit_large_file_exception": large})
    return json.loads(b"".join(pieces))


def local(value):
    marker = "/results/frozen_fullplan_v4_humble54/"
    if marker not in value:
        raise ValueError("unexpected original result path")
    result = (ROOT / value.split(marker, 1)[1]).resolve()
    if not result.is_relative_to(ROOT.resolve()):
        raise ValueError("original result path leaves root")
    return result


def main():
    old_path = OUT / "identity_coverage.json"
    old = read_bound(old_path, OLD_SHA)
    original_small = {row["path"]: row for row in old["small_inputs"]}
    cases = []
    for case, (size, digest) in ALLOWED.items():
        prefix = "reliability_v4_humble54_core12_probe01_" + case
        accounting_path = ROOT / "full28_storage_measurement_probe02_after07_01" / (prefix + ".json")
        accounting_pin = original_small[accounting_path.relative_to(PROJECT).as_posix()]
        accounting = read_bound(accounting_path, accounting_pin["sha256"], accounting_pin["bytes"])
        original_terminal = accounting["original_terminal"]
        terminal = read_bound(local(original_terminal["path"]), original_terminal["sha256"])
        report_pin = accounting["original_report_bindings"]["physical_identity"]
        expected_path = (ROOT / prefix / "physical_identity.json").resolve()
        if (local(report_pin["path"]) != expected_path or report_pin["sha256"] != digest
                or accounting["files"]["physical_identity.json"] != size
                or terminal["artifact_hashes"]["physical_identity.json"] != digest):
            raise ValueError("explicit car exception differs from original accounting/terminal")
        report = read_bound(expected_path, digest, size, large=True)
        grid = report["conservative_task_time_identity"]
        frame = report["conservative_selected_identity"]
        if any(grid[key] != value for key, value in terminal["engineering_evidence"]["physical_identity"].items()):
            raise ValueError("original grid terminal/report disagreement")
        if sum(grid["unknown_reason_counts"].values()) != grid["unknown"]:
            raise ValueError("original grid reason counts inconsistent")
        unknown_frames = Counter(item["reason"] for item in frame["outcomes"] if item["outcome"] == "unknown")
        if sum(unknown_frames.values()) != frame["unknown"]:
            raise ValueError("original frame reason counts inconsistent")
        copied_grid = {key: value for key, value in grid.items() if key not in ("timeline", "tasks")}
        copied_frame = {key: value for key, value in frame.items() if key != "outcomes"}
        tasks = {task_id: {key: value for key, value in task.items() if key != "initial_geometric_match"}
                 for task_id, task in grid["tasks"].items()}
        cases.append({"id": case, "original_engineering_status": terminal["status"],
                      "physical_report": report_pin, "terminal": original_terminal,
                      "time_grid": copied_grid, "time_grid_tasks": tasks,
                      "diagnostic_frame_identity": copied_frame,
                      "diagnostic_frame_unknown_reason_counts": dict(unknown_frames),
                      "diagnostic_frame_counts": report["selected_physical_identity_all"]["counts"],
                      "camera_geometry_status_counts": report["camera_geometry_status_counts"],
                      "label_protocol": report["label_protocol"], "freshness_protocol": report["freshness_protocol"],
                      "selected_identity_protocol": report["selected_identity_protocol"],
                      "metric_reference": report["metric_reference"],
                      "observed_id_switch_boundary": "The copied observed_physical_identity_switches_within_task=0 is conditional on known recorded matches inside each explicit task. UNKNOWN gaps are not certified, and explicit new tasks partition the metric; true switches during UNKNOWN remain unidentifiable from these labels."})
    if hashlib.sha256(old_path.read_bytes()).hexdigest() != OLD_SHA:
        raise ValueError("old read-only report changed")
    result = {"created_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "PINNED_TWO_CAR_REPORT_READ_ONLY_REASON_EXTRACTION_NOT_RESCORING",
              "prior_report": {"path": old_path.relative_to(PROJECT).as_posix(), "sha256": OLD_SHA, "unchanged": True},
              "exception": "Exactly the two listed car physical_identity JSONs, each <=8MiB; all other reads <=2MiB. No bag/model/trace/native/WSL access.",
              "cases": cases,
              "time_grid_difference_active_minus_stage2": {"unknown_total": 25,
                  "request_not_yet_confirmed": 0, "no_identity_evidence_in_time_cell": 28,
                  "unknown_identity_evidence_in_time_cell": -4, "task_boundary_within_time_cell": 1,
                  "interpretation": "Description of these two different development scenes only; not a paired causal gimbal effect or a statistical estimate."},
              "denominator_boundary": "Frame rows are diagnostic-image opportunities inside explicit tasks. Fixed 0.1s cells span first REQUEST to last recorded /clock, including request-confirmation waits, loss/hover and gaps; final partial cell retained. No interpolation, forward-fill, FOLLOW-only filtering or zero substitution. Counts from the two populations cannot be added.",
              "phase_stratification": "Original reasons do not distinguish TAKEOFF/FOLLOW/HOVER within these unknown classes; no flight-phase counts inferred.",
              "labels_and_truth": "Original labels are independent offline static render-mesh projections from exact-source actor/camera GT and guarded geometry. Known gimbal camera geometry does not certify physical identity visibility. This read did not inspect images or perform the independent visible-label review required by the original label protocol.",
              "new_data_boundary": "This supplement resolves the already-recorded car reason breakdown without a new flight. Old UNKNOWN remains UNKNOWN; formal repeated-seed reliability and paired estimator/gimbal claims still need the planned new batch.",
              "dds_latency_unknown_is_separate": True, "formal_progress": "0/280_UNCHANGED",
              "native_started": False, "original_verdicts_modified": False,
              "source": {"path": Path(__file__).relative_to(PROJECT).as_posix(), "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
              "input_bindings": BINDINGS}
    destination = OUT / "car_detailed_review01.json"
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    markdown = """# 汽车身份未知原因补充核查

旧 identity_coverage.json 保持原SHA不变。本次仅增加两份精确授权的汽车物理身份报告读取例外：3,066,769 / 7,660,044字节，单文件8MiB硬限，实际SHA和读前后stat均与原终态/accounting绑定匹配；未读取其他大文件、bag、模型或trace，未启动WSL/仿真。

| 原因（固定0.1秒任务时间格） | 汽车stage2 | 汽车stage3主动云台多目标 |
|---|---:|---:|
| REQUEST尚未确认 | 2 | 2 |
| 格内没有独立身份证据 | 13 | 41 |
| 格内已有身份证据为未知 | 99 | 95 |
| 格内发生任务边界 | 0 | 1 |
| 未知总数 / 全部时间格 | 114 / 754 | 139 / 753 |

两份报告分别保留640/614个正确格、0个已知错格，覆盖84.88%/81.54%。时间格从首次REQUEST延续到最后记录/clock，包括等待确认、丢失悬停和缺证据时段；不按FOLLOW剔除，不前向填充。原原因没有进一步按飞行状态划分，不能推算每种状态的未知数量。

逐诊断帧是另一分母：stage2为743帧，644正确、99未知；stage3为714帧，619正确、95未知。未知分别为73/70帧没有新鲜的选中检测、26/25帧已知或不能排除外部遮挡。两场景未知时间格相差25，原理由差额为无证据格+28、未知证据格−4、任务边界格+1；这一描述性差异不能证明云台的因果效果。主动云台相机几何896/896 KNOWN，也不能替代物理身份可见性证明。

原报告中的“任务内观测到的物理身份切换0次”仅覆盖已有已知证据；UNKNOWN内是否发生真实换人仍不能判定。显式重新选框会划分新任务，任务UUID不提供物理身份标签。

标签来自原离线静态渲染网格投影、图像源时刻的独立actor/camera真值及遮挡保护规则；本次没有检查图像，也没有完成原协议要求的独立可见标签复核。没有重评分、补标签或改变原工程PASS/UNKNOWN。详细协议与原件绑定见 [car_detailed_review01.json](car_detailed_review01.json)。正式重复实验和算法/云台比较仍需新批次；本次原因细分无需重飞，且不能反向证明旧未知区间。
"""
    with (OUT / "car_detailed_review01.md").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(markdown)
    print(json.dumps({"path": str(destination), "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                      "old_report_sha256": hashlib.sha256(old_path.read_bytes()).hexdigest(), "cases": len(cases)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
