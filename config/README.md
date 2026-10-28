# Configuration templates

`tracking.yaml` is the repository-level source template for the ROS 2 node
parameters. The installable copy is under
`ros2_ws/src/uav_tracking_bringup/config/`. It keeps the single-instance core
line enabled by default and exposes the designated-instance selection topic as
an optional extension.

Before a trial, copy the exact YAML path and its hash into the experiment
artifact. Do not tune parameters interactively during a comparison run.
