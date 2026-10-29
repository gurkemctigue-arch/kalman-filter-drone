"""Portable source/ELF/proc fixtures only; never launch ROS, WSL or ldd."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from uav_tracking import ros_gz_runtime as runtime

ROOT = Path(__file__).resolve().parents[1]


class FixtureBackend(runtime.RuntimeBackend):
    fixture_only = True

    def __init__(self, executable, dependencies):
        super().__init__()
        self.executable = executable
        self.dependencies = dependencies
        self.maps = [self.mapping(path) for path in [executable, *dependencies]]
        self.pid = 1234
        self.start_ticks = 987654
        self.stat_reads = 0
        self.reuse_after_first_stat = False
        self.ldd_override = None
        self.plugin_dependencies = {}
        self.git_cache = {}

    def command(self, argv, *, cwd=None):
        if argv[0] == "ldd":
            if self.ldd_override is not None:
                return self.ldd_override.encode()
            lines = ["linux-vdso.so.1 (0x00001)"]
            dependencies = self.plugin_dependencies.get(argv[1], self.dependencies)
            lines += [str(path.name) + " => " + str(path) + " (0x00002)" for path in dependencies]
            return ("\n".join(lines) + "\n").encode()
        if argv[0] != "git":
            raise AssertionError("Unexpected non-fixture probe")
        # Real tiny Git fixtures establish diff/index behavior. Cache identical
        # read-only snapshots to avoid repeatedly spawning Git's shell helper
        # on Windows; changed file/index bytes always invalidate the cache.
        repo = Path(argv[2])
        fingerprint = tuple((path.name, path.read_bytes()) for path in sorted(repo.iterdir()) if path.is_file())
        index = repo / ".git/index"
        key = (tuple(argv), fingerprint, index.read_bytes() if index.exists() else None)
        if key not in self.git_cache:
            self.git_cache[key] = super().command(argv, cwd=cwd)
        return self.git_cache[key]

    @staticmethod
    def mapping(path):
        info = runtime._regular_file(path, elf=True)
        return {"path": str(path), **{key: info[key] for key in ("device_major", "device_minor", "inode")}}

    def proc_text(self, pid, filename):
        if pid != self.pid:
            raise FileNotFoundError("Fixture PID does not exist")
        if filename == "stat":
            self.stat_reads += 1
            fields = ["0"] * 20
            fields[0:4] = ["S", "1", "1234", "1234"]
            fields[19] = str(self.start_ticks + int(self.reuse_after_first_stat and self.stat_reads > 1))
            return str(pid) + " (parameter_bridge) " + " ".join(fields)
        if filename != "maps":
            raise AssertionError("Unexpected proc file")
        rows = []
        for index, item in enumerate(self.maps):
            path = item["path"].replace("\\", "\\134").replace(" ", "\\040")
            rows.append(f'{index+1:08x}-{index+2:08x} r-xp 00000000 '
                        f'{item["device_major"]:x}:{item["device_minor"]:x} {item["inode"]} {path}')
        return "\n".join(rows) + "\n"

    def exe_path(self, pid):
        return str(self.executable)

    def exe_file(self, pid):
        return self.executable

    def namespace_file(self, pid, path):
        return Path(path)


class RosGzRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ros_gz_runtime_fixture_", dir=ROOT)
        self.directory = Path(self.temporary.name).resolve()
        self.overlay = self.directory / "new overlay"
        self.repo = self.overlay / "src/ros_gz"
        self.repo.mkdir(parents=True)
        self.source = self.repo / "bridge.cc"
        self.source.write_text("int main() { return 0; }\n", encoding="utf-8")
        self.git("init", "--quiet")
        self.git("add", "bridge.cc")
        self.git("-c", "user.name=Runtime fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "--quiet", "-m", "Fixture source")
        self.executable = self.overlay / "install/ros_gz_bridge/lib/ros_gz_bridge/parameter_bridge"
        self.bridge = self.overlay / "install/ros_gz_bridge/lib/libros_gz_bridge.so"
        self.interface = self.overlay / "install/ros_gz_interfaces/lib/libros_gz_interfaces__rosidl_typesupport_cpp.so"
        self.system = self.directory / "system/libzmq.so.5"
        for path in (self.executable, self.bridge, self.interface, self.system):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"\x7fELF\x02\x01\x01\0" + path.name.encode() + b"\0" * 64)
        self.backend = FixtureBackend(self.executable, [self.bridge, self.interface, self.system])
        self.patch = self.directory / "reviewed.patch"

    def tearDown(self):
        self.temporary.cleanup()

    def git(self, *arguments):
        result = subprocess.run(["git", "-C", str(self.repo), *arguments], capture_output=True, check=True)
        return result.stdout

    def register(self, **kwargs):
        return runtime.create_registration(self.overlay, self.repo, backend=self.backend, **kwargs)

    def verify_live(self, value, **kwargs):
        return runtime.verify_live_process(value, self.backend.pid,
            expected_start_ticks=self.backend.start_ticks, backend=self.backend, **kwargs)

    def test_candidate_fixture_explicitly_locks_source_and_dependency_closure(self):
        value = self.register()
        self.assertTrue(value["fixture_only"])
        self.assertEqual(value["evidence_scope"], "ORCHESTRATION_FIXTURE_ONLY")
        self.assertEqual(value["source"]["commit"], self.git("rev-parse", "HEAD").decode().strip())
        self.assertEqual(value["source"]["tracked_diff_bytes"], 0)
        self.assertEqual(len(value["dependencies"]), 3)
        self.assertEqual(runtime.verify_registration(value, backend=self.backend)["status"], "PASS")
        report = self.verify_live(value)
        self.assertEqual(report["mapped_elf_count"], 4)
        self.assertEqual(report["process"]["start_ticks"], self.backend.start_ticks)
        self.assertTrue(report["fixture_only"])

    def test_dirty_source_requires_explicit_patch_and_locks_both_diff_and_patch(self):
        self.source.write_text("int main() { return 1; }\n", encoding="utf-8")
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, "explicit reviewed patch"):
            self.register()
        self.patch.write_bytes(self.git("diff", "--binary", "HEAD", "--"))
        value = self.register(patch_path=self.patch)
        self.assertGreater(value["source"]["tracked_diff_bytes"], 0)
        self.assertEqual(value["source"]["tracked_diff_sha256"], value["patch"]["sha256"])
        self.patch.write_bytes(self.patch.read_bytes() + b"\nchanged review")
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, "Registered file changed: patch"):
            runtime.verify_registration(value, backend=self.backend)

    def test_post_registration_working_tree_change_is_rejected(self):
        value = self.register()
        self.source.write_text("int main() { return 2; }\n", encoding="utf-8")
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, "explicit reviewed patch|source.*changed"):
            runtime.verify_registration(value, backend=self.backend)

    def test_identical_patch_can_move_to_frozen_copy_without_reading_original(self):
        self.source.write_text("int main() { return 1; }\n", encoding="utf-8")
        self.patch.write_bytes(self.git("diff", "--binary", "HEAD", "--"))
        value = self.register(patch_path=self.patch)
        frozen = self.directory / "frozen_copy.patch"
        frozen.write_bytes(self.patch.read_bytes())
        self.patch.unlink()
        report = runtime.verify_registration(value, patch_path=frozen, backend=self.backend)
        self.assertEqual(report["patch_verified_path"], str(frozen.resolve()))
        frozen.write_bytes(frozen.read_bytes() + b"wrong")
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, "Registered file changed: patch"):
            runtime.verify_registration(value, patch_path=frozen, backend=self.backend)

    def test_changed_dependency_or_ldd_resolution_is_rejected(self):
        value = self.register()
        self.system.write_bytes(self.system.read_bytes() + b"modified")
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, "dependency paths or ELF bytes changed"):
            runtime.verify_registration(value, backend=self.backend)

    def test_changed_executable_is_rejected(self):
        value = self.register()
        self.executable.write_bytes(self.executable.read_bytes() + b"modified")
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, "Registered file changed: executable"):
            runtime.verify_registration(value, backend=self.backend)

    def test_fixture_cannot_be_presented_as_production_registration(self):
        value = self.register()
        production = FixtureBackend(self.executable, self.backend.dependencies)
        production.fixture_only = False
        with mock.patch.object(runtime.platform, "system", return_value="Linux"):
            with self.assertRaisesRegex(runtime.RuntimeRegistrationError, "Fixture evidence"):
                runtime.verify_registration(value, backend=production)

    def test_production_probes_reject_nonlinux_before_running_commands(self):
        with mock.patch.object(runtime.platform, "system", return_value="Windows"):
            with self.assertRaisesRegex(runtime.RuntimeRegistrationError, "require Linux"):
                runtime.create_registration(self.overlay, self.repo)

    def test_wrong_commit_untracked_source_or_hidden_index_cannot_register(self):
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, "expected commit"):
            self.register(expected_commit="0" * 40)
        untracked = self.repo / "unreviewed.cc"
        untracked.write_text("bad", encoding="utf-8")
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, "Untracked source"):
            self.register()
        untracked.unlink()
        self.git("update-index", "--assume-unchanged", "bridge.cc")
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, "hidden, skipped"):
            self.register()

    def test_old_ros_gz_dependency_rejected_during_registration(self):
        old = self.directory / "old_overlay/libros_gz_bridge.so"
        old.parent.mkdir()
        old.write_bytes(self.bridge.read_bytes())
        self.backend.dependencies[0] = old
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, "Old or mixed ros_gz"):
            self.register()

    def test_explicitly_registered_interfaces_underlay_is_allowed_but_cannot_drift(self):
        underlay = self.directory / "original underlay/libros_gz_interfaces__rosidl_typesupport_cpp.so"
        underlay.parent.mkdir()
        underlay.write_bytes(self.interface.read_bytes())
        self.backend.dependencies[1] = underlay
        self.backend.maps[2] = self.backend.mapping(underlay)
        value = self.register()
        self.assertEqual(self.verify_live(value)["status"], "PASS")
        underlay.write_bytes(underlay.read_bytes() + b"changed")
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, "dependency paths or ELF bytes changed"):
            runtime.verify_registration(value, backend=self.backend)

    def test_missing_ldd_library_is_rejected(self):
        self.backend.ldd_override = "libros_gz_bridge.so => not found\n"
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, "Unresolved"):
            self.register()

    def test_explicit_dlopen_plugin_and_its_dependency_union_must_be_mapped_and_unchanged(self):
        plugin = self.interface.with_name('libros_gz_interfaces__rosidl_typesupport_fastrtps_cpp.so')
        plugin.write_bytes(b'\x7fELFplugin')
        extra = self.system.with_name('libplugin_support.so')
        extra.write_bytes(b'\x7fELFextra')
        self.backend.plugin_dependencies[str(plugin)] = [self.interface, self.system, extra]
        value = self.register(plugin_elf_paths=[plugin])
        self.assertEqual(len(value['plugins']), 1)
        self.assertEqual(len(value['dependencies']), 4)
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, 'missing from live maps'):
            self.verify_live(value)
        self.backend.maps.extend([self.backend.mapping(plugin), self.backend.mapping(extra)])
        self.assertEqual(self.verify_live(value)['mapped_elf_count'], 6)
        plugin.write_bytes(plugin.read_bytes() + b'changed')
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, 'plugin paths or ELF bytes changed'):
            runtime.verify_registration(value, backend=self.backend)

    def test_unregistered_dlopen_plugin_and_old_bridge_plugin_are_rejected(self):
        value = self.register()
        plugin = self.interface.with_name('libros_gz_interfaces__rosidl_typesupport_fastrtps_cpp.so')
        plugin.write_bytes(b'\x7fELFplugin')
        self.backend.maps.append(self.backend.mapping(plugin))
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, 'Unregistered/old ros_gz ELF'):
            self.verify_live(value)
        old = self.directory / 'old/libros_gz_bridge.so'
        old.parent.mkdir()
        old.write_bytes(self.bridge.read_bytes())
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, 'Old bridge cannot be declared'):
            self.register(plugin_elf_paths=[old])

    def test_unknown_old_ros_gz_mapping_rejected_even_when_all_expected_files_match(self):
        value = self.register()
        old = self.directory / "old_overlay/libros_gz_bridge.so"
        old.parent.mkdir()
        old.write_bytes(self.bridge.read_bytes())
        self.backend.maps.append(self.backend.mapping(old))
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, "Unregistered/old ros_gz"):
            self.verify_live(value)

    def test_deleted_or_wrong_inode_mapping_is_rejected(self):
        value = self.register()
        self.backend.maps[1]["path"] += " (deleted)"
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, "mapped ELF is deleted"):
            self.verify_live(value)
        self.backend.maps[1]["path"] = str(self.bridge)
        self.backend.maps[1]["inode"] += 1
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, "device/inode"):
            self.verify_live(value)

    def test_missing_dependency_map_is_rejected(self):
        value = self.register()
        self.backend.maps.pop()
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, "missing from live maps"):
            self.verify_live(value)

    def test_wrong_executable_and_pid_reuse_are_rejected(self):
        value = self.register()
        old = self.directory / "old_parameter_bridge"
        old.write_bytes(self.executable.read_bytes())
        self.backend.executable = old
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, "not the registered overlay"):
            self.verify_live(value)
        self.backend.executable = self.executable
        self.backend.reuse_after_first_stat = True
        self.backend.stat_reads = 0
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, "identity changed during"):
            self.verify_live(value)

    def test_expected_launch_identity_and_registration_digest_are_checked(self):
        value = self.register()
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, "creation identity differs"):
            runtime.verify_live_process(value, self.backend.pid,
                expected_start_ticks=self.backend.start_ticks + 1, backend=self.backend)
        altered = deepcopy(value)
        altered["overlay_root"] = str(self.directory)
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, "digest is invalid"):
            runtime.verify_registration(altered, backend=self.backend)

    def test_non_elf_and_duplicate_install_layout_are_rejected(self):
        self.executable.write_bytes(b"not ELF")
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, "Expected ELF"):
            self.register()

        self.executable.write_bytes(b"\x7fELFfixture")
        second = self.overlay / "install/lib/ros_gz_bridge/parameter_bridge"
        second.parent.mkdir(parents=True)
        second.write_bytes(self.executable.read_bytes())
        with self.assertRaisesRegex(runtime.RuntimeRegistrationError, "exactly one isolated/merged"):
            self.register()

    def test_one_gib_resource_limit_rejects_oversize_metadata_without_large_fixture(self):
        self.assertEqual(runtime.MAX_ELF_BYTES, 1024 ** 3)
        metadata = mock.Mock(st_mode=self.executable.stat().st_mode, st_size=1024 ** 3 + 1)
        with mock.patch.object(runtime.os, "fstat", return_value=metadata):
            with self.assertRaisesRegex(runtime.RuntimeRegistrationError, "bounded regular file"):
                runtime._regular_file(self.executable, elf=True)

    def test_maps_and_ldd_parse_spaces_and_loader_without_launching_anything(self):
        rows = runtime.parse_ldd("linux-vdso.so.1 (0x123)\n" + str(self.system) + " (0xabc)\n")
        self.assertEqual(rows[0]["path"], str(self.system))
        parsed = runtime.parse_maps(self.backend.proc_text(self.backend.pid, "maps"))
        self.assertEqual(parsed[0]["path"], str(self.executable))
        with self.assertRaises(runtime.RuntimeRegistrationError):
            runtime.parse_maps("malformed")

    def test_cli_help_and_review_file_sha_mismatch_are_portable(self):
        script = ROOT / "scripts/ros_gz_runtime.py"
        command = [sys.executable, str(script)]
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        help_result = subprocess.run([*command, "--help"], capture_output=True, text=True, creationflags=flags)
        self.assertEqual(help_result.returncode, 0)
        registration = self.directory / "candidate.json"
        registration.write_text(json.dumps(self.register()), encoding="utf-8")
        result = subprocess.run([*command, "verify", "--registration", str(registration),
            "--expected-registration-sha256", "0" * 64], capture_output=True, text=True, creationflags=flags)
        self.assertEqual(result.returncode, 2)
        self.assertIn("independently reviewed SHA", result.stderr)


if __name__ == "__main__":
    unittest.main()
