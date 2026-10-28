# Launch templates

`tracking_sim.launch.py` mirrors the installable launch file in
`ros2_ws/src/uav_tracking_bringup/launch/`. It defaults to `start_pipeline:=false`
because the algorithm packages are not part of this scaffold. Supply an
absolute world file and explicitly enable the simulator and pipeline only
after the selected ROS 2, Gazebo, and PX4 versions pass the smoke test.
The static `map -> camera_link` transform uses the REP-103 optical frame
convention. For a ROS/Gazebo-only run without `px4_msgs`, pass
`start_px4_adapter:=false` together with `start_pipeline:=true`.
