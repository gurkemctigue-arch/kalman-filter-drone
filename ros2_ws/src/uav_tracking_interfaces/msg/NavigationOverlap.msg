# Same-acquisition evidence for one positive-area detection-box intersection.
# These are raw sensor samples, not an identity or visibility decision.
uint64 candidate_a_id
uint64 candidate_b_id
uint16 class_a_id
uint16 class_b_id
float32[4] bbox_a_px
float32[4] bbox_b_px
# Every pixel cell touched by the continuous intersection, without clipping.
# A negative origin / image overflow is incomplete evidence and is not sampled.
int32 u0
int32 v0
uint32 width
uint32 height
uint32 expected_pixel_count
uint32 valid_pixel_count
# False means the raw rectangle cannot fit the integer wire representation.
# Its extent/count fields are zero placeholders; they are never complete data.
bool rectangle_representable
# False for any invalid pixel, overflow or intersection larger than 4096 cells.
# Over-budget / out-of-image intersections retain expected count but no points.
bool depth_complete
# Row-major camera optical xyz for valid original pixels. Never synthesized.
# Complete evidence requires exactly expected_pixel_count * 3 finite values.
float32[] points_camera_m
