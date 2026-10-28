# One detector result. This is a candidate observation, not a persistent track.
std_msgs/Header header
uint64 candidate_id
string class_name
uint16 class_id
float32 confidence

float32 bbox_x_min_px
float32 bbox_y_min_px
float32 bbox_x_max_px
float32 bbox_y_max_px
float32 center_u_px
float32 center_v_px

bool depth_valid
float32 depth_m
float32 depth_valid_ratio
float32 depth_std_m
float32 depth_min_m
float32 depth_max_m
geometry_msgs/Point position_camera_m
string camera_frame

# Optional same-acquisition RGB-D support for an independent ground reference.
# Flat xyz camera-optical coordinates; never simulator labels or model points.
float32[] navigation_points_camera_m
geometry_msgs/Vector3 navigation_bottom_ray_camera
# Inside image bounds and no overlap with another confident detection (any class).
# False forbids footprint geometry; surface identity tracking remains separate.
bool navigation_bbox_complete
