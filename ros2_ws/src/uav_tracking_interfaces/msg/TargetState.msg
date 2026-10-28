# Filtered target state in a stable local/world frame.
std_msgs/Header header
uint8 STATE_UNINITIALIZED=0
uint8 STATE_MEASURED=1
uint8 STATE_PREDICTED=2
uint8 STATE_LOST=3
# AUTO_UNIQUE saw several candidates; retain identity but prohibit following.
uint8 STATE_AMBIGUOUS=4
uint8 state
uint64 track_id
string target_uuid
string class_name
geometry_msgs/Point position_m
geometry_msgs/Vector3 velocity_mps
geometry_msgs/Vector3 acceleration_mps2
float32[36] covariance
float32 prediction_age_s
uint32 rejected_measurements
bool target_visible
