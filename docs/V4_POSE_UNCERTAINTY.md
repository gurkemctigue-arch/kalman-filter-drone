# PX4 位姿不确定度到 RGB-D 目标观测的传播

这一改动使用 PX4 自己报告的位姿方差，补充 RGB-D 深度、检测质量和目标几何先验的不确定度。它不读取仿真真值、不修正地图坐标或航向，不承诺已经校准的概率误差范围。

`propagate_vehicle_uncertainty` 默认仍为 `false`。adapter 无论该开关如何都可以发布实际可获得的位姿协方差；只有显式开启后，目标估计节点才订阅并传播它。开关关闭时保留原有表面轨迹估计行为，导航仍使用原来的 `navigation_pose_std_m` 位姿项。新试验应保存实际运行参数，不能仅凭代码存在就声称试验已使用该能力。

## 消息语义与坐标轴

钉住 PX4 `d6f12ad1c4f70ad3230afd7d86e971421e02fef4` 的 `msg/versioned/VehicleOdometry.msg` 声明：位置为局部参考系坐标，正常 `POSE_FRAME_NED` 与真北对齐；`position_variance` 为位置误差方差；`orientation_variance` 为表达在机体系的姿态误差方差，单位分别为平方米和弧度平方。它只提供三个方差分量，没有位置–姿态或各轴之间的完整交叉协方差。

ROS `geometry_msgs/PoseWithCovariance.msg` 声明 6×6 行主序协方差，顺序为 `(x, y, z, rotation about X, rotation about Y, rotation about Z)`，旋转使用固定轴表示。对当前 `map → base_link` 里程计，下面以世界固定轴小旋转向量解释其角误差；这是一阶局部误差约定，不是把任意大角度欧拉角误差直接当作独立高斯量。

定义 `N` 为 NED→ENU，`F=diag(1,-1,-1)` 为 FRD→FLU，`R_NB` 为 PX4 四元数表达的 FRD→NED 旋转。ROS 姿态为 `R_WB=N R_NB F`，转换为：

```text
C_position_world = N diag(position_variance) Nᵀ
C_attitude_body_flu = F diag(orientation_variance) Fᵀ
C_attitude_world = R_WB C_attitude_body_flu R_WBᵀ
```

所以不能只交换姿态方差的前两项，也不能始终把 PX4 第三个方差直接放进世界 Z 轴。倾斜和偏航后，旋转后的世界角协方差一般包含非零交叉项。转换后组装 `[translation_world, small_rotation_world]` 的 6×6 位姿协方差；PX4 未提供的平移–旋转相关项目前声明为零，不能解读为已证明不存在相关性。

| 数据 | 6 维顺序 | 用途 |
| --- | --- | --- |
| ROS `odometry.pose.covariance` | `[x,y,z,θx,θy,θz]` | 位姿误差传播 |
| 跟踪 `TargetState.covariance` | `[x,y,z,vx,vy,vz]` | 目标位置–速度滤波状态 |

两者不能直接互换，也不能把位姿 6×6 整体加到目标六状态协方差。无效、负数或非有限的 PX4 方差保持为未知，adapter 发布非有限协方差作为不可用证据；开启传播时拒绝该观测的世界位置，而不是把未知噪声当成零。

## 三维观测的雅可比与视线长度

设目标测量点为 `p_W`，同一时刻无人机 `base_link` 原点为 `t_W`。令 `r=p_W−t_W`。小位姿扰动的一阶影响为：

```text
δp_W ≈ δt_W − [r]× δθ_W
J_pose = [ I₃  −[r]× ]
R_pose = J_pose C_pose_world J_poseᵀ
```

`r` 必须从无人机原点量起，包含相机安装平移和目标视线。只用相机到目标的向量会漏掉相机安装杆臂；只加位置方差会漏掉随目标距离平方增长的角度项。`pose_point_covariance()` 保留输入中存在的平移–旋转交叉项，并检查有限性、对称性和半正定性。

例如目标位于世界 X 方向十米、世界 Z 角标准差为 0.1 rad，则单独的角度项会给横向 Y 产生约 1 平方米的方差；五米时约 0.25 平方米。这个例子展示几何传播，不保证真实误差服从该分布。

表面观测使用自身的 `p_W` 计算 `R_pose`。地面足迹导航参考须在几何推断完成后，用推断出的足迹中心重新计算杆臂，不能直接复用可见表面点的传播矩阵。导航使用 `R_geometry + R_pose`；开启传播后不再同时叠加原固定 `navigation_pose_std_m² I`，避免把同一位姿项重复计入。

## 关联、接受门控与输出消融

表面轨迹通过 detection metadata 的 `additional_measurement_covariance` 携带 `R_pose`。同一观测在三维关联与共享接受滤波中使用同一个 `R_sensor_adaptive + R_pose`。扩大协方差会改变马氏距离的归一化，但没有改变数值门限或物理最大关联距离。多个候选同时可匹配时仍必须进入歧义，不能把较宽的概率门当作切换身份的许可。

`raw`、`ema` 和 `fixed_kf` 的共享接受滤波仍采用自适应检测/深度噪声，以保持不同输出算法的输入接受规则一致。`fixed_kf` 输出自身必须使用 `R_sensor_fixed + 同一R_pose`，不能原样收到共享接受滤波的总自适应 R，否则它就不再是固定传感器噪声基线。原始与 EMA 输出协方差属于已声明的启发式，不是完整滤波后验。

独立审查新增 `tests/test_pose_uncertainty_review.py`，除数学验证外覆盖以下集成边界：

- 固定输出的传感器 R 不随检测置信度改变，共享接受 R 仍随质量改变；
- raw/EMA 第一帧的输出协方差不得丢掉已知位姿项；
- 先有二维轨迹再第一次获得三维位置时，显式测量协方差必须进入初始化位置协方差；
- 位姿缓存不得把另一个 child frame 的原点当成 `base_link`；
- 宽协方差下多目标匹配歧义仍保持原 `target_uuid`，不接受新身份。

原 `tests/test_pose_uncertainty.py` 已验证距离平方效应、坐标旋转、无效矩阵拒绝及所有方法的共享接受规则，但仅检查共享 gate 不足以证明固定输出仍保持固定 R。这些回归测试应在开启正式消融前全部通过；审查发现的实现问题及修复由工作代码和测试结果记录。

## 时间合同仍然有限

当前 adapter 的里程计 header 仍为 ROS 接收时的 `now()`，尚未改成经验证的源采样时间。当前协方差缓存与 TF 使用相同的 ROS header 时间域，在图像采集时刻附近选取不超过 0.05 秒的位姿样本。这个邻近窗口不是对源时间正确性的证明，也不等于插值得到了同一物理采样时刻的协方差。

nav01 的原始证据显示，默认 XRCE 同步会把 PX4 时间转换为 Agent 系统墙钟，并在慢速仿真中产生偏移跳变；直接把 `timestamp_sample` 写入使用 `/clock` 的 ROS header 会混用时间域。因此源时间修复需要独立的仿真/实机同步合同、重启与跳变检查，不能与协方差传播混为一项收益。详见 `V4_EGO_ATTITUDE_DIAGNOSIS.md`。

## 统计与建模边界

当前传播是已接受几何解附近的一阶线性化。姿态误差较大、遮挡导致几何模型切换、车辆可见面假设变化或接近不可观测的地面交点时，这个雅可比不覆盖模型选择错误；应由几何有效性和身份状态拒绝相应观测。

检测/深度噪声、尺寸先验、位姿误差被近似视为可相加的项。相邻图像共享 PX4 位置和航向偏差，表面轨迹与足迹导航也共享 RGB-D 和 TF，它们并不独立。将每一帧的 `R_pose` 加入普通 KF，不会自动建模这类跨时间或跨估计器相关性；长期重复观测仍可能造成过度自信。

PX4 报告的方差来自其内部模型，可能低估初始航向偏差、磁传感器问题、时钟偏差或系统误差。RGB-D 几何项和 raw/EMA 方差也含启发式。因此这里只能声称传播了已知来源的不确定度，不能声称已经校准、95%覆盖真实误差、NEES/NIS符合理论或解决了航向偏差。后续应在独立数据上检查误差覆盖与创新一致性，并保留失败与拒绝观测。

磁场物理环境一致性、位姿协方差传播和源时间合同应分别进行消融。mag-only nav02 仍出现原有初始横向偏差和约十九秒附近丢跟；这并未支持“旧世界磁场已被证实造成该航向误差”的因果结论。还需核实实际 PX4 磁传感器路径与选用实例，不能因世界声明的偏角差和实测偏差量级接近而推断实际输入或主因。

源定义依据：[钉住 PX4 VehicleOdometry](https://github.com/PX4/PX4-Autopilot/blob/d6f12ad1c4f70ad3230afd7d86e971421e02fef4/msg/versioned/VehicleOdometry.msg)、ROS 安装中的 `geometry_msgs/msg/PoseWithCovariance.msg`（已读取其固定轴和行主序注释）。
