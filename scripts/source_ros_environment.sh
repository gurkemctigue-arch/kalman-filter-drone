#!/usr/bin/env bash
# Source underlays selected for this isolated workspace. Caller handles nounset.
tracking_ros_distro="${STAGE1_ROS_DISTRO:-${ROS_DISTRO:-jazzy}}"
source "/opt/ros/$tracking_ros_distro/setup.bash"
if [ -n "${STAGE1_ROS_GZ_WS:-}" ]; then
  source "$STAGE1_ROS_GZ_WS/install/setup.bash"
fi
source "${STAGE1_PX4_MSGS_WS:-/root/px4_msgs_ws}/install/setup.bash"
