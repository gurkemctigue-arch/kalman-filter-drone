"""Storage and failure contracts; synthetic files only, no ROS or host scans."""
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("runtime_health_live_fixture", ROOT / "scripts/observe_runtime_health.py")
observer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(observer)


class LiveStorageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / "private_tmpfs_root"
        self.path = self.root / "owner" / "session"
        self.mount = {"filesystem": "tmpfs", "mountpoint": str(self.base), "device": "shm"}
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(observer, "LIVE_OUTPUT_ROOT", self.root))
        self.mount_lookup = stack.enter_context(patch.object(observer.link_observer, "mount_information", return_value=self.mount))
        stack.enter_context(patch.object(observer.os, "getuid", return_value=17, create=True))
        original = Path.lstat
        self.bad_uid = self.bad_mode = False

        def owned(path, *args, **kwargs):
            value = original(path, *args, **kwargs)
            if path == self.root or path.is_relative_to(self.root):
                # Emulate POSIX uid/mode on Windows, preserving the real file type.
                fields = list(value)
                fields[0] = (value.st_mode & ~0o7777) | (0o755 if self.bad_mode else 0o700)
                fields[4] = 18 if self.bad_uid else 17
                return os.stat_result(fields)
            return value
        stack.enter_context(patch.object(Path, "lstat", owned))

    def test_new_private_nested_directory_is_created_and_original_is_never_reused(self):
        directory, mount = observer.new_live_output_directory(self.path)
        self.assertEqual(directory, self.path)
        self.assertEqual(mount, self.mount)
        self.assertTrue(self.path.is_dir())
        self.assertRaises(ValueError, observer.new_live_output_directory, self.path)

    def test_relative_root_outside_traversal_and_existing_paths_reject(self):
        for path in (Path("relative"), self.root, self.base / "elsewhere", self.root / ".." / "escape"):
            with self.subTest(path=path):
                self.assertRaises(ValueError, observer.new_live_output_directory, path)
        self.assertFalse(self.root.exists())

    def test_non_tmpfs_and_nested_mounts_reject_before_directory_creation(self):
        for mount in ({**self.mount, "filesystem": "9p"}, {**self.mount, "filesystem": "ext4"},
                      {**self.mount, "mountpoint": str(self.root)}):
            with self.subTest(mount=mount):
                self.mount_lookup.return_value = mount
                self.assertRaisesRegex(ValueError, "actual /dev/shm tmpfs", observer.new_live_output_directory, self.path)
                self.assertFalse(self.root.exists())

    def test_other_uid_or_nonprivate_parent_rejects_without_creating_child(self):
        self.root.mkdir()
        for field in ("bad_uid", "bad_mode"):
            with self.subTest(field=field):
                setattr(self, field, True)
                self.assertRaisesRegex(ValueError, "owned by this uid", observer.new_live_output_directory, self.path)
                self.assertFalse((self.root / "owner").exists())
                setattr(self, field, False)

    def test_mount_change_during_creation_is_detected(self):
        self.mount_lookup.side_effect = [self.mount, {**self.mount, "device": "replaced"}]
        self.assertRaisesRegex(ValueError, "filesystem changed", observer.new_live_output_directory, self.path)

    @unittest.skipUnless(os.name == "posix", "Real symbolic links are validated in Linux")
    def test_ancestor_leaf_and_broken_symlinks_are_not_aliases_for_live_output(self):
        outside = self.base / "outside"
        outside.mkdir()
        self.root.symlink_to(outside, target_is_directory=True)
        self.assertRaises(ValueError, observer.new_live_output_directory, self.path)
        self.root.unlink()
        self.root.mkdir()
        leaf = self.root / "leaf"
        leaf.symlink_to(self.base / "missing", target_is_directory=True)
        self.assertRaises(ValueError, observer.new_live_output_directory, leaf)

    def test_default_storage_preserves_the_original_d_directory_and_mount(self):
        archive, mount = self.base / "archive", {"filesystem": "9p"}
        with patch.object(observer, "new_output_directory", return_value=(archive, mount)) as original, \
                patch.object(observer, "new_live_output_directory") as live:
            result = observer.new_storage(archive)
        original.assert_called_once_with(archive)
        live.assert_not_called()
        self.assertEqual(result["mode"], "legacy_direct_d")
        self.assertEqual(result["live_directory"], archive)
        self.assertEqual(result["live_mount"], mount)

    def test_live_storage_keeps_archive_validation_and_distinct_physical_destination(self):
        archive = self.base / "archive"
        with patch.object(observer, "new_output_directory", return_value=(archive, {"filesystem": "9p"})) as original:
            result = observer.new_storage(archive, self.path)
        original.assert_called_once_with(archive)
        self.assertEqual(result["mode"], "private_tmpfs_external_archive")
        self.assertEqual(result["archive_directory"], archive)
        self.assertEqual(result["live_directory"], self.path)

    def test_live_capacity_sampling_never_touches_archive_and_never_invents_bytes(self):
        archive = self.base / "archive"
        storage = {"mode": "private_tmpfs_external_archive", "archive_directory": archive, "live_directory": self.path}
        calls = []
        def usage(path):
            self.assertNotEqual(path, archive, "DrvFS capacity query entered freshness sampling")
            calls.append(path)
            return SimpleNamespace(total=100, used=20, free=80)
        with patch.object(observer.shutil, "disk_usage", side_effect=usage):
            result = observer.sample_disks(storage)
        self.assertEqual(calls, [Path("/"), self.path])
        self.assertEqual(result["output_d_mount"], {"path": str(archive), "status": "deferred_to_archive_owner"})
        self.assertEqual(result["live_output_tmpfs"]["free_bytes"], 80)

    def test_default_capacity_sampling_retains_original_two_queries(self):
        archive = self.base / "archive"
        storage = {"mode": "legacy_direct_d", "archive_directory": archive}
        with patch.object(observer, "disk_snapshot", return_value={"legacy": True}) as sampled:
            self.assertEqual(observer.sample_disks(storage), {"legacy": True})
        sampled.assert_called_once_with({"linux_root": Path("/"), "output_d_mount": archive})


class LiveLifecycleTests(unittest.TestCase):
    def run_main(self, temporary, *, live=True, fault=None, ros=False):
        base = Path(temporary)
        archive, local = base / "archive", base / "live"
        archive.mkdir()
        local.mkdir()
        directory = local if live else archive
        storage = {"mode": "private_tmpfs_external_archive" if live else "legacy_direct_d",
                   "archive_directory": archive, "archive_mount": {"filesystem": "9p"},
                   "live_directory": directory, "live_mount": {"filesystem": "tmpfs" if live else "9p"}}
        created, rows = [], []
        class Writer:
            def __init__(self, path, maximum):
                created.append((path, maximum))
                self.path, self.maximum, self.alive, self.dropped = path, maximum, True, 0
                path.write_bytes(b"")
            def submit(self, row):
                rows.append(row)
                if fault == "drop" and row["event"] == "RUNTIME_HEALTH_SAMPLE":
                    self.dropped += 1
                    return False
                with self.path.open("ab") as handle:
                    handle.write((json.dumps(row) + "\n").encode())
                return True
            def status(self):
                sample_seen = any(row["event"] == "RUNTIME_HEALTH_SAMPLE" for row in rows)
                return {"writer_alive": self.alive, "error": "OSError" if sample_seen and fault == "writer" else None,
                        "limit_reached": sample_seen and fault == "limit", "dropped_aggregates": self.dropped,
                        "bytes_written": self.path.stat().st_size}
            def finish(self):
                self.alive = fault == "alive"
                result = self.status()
                if fault == "size_mismatch":
                    result["bytes_written"] += 1
                return result
        receiver = SimpleNamespace(thread=SimpleNamespace(is_alive=lambda: True), error=None,
                                   start=Mock(), finish=Mock(return_value={"thread_alive": False, "error": None}))
        if fault == "receiver":
            receiver.finish.return_value = {"thread_alive": True, "error": "SyntheticReceiverFailure"}
        if fault == "start":
            receiver.start.side_effect = RuntimeError("SyntheticStartFailure")
        clock = iter(i * .3 for i in range(100))
        original_is_file = Path.is_file
        def host_sample(previous):
            stamp = observer.time.monotonic()
            return {"utc": "synthetic", "sample_gap_wall_s": None, "monotonic_s": stamp}, stamp
        with ExitStack() as stack:
            stack.enter_context(patch.object(observer.sys, "platform", "linux"))
            stack.enter_context(patch.object(Path, "is_file", lambda path: path == Path("/proc/meminfo") or original_is_file(path)))
            stack.enter_context(patch.object(observer, "new_storage", return_value=storage))
            stack.enter_context(patch.object(observer.link_observer, "BoundedWriter", Writer))
            stack.enter_context(patch.object(observer, "ProcessSampler", return_value=SimpleNamespace(sample=lambda _: {})))
            stack.enter_context(patch.object(observer.host_observer, "sample", side_effect=host_sample))
            stack.enter_context(patch.object(observer, "sample_disks", return_value={"synthetic": True}))
            stack.enter_context(patch.object(observer.time, "monotonic", side_effect=lambda: next(clock)))
            stack.enter_context(patch.object(observer.signal, "signal", return_value=None))
            stack.enter_context(patch.object(observer, "RosReceiver", return_value=receiver))
            output = stack.enter_context(redirect_stdout(io.StringIO()))
            args = ["--output-dir", str(archive), "--duration-wall-s", "1", "--max-log-mib", "64"]
            if live: args += ["--live-output-dir", str(local)]
            if ros: args += ["--ros"]
            if fault == "start":
                self.assertRaisesRegex(RuntimeError, "SyntheticStartFailure", observer.main, args)
                code = None
            else:
                code = observer.main(args)
        return code, json.loads(output.getvalue()), created, rows, receiver, archive, local

    def test_live_main_writes_only_local_complete_log_and_reports_archive_pending(self):
        with tempfile.TemporaryDirectory() as temporary:
            code, result, created, rows, _, archive, local = self.run_main(temporary)
            self.assertEqual(code, 0)
            self.assertEqual(created, [(local / "health.jsonl", 64 * 1024**2)])
            self.assertEqual(list(archive.iterdir()), [])
            self.assertEqual(result["output"], str(archive))
            self.assertEqual(result["health_log"], str(local / "health.jsonl"))
            self.assertEqual(result["health_log_size_bytes"], (local / "health.jsonl").stat().st_size)
            self.assertTrue(result["flushed_cleanly"])
            self.assertEqual(result["archive_status"], "pending_external_owner")
            self.assertFalse(result["cleanup"]["archive_performed"])
            self.assertFalse(result["cleanup"]["live_directory_removed"])
            self.assertEqual(rows[0]["archive_status"], "pending_external_owner")
            self.assertEqual(rows[-1]["event"], "RUNTIME_HEALTH_OBSERVER_STOPPED")

    def test_default_main_keeps_original_output_and_final_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            code, result, created, _, _, archive, _ = self.run_main(temporary, live=False)
            self.assertEqual(code, 0)
            self.assertEqual(created[0][0], archive / "health.jsonl")
            self.assertEqual(result["output"], str(archive))
            self.assertNotIn("archive_status", result)
            self.assertNotIn("live_output", result)

    def test_writer_failure_limit_drop_and_receiver_cleanup_cannot_claim_success(self):
        for fault in ("writer", "limit", "drop", "alive", "receiver", "size_mismatch"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                code, result, _, _, receiver, archive, local = self.run_main(temporary, fault=fault, ros=True)
                self.assertEqual(code, 2)
                self.assertFalse(result["flushed_cleanly"])
                self.assertEqual(result["archive_status"], "pending_external_owner")
                self.assertTrue((local / "health.jsonl").is_file())
                self.assertEqual(list(archive.iterdir()), [])
                receiver.finish.assert_called_once()

    def test_receiver_start_failure_still_flushes_and_retains_local_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, result, _, _, receiver, archive, local = self.run_main(temporary, fault="start", ros=True)
            self.assertEqual(result["reason"], "observer_exception")
            receiver.finish.assert_called_once()
            self.assertTrue((local / "health.jsonl").is_file())
            self.assertEqual(list(archive.iterdir()), [])

    def test_unstarted_ros_receiver_releases_context_without_joining_unstarted_thread(self):
        receiver = observer.RosReceiver.__new__(observer.RosReceiver)
        receiver.stopping, receiver.executor, receiver.node, receiver.context, receiver.rclpy = [Mock() for _ in range(5)]
        receiver.thread, receiver.error = Mock(ident=None), None
        receiver.thread.is_alive.return_value = False
        receiver.context.ok.return_value = True
        self.assertEqual(receiver.finish(), {"thread_alive": False, "error": None})
        receiver.thread.join.assert_not_called()
        receiver.node.destroy_node.assert_called_once()
        receiver.rclpy.shutdown.assert_called_once_with(context=receiver.context)

    def test_setup_failure_releases_unstarted_receiver_before_any_writer_starts(self):
        for failure in ("storage", "sampler"):
            with self.subTest(failure=failure), ExitStack() as stack:
                stack.enter_context(patch.object(observer.sys, "platform", "linux"))
                stack.enter_context(patch.object(Path, "is_file", return_value=True))
                receiver = SimpleNamespace(finish=Mock())
                stack.enter_context(patch.object(observer, "RosReceiver", return_value=receiver))
                storage = stack.enter_context(patch.object(observer, "new_storage", return_value={}))
                sampler = stack.enter_context(patch.object(observer, "ProcessSampler"))
                writer = stack.enter_context(patch.object(observer.link_observer, "BoundedWriter"))
                (storage if failure == "storage" else sampler).side_effect = ValueError("SyntheticSetupFailure")
                stack.enter_context(redirect_stderr(io.StringIO()))
                with self.assertRaises(SystemExit) as ended:
                    observer.main(["--output-dir", "/synthetic/archive", "--ros"])
                self.assertEqual(ended.exception.code, 2)
                receiver.finish.assert_called_once()
                writer.assert_not_called()

    def test_log_bound_cannot_exceed_64_mib_or_be_disabled_before_setup(self):
        with patch.object(observer.sys, "platform", "linux"), \
                patch.object(Path, "is_file", return_value=True), \
                patch.object(observer, "new_storage") as storage, redirect_stderr(io.StringIO()):
            for maximum in ("0", "65"):
                with self.subTest(maximum=maximum), self.assertRaises(SystemExit) as ended:
                    observer.main(["--output-dir", "/synthetic/archive", "--max-log-mib", maximum])
                self.assertEqual(ended.exception.code, 2)
            storage.assert_not_called()


if __name__ == "__main__":
    unittest.main()
