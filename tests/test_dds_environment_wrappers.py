"""Exercise real runtime wrappers with fixture ROS setup and fake endpoints.

The project setup genuinely prepends its library directory. The production DDS
shell helper runs unchanged; its CLI reads a small fixture registration instead
of hashing native ELFs. No ROS node, simulator, Agent or test suite is started.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
WRAPPERS = {
    "ros_python.sh": ["sentinel.py", "--fixture"],
    "run_stage1_trial.sh": ["--fixture"],
    "research_env.sh": ["sentinel.py", "--fixture"],
    "evaluate_stage1_flight.sh": ["--fixture"],
    "verify_stage1.sh": [],
    "run_stage1_flight.sh": ["agent", "person"],
}


@unittest.skipUnless(
    sys.platform.startswith("linux") and shutil.which("bash") and Path("/usr/bin/python3").is_file(),
    "Linux Bash wrapper fixture; no ROS or native ELF is required",
)
class DdsEnvironmentWrapperTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dds wrapper ordering ")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()
        self.project = self.directory / "project with spaces"
        self.binary = self.directory / "bin"
        self.project_lib = self.project / "ros2_ws/install/lib"
        self.agent_lib = self.directory / "agent/lib"
        self.dds_prefix = self.directory / "isolated/install"
        self.legacy_lib = self.directory / "legacy/lib"
        self.calls = self.directory / "cli_calls.jsonl"
        self.endpoints = self.directory / "endpoints.jsonl"
        self.config = self.project / "config/dds_runtime_humble22.json"
        self.bash = shutil.which("bash")
        for name in (*WRAPPERS, "source_ros_environment.sh", "apply_humble22_dds_runtime.sh"):
            self.write(self.project / "scripts" / name,
                       (ROOT / "scripts" / name).read_text(encoding="utf-8"))
        self.write(self.project / "ros2_ws/install/setup.bash", """
            export DDS_FIXTURE_SOURCE_SEQUENCE="${DDS_FIXTURE_SOURCE_SEQUENCE:-}|project"
            export LD_LIBRARY_PATH="$DDS_FIXTURE_PROJECT_LIB${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
        """)
        self.messages = self.directory / "messages"
        self.write(self.messages / "install/setup.bash", """
            export DDS_FIXTURE_SOURCE_SEQUENCE="${DDS_FIXTURE_SOURCE_SEQUENCE:-}|messages"
            export LD_LIBRARY_PATH="$DDS_FIXTURE_MESSAGES_LIB${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
        """)
        self.registration = {
            "fixture_only": True,
            "prefix": str(self.dds_prefix),
            "agent_library_directory": str(self.agent_lib),
        }
        self.write(self.config, json.dumps(self.registration))
        self.write(self.project / "scripts/dds_runtime.py", """
            import argparse, json, os, sys
            from pathlib import Path
            parser = argparse.ArgumentParser()
            parser.add_argument('action', choices=['environment'])
            parser.add_argument('--registration', required=True)
            parser.add_argument('--current-library-path', required=True)
            args = parser.parse_args()
            with Path(os.environ['DDS_FIXTURE_CALLS']).open('a') as stream:
                stream.write(json.dumps({'current': args.current_library_path,
                    'sequence': os.environ.get('DDS_FIXTURE_SOURCE_SEQUENCE', '')}) + '\\n')
            value = json.loads(Path(args.registration).read_text())
            if value.get('fixture_only') is not True or value.get('fixture_invalid'):
                print('Fixture registration rejected', file=sys.stderr)
                raise SystemExit(2)
            parts = [value['agent_library_directory'], str(Path(value['prefix']) / 'lib')]
            for part in args.current_library_path.split(':'):
                if part and part not in parts:
                    parts.append(part)
            print(':'.join(parts))
        """)
        endpoint = """#!/usr/bin/python3
import json, os, sys
from pathlib import Path
value = {'argv': sys.argv[1:], 'library_path': os.environ.get('LD_LIBRARY_PATH'),
    'rmw': os.environ.get('RMW_IMPLEMENTATION'),
    'registration': os.environ.get('UAV_TRACKING_DDS_RUNTIME_CONFIG'),
    'sequence': os.environ.get('DDS_FIXTURE_SOURCE_SEQUENCE', '')}
with Path(os.environ['DDS_FIXTURE_ENDPOINTS']).open('a') as stream:
    stream.write(json.dumps(value) + '\\n')
print(json.dumps(value))
"""
        for name in ("python3", "MicroXRCEAgent"):
            self.write(self.binary / name, endpoint, executable=True)
        self.write(self.binary / "ros2", """#!/usr/bin/python3
import os, sys
if sys.argv[1:] != ['pkg', 'prefix', 'uav_tracking_bringup']:
    raise SystemExit('Unexpected fixture ros2 invocation')
print(os.environ['DDS_FIXTURE_INSTALL'])
""", executable=True)

    @staticmethod
    def write(path, content, *, executable=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8", newline="\n")
        if executable:
            path.chmod(0o755)

    @staticmethod
    def json_lines(path):
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def invoke(self, name, *, distro="humble", preapply=False, conflicting_registration=False):
        for path in (self.calls, self.endpoints):
            path.unlink(missing_ok=True)
        environment = dict(os.environ)
        for key in ("BASH_ENV", "ENV", "UAV_TRACKING_DDS_RUNTIME_CONFIG", "RMW_IMPLEMENTATION", "STAGE1_ROS_GZ_WS"):
            environment.pop(key, None)
        environment.update(
            PATH=str(self.binary) + os.pathsep + os.environ["PATH"],
            STAGE1_PROJECT_ROOT=str(self.project), STAGE1_PX4_MSGS_WS=str(self.messages),
            STAGE1_PYTHON_EXECUTABLE=str(self.binary / "python3"),
            ROS_DISTRO=distro, STAGE1_ROS_DISTRO=distro,
            LD_LIBRARY_PATH=str(self.legacy_lib),
            DDS_FIXTURE_ROOT=str(self.project), DDS_FIXTURE_DISTRO=distro,
            DDS_FIXTURE_PROJECT_LIB=str(self.project_lib),
            DDS_FIXTURE_MESSAGES_LIB=str(self.messages / "install/lib"),
            DDS_FIXTURE_ROS_LIB=str(self.directory / "ros/lib"),
            DDS_FIXTURE_CALLS=str(self.calls), DDS_FIXTURE_ENDPOINTS=str(self.endpoints),
            DDS_FIXTURE_INSTALL=str(self.project / "ros2_ws/install"),
            DDS_FIXTURE_BASH=self.bash, DDS_FIXTURE_PREAPPLY="1" if preapply else "0",
        )
        if conflicting_registration:
            environment["UAV_TRACKING_DDS_RUNTIME_CONFIG"] = str(self.directory / "foreign.json")
        launcher = r'''
source() {
  case "$1" in
    /opt/ros/*/setup.bash)
      export ROS_DISTRO="$DDS_FIXTURE_DISTRO"
      export DDS_FIXTURE_SOURCE_SEQUENCE="${DDS_FIXTURE_SOURCE_SEQUENCE:-}|ros"
      export LD_LIBRARY_PATH="$DDS_FIXTURE_ROS_LIB${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
      ;;
    *) builtin source "$@" ;;
  esac
}
export -f source
if [[ "$DDS_FIXTURE_PREAPPLY" == 1 ]]; then
  builtin source "$DDS_FIXTURE_ROOT/scripts/apply_humble22_dds_runtime.sh" "$DDS_FIXTURE_ROOT" || exit 2
fi
exec "$DDS_FIXTURE_BASH" "$@"
'''
        result = subprocess.run(
            [self.bash, "-c", launcher, "dds-wrapper-fixture", str(self.project / "scripts" / name), *WRAPPERS[name]],
            cwd=self.directory, env=environment, capture_output=True, text=True, timeout=20,
        )
        return result, self.json_lines(self.calls), self.json_lines(self.endpoints)

    def assert_humble_endpoints(self, name, result, calls, endpoints):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(endpoints), 2 if name == "verify_stage1.sh" else 1)
        self.assertEqual(calls[-1]["current"].split(":")[0], str(self.project_lib))
        self.assertEqual(calls[-1]["sequence"].split("|")[-1], "project")
        for endpoint in endpoints:
            parts = endpoint["library_path"].split(":")
            self.assertEqual(parts[:2], [str(self.agent_lib), str(self.dds_prefix / "lib")])
            self.assertIn(str(self.project_lib), parts)
            self.assertEqual(len(parts), len(set(parts)))
            self.assertEqual(endpoint["rmw"], "rmw_fastrtps_cpp")
            self.assertEqual(endpoint["registration"], str(self.config))

    def test_humble_all_six_wrappers_apply_after_project_setup(self):
        for name in WRAPPERS:
            with self.subTest(wrapper=name):
                result, calls, endpoints = self.invoke(name)
                self.assertEqual(len(calls), 1, result.stderr)
                self.assert_humble_endpoints(name, result, calls, endpoints)

    def test_reapply_after_an_already_active_environment_restores_order_and_deduplicates(self):
        for name in WRAPPERS:
            with self.subTest(wrapper=name):
                result, calls, endpoints = self.invoke(name, preapply=True)
                self.assertEqual(len(calls), 2, result.stderr)
                self.assertNotIn("project", calls[0]["sequence"].split("|"))
                self.assert_humble_endpoints(name, result, calls, endpoints)

    def test_invalid_humble_configuration_stops_before_any_endpoint(self):
        for mode in ("invalid_payload", "conflicting_registration"):
            self.write(self.config, json.dumps({**self.registration, "fixture_invalid": mode == "invalid_payload"}))
            for name in WRAPPERS:
                with self.subTest(wrapper=name, mode=mode):
                    result, calls, endpoints = self.invoke(name, conflicting_registration=mode == "conflicting_registration")
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertEqual(endpoints, [])
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(len(calls), 1 if mode == "invalid_payload" else 0)

    def test_jazzy_keeps_its_loader_environment_without_calling_the_humble_cli(self):
        for name in WRAPPERS:
            with self.subTest(wrapper=name):
                result, calls, endpoints = self.invoke(name, distro="jazzy")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls, [])
                self.assertEqual(len(endpoints), 2 if name == "verify_stage1.sh" else 1)
                for endpoint in endpoints:
                    self.assertEqual(endpoint["library_path"].split(":")[0], str(self.project_lib))
                    self.assertNotIn(str(self.agent_lib), endpoint["library_path"].split(":"))
                    self.assertNotIn(str(self.dds_prefix / "lib"), endpoint["library_path"].split(":"))
                    self.assertIsNone(endpoint["rmw"])
                    self.assertIsNone(endpoint["registration"])


if __name__ == "__main__":
    unittest.main()
