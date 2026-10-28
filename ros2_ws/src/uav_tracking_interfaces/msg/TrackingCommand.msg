# Controller output. The PX4 adapter owns conversion to PX4-specific messages.
std_msgs/Header header
uint8 MODE_HOLD=0
uint8 MODE_VELOCITY=1
uint8 MODE_POSITION=2
uint8 MODE_SEARCH=3
uint8 MODE_FAILSAFE=4
uint8 mode
uint64 track_id
geometry_msgs/Vector3 linear_mps
geometry_msgs/Point position_m
float32 yaw_rad
float32 yaw_rate_radps
bool valid
float32 command_age_s
