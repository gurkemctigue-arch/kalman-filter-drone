# 仿真随机种子与 PX4 持久参数证据

每次试验的 `run_config.json` 保留登记的零起始 `seed`、实际 `gazebo_seed` 及映射说明。正式种子0至9对应 Gazebo种子1至10；目标速度/故障随机数仍使用原登记种子。runner 将实际种子通过 `STAGE_SIM_SEED` 传到 `run_stage1_flight.sh`，EGL、WSLg两个分支均显式执行 `gz sim --seed <非零种子>`。日志也记录该实参。相同种子不能保证操作系统调度、推理完成时刻及闭环飞行逐位一致。

这一映射来自当前安装环境的直接证据，而非猜测：

- `gz sim --help` 明确支持 `--seed [arg]`。
- `/opt/ros/jazzy/opt/gz_sim_vendor/lib/ruby/gz/cmdsim8.rb` 默认 seed=0。
- 当前8.15.0的 `libgz-sim8-gz.so.8.15.0` 中，`runServer` 在地址 `0x2556f–0x25577` 检查种子是否非零，仅非零分支进入 `0x25788` 调用 `ServerConfig::SetSeed`。因此显式 `--seed 0` 也不能固定生成器。
- `libgz-sim8.so.8.15.0` 的 `ServerConfig::SetSeed` 调用 `gz::math::Rand::Seed`。当前 `libgz-math7.so` 的 `Rand::SeedMutable` 初始化调用 `std::random_device::_M_init` 和 `_M_getval`。未显式设置的默认种子不是统一固定值。

旧工程探针没有向 Gazebo传递种子，其原始 `seed` 只能证明速度/故障随机数配置，不能补写成仿真传感器噪声也已配对受控。旧结果保留为不同运行协议的历史证据。固定 Gazebo进程随机生成器也不能直接证明所有外部插件/硬件噪声都共享同一生成器。

`tests/test_simulation_seed.py` 通过 mock完整runner检查实际子进程环境、保存的双种子和参数快照；另在 WSL运行真实 Bash脚本，使用假 `gz` 可执行文件捕获最终 argv，检查两个渲染分支、暂停/立即运行及非法零种子拒绝。该测试没有启动 Gazebo、PX4、ROS节点或传感器。

## PX4 参数归档

当前 PX4 `rcS` 每次导入 `build/px4_sitl_default/rootfs/parameters.bson`。同一 `SYS_AUTOSTART=4001` 通常不会触发重新配置；它不是每次从空参数开始。`px4_stage1_startup.sh` 在标准启动后显式设置 `COM_RC_IN_MODE=4`、`NAV_DLL_ACT=0`，保留其余估计器、Offboard与起飞检查。

新runner在任何试验进程启动前复制该持久文件为 `configuration/px4_parameters_before.bson`，在停止 PX4之后复制为 `px4_parameters_after.bson`。`configuration/px4_parameters.json` 记录来源、文件存在性、字节数及每份SHA256，不向rootfs反向写入、导入或重置参数。BSON只保存持久的非默认值，仍须结合冻结固件、airframe默认值及启动脚本解释；前后哈希变化也须先区分校准/飞行计数与控制参数变动。

本次只读审计的文件为372字节，两次读取SHA256均为 `a9a89b51c6f3adaad9e13cb2df0e80e2f28d7acbc479fb77bdf4bead8bc7c6ff`。19个持久条目如下：

| 参数 | 值 |
| --- | ---: |
| CAL_ACC0_ID / CAL_ACC1_ID / CAL_ACC2_ID | 1310988 / 1310996 / 1311004 |
| CAL_GYRO0_ID / CAL_GYRO1_ID / CAL_GYRO2_ID | 1310988 / 1310996 / 1311004 |
| CAL_BARO0_ID / CAL_BARO0_OFF / CAL_BARO0_PRIO | 6619404 / 1.220703125 / 50 |
| CAL_MAG0_ID / CAL_MAG0_PRIO | 197388 / 50 |
| CAL_MAG1_ID / CAL_MAG1_PRIO | 197644 / 50 |
| COM_RC_IN_MODE | 4 |
| EKF2_MAG_DECL | 3.4057650566101074 |
| NAV_DLL_ACT | 0 |
| SENS_BOARD_X_OFF | 约0.000001 |
| SENS_DPRES_OFF | 约0.001 |
| SYS_AUTOSTART | 4001 |

本文件未观察到持久的 MPC或姿态控制增益覆盖。两次读取相同不能倒推旧试验每次都相同；从新录制开始使用逐次前后快照核验。
