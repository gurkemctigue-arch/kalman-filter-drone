# 离线模型资源与几何来源

Humble13的行人crossing开发槽因真实场景节点收尾错误保留为`INFRASTRUCTURE_ERROR`。随后在独立诊断目录读取同一bag时，physical-identity评价又暴露了离线模型解析路径问题：旧helper硬编码`/root/PX4-Autopilot`，隔离Humble环境实际使用`/root/uav_humble22/PX4-Autopilot-v4mag`。`gz sdf -p`因此无法解析`model://x500`。原bag、计划、终态及第一次诊断失败均不修改。

`extract_research_recording.model_camera_mount`与`evaluate_online_state_accuracy.body_frame_mount`现在共同使用显式`STAGE1_PX4_ROOT`选择PX4模型树；`scripts/humble22_env.sh`已经从所选Humble PX4配置设置该变量。未设置时保留历史默认，声明的树缺模型时直接失败，不搜索另一份安装，也不混入环境中无关的Gazebo模型路径。该修改只影响离线相机和机体几何评价，不改变运行时关联、状态估计或控制。

每次评价的mount证据同时记录声明的两个模型资源根、变量选择方式、递归include实际解析到的SDF绝对路径及SHA256，以及`gz sdf -p`展开结果SHA256。展开仍由真实Gazebo/SDF工具完成，坐标变换仍按模型frame层级计算，不从目标误差拟合偏移。真实Humble解析得相机相对模型原点`[0.13233, 0, 0.50078] m`，其中包含`base_link`的`0.24 m`继承位移；机体原点的独立展开检查另行记录。

旧飞行数据的诊断使用单独命名的离线源码revision及输出目录，保存候选helper和依赖源码清单、命令、输出摘要及原件前后SHA。诊断不将基础设施失败改判为成功，也不代替新冻结源的完整开发矩阵和正式重复实验。
