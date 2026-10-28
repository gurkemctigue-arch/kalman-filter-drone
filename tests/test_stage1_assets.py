"""Static checks for the installable stage-one Gazebo asset contract."""

from pathlib import Path
import math
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
BRINGUP = ROOT / "ros2_ws" / "src" / "uav_tracking_bringup"
ROOT_LAUNCH = ROOT / "launch" / "tracking_sim.launch.py"


class Stage1AssetTests(unittest.TestCase):
    def test_static_tf_declares_optical_camera_orientation(self) -> None:
        launch_source = (BRINGUP / "launch" / "tracking_sim.launch.py").read_text(encoding="utf-8")
        # The detector's pinhole point is REP-103 optical (right/down/forward)
        # and must not be transformed as if camera_link were FLU body axes.
        self.assertIn('"-0.54291564"', launch_source)
        self.assertIn('"0.54291564"', launch_source)
        self.assertIn('"camera_link",', launch_source)
        self.assertNotIn('"0", "0.18", "0", "map", "camera_link"', launch_source)
        root_source = ROOT_LAUNCH.read_text(encoding="utf-8")
        self.assertIn('"-0.54291564"', root_source)
        self.assertIn('"start_px4_adapter"', root_source)
        self.assertNotIn('executable="gz_sim"', root_source)

    def test_each_world_has_one_target_and_one_rgbd_sensor(self) -> None:
        worlds = sorted((BRINGUP / "worlds").glob("stage1_single_*.sdf"))
        self.assertEqual({path.stem for path in worlds}, {"stage1_single_target", "stage1_single_car"})
        for path in worlds:
            root = ET.parse(path).getroot()
            world = root.find("world")
            self.assertIsNotNone(world)
            target_includes = [
                include for include in world.findall("include")
                if include.findtext("name", "").startswith("target_")
            ]
            self.assertEqual(len(target_includes), 1, path.name)
            self.assertEqual(target_includes[0].findtext("uri", "").split("model://")[-1], target_includes[0].findtext("name"), path.name)
            sensors = world.findall(".//sensor[@type='rgbd_camera']")
            self.assertEqual(len(sensors), 1, path.name)
            self.assertEqual(sensors[0].findtext("topic"), "/camera/rgbd")
            self.assertEqual(sensors[0].findtext("camera/optical_frame_id"), "camera_link")
            self.assertIsNotNone(sensors[0].find("camera/depth_camera/clip"))
            self.assertEqual(sensors[0].findtext("camera/depth_camera/output"), "depths")
            self.assertIsNotNone(world.find("plugin[@name='gz::sim::systems::SceneBroadcaster']"))
            model_name = "target_person" if path.stem.endswith("target") else "target_car"
            model = ET.parse(BRINGUP / "models" / model_name / "model.sdf").getroot()
            pose_plugin = model.find(".//plugin[@name='gz::sim::systems::PosePublisher']")
            self.assertIsNotNone(pose_plugin, model_name)
            self.assertEqual(pose_plugin.findtext("topic"), "/ground_truth/poses")

    def test_target_initial_poses_visible_and_scenario_motion_is_explicit(self) -> None:
        """Sensor worlds start in view and never move without scenario input."""

        horizontal_half_fov = 1.04719755 / 2.0
        vertical_half_fov = math.atan(math.tan(horizontal_half_fov) * 480.0 / 640.0)
        camera_pitch = 0.18
        camera_z = 3.0
        model_specs = {
            "stage1_single_target.sdf": ("target_person", (0.0, 1.94)),
            "stage1_single_car.sdf": ("target_car", (0.0, 1.55)),
        }
        for world_name, (model_name, target_z_bounds) in model_specs.items():
            world = ET.parse(BRINGUP / "worlds" / world_name).getroot().find("world")
            self.assertIsNotNone(world)
            include = next(
                include for include in world.findall("include")
                if include.findtext("name") == model_name
            )
            model = ET.parse(BRINGUP / "models" / model_name / "model.sdf").getroot()
            self.assertIsNone(model.find(".//plugin[@name='gz::sim::systems::TrajectoryFollower']"))
            motion = model.find(".//plugin[@name='gz::sim::systems::VelocityControl']")
            self.assertIsNotNone(motion)
            self.assertEqual(motion.findtext("topic"), "/scenario/target/cmd_vel")
            self.assertEqual(motion.findtext("initial_linear"), "0 0 0")
            x, y = (float(value) for value in include.findtext("pose").split()[:2])
            self.assertGreater(x, 0.1, model_name)
            self.assertLess(abs(math.atan2(y, x)), horizontal_half_fov, model_name)
            for target_z in target_z_bounds:
                vertical_angle = math.atan2(camera_z - target_z, x)
                self.assertLess(abs(vertical_angle - camera_pitch), vertical_half_fov, model_name)
            bridge_name = "stage1_car_bridge.yaml" if model_name == "target_car" else "stage1_bridge.yaml"
            bridge = (BRINGUP / "config" / bridge_name).read_text(encoding="utf-8")
            self.assertIn('gz_topic_name: "/ground_truth/poses"', bridge)

    def test_local_meshes_and_bridge_topics_are_present(self) -> None:
        for category in ("target_person", "target_car"):
            mesh = BRINGUP / "models" / category / "meshes" / f"{category}.dae"
            self.assertTrue(mesh.is_file())
            ET.parse(mesh)
        person_model = ET.parse(BRINGUP / "models" / "target_person" / "model.sdf").getroot()
        self.assertEqual(
            person_model.findtext(".//visual/geometry/mesh/uri"),
            "model://fuel_walking_person/meshes/walking.dae",
        )
        mesh = BRINGUP / "models" / "fuel_walking_person" / "meshes" / "walking.dae"
        mesh_root = ET.parse(mesh).getroot()
        ns = {"c": "http://www.collada.org/2005/11/COLLADASchema"}
        images = mesh_root.findall("c:library_images/c:image/c:init_from", ns)
        self.assertGreaterEqual(len(images), 5)
        for image in images:
            self.assertTrue((mesh.parent / image.text).is_file(), image.text)
        car_model = ET.parse(BRINGUP / "models" / "target_car" / "model.sdf").getroot()
        self.assertEqual(
            car_model.findtext(".//visual/geometry/mesh/uri"),
            "model://fuel_prius_hybrid/meshes/Hybrid.obj",
        )
        car_mesh = BRINGUP / "models" / "fuel_prius_hybrid" / "meshes" / "Hybrid.obj"
        self.assertTrue(car_mesh.is_file())
        material = car_mesh.with_suffix(".mtl")
        self.assertTrue(material.is_file())
        texture_lines = [line.split(maxsplit=1)[1] for line in material.read_text().splitlines() if line.lstrip().startswith("map_Kd ")]
        self.assertGreaterEqual(len(texture_lines), 2)
        for texture in texture_lines:
            self.assertTrue((material.parent / texture).is_file(), texture)
        for bridge in ("stage1_bridge.yaml", "stage1_car_bridge.yaml"):
            text = (BRINGUP / "config" / bridge).read_text(encoding="utf-8")
            self.assertIn("/camera/color/image_raw", text)
            self.assertIn("/camera/aligned_depth_to_color/image_raw", text)
            self.assertIn("/camera/color/camera_info", text)
            self.assertIn("/ground_truth/poses", text)
            self.assertEqual(text.count("ros_topic_name:"), 5)
            self.assertEqual(text.count("direction: GZ_TO_ROS"), 5)
            self.assertIn('gz_type_name: "gz.msgs.Image"', text)
            self.assertIn('ros_type_name: "tf2_msgs/msg/TFMessage"', text)
        for params in ("stage1_tracking_person.yaml", "stage1_tracking_car.yaml"):
            text = (BRINGUP / "config" / params).read_text(encoding="utf-8")
            self.assertIn("depth_scale: 1.0", text)
            self.assertIn("use_sim_time: true", text)

    def test_runtime_assets_do_not_reference_gazebo_ids(self) -> None:
        for path in (BRINGUP / "worlds").glob("*.sdf"):
            text = path.read_text(encoding="utf-8").lower()
            self.assertNotIn("actor_id", text)
            self.assertNotIn("entity_id", text)


if __name__ == "__main__":
    unittest.main()
