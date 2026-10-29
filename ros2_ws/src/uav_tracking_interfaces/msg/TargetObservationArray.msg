# All candidates from one completed RGB-D inference, including empty frames.
# Every observation must have the same acquisition header as this frame.
std_msgs/Header header
TargetObservation[] observations
# Same-stamp depth samples outside all detected object boxes, flat xyz.
float32[] navigation_ground_points_camera_m
# All detected-box intersections, including non-task classes, from this frame.
NavigationOverlap[] navigation_overlaps
