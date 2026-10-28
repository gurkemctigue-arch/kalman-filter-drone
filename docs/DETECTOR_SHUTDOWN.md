# 检测器有序停止与重复信号

保留记录 `stage23_engineering_v1_s3_car_gimbal_midpoint_seed000/ros.log` 显示：首次 SIGINT 令 `rclpy.spin` 抛出 `KeyboardInterrupt`，清理阶段已调用 `NonQueuingWorker.shutdown()`；随后第二次中断发生在 `ThreadPoolExecutor.shutdown → Thread.join → _wait_for_tstate_lock`。检测器最终报告 `terminate called without an active exception` 并以 SIGABRT（-6）退出。该现象发生在正常录制结束后，不能解释为推理阶段测量失效，但会产生大型 WSL 崩溃转储。

检测器现在关闭 rclpy 的默认信号处理，显式安装仅设置停止布尔值的 SIGINT/SIGTERM 处理器，使用同一个单线程 ROS executor 处理回调。主循环最多等待 0.2 s 的空闲 executor 超时后开始清理；活动回调的业务逻辑、推理频率、丢帧策略和检测参数不变。清理期间重复信号继续只设置同一个布尔值，不抛出新的 `KeyboardInterrupt`。

停止顺序是：停止 executor；标记检测器正在退出并取消提交计时器；等待已接收的原生推理结束；销毁节点发布器；关闭 ROS context；恢复进入 main 前的信号处理器。正在退出时丢弃末次推理结果，避免在清理期间向关闭中的 ROS 链路发布。原有 worker 的无限等待 join 保留，不使用短超时后放弃原生工作的方法。

`tests/test_detector_worker.py` 在不需要 ROS、torch 或 Gazebo 的条件下验证慢推理期间多次 SIGINT/SIGTERM 请求，真实线程 join 完成后才销毁发布器和 context，以及停止后不发布末次检测结果。该文件 12 项测试通过。完整 Windows 回归当次 339 项通过；临时目录使用 D 盘以绕开 C 盘容量限制。

真实 ROS/PX4 飞行的停止日志、进程退出码与新的 WSL 转储情况仍需在同步此修改后的运行中核对；单元测试不证明 WSL 转储问题已通过真实场景验收。旧日志、失败退出码和已生成的转储应保留来源记录，归档转储不属于算法结果修复。
