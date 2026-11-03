#!/usr/bin/env python3
"""Build a bounded, read-only view of the original Humble54 development records."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from html import escape
import hashlib
import json
import math
import os
from pathlib import Path
import re
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "results/diagnostics/humble54_development_view01"
PUBLISHED = ROOT / "results/frozen_fullplan_v4_humble54"
MAX_JSON_BYTES = 2 * 1024 * 1024
PLANS = (
    (
        "核心开发场景（12 槽）",
        "reliability_v4_humble54_core12_probe01_matrix",
        "ed88783162991c151ab3d537d4eb7d3546b3688339a06db6f35b7f2ef7c48d4b",
        12,
    ),
    (
        "扩展开发场景（16 槽）",
        "reliability_v4_humble54_extension16_probe02_matrix",
        "1f7ff9559bcf9b1b02528a771f046481712a0ff5ec33eb961fe90310d1dcca54",
        16,
    ),
)
SAFETY = ROOT / (
    "tools/experiment_orchestration/humble54_safety4_closed03/"
    "originals/audit/slots_facts.json"
)
MONITOR = ROOT / "results/monitor_humble54_probe02_owner07/index.html"
ID_PATTERN = re.compile(r"[A-Za-z0-9_-]+\Z")
INPUTS: list[dict] = []


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, kind: str, expected_sha: str | None = None) -> dict:
    """Read only an explicitly selected small JSON and record its exact bytes."""
    before = path.stat()
    if not path.is_file() or before.st_size > MAX_JSON_BYTES:
        raise ValueError(f"Not a bounded small JSON: {path}")
    raw = path.read_bytes()
    after = path.stat()
    if len(raw) != before.st_size or (before.st_size, before.st_mtime_ns) != (
        after.st_size, after.st_mtime_ns
    ):
        raise ValueError(f"Input changed during read: {path}")
    sha = hashlib.sha256(raw).hexdigest()
    if expected_sha is not None and sha != expected_sha:
        raise ValueError(f"Original plan bytes differ from the pinned input: {path}")
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    INPUTS.append({
        "kind": kind,
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": len(raw),
        "sha256": sha,
        "mtime_utc": datetime.fromtimestamp(after.st_mtime, timezone.utc).isoformat(),
    })
    return obj


def check_content_digest(obj: dict, field: str, path: Path) -> None:
    content = {key: value for key, value in obj.items() if key != field}
    digest = hashlib.sha256(json.dumps(
        content, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()).hexdigest()
    if obj.get(field) != digest:
        raise ValueError(f"Original {field} mismatch: {path}")


def href(path: Path) -> str:
    return quote(Path(os.path.relpath(path, OUTPUT)).as_posix(), safe="/._-")


def link(path: Path, label: str) -> str:
    return f'<a href="{href(path)}">{escape(label)}</a>'


def shown(value: object) -> str:
    return escape(str(value)) if value is not None else "—"


def metric(value: object) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return f"{value:.3f}"
    return "—"


def media_links(directory: Path) -> str:
    """Only inspect filenames/existence; never read or decode any media payload."""
    links = []
    for name, label in (
        ("onboard.mp4", "机载录像"),
        ("flight_evaluation.json", "跟随报告"),
        ("navigation_reference_evaluation.json", "导航报告"),
        ("stage2_evaluation.json", "身份报告"),
        ("stage3_evaluation.json", "云台报告"),
        ("summary.json", "运行摘要"),
    ):
        path = directory / name
        if path.is_file():
            links.append(link(path, label))
    frames = sorted(directory.glob("frame_*.jpg")) if directory.is_dir() else []
    if frames:
        for index, label in ((0, "首帧"), (len(frames) // 2, "中帧"), (-1, "末帧")):
            links.append(link(frames[index], label))
    return " · ".join(links) or "尚无已发布媒体或报告"


def collect_plan(title: str, directory: str, raw_sha: str, count: int) -> dict:
    path = PUBLISHED / directory / "plan.json"
    plan = read_json(path, "original_plan", raw_sha)
    check_content_digest(plan, "plan_sha256", path)
    if len(plan["trials"]) != count:
        raise ValueError(f"Unexpected original plan size: {path}")
    expected_root = "/mnt/d/" + ROOT.name + "/results/frozen_fullplan_v4_humble54"
    if plan.get("results_root") != expected_root:
        raise ValueError(f"Unexpected original published results root: {path}")
    rows = []
    seen = set()
    for trial in plan["trials"]:
        trial_id, name = trial["id"], trial["name"]
        if not ID_PATTERN.fullmatch(trial_id) or not ID_PATTERN.fullmatch(name) or trial_id in seen:
            raise ValueError(f"Unsafe or duplicate original trial identity: {trial_id}")
        seen.add(trial_id)
        terminal_path = path.parent / "slots" / (trial_id + ".json")
        started_path = path.parent / "slots" / (trial_id + ".started.json")
        started = None
        if started_path.is_file():
            started = read_json(started_path, "original_started")
            if started.get("id") != trial_id or started.get("plan_sha256") != plan["plan_sha256"]:
                raise ValueError(f"Original START binding mismatch: {started_path}")
        terminal = None
        if terminal_path.is_file():
            terminal = read_json(terminal_path, "original_terminal")
            check_content_digest(terminal, "record_sha256", terminal_path)
            if any(terminal.get(k) != expected for k, expected in (
                ("id", trial_id), ("name", name), ("plan_sha256", plan["plan_sha256"])
            )):
                raise ValueError(f"Original terminal binding mismatch: {terminal_path}")
            status = terminal["status"]
            if not isinstance(status, str) or not status:
                raise ValueError(f"Original terminal has no status: {terminal_path}")
        else:
            status = "STARTED_AWAITING_TERMINAL" if started is not None else "PENDING"
        rows.append({
            "trial": trial, "status": status, "terminal": terminal, "started": started,
            "terminal_path": terminal_path, "started_path": started_path,
            "published_directory": PUBLISHED / name,
        })
    return {"title": title, "path": path, "plan": plan, "rows": rows}


def status_markup(status: str) -> str:
    css = "pass" if status == "PASS" else "fail" if status == "FAIL" else "other"
    label = {
        "STARTED_AWAITING_TERMINAL": "已启动，待原终态",
        "PENDING": "尚未启动",
        "INCOMPLETE_EVIDENCE": "INCOMPLETE_EVIDENCE（证据不完整）",
    }.get(status, status)
    return f'<span class="status {css}">{escape(label)}</span>'


def counts_text(rows: list[dict]) -> str:
    counts = Counter(row["status"] for row in rows)
    return "；".join(f"{shown(key)}：{value}" for key, value in counts.items())


def trial_row(row: dict) -> str:
    trial, terminal, started = row["trial"], row["terminal"], row["started"]
    original = terminal or {}
    measured = original.get("engineering_evidence", {}).get("measured") or {}
    title = trial.get("extension_condition") or trial["group"]
    identity = f'{"行人" if trial["target_class"] == "person" else "汽车"} · {title}'
    details = [f'<div>原任务 ID：<code>{shown(trial["id"])}</code></div>']
    details.append(f'<div>计划内容 SHA-256：<code>{shown(original.get("plan_sha256", (started or {}).get("plan_sha256")))}</code></div>')
    if terminal:
        details.append(f'<div>原终态内容 SHA-256：<code>{shown(terminal.get("record_sha256"))}</code></div>')
        raw_sha = next(item["sha256"] for item in INPUTS if item["path"] == row["terminal_path"].relative_to(ROOT).as_posix())
        details.append(f'<div>原终态文件 SHA-256：<code>{raw_sha}</code></div>')
        details.append(link(row["terminal_path"], "原终态 JSON"))
    if started:
        details.append(link(row["started_path"], "原启动登记 JSON"))
    start = original.get("started_utc", (started or {}).get("started_utc"))
    end = original.get("finished_utc")
    return (
        f'<tr data-trial-id="{escape(trial["id"])}"><td><strong>{escape(identity)}</strong>'
        f'<div class="small">阶段 {shown(trial["stage"])} · seed {shown(trial["seed"])} · '
        f'{shown(trial.get("command_mode"))} · 云台 {shown(trial.get("gimbal_mode"))}</div>'
        f'<details><summary>原件与 SHA-256</summary>{"".join(details)}</details></td>'
        f'<td>{status_markup(row["status"])}<div class="small">工程结果：{shown(original.get("engineering_result"))}'
        f'<br>执行状态：{shown(original.get("execution_status"))}</div></td>'
        f'<td class="number">{metric(measured.get("base_link_distance_rmse_m"))}</td>'
        f'<td class="number">{metric(measured.get("base_link_height_rmse_m"))}</td>'
        f'<td class="small">开始：{shown(start)}<br>结束：{shown(end)}</td>'
        f'<td>{media_links(row["published_directory"])}</td></tr>'
    )


def render(groups: list[dict], safety: dict, created: str) -> str:
    rows = [row for group in groups for row in group["rows"]]
    counts = Counter(row["status"] for row in rows)
    terminal_count = sum(row["terminal"] is not None for row in rows)
    safety_rows = safety.get("slots", [])
    safety_pass = sum(slot.get("original_status") == "PASS" for slot in safety_rows)
    group_html = []
    for group in groups:
        group_html.append(
            f'<section><h2>{escape(group["title"])}</h2><p>{counts_text(group["rows"])}。'
            f'{link(group["path"], "原始计划 JSON")}</p><div class="table-scroll"><table>'
            '<thead><tr><th>场景</th><th>原始结果</th><th>距离 RMSE / m</th>'
            '<th>高度 RMSE / m</th><th>原始 UTC 时间</th><th>查看成果</th></tr></thead><tbody>'
            + "".join(trial_row(row) for row in group["rows"])
            + '</tbody></table></div></section>'
        )
    safety_html = "".join(
        f'<li><code>{shown(slot.get("id"))}</code>：{shown(slot.get("original_status"))}</li>'
        for slot in safety_rows
    )
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Humble54 开发成果查看</title><style>
:root{{color-scheme:light;--ink:#173047;--line:#d9e2ec;--muted:#526579}}
*{{box-sizing:border-box}}body{{margin:0;background:#f3f6fa;color:var(--ink);font-family:"Microsoft YaHei",system-ui,sans-serif;line-height:1.65}}
main{{max-width:1580px;margin:auto;padding:26px}}h1{{font-size:1.9rem;margin:0 0 8px}}h2{{font-size:1.25rem}}
a{{color:#145d9b}}section,.notice,.card{{background:white;border:1px solid var(--line);border-radius:10px;padding:18px;margin:18px 0}}
.notice{{border-left:5px solid #c77713;background:#fffaf0}}.cards{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}}
.card{{margin:0}}.card strong{{display:block;font-size:1.8rem}}.small{{font-size:.81rem;color:var(--muted)}}
table{{width:100%;border-collapse:collapse;font-size:.91rem}}th,td{{text-align:left;padding:12px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{background:#edf3f8}}td:first-child{{min-width:250px}}td:last-child{{min-width:190px}}.table-scroll{{overflow-x:auto}}
.number{{font-variant-numeric:tabular-nums;text-align:right}}.status{{font-weight:bold;display:inline-block;padding:2px 7px;border-radius:4px}}
.pass{{background:#dff2e6;color:#146134}}.fail{{background:#fde5e2;color:#a32620}}.other{{background:#fff0d6;color:#785010}}
code{{font-family:Consolas,monospace;font-size:.83em;overflow-wrap:anywhere}}details{{max-width:480px;font-size:.8rem;margin-top:8px}}summary{{cursor:pointer}}
details a{{display:inline-block;margin-right:12px}}footer{{font-size:.85rem;color:var(--muted)}}
@media(max-width:760px){{main{{padding:14px}}.cards{{grid-template-columns:1fr}}h1{{font-size:1.4rem}}}}
</style></head><body><main>
<h1>Humble54 开发成果查看</h1>
<p>生成时快照：<code>{escape(created)}</code>（UTC）。{link(MONITOR, "查看原实时实验进度页")} · {link(OUTPUT / "inputs_receipt.json", "查看本页输入凭证")}</p>
<div class="notice"><strong>开发 PASS 不等于项目完成。</strong>本页逐项展示原始终态登记，不重新运行评价，也不改变 PASS、FAIL 或证据不完整结论。
正式独立验证仍为 0/280；开发 28 槽和独立安全 4 槽均不计入正式分母。原始结果用于定位问题，不能证明自适应 KF 全面优于其他方法。</div>
<div class="cards"><div class="card">开发 28 槽<strong>{terminal_count} / 28 已有终态</strong><div>{counts_text(rows)}</div></div>
<div class="card">独立安全开发<strong>{safety_pass} / {len(safety_rows)} 原始 PASS</strong><div>与上述开发 28 槽分开记录。</div></div>
<div class="card">正式独立验证<strong>0 / 280</strong><div>当前项目登记边界；本页不扫描或推断正式矩阵。</div></div></div>
<p class="small">距离与高度 RMSE 直接摘录原终态 <code>engineering_evidence.measured</code> 的
<code>base_link_distance_rmse_m</code> / <code>base_link_height_rmse_m</code>；缺失显示“—”，仅保留三位小数用于阅读。
“已启动，待原终态”仅表示存在启动登记，不证明进程现在仍在运行。实时状态请查看原监控页，本页不会自动刷新。</p>
{"".join(group_html)}
<section><h2>独立安全 4 槽</h2><p>{link(SAFETY, "原始安全事实快照")}；原事实生成时间：<code>{shown(safety.get("created_utc"))}</code>。</p><ul>{safety_html}</ul>
<p class="small">仅展示已归档事实中的 original_status，未重跑安全评价或检查当前进程。</p></section>
<footer>录像、图片和报告均链接原发布目录，点击后才打开。本页不自动播放或加载媒体；未读取 telemetry、rosbag 或模型，未校验整包。
终态 SHA、计划绑定及小 JSON 字节凭证用于追溯本页输入，不替代完整实验验收。</footer>
</main></body></html>'''


def write_atomic(path: Path, data: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(data, encoding="utf-8", newline="\n")
    temporary.replace(path)


def main() -> None:
    started = utc_now()
    INPUTS.clear()
    groups = [collect_plan(*spec) for spec in PLANS]
    safety = read_json(SAFETY, "original_safety_facts")
    if safety.get("kind") != "RELIABILITY_V4_SAFETY_EXECUTION_FACTS" or len(safety.get("slots", [])) != 4:
        raise ValueError("Unexpected independent safety facts input")
    created = utc_now()
    html = render(groups, safety, created)
    rows = [row for group in groups for row in group["rows"]]
    receipt = {
        "schema_version": 1,
        "kind": "HUMBLE54_DEVELOPMENT_VIEW_INPUTS_RECEIPT",
        "scope": "READ_ONLY_ORIGINAL_DEVELOPMENT_RESULTS_NOT_FORMAL_ADMISSION",
        "read_started_utc": started,
        "created_utc": created,
        "original_status_counts": dict(Counter(row["status"] for row in rows)),
        "development_planned_count": len(rows),
        "development_original_terminal_count": sum(row["terminal"] is not None for row in rows),
        "independent_safety_original_status_counts": dict(Counter(
            slot.get("original_status") for slot in safety["slots"]
        )),
        "formal_boundary": {"registered_trials": 0, "planned_trials": 280,
                            "source": "Project owner scope at preparation; formal matrix not read"},
        "input_limit_bytes_each": MAX_JSON_BYTES,
        "inputs": INPUTS,
        "html_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
        "limits": [
            "No verdict recomputation; original status and measured values only",
            "START marker is not a current liveness observation",
            "Media/report links inspect existence or filenames only",
            "No telemetry, rosbag, model, payload archive or full-package hashing",
            "No native simulation, browser, watcher or frozen-source writes",
        ],
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_atomic(OUTPUT / "index.html", html)
    write_atomic(OUTPUT / "inputs_receipt.json", json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(OUTPUT / "index.html"), "counts": receipt["original_status_counts"],
                      "inputs": len(INPUTS), "input_bytes": sum(item["bytes"] for item in INPUTS)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
