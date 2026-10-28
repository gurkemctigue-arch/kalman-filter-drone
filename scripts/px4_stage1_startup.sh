#!/bin/sh
# PX4 -s startup wrapper; executed in PX4's normal rootfs.
# Environment overrides in PX4 v1.17 rcS happen before airframe set-defaults.
# In particular NAV_DLL_ACT=0 equals the global default and can be replaced
# by 4001_gz_x500's later set-default=2. Configure the GCS-free simulation
# after the normal startup without bypassing estimator or arming checks.
. etc/init.d-posix/rcS
param set NAV_DLL_ACT 0
param set COM_RC_IN_MODE 4
