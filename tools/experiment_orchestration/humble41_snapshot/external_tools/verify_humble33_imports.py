"""Check generated module origins, ament prefixes and real CDR round trip."""
import importlib
import json
from pathlib import Path
import subprocess
import hashlib
import os
from humble33_review_guard import ROOT, require_review, require_frozen_sources, require_bridge_runtime

review = require_review('build')
if (os.environ.get('HUMBLE22_ROS_GZ_WS') != review['bridge_overlay_root']
        or os.environ.get('STAGE1_ROS_GZ_WS') != review['bridge_overlay_root']):
    raise ValueError('Selected ros_gz runtime does not match the independently reviewed overlay')
bridge_prefix = Path(subprocess.check_output(['ros2', 'pkg', 'prefix', 'ros_gz_bridge'], text=True).strip()).resolve(strict=True)
if bridge_prefix != (Path(review['bridge_overlay_root']) / 'install').resolve(strict=True):
    raise ValueError('Actual ros_gz_bridge ament prefix fell back to another underlay')
bridge_validation = require_bridge_runtime(review, ROOT)
modules = {}
for name in ('uav_tracking.core', 'uav_tracking.core.target_manager', 'uav_tracking_nodes.stage2_telemetry',
             'uav_tracking_nodes', 'uav_tracking_nodes.detector_node', 'uav_tracking_nodes.inference_timing',
             'uav_tracking_nodes.inference_worker', 'uav_tracking_interfaces.msg',
             'uav_tracking_interfaces.msg._target_observation_array', 'uav_tracking_interfaces.msg._target_state',
             'uav_tracking_interfaces.msg._target_observation', 'uav_tracking_interfaces.msg._navigation_overlap'):
    location = Path(importlib.import_module(name).__file__).resolve(strict=True)
    if not location.is_relative_to(ROOT):
        raise ValueError('Frozen32 import escaped: '+name)
    modules[name] = str(location)
prefixes = {}
for name in ('uav_tracking_nodes', 'uav_tracking_interfaces', 'uav_tracking_bringup', 'uav_tracking_px4_adapter'):
    prefix = Path(subprocess.check_output(['ros2', 'pkg', 'prefix', name], text=True).strip()).resolve(strict=True)
    if not prefix.is_relative_to(ROOT):
        raise ValueError('Frozen32 ament prefix escaped: '+name)
    prefixes[name] = str(prefix)
with (ROOT / 'results/freeze_validation/import_isolation.json').open('x') as stream:
    json.dump({'root': str(ROOT), 'module_files': modules, 'ros_package_prefixes': prefixes,
               'module_count': len(modules), 'ament_package_count': len(prefixes), 'isolated': True,
               'bridge_package_prefix': str(bridge_prefix), 'selected_bridge_overlay': review['bridge_overlay_root'],
               'bridge_runtime_validation': bridge_validation}, stream, indent=2)
    stream.write('\n')

# This runs once after the actual build, in the same sourced Python process.
# Real generated setters and CDR type support expose IDL/wire errors which a
# SimpleNamespace unit fixture cannot observe. No node or simulator is made.
from rclpy.serialization import serialize_message, deserialize_message
from uav_tracking_interfaces.msg import NavigationOverlap, TargetObservation, TargetObservationArray

normal = NavigationOverlap()
normal.candidate_a_id, normal.candidate_b_id = 7, 8
normal.class_a_id, normal.class_b_id = 2, 0
normal.bbox_a_px, normal.bbox_b_px = [10., 10., 20., 20.], [12., 13., 14., 14.]
normal.u0, normal.v0, normal.width, normal.height = 12, 13, 2, 1
normal.expected_pixel_count, normal.valid_pixel_count = 2, 2
normal.rectangle_representable, normal.depth_complete = True, True
normal.points_camera_m = [.125, -.25, 5., .25, -.25, 5.]
incomplete = NavigationOverlap()
incomplete.candidate_a_id, incomplete.candidate_b_id = 7, 9
incomplete.class_a_id, incomplete.class_b_id = 2, 3
incomplete.bbox_a_px, incomplete.bbox_b_px = [-3e9, 5., 5., 12.], [-3e9, 7., 10., 14.]
incomplete.u0, incomplete.v0 = -3, 7
incomplete.width = incomplete.height = 0
incomplete.expected_pixel_count = incomplete.valid_pixel_count = 0
incomplete.rectangle_representable, incomplete.depth_complete = False, False
incomplete.points_camera_m = []
observation = TargetObservation()
observation.candidate_id, observation.class_id = 7, 2
observation.class_name, observation.camera_frame = 'car', 'camera_link'
observation.depth_valid, observation.depth_m = True, 5.
observation.navigation_bbox_inside_image = True
observation.navigation_bbox_complete = False
observation.navigation_overlap_count = 2
observation.navigation_points_camera_m = [.125, -.25, 5., .25, -.25, 5.]
observation.navigation_visibility_support_camera_m = [.5, -.25, 5.]
frame = TargetObservationArray()
frame.header.stamp.sec, frame.header.stamp.nanosec = 12, 345678901
frame.header.frame_id = 'camera_link'
observation.header = frame.header
frame.observations = [observation]
frame.navigation_overlaps = [normal, incomplete]
frame.navigation_ground_points_camera_m = [1., 2., 3.]
wire = serialize_message(frame)
decoded = deserialize_message(wire, TargetObservationArray)
selected, = decoded.observations
complete, unknown = decoded.navigation_overlaps
checks = {
    'same_acquisition_header': decoded.header == frame.header and selected.header == decoded.header,
    'new_observation_flags_and_count': selected.navigation_bbox_inside_image is True
        and selected.navigation_bbox_complete is False and selected.navigation_overlap_count == 2,
    'original_full_cloud_preserved': list(selected.navigation_points_camera_m) == list(observation.navigation_points_camera_m),
    'exclusive_cloud_preserved_separately': list(selected.navigation_visibility_support_camera_m)
        == list(observation.navigation_visibility_support_camera_m)
        and len(selected.navigation_points_camera_m) != len(selected.navigation_visibility_support_camera_m),
    'pair_candidate_and_class_ids': (complete.candidate_a_id, complete.candidate_b_id,
        complete.class_a_id, complete.class_b_id) == (7, 8, 2, 0)
        and (unknown.candidate_a_id, unknown.candidate_b_id, unknown.class_a_id, unknown.class_b_id) == (7, 9, 2, 3),
    'complete_rectangle_and_counts': (complete.u0, complete.v0, complete.width, complete.height,
        complete.expected_pixel_count, complete.valid_pixel_count) == (12, 13, 2, 1, 2, 2)
        and complete.rectangle_representable is True and complete.depth_complete is True,
    'complete_float32_points': list(complete.points_camera_m) == list(normal.points_camera_m)
        and len(complete.points_camera_m) == complete.expected_pixel_count * 3,
    'signed_origin_and_incomplete_wire_fields': unknown.u0 == -3 and unknown.v0 == 7
        and unknown.rectangle_representable is False and unknown.depth_complete is False
        and unknown.width == unknown.height == unknown.expected_pixel_count == unknown.valid_pixel_count == 0
        and not unknown.points_camera_m,
    'raw_bbox_fields': list(complete.bbox_a_px) == list(normal.bbox_a_px)
        and list(complete.bbox_b_px) == list(normal.bbox_b_px)
        and list(unknown.bbox_a_px) == list(incomplete.bbox_a_px)
        and list(unknown.bbox_b_px) == list(incomplete.bbox_b_px),
    'ground_support_preserved': list(decoded.navigation_ground_points_camera_m) == [1., 2., 3.],
    'pair_count_matches_observation': len(decoded.navigation_overlaps) == selected.navigation_overlap_count,
}
source_binding = require_frozen_sources(review)
receipt = {'scope': 'ACTUAL_BUILT_ROS_MESSAGE_SERIALIZATION_ONLY_NO_NODE_NO_SIMULATION',
           'status': 'PASS' if all(checks.values()) else 'FAIL', 'checks': checks,
           'serialized_bytes': len(wire), 'serialized_sha256': hashlib.sha256(wire).hexdigest(),
           'generated_module_files': {name: location for name, location in modules.items()
                                      if name.startswith('uav_tracking_interfaces.')},
           'source_binding_after_roundtrip': source_binding, 'execution_count': 1}
with (ROOT / 'results/freeze_validation/generated_message_roundtrip.json').open('x') as stream:
    json.dump(receipt, stream, indent=2)
    stream.write('\n')
if not all(checks.values()):
    raise ValueError('Built ROS message CDR round trip failed: '+repr(checks))
print(json.dumps({'generated_message_roundtrip': receipt['status'], 'checks': len(checks),
                  'module_origins': len(modules), 'ament_prefixes': len(prefixes)}))
