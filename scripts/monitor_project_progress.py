"""Observe local processes and small execution records; never start ROS or read bags.

All writes belong to an independent monitor directory inside this project.
COMPLETED means the monitored command ended, never engineering acceptance.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
OWNER = "uav-project-progress-v1"
ACTIVE = {"RUNNING", "EVALUATING"}
STATES = sorted(ACTIVE | {"STOPPED_FAULT", "COMPLETED", "STALE", "UNVERIFIED"})
MAX_SOURCE_BYTES = 8 * 1024 * 1024


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.timestamp() if result.tzinfo else None
    except (TypeError, ValueError, OverflowError):
        return None


def read_json(path):
    path = Path(path)
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("Small-record size limit exceeded: " + str(path))
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_json(path, value):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def prepare_output(value):
    path = Path(value).resolve()
    if not path.is_relative_to(ROOT) or path == ROOT:
        raise ValueError("Monitor output must be a separate directory inside this project")
    if any(part.lower().startswith("frozen_") for part in path.relative_to(ROOT).parts):
        raise ValueError("Frozen evidence directories are read-only")
    if path.exists():
        marker = path / "monitor_owner.json"
        if any(path.iterdir()) and (not marker.is_file() or read_json(marker).get("owner") != OWNER):
            raise ValueError("Refusing to write into a directory not owned by this monitor")
    path.mkdir(parents=True, exist_ok=True)
    if not (path / "monitor_owner.json").exists():
        atomic_json(path / "monitor_owner.json", {"owner": OWNER, "created_utc": utc_now()})
    return path


def process_identity(pid):
    """PID plus kernel creation identity; permission/unsupported cases stay unknown."""
    result = {"pid": int(pid), "alive": None, "start_token": None, "created_utc": None}
    if int(pid) <= 0:
        return {**result, "alive": False, "error": "invalid_pid"}
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        handle = kernel.OpenProcess(0x1000, False, int(pid))
        if not handle:
            error = ctypes.get_last_error()
            return {**result, "alive": False if error == 87 else None, "error": "OpenProcess:" + str(error)}
        try:
            exit_code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return {**result, "error": "GetExitCodeProcess_failed"}
            result["alive"] = exit_code.value == 259
            values = [wintypes.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in values)):
                return {**result, "error": "GetProcessTimes_failed"}
            creation = (values[0].dwHighDateTime << 32) | values[0].dwLowDateTime
            result["start_token"] = "windows_filetime:" + str(creation)
            result["created_utc"] = datetime.fromtimestamp((creation - 116444736000000000) / 1e7, timezone.utc).isoformat()
            return result
        finally:
            kernel.CloseHandle(handle)
    if sys.platform.startswith("linux"):
        try:
            stat = Path("/proc", str(pid), "stat").read_text()
            fields = stat[stat.rfind(")") + 2:].split()
            boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            start_ticks = int(fields[19])
            ticks = os.sysconf("SC_CLK_TCK")
            boot_seconds = next(int(line.split()[1]) for line in Path("/proc/stat").read_text().splitlines() if line.startswith("btime "))
            return {**result, "alive": fields[0] not in {"Z", "X"},
                    "start_token": "linux:" + boot_id + ":" + str(start_ticks),
                    "created_utc": datetime.fromtimestamp(boot_seconds + start_ticks / ticks, timezone.utc).isoformat()}
        except FileNotFoundError:
            return {**result, "alive": False, "error": "process_not_found"}
        except (OSError, ValueError, IndexError, StopIteration) as error:
            return {**result, "error": str(error)}
    return {**result, "error": "kernel_creation_identity_not_supported"}


def verify_process(expected):
    if not expected or expected.get("start_token") is None:
        return {"verified_alive": False, "identity_matches": None, "observation": None,
                "reason": "No recorded process creation identity"}
    observed = process_identity(expected["pid"])
    matches = observed.get("start_token") == expected["start_token"] if observed.get("start_token") else None
    return {"verified_alive": bool(observed["alive"] is True and matches is True),
            "identity_matches": matches, "observation": observed,
            "reason": "PID creation identity checked; PID reuse is not accepted"}


def source_records(sources):
    report = {"paths": sources, "errors": [], "events": [], "ledger": None, "plan": None}
    for kind in ("events", "ledger", "plan"):
        if not sources.get(kind):
            continue
        try:
            path = Path(sources[kind])
            if kind != "events":
                value = read_json(path)
                if not isinstance(value, dict):
                    raise ValueError("Expected JSON object")
                report[kind] = value
                continue
            if path.stat().st_size > MAX_SOURCE_BYTES:
                raise ValueError("Event record exceeds small-source limit")
            lines = path.read_text(encoding="utf-8-sig").splitlines()
            for number, line in enumerate(lines, 1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise ValueError("Event must be an object")
                    report["events"].append(value)
                except ValueError as error:
                    report["errors"].append({"source": kind, "line": number, "error": str(error)})
        except (OSError, ValueError) as error:
            report["errors"].append({"source": kind, "error": str(error)})
    return report


def evidence_summary(records):
    events, ledger, plan = records["events"], records["ledger"] or {}, records["plan"] or {}
    completed = {row["slot"]: row for row in events if row.get("event") == "COMPLETE_SLOT" and row.get("slot")}
    started = {row["slot"]: row for row in events if row.get("event") == "START_SLOT" and row.get("slot")}
    trials = plan.get("trials", [])
    planned = {row.get("id") for row in trials if isinstance(row, dict) and row.get("id")}
    declared_total = max((row.get("total", 0) for row in events if isinstance(row.get("total", 0), int)), default=0)
    total = len(planned) or declared_total or None
    current = next((row.get("slot") for row in reversed(events) if row.get("event") == "START_SLOT"
                    and row.get("slot") not in completed), None)
    last = events[-1] if events else None
    fault = next((row for row in reversed(events) if row.get("event") in {
        "INFRASTRUCTURE_STOP_NO_AUTOMATIC_RETRY", "STOPPED_FAULT", "ABORTED"}), None)
    exits = [ledger.get("returncode")] + [row.get("returncode") for row in ledger.get("executions", []) if isinstance(row, dict)]
    terminal_utc = (fault or {}).get("utc") or ledger.get("finished_utc")
    if fault or any(isinstance(code, int) and code != 0 for code in exits):
        state = "STOPPED_FAULT"
    elif ledger.get("finished_utc") and ledger.get("returncode") == 0:
        state = "COMPLETED" if total is None or len(completed) == total else "UNVERIFIED"
    elif total and len(completed) == total:
        state, terminal_utc = "COMPLETED", (last or {}).get("utc")
    else:
        state = "UNVERIFIED"
    if records["errors"] and state == "COMPLETED":
        state = "UNVERIFIED"
    last_utc = (last or {}).get("utc")
    executions = ledger.get("executions", [])
    latest_execution = executions[-1] if executions else None
    return {"state": state, "current_slot": current, "last_slot": (last or {}).get("slot"),
            "planned_slots": total, "attempted_slots": len(started), "recorded_terminal_slots": len(completed),
            "unattempted_slots": max(0, total - len(started)) if total is not None else None,
            "attempted_without_terminal": sorted(set(started) - set(completed)),
            "status_counts": dict(Counter(row.get("status", "UNKNOWN") for row in completed.values())),
            "last_event": last, "last_event_utc": last_utc, "terminal_utc": terminal_utc,
            "ledger_step": ledger.get("step"), "ledger_finished_utc": ledger.get("finished_utc"),
            "ledger_returncode": ledger.get("returncode"), "latest_execution": latest_execution,
            "errors": records["errors"],
            "claim_boundary": "Execution records and counts only; engineering FAIL/PENDING are never counted as PASS"}


def snapshot(state, *, now=None):
    now = time.time() if now is None else now
    evidence = evidence_summary(source_records(state.get("sources", {})))
    task = state.get("task")
    process = verify_process((task or {}).get("process"))
    monitor = verify_process(state.get("monitor_process"))
    heartbeat = timestamp(state.get("heartbeat_utc"))
    age = now - heartbeat if heartbeat is not None else None
    stale_after = state.get("stale_after_s", 10.0)
    reason = "No verified current process or heartbeat; files alone do not establish activity"
    status = evidence["state"]
    scope = "observed_execution_records"
    if task:
        scope = "monitored_command"
        if task.get("finished_utc"):
            code = task.get("returncode")
            status = "COMPLETED" if code == 0 else "STOPPED_FAULT" if isinstance(code, int) else "UNVERIFIED"
            reason = "Monitored command ended; this is not project acceptance"
        elif age is None or age < -2.0:
            status, reason = "UNVERIFIED", "Heartbeat missing or wall clock moved backwards"
        elif age > stale_after or not monitor["verified_alive"]:
            status, reason = "STALE", "Independent monitor heartbeat/creation identity is no longer current"
        elif not process["verified_alive"]:
            status, reason = "UNVERIFIED", "Target process exited or its creation identity cannot be verified; exit outcome is unknown"
        else:
            status = "EVALUATING" if task.get("phase") == "evaluation" else "RUNNING"
            reason = "Target PID creation identity, monitor identity and fresh heartbeat verified"
            terminal = timestamp(evidence.get("terminal_utc"))
            created = timestamp(task["process"].get("created_utc"))
            if evidence["state"] == "STOPPED_FAULT" and terminal is not None and created is not None and terminal >= created:
                status, reason = "STOPPED_FAULT", "Current command has recorded a fault; process may still be cleaning up"
    elif status == "STOPPED_FAULT":
        reason = "Preserved nonzero exit or explicit infrastructure stop; no current process is claimed"
    elif status == "COMPLETED":
        reason = "Recorded execution ended; engineering acceptance and entire-project completion remain separate"
    return {"schema_version": 1, "owner": OWNER, "generated_utc": datetime.fromtimestamp(now, timezone.utc).isoformat(),
            "status": status, "reason": reason, "completion_scope": scope,
            "phase": (task or {}).get("phase") or evidence.get("ledger_step"), "task": task,
            "process_check": process, "monitor_check": monitor,
            "heartbeat_utc": state.get("heartbeat_utc"), "heartbeat_age_s": age,
            "stale_after_s": stale_after, "evidence_sources": state.get("sources", {}), "evidence": evidence,
            "tasks": state.get("tasks", []), "notification": None,
            "claim_boundary": "No ROS/WSL/simulator is started, no bag is read. No automatic chat wake-up or engineering PASS is promised."}


def notify_local(output, report, requested):
    previous_path = output / "notification.json"
    if not requested or report["status"] in ACTIVE | {"STALE"}:
        return read_json(previous_path) if previous_path.exists() else {"requested": False, "submitted": False, "user_observed": None}
    key = hashlib.sha256(json.dumps([report["status"], report.get("task"), report["evidence"].get("terminal_utc")], sort_keys=True).encode()).hexdigest()
    if previous_path.exists():
        previous = read_json(previous_path)
        if previous.get("terminal_key") == key:
            return previous
    result = {"requested": True, "attempted_utc": utc_now(), "terminal_key": key,
              "channel": "windows_local_toast", "submitted": False, "user_observed": None}
    if os.name != "nt":
        result["error"] = "Local toast is supported only on Windows; terminal summary remains available"
    else:
        script = r'''$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml('<toast><visual><binding template="ToastGeneric"><text></text><text></text></binding></visual></toast>')
$nodes = $xml.GetElementsByTagName('text')
$nodes.Item(0).InnerText = $env:UAV_MONITOR_NOTIFICATION_TITLE
$nodes.Item(1).InnerText = $env:UAV_MONITOR_NOTIFICATION_TEXT
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('WindowsPowerShell').Show($toast)
'''
        environment = dict(os.environ, UAV_MONITOR_NOTIFICATION_TITLE="UAV project: " + report["status"],
                           UAV_MONITOR_NOTIFICATION_TEXT=report["reason"])
        try:
            sent = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                  env=environment, capture_output=True, text=True, timeout=8,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
            result.update(submitted=sent.returncode == 0, returncode=sent.returncode)
            if sent.returncode:
                result["error"] = (sent.stderr or sent.stdout)[-2000:]
        except (OSError, subprocess.TimeoutExpired) as error:
            result["error"] = str(error)
    atomic_json(previous_path, result)
    return result


def write_report(output, state, *, notify=False):
    report = snapshot(state)
    report["notification"] = notify_local(output, report, notify)
    atomic_json(output / "progress.json", report)
    terminal = report["status"] not in ACTIVE | {"STALE"}
    if terminal:
        atomic_json(output / "end_summary.json", report)
    payload = json.dumps(report, ensure_ascii=False).replace("<", "\\u003c")
    content = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta http-equiv="refresh" content="5"><meta name="viewport" content="width=device-width">
<title>UAV project progress</title><style>body{font:16px system-ui;max-width:1000px;margin:2rem auto;padding:0 1rem;background:#101827;color:#e5edf8}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#192538;padding:1rem}#status{font-size:2rem;font-weight:700}a{color:#9acbff}.note{color:#c4ccda}</style>
<p>无人机跟踪项目 · 本地运行证据</p><div id="status"></div><p id="reason"></p>
<p id="freshness"></p><p class="note">页面每5秒重载独立监控生成的最新快照。COMPLETED只指当前命令或已记录批次结束；工程验收与整个项目完成需独立报告。没有聊天自动唤醒。</p>
<p><a href="progress.json">机器可读状态</a> · <a href="end_summary.json">最后结束摘要（可能属于上一任务）</a></p><pre id="details"></pre>
<script>const data=PAYLOAD;
function update(){let age=(Date.now()-Date.parse(data.generated_utc))/1000;let heartbeat=(Date.now()-Date.parse(data.heartbeat_utc))/1000;let status=data.status;let reason=data.reason;
if(['RUNNING','EVALUATING'].includes(status)&&(age>data.stale_after_s||heartbeat>data.stale_after_s)){status='STALE';reason='监控快照或心跳已过期；无法声称任务仍在运行。';}
if(['RUNNING','EVALUATING'].includes(status)&&age < -2){status='UNVERIFIED';reason='本地时钟与快照时间不一致。';}
document.getElementById('status').textContent=status;document.getElementById('reason').textContent=reason;
document.getElementById('freshness').textContent='快照UTC：'+data.generated_utc+'；快照年龄：'+Math.max(0,age).toFixed(1)+'秒；最后心跳：'+(data.heartbeat_utc||'未记录');
document.getElementById('details').textContent=JSON.stringify(data,null,2);}
update();setInterval(update,1000);</script></html>'''.replace("PAYLOAD", payload)
    temporary = output / ("index." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, output / "index.html")
    return report


def acquire_lock(output):
    path = output / "monitor.lock.json"
    if path.exists():
        previous = read_json(path)
        checked = verify_process(previous.get("process"))
        if checked["verified_alive"] or (checked["observation"] or {}).get("alive") is None:
            raise ValueError("Another monitor owns this output, or its identity is unknown")
        path.unlink()
    lock = {"owner": OWNER, "id": uuid.uuid4().hex, "process": process_identity(os.getpid())}
    with path.open("x", encoding="utf-8") as stream:
        json.dump(lock, stream)
    return lock


def sources_from(args, previous):
    sources = dict(previous.get("sources", {}))
    for name in ("events", "ledger", "plan"):
        value = getattr(args, name, None)
        if value:
            sources[name] = str(Path(value).resolve())
    return sources


def monitor(args, output, previous):
    lock = acquire_lock(output)
    child = None
    state = previous.copy()
    try:
        task_id = args.task_id or lock["id"]
        tasks = list(previous.get("tasks", []))
        if any(row.get("id") == task_id for row in tasks):
            raise ValueError("Task ID already exists; use a new unique ID")
        command = args.command[1:] if args.action == "run" and args.command[:1] == ["--"] else getattr(args, "command", [])
        if args.action == "run":
            if not command:
                raise ValueError("run requires a command after --")
            log = (output / ("command_" + lock["id"] + ".log")).open("x", encoding="utf-8")
            try:
                child = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            finally:
                log.close()
            target = process_identity(child.pid)
        else:
            target = process_identity(args.pid)
        already_finished = child is not None and child.poll() is not None
        if not already_finished and (target["alive"] is not True or not target["start_token"]):
            raise ValueError("Cannot verify target PID creation identity")
        task = {"id": task_id, "phase": args.phase, "started_utc": utc_now(),
                "process": target, "finished_utc": None, "returncode": None,
                "monitor_kind": "owned_child" if child else "external_process",
                "label": args.label or args.phase}
        state = {"owner": OWNER, "host": socket.gethostname(), "sources": sources_from(args, previous),
                 "monitor_process": lock["process"], "task": task, "tasks": tasks + [task],
                 "stale_after_s": args.stale_after, "heartbeat_utc": utc_now()}
        while True:
            state["heartbeat_utc"] = utc_now()
            code = child.poll() if child else None
            live = verify_process(target)["verified_alive"]
            if code is not None or not live:
                task.update(finished_utc=utc_now(), returncode=code)
                if child is None:
                    task["outcome_note"] = "External process disappeared; its exit code is unavailable"
            atomic_json(output / "monitor_state.json", state)
            report = write_report(output, state, notify=args.notify and task["finished_utc"] is not None)
            if task["finished_utc"]:
                print(json.dumps({"status": report["status"], "task": task["id"], "output": str(output)}, ensure_ascii=True))
                return code if code is not None and 0 <= code <= 125 else 2 if child else 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        if state.get("task"):
            state["task"].update(finished_utc=utc_now(), returncode=child.returncode if child else None,
                                 outcome_note="Monitor interrupted; external targets are never terminated")
            atomic_json(output / "monitor_state.json", state)
            write_report(output, state, notify=args.notify)
        return 130
    finally:
        path = output / "monitor.lock.json"
        if path.exists() and read_json(path).get("id") == lock["id"]:
            path.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("snapshot", "watch", "run"):
        command = commands.add_parser(action)
        command.add_argument("--output", type=Path, required=True)
        for source in ("events", "ledger", "plan"):
            command.add_argument("--" + source, type=Path)
        command.add_argument("--notify", action="store_true", help="Attempt a local Windows toast; delivery/viewing is not guaranteed")
        if action != "snapshot":
            command.add_argument("--phase", choices=("simulation", "evaluation", "archive", "statistics", "documents", "batch"), required=True)
            command.add_argument("--task-id")
            command.add_argument("--label")
            command.add_argument("--interval", type=float, default=1.0)
            command.add_argument("--stale-after", type=float, default=10.0)
        if action == "watch":
            command.add_argument("--pid", type=int, required=True, help="Local OS PID; this script never invokes WSL to discover Linux PIDs")
        if action == "run":
            command.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        if args.action != "snapshot" and (not math.isfinite(args.interval) or not math.isfinite(args.stale_after)
                                          or not 0 < args.interval < args.stale_after):
            raise ValueError("Require 0 < interval < stale-after, both finite")
        output = prepare_output(args.output)
        previous = read_json(output / "monitor_state.json") if (output / "monitor_state.json").exists() else {}
        if not previous and (output / "progress.json").exists():
            previous["sources"] = read_json(output / "progress.json").get("evidence_sources", {})
        if args.action == "snapshot":
            previous["sources"] = sources_from(args, previous)
            report = write_report(output, previous, notify=args.notify)
            print(json.dumps({"status": report["status"], "evidence": report["evidence"], "output": str(output)}, ensure_ascii=True))
            return 0
        return monitor(args, output, previous)
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "UNVERIFIED", "error": str(error)}, ensure_ascii=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
