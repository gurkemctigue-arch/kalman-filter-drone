"""Offline mount geometry must use the selected simulation's model tree."""
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("recording_camera_resource_test", ROOT / "scripts/extract_research_recording.py")
recording = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recording)
online_spec = importlib.util.spec_from_file_location("online_camera_resource_test", ROOT / "scripts/evaluate_online_state_accuracy.py")
online = importlib.util.module_from_spec(online_spec)
online_spec.loader.exec_module(online)


EXPANDED = """<sdf><model name="x500_stage1">
<link name="base_link"><pose>0 0 .24 0 0 0</pose></link>
<link name="tracking_camera_mount"><pose relative_to="base_link">.13233 0 .26078 0 .35 0</pose></link>
</model></sdf>"""


class RecordingCameraResourceTests(unittest.TestCase):
    def make_models(self, root, px4):
        project = root / "ros2_ws/src/uav_tracking_bringup/models"
        external = px4 / "Tools/simulation/gz/models"
        sources = {
            project / "x500_stage1/model.sdf": '<sdf><model><include><uri>model://x500</uri></include></model></sdf>',
            external / "x500/model.sdf": '<sdf><model><include><uri>model://x500_base</uri></include></model></sdf>',
            external / "x500_base/model.sdf": '<sdf><model><link name="base_link"/></model></sdf>',
        }
        for path, content in sources.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        return project, external, sources

    def test_explicit_tree_and_inherited_model_sources_are_bound_to_mount(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, px4 = Path(temporary) / "project", Path(temporary) / "isolated-px4"
            project, external, sources = self.make_models(root, px4)
            with patch.dict(os.environ, {"STAGE1_PX4_ROOT": str(px4), "GZ_SIM_RESOURCE_PATH": "unrelated-models"}), \
                    patch.object(recording.subprocess, "run", return_value=SimpleNamespace(stdout=EXPANDED)) as run:
                position, _, evidence = recording.model_camera_mount(root)
            self.assertAlmostEqual(position[0], .13233)
            self.assertAlmostEqual(position[2], .50078)
            expected = os.pathsep.join((str(project), str(external)))
            self.assertEqual(run.call_args.kwargs["env"]["GZ_SIM_RESOURCE_PATH"], expected)
            self.assertEqual(run.call_args.kwargs["env"]["SDF_PATH"], expected)
            self.assertEqual(evidence["px4_model_resource_selection"], "STAGE1_PX4_ROOT")
            self.assertEqual(evidence["resolved_model_sdf_sha256"], {
                str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources})

    def test_missing_explicit_model_does_not_fall_back_to_another_installation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, px4 = Path(temporary) / "project", Path(temporary) / "isolated-px4"
            _, _, sources = self.make_models(root, px4)
            next(path for path in sources if path.parent.name == "x500_base").unlink()
            with patch.dict(os.environ, {"STAGE1_PX4_ROOT": str(px4)}), \
                    patch.object(recording.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "absent from declared resources"):
                    recording.model_camera_mount(root)
            run.assert_not_called()

    def test_unset_override_retains_the_historical_default(self):
        with patch.dict(os.environ, {}, clear=True):
            resources, selection = recording.camera_model_resources(Path("project"))
        self.assertEqual(resources[1], Path("/root/PX4-Autopilot/Tools/simulation/gz/models"))
        self.assertEqual(selection, "historical_default")

    def test_ego_body_mount_uses_the_same_explicit_resource_and_source_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, px4 = Path(temporary) / "project", Path(temporary) / "isolated-px4"
            project, external, sources = self.make_models(root, px4)
            with patch.dict(os.environ, {"STAGE1_PX4_ROOT": str(px4)}), \
                    patch.object(online, "ROOT", root), \
                    patch.object(online.subprocess, "run", return_value=SimpleNamespace(stdout=EXPANDED)) as run:
                position, _, evidence = online.body_frame_mount(project / "x500_stage1/model.sdf")
            self.assertEqual(position.tolist(), [0.0, 0.0, .24])
            self.assertEqual(run.call_args.kwargs["env"]["SDF_PATH"],
                             os.pathsep.join((str(project), str(external))))
            self.assertEqual(evidence["px4_model_resource_selection"], "STAGE1_PX4_ROOT")
            self.assertEqual(evidence["resolved_model_sdf_sha256"], {
                str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources})


if __name__ == "__main__":
    unittest.main()
