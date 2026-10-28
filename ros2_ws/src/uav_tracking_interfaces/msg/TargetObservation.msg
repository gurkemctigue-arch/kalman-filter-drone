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
