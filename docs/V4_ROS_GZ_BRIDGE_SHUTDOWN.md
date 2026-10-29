# Humble ROS–Gazebo 桥的生命周期修复

Humble23第4条开发实验完成飞行和录制，但`parameter_bridge`在收到SIGINT后退出-11。整批正确停止，保留3 PASS、1 INFRA、8 PENDING。本文记录独立修复候选，不能用桥小测试代替完整闭环验收。

原桥来自Humble 0.244.27，commit为`856e319ee4da713609b3f6e58c74ac8db7662482`。源码审查与实际GDB计数确认：ROS→GZ订阅回调强持有桥节点；节点又持有订阅，形成引用环。包含7条命令topic的stage3配置在main返回前仍有8个节点强引用。无流、RGB-D小场景及实际7路控制命令/服务负载中尚未取得原SIGSEGV堆栈；因此“引用环已确认”与“原崩溃根因已全部证明”必须分开表述。

[候选补丁](../patches/ros_gz_bridge_ownership_shutdown_A01.patch)把回调改为弱引用，在执行时临时锁定；GZ→ROS handle析构时主动退订；桥析构明确停止timer、释放service与handles，最后释放GZ node。它不忽略信号或退出码，不添加延时，也不改变跟踪、控制和安全门。异步service错误分支的潜在双回复是另一个已知问题，本候选没有把它混入生命周期修复。

原安装和已有冻结必须保持不变。构建新副本的入口：

```bash
bash scripts/build_humble22_ros_gz_shutdown.sh \
  /root/uav_humble22/ros_gz_ws \
  /root/uav_humble22/ros_gz_shutdown_NEW_ws
```

该命令只构建桥包，接口消息从原固定underlay取得。`MAKEFLAGS=-j2`与`CMAKE_BUILD_PARALLEL_LEVEL=2`在环境中限制并行，不能以同名`-D`缓存变量代替。新项目通过`HUMBLE22_ROS_GZ_WS`选择overlay，须在构建项目前设置，使生成的项目setup也绑定它。

准入证据需同时包含实际源码/patch、桥ELF及动态库依赖的注册，真实进程加载来源，RGB-D/关节/控制命令与服务验证，以及退出时节点确实析构的证据。旧的PX4 `GZBridge.cpp`磁场注册不覆盖此C++ ROS桥。通过小测试之后仍需新冻结、两类clean、完整开发矩阵及后续正式重复，原23失败不能回填为PASS。

独立A01副本已构建成功（单桥包，4分35秒）。正确绑定延迟加载动态库断点的`A01_commands02`在实际活跃数据下测得main返回前强引用数为1，随后真实进入桥析构，桥、客户端及Gazebo均正常退出；映射中只有A01的桥库。前两次A01探针正常退出，但它们的析构断点未开启pending，日志标签不足以作为析构证据，原记录保留。这些证据确认引用环修复生效，尚不证明原SIGSEGV唯一根因或完整飞行可靠性。
