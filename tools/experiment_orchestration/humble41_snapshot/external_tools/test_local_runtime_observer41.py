"""Pure/fake native owner and real temporary-file copies; no WSL/ROS/SITL."""
from contextlib import ExitStack
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import local_runtime_observer41 as m


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


class Clock:
    now = 100.

    def __call__(self):
        return self.now


class Process:
    def __init__(self, close=None):
        self.returncode = None
        self.close = close
        self.stdout = io.BytesIO()
        self.sent = []
        self.killed = False

    def poll(self):
        return self.returncode

    def send_signal(self, sent):
        self.sent.append(sent)
        self.returncode = 0

    def wait(self, timeout):
        if self.close:
            self.returncode = self.close()
            self.close = None
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9


class OwnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="observer41_fake_")
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "D/frozen41"
        (self.root / "results").mkdir(parents=True)
        (self.root / "scripts").mkdir()
        (self.root / "scripts/observe_runtime_health.py").write_bytes(b"# synthetic collector source\n")
        self.live_base = self.base / "shm/private"
        self.live_base.mkdir(parents=True)
        self.clock = Clock()
        self.patches = ExitStack()
        self.patches.enter_context(patch.object(m, "LIVE_BASE", self.live_base))
        self.patches.enter_context(patch.object(m, "D_ROOT", self.base / "D"))
        self.patches.enter_context(patch.object(m.time, "monotonic", side_effect=self.clock))
        self.patches.enter_context(patch.object(m, "check_private"))
        self.patches.enter_context(patch.object(m, "capacity", side_effect=self.capacity))
        self.patches.enter_context(patch.object(m, "prepare_live", side_effect=self.prepare))

    def tearDown(self):
        self.patches.close()
        self.temp.cleanup()

    def prepare(self):
        folder = self.live_base / ("owner41_" + "a" * 32)
        folder.mkdir()
        return folder

    def capacity(self, _):
        reserve = 2 * (m.HEALTH_LIMIT + m.CONSOLE_LIMIT + m.SMALL_LIMIT)
        return {"mount": {"mountpoint": str(self.live_base.parent), "filesystem": "tmpfs"},
                "free_bytes": reserve + 1024, "required_free_bytes": reserve,
                "health_limit_bytes": m.HEALTH_LIMIT, "console_limit_bytes": m.CONSOLE_LIMIT}

    def sample(self, session, stamp=None):
        return {"schema_version": 1, "event": "RUNTIME_HEALTH_SAMPLE",
                "monotonic_s": self.clock.now if stamp is None else stamp,
                "ros_receiver": {"thread_alive": True, "error": None},
                "writer": {"writer_alive": True, "error": None, "limit_reached": False,
                           "dropped_aggregates": 0},
                "disk": {"output_d_mount": {"path": str(session.archive / "runtime_health"),
                                          "status": "deferred_to_archive_owner"},
                         "live_output_tmpfs": {"path": str(session.local / "runtime_health")}}}

    def health(self, session, *, stopped=True):
        start = {"schema_version": 1, "event": "RUNTIME_HEALTH_OBSERVER_STARTED",
            "monotonic_s": session.started, "storage_mode": m.MODE, "ros_enabled": True,
            "duration_wall_s": 7200., "period_wall_s": 1.,
            "live_output": str(session.local / "runtime_health"),
            "archive_output": str(session.archive / "runtime_health"),
            "archive_status": "pending_external_owner",
            "output_mount": {"mountpoint": str(self.live_base.parent), "filesystem": "tmpfs"},
            "source_sha256": {"observe_runtime_health.py": session.owner.collector_source["sha256"]}}
        samples = []
        if session.health.is_file():
            samples = [json.loads(line) for line in session.health.read_text().splitlines()
                       if json.loads(line).get("event") == "RUNTIME_HEALTH_SAMPLE"]
        if not samples or samples[-1]["monotonic_s"] != self.clock.now:
            samples.append(self.sample(session))
        stop = {"schema_version": 1, "event": "RUNTIME_HEALTH_OBSERVER_STOPPED",
            "monotonic_s": self.clock.now, "reason": "signal", "samples_collected": len(samples),
            "samples_submitted": len(samples), "ros_receiver_final": {"thread_alive": False, "error": None}}
        rows = [start, *samples] + ([stop] if stopped else [])
        session.health.parent.mkdir(parents=True, exist_ok=True)
        session.health.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        # The actual collector creates its D leaf, but never writes into it.
        (session.archive / "runtime_health").mkdir(parents=True, exist_ok=True)

    def console_final(self, session):
        size = session.health.stat().st_size
        count = sum(json.loads(line).get("event") == "RUNTIME_HEALTH_SAMPLE"
                    for line in session.health.read_text().splitlines())
        return {"storage_mode": m.MODE, "flushed_cleanly": True, "reason": "signal",
            "output": str(session.archive / "runtime_health"),
            "live_output": str(session.local / "runtime_health"), "health_log": str(session.health),
            "health_log_size_bytes": size, "health_log_stat_error": None,
            "samples_collected": count, "samples_submitted": count,
            "writer_final": {"bytes_written": size, "writer_alive": False, "error": None,
                             "limit_reached": False, "dropped_aggregates": 0},
            "ros_receiver_final": {"thread_alive": False, "error": None},
            "cleanup": {"live_directory_removed": False, "archive_performed": False,
                        "responsible_owner": "external_archive_owner", "local_evidence_retained": True}}

    def start_session(self, session):
        self.health(session)
        dump(session.local / "observer_console.log", self.console_final(session))
        session.process = Process()
        session.console = SimpleNamespace(finish=lambda: None)
        session.first_check = session.check()
        session.first_fresh_at = self.clock.now
        session._started_contract()
        return session

    def owner(self, single=True):
        factory = m.SingleObserver if single else m.RollingObserver
        owner = factory(self.root / "results/new_observer", self.root)
        with patch.object(m.Session, "start", autospec=True, side_effect=self.start_session):
            owner.__enter__()
        return owner

    def archive_process(self, command, **kwargs):
        self.assertEqual(command[3], "_archive-worker")
        self.assertTrue(all(s.native is not None for s in self.active.sessions))
        def close():
            try:
                return m._archive_worker(Path(command[5]), command[7])
            except (OSError, ValueError, KeyError, TypeError):
                return 2
        return Process(close)

    def finish(self, owner):
        self.active = owner
        with patch.object(m.subprocess, "Popen", side_effect=self.archive_process):
            return owner.finish()

    def test_positive_native_then_real_verified_archive_and_idempotent_finish(self):
        owner = self.owner()
        self.assertEqual(owner.check()["sample_age_wall_s"], 0.)
        result = self.finish(owner)
        self.assertTrue(result["healthy_cleanup"], result)
        self.assertTrue(owner.live.is_dir())
        self.assertEqual(owner.finish(), result)
        receipt = m.validate_observer_root(result, owner.directory, self.root)
        self.assertTrue(receipt["native_and_archive_both_verified"])
        self.assertEqual(len(result["archive"]["copies"]), 4)

    def test_hot_check_never_stats_or_reads_D(self):
        owner = self.owner()
        real_stat = Path.stat
        real_open = Path.open
        def checked_stat(path, *args, **kwargs):
            self.assertFalse(path.is_relative_to(owner.directory), str(path))
            return real_stat(path, *args, **kwargs)
        def checked_open(path, *args, **kwargs):
            self.assertFalse(path.is_relative_to(owner.directory), str(path))
            return real_open(path, *args, **kwargs)
        with patch.object(Path, "stat", checked_stat), patch.object(Path, "open", checked_open):
            self.assertEqual(owner.check()["sample_age_wall_s"], 0.)

    def test_original10s_stale_future_nonfinite_bool_gates(self):
        owner = self.owner()
        sample = self.sample(owner.current)
        for stamp in (89.999, 100.1, float("inf"), float("nan"), True):
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                m.validate_sample({**sample, "monotonic_s": stamp}, 100.,
                                  owner.current.archive / "runtime_health")
        self.assertEqual(m.validate_sample({**sample, "monotonic_s": 90.}, 100.,
                         owner.current.archive / "runtime_health")["sample_age_wall_s"], 10.)

    def test_receiver_writer_dropped_limit_and_deferred_fields_fail_closed(self):
        owner = self.owner()
        good = self.sample(owner.current)
        defects = []
        for section, key, value in (("ros_receiver", "thread_alive", False),
                ("ros_receiver", "error", "bad"), ("writer", "writer_alive", False),
                ("writer", "dropped_aggregates", 1), ("writer", "limit_reached", True)):
            bad = deepcopy(good); bad[section][key] = value; defects.append(bad)
        bad = deepcopy(good); bad["disk"]["output_d_mount"]["free_bytes"] = 1; defects.append(bad)
        for bad in defects:
            with self.assertRaises(ValueError):
                m.validate_sample(bad, 100., owner.current.archive / "runtime_health")

    def test_long_D_archive_is_not_reinterpreted_as_live_staleness(self):
        owner = self.owner()
        original = m._copy_new
        def slow(*args):
            self.clock.now += 12.
            return original(*args)
        with patch.object(m, "_copy_new", side_effect=slow):
            result = self.finish(owner)
        self.assertGreater(result["archive"]["payload_elapsed_wall_s"], 10.)
        self.assertTrue(result["healthy_cleanup"])
        m.validate_observer_root(result, owner.directory, self.root)

    def test_archive_timeout_keeps_native_outcome_raw_and_no_retry(self):
        owner = self.owner()
        process = Process()
        def wait(timeout):
            if not process.killed:
                raise subprocess.TimeoutExpired("archive", timeout)
            return -9
        process.wait = wait
        with patch.object(m.subprocess, "Popen", return_value=process) as spawn:
            result = owner.finish()
            self.assertFalse(result["healthy_cleanup"])
            self.assertTrue(result["native"]["healthy_cleanup"])
            self.assertEqual(result["status"], "ARCHIVE_INFRA_ERROR")
            self.assertTrue(owner.current.health.is_file())
            self.assertEqual(owner.finish(), result)
            self.assertEqual(spawn.call_count, 1)

    def test_D_candidate_cannot_promote_archive_that_finishes_after_owner_budget(self):
        owner = self.owner()
        self.active = owner
        def delayed(command, **kwargs):
            process = self.archive_process(command, **kwargs)
            callback = process.close
            def late():
                code = callback()
                self.clock.now += 1801.
                return code
            process.close = late
            return process
        with patch.object(m.subprocess, "Popen", side_effect=delayed):
            result = owner.finish()
        self.assertFalse(result["healthy_cleanup"])
        self.assertTrue(result["native"]["healthy_cleanup"])
        candidate = m.read_json(owner.directory / "execution_terminal.json")
        self.assertEqual(candidate["status"], "COPY_VERIFIED_PENDING_OWNER_CLOSURE")
        self.assertFalse(candidate["healthy_cleanup"])
        with self.assertRaises(ValueError):
            m.validate_observer_root(None, owner.directory, self.root)
        with self.assertRaises(ValueError):
            m.validate_observer_root(result, owner.directory, self.root)

    def test_missing_partial_health_never_becomes_native_or_archive_pass(self):
        owner = self.owner()
        with owner.current.health.open("ab") as stream:
            stream.write(b'{"event":"unfinished"')
        result = self.finish(owner)
        self.assertFalse(result["healthy_cleanup"])
        with self.assertRaises((ValueError, OSError, KeyError)):
            m.validate_observer_root(result, owner.directory, self.root)

    def test_forced_native_stop_is_retained_and_cannot_promote(self):
        owner = self.owner()
        process = owner.current.process
        process.send_signal = lambda _: None
        def wait(timeout):
            if not process.killed:
                raise subprocess.TimeoutExpired("native", timeout)
            return -9
        process.wait = wait
        result = self.finish(owner)
        self.assertFalse(result["healthy_cleanup"])
        self.assertTrue(owner.current.native["observer_forced_stop"])
        self.assertTrue(owner.current.health.is_file())

    def test_archive_refuses_preexisting_file_without_overwrite(self):
        owner = self.owner()
        target = owner.directory / "native_exit_terminal.json"
        target.write_bytes(b"retain original")
        result = self.finish(owner)
        self.assertFalse(result["healthy_cleanup"])
        self.assertEqual(target.read_bytes(), b"retain original")

    def test_collector_source_drift_refuses_archive(self):
        owner = self.owner()
        (self.root / "scripts/observe_runtime_health.py").write_bytes(b"changed")
        result = self.finish(owner)
        self.assertFalse(result["healthy_cleanup"])
        self.assertTrue(owner.current.health.is_file())

    def test_archived_raw_mutation_is_rejected(self):
        owner = self.owner()
        result = self.finish(owner)
        target = owner.directory / "session_001/runtime_health/health.jsonl"
        with target.open("ab") as stream:
            stream.write(b"\n")
        with self.assertRaises(ValueError):
            m.validate_observer_root(result, owner.directory, self.root)

    def test_coherent_bad_raw_count_cannot_be_repaired_by_new_hashes(self):
        owner = self.owner()
        self.finish(owner)
        folder = owner.directory / "session_001"
        rows = [json.loads(line) for line in (folder / "runtime_health/health.jsonl").read_text().splitlines()]
        rows[-1]["samples_collected"] = 2
        (folder / "runtime_health/health.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows))
        with self.assertRaisesRegex(ValueError, "STOP count"):
            m.validate_closed_raw(folder, owner.current.local, owner.current.archive, owner.collector_source)

    def test_source_mismatched_START_is_rejected_before_any_D_copy(self):
        owner = self.owner()
        rows = [json.loads(line) for line in owner.current.health.read_text().splitlines()]
        rows[0]["source_sha256"]["observe_runtime_health.py"] = "0"*64
        owner.current.health.write_text("".join(json.dumps(r)+"\n" for r in rows))
        dump(owner.current.local / "observer_console.log", self.console_final(owner.current))
        with patch.object(m.subprocess, "Popen") as spawn:
            result = owner.finish()
        self.assertFalse(result["healthy_cleanup"])
        spawn.assert_not_called()

    def test_rotation_waits_for_new_first_then_stops_old_without_archive(self):
        owner = self.owner(single=False)
        self.clock.now += 5400.
        self.health(owner.current)
        dump(owner.current.local / "observer_console.log", self.console_final(owner.current))
        with patch.object(m.Session, "start", autospec=True, side_effect=self.start_session), \
                patch.object(m.subprocess, "Popen") as spawn:
            result = owner.check()
        self.assertEqual(result["sample_age_wall_s"], 0.)
        self.assertEqual(len(owner.sessions), 2)
        self.assertTrue(owner.sessions[0].native["healthy_cleanup"])
        self.assertIsNone(owner.sessions[1].native)
        spawn.assert_not_called()
        result = self.finish(owner)
        self.assertTrue(result["healthy_cleanup"], result)
        m.validate_observer_root(result, owner.directory, self.root)

    def test_sample_during_native_shutdown_does_not_invalidate_pre_stop_freshness(self):
        owner = self.owner()
        session = owner.current
        original_signal = session.process.send_signal
        def native_exit(sent):
            self.clock.now += .2
            self.health(session)
            dump(session.local / "observer_console.log", self.console_final(session))
            original_signal(sent)
        session.process.send_signal = native_exit
        result = self.finish(owner)
        self.assertTrue(result["healthy_cleanup"], result)
        self.assertEqual(session.native["final_fresh_sample"]["latest_sample_monotonic_s"], 100.)
        m.validate_observer_root(result, owner.directory, self.root)

    def test_cleanup_of_other_sessions_after_one_stop_error(self):
        owner = self.owner()
        other = SimpleNamespace(native=None, stop_native=lambda **_: setattr(other, "native", {"failed": True}))
        owner.sessions.append(other)
        with patch.object(owner.current, "stop_native", side_effect=OSError("signal race")):
            result = owner.finish()
        self.assertFalse(result["healthy_cleanup"])
        self.assertIsNotNone(other.native)

    def test_finite_archive_budget_and_fresh_output_are_required(self):
        for value in (0, -1, True, float("nan"), 1801):
            with self.subTest(value=value), self.assertRaises(ValueError):
                m.SingleObserver(self.root / "results/new", self.root, archive_wall_budget_s=value)
        old = self.root / "results/already"
        old.mkdir()
        with self.assertRaises(ValueError):
            m.SingleObserver(old, self.root)

    def test_exact_explicit_command_and_no_legacy_import(self):
        owner = self.owner()
        command = owner.current.command
        self.assertEqual(command.count("--output-dir"), 1)
        self.assertEqual(command.count("--live-output-dir"), 1)
        self.assertIn(str(owner.current.archive / "runtime_health"), command)
        self.assertIn(str(owner.current.local / "runtime_health"), command)
        self.assertIn("--ros", command)
        source = Path(m.__file__).read_text()
        self.assertNotIn("import reviewed_timing_diagnostic", source)
        self.assertNotIn("import car_surface_probe40", source)

    def test_console_drain_is_bounded_and_overflow_fails(self):
        path = self.base / "bounded_console"
        console = m.Console(io.BytesIO(b"x" * (m.CONSOLE_LIMIT + 1)), path)
        with self.assertRaises(ValueError):
            console.finish()
        self.assertEqual(path.stat().st_size, m.CONSOLE_LIMIT)

    def test_manifest_relative_paths_reject_escape_or_extra_payloads(self):
        for name in ("../health.jsonl", "/tmp/health.jsonl", "session_001/rosbag.db3",
                     "session_001/runtime_health/else.json", "archive_manifest.json"):
            self.assertFalse(m._allowed_relative(name), name)


if __name__ == "__main__":
    unittest.main()
