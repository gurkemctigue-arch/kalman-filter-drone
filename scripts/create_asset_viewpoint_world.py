"""Generate an isolated rendered-view experiment, never runtime observations."""

import argparse
import math
from pathlib import Path
import xml.etree.ElementTree as ET


def add(parent, tag, text=None, **attributes):
    node = ET.SubElement(parent, tag, attributes)
    if text is not None:
        node.text = str(text)
    return node


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    sdf = ET.Element("sdf", version="1.10")
    world = add(sdf, "world", name="asset_viewpoints")
    add(world, "gravity", "0 0 -9.81")
    physics = add(world, "physics", name="default", type="ignored")
    add(physics, "max_step_size", .004)
    add(physics, "real_time_factor", 1)
    for library, system in (("physics", "Physics"), ("user-commands", "UserCommands"), ("scene-broadcaster", "SceneBroadcaster"), ("sensors", "Sensors")):
        plugin = add(world, "plugin", filename=f"gz-sim-{library}-system", name=f"gz::sim::systems::{system}")
        if system == "Sensors":
            add(plugin, "render_engine", "ogre2")
    scene = add(world, "scene")
    add(scene, "ambient", "0.6 0.6 0.6 1")
    add(scene, "background", "0.65 0.75 0.9 1")
    add(scene, "shadows", "true")
    sun = add(world, "light", name="sun", type="directional")
    add(sun, "pose", "0 0 10 0 0 0")
    add(sun, "direction", "-0.3 0.2 -1")
    add(sun, "diffuse", "0.9 0.9 0.9 1")
    add(sun, "specular", "0.1 0.1 0.1 1")
    ground = add(world, "model", name="ground")
    add(ground, "static", "true")
    link = add(ground, "link", name="link")
    visual = add(link, "visual", name="ground")
    plane = add(add(visual, "geometry"), "plane")
    add(plane, "normal", "0 0 1")
    add(plane, "size", "1000 1000")
    material = add(visual, "material")
    add(material, "ambient", "0.32 0.36 0.29 1")
    add(material, "diffuse", "0.45 0.48 0.38 1")
    views = [(distance, yaw) for distance in (5, 9) for yaw in (0, math.pi / 4, math.pi / 2, 3 * math.pi / 4, math.pi, 5 * math.pi / 4, 3 * math.pi / 2, 7 * math.pi / 4)]
    for index, (distance, yaw) in enumerate(views):
        lane = index * 40
        camera_model = add(world, "model", name=f"camera_{index}")
        add(camera_model, "static", "true")
        # Same camera projection/mount pitch as x500_stage1 after takeoff.
        add(camera_model, "pose", f"0 {lane} 3.0 0 .35 0")
        sensor = add(add(camera_model, "link", name="link"), "sensor", name="rgbd", type="rgbd_camera")
        add(sensor, "always_on", "true")
        add(sensor, "update_rate", 3)
        add(sensor, "topic", f"/asset/view{index}")
        camera = add(sensor, "camera")
        add(camera, "horizontal_fov", 1.204)
        image = add(camera, "image")
        add(image, "width", 640)
        add(image, "height", 480)
        add(image, "format", "R8G8B8")
        clip = add(camera, "clip")
        add(clip, "near", .1)
        add(clip, "far", 30)
        add(camera, "optical_frame_id", "camera_link")
        target = add(world, "model", name=f"car_{index}")
        add(target, "static", "true")
        add(target, "pose", f"{distance} {lane} 0 0 0 {yaw}")
        visual = add(add(target, "link", name="link"), "visual", name="car")
        add(visual, "pose", f"0 0 .02 0 0 {math.pi / 2}")
        mesh = add(add(visual, "geometry"), "mesh")
        add(mesh, "uri", "model://fuel_prius_hybrid/meshes/Hybrid.obj")
        add(mesh, "scale", ".01 .01 .01")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(sdf)
    ET.ElementTree(sdf).write(args.output, encoding="utf-8", xml_declaration=True)
    print(" ".join(f"view{index}=/asset/view{index}/image" for index in range(len(views))))


if __name__ == "__main__":
    main()
