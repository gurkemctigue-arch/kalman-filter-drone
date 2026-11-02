# 时钟桥隔离候选的原生组件证据

这是一轮组件验证，尚未完成原失败场景的完整飞行复验。原 Humble51 核心批次仍为 3 PASS、1 FAIL、8 PENDING；正式实验仍为 0/280。

`rgbd_probe01/receipt.json` 记录一次真实的双桥组件检查：原 Humble overlay、生产阶段三模型、640×480 RGB-D、10 Hz、物理步长 4 ms、RTF 0.125，观察 20 秒仿真时间。可靠订阅者实际收到 RGB 202 帧、深度 202 帧、CameraInfo 203 帧，其中 202 组时间戳同步。可靠时钟收到 5048 条，最大回调墙钟间隔 33.70 ms，最大源时间步长 4 ms；此次检查未观察到定义的交付异常。唯一时钟发布者、SetEntityPose 服务及两桥的实际 ROS-GZ/DDS 映射均通过。Gazebo 和两桥均正常退出、直接子进程已回收、进程组无残留，未强杀。耗时 167.16 秒。

此检查未运行 PX4、YOLO 或录包，因此不能证明原飞行中的罕见时序停顿已被修复，也不能替代 75 秒跟随复验、完整新核心批次或正式重复实验。

`runtime_capture01/` 保存此前的单独时钟进程检查。真实 ROS-GZ/DDS 映射和正常退出通过，但原总结果为 FAIL：诊断脚本误要求 RMW 图接口暴露 history/depth；实际 Humble 返回 UNKNOWN history、depth=0。原 FAIL 未修改；`standalone_capture_interpretation01.json` 只解释证据范围。新时钟注册使用真实的 65 项依赖和空插件列表，未借用数据桥的 SetEntityPose 插件证据。

`split_targeted_tests01.log` 保留第一轮测试中发现的一个测试语法错误。修正后，第二轮 `split_targeted_tests02.log` 的 54 项新增测试全部通过。组件检查脚本及所有副本均按原字节保存，来源、大小和 SHA-256 见 `manifest.json`。这些脚本固定了本次诊断路径，后续候选必须使用新的输出目录。
