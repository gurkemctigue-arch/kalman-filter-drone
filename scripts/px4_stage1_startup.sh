#!/bin/sh
# PX4 -s startup wrapper; executed in PX4's normal rootfs.
# Environment overrides in PX4 v1.17 rcS happen before airframe set-defaults.
# In particular NAV_DLL_ACT=0 equals the global default and can be replaced
# by 4001_gz_x500's later set-default=2. Configure the GCS-free simulation
# after the normal startup without bypassing estimator or arming checks.
. etc/init.d-posix/rcS
param set NAV_DLL_ACT 0
param set COM_RC_IN_MODE 4
# Evidence of the value used when rcS launched the client. The environment
# override is applied before rcS; changing it here would be too late.
param show UXRCE_DDS_SYNCT
param show SENS_EN_MAGSIM
if [ "${STAGE1_TAKEOFF_MODE:-offboard_velocity}" = "px4_native" ]; then
    param show MIS_TAKEOFF_ALT
    param show COM_TAKEOFF_ACT
    param show SENS_IMU_MODE
fi
