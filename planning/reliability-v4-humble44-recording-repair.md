# Humble43录制异常与Humble44验证路线

**23:17后续更新：44四包冷构建PASS，但全Linux suite失败，转新Humble45继续验证。** 原1767项为3 ERROR、5项平台跳过；3项错误均为`tests/test_simulation_seed.py`临时root没有复制新增录包配置。validate launcher原FAILED/child2，suite原FAIL/rc1，原始记录见[失败快照](../tools/diagnostics/humble44_validation_failure01/README.md)。已仅补夹具5行，保留生产配置校验及全部原生命周期断言；受影响的13项已由root在Humble原生全部通过，0跳过、1.517秒。下列原路线继续适用于新45，但44原root和失败不再修改；45仍须重新冷构建和完整测试后再运行单场汽车复测。此前[录包smoke](../tools/diagnostics/humble44_recorder_qos_smoke01/README.md)1290条全匹配只限低量合成，不抵消全suite失败。

2026-11-01。Humble43核心12和安全4的既有通过记录保留；扩展16原始结果12 PASS、4 FAIL，最后汽车远距离的source-clock/native-startup硬门未过，批次停止。正式仍0/280。

一次真实Ubuntu 22.04/Humble只读诊断于14:28:00.747903—14:28:39.616187 UTC完成并退出0，见[原生诊断快照](../tools/diagnostics/humble43_clock_boundary_snapshot01/README.md)。原9173个source-clock帧字典逐项复算一致；两个原reader串行各一次，原压缩包及小元数据未改变，临时目录恢复。诊断不包含图像、深度或真值读取。

## 已确定的故障位置

- 原header为2.740秒的adapted odometry仅一条；完整原4话题中没有同source key的raw或timing。不能用已保存的重复adapted解释，也还不能确定消息缺于发布、传输还是录包端。
- 一条WAITING phase的source为2.756秒，最近已录clock为2.700秒，age=-0.056秒；下一clock为2.764秒。它超出原50毫秒未来容限约6毫秒。
- 首clock在两套过滤序列中均为序号0，因此首clock前记录拆分不能解释这次异常。两异常邻近，共同根因尚未证明。

## 局部候选修复

原生安装头文件`rosbag2_transport/qos.hpp`的Rosbag2QoS构造及default_history使用`rmw_qos_profile_default.depth`；`rmw/qos_profiles.h`将其定义为KEEP_LAST、10。原生record.py已有默认100 MiB双缓冲cache，本次不调整cache。

新候选仅显式配置5条低带宽证据流的recorder接收历史：clock 2048、raw/timing/adapted 1024、phase 256。raw保持BEST_EFFORT和TRANSIENT_LOCAL，其余保持RELIABLE和VOLATILE；不改适配器、phase发布代码、跟踪/控制算法或评价器。runner把配置原字节复制到每场configuration目录，记录SHA256，并让实际ros2 bag进程读取该快照。

这是增加接收容量的修复假设，不能据此断言队列溢出已经确证或保证跨话题顺序。保留原时间戳、50/500毫秒门限、全部消息和原43失败。

## 按依赖执行

1. 对配置归档、真实命令传参及不兼容QoS拒绝进行定向测试，运行受影响的启动、source-clock、native-startup和退出回归。
2. 独立ROS domain下运行原生5话题录包冒烟，确认CLI/YAML兼容和已知序列完整录入；这是合成工程测试，不替代飞行验收或根因复现。
3. 用新Humble44根冷构建、验证导入来源和完整Linux测试。43源码、原槽和owner记录保持原值。
4. 新名称复测原汽车远距离条件；原source-clock、native-startup、closure、archive及飞行门全部保留。若失败，按新原始证据继续定位，不删除WAITING或用后一个clock回填。
5. 候选通过后，在同一最终候选来源验证核心12、安全4和扩展16；完整、安全的压力算法FAIL仍按原合同统计，source/native硬门不得豁免。
6. 健康开发证据齐备后完成实际容量预算、定标、最终根及协议登记，再执行正式120+160、四法离线分析、身份/检测统计和最终可视化及文档交付。

原43扩展进度页继续显示STOPPED_FAULT是正确历史状态。新增候选与实验使用新具名目录，不在旧页面或旧槽中补写PASS。

身份附件工具的20项合成测试已由root在UAVHumble22原生Python 3.10运行，退出0、20/20通过、0.390秒，[原始日志](../tools/offline_evaluation/physical_recovery_v1/native_humble44_01.log)按原字节保留。这确认该工具在Linux上的单元行为；真实补充protocol仍须在最终FORMAL120全部零START时登记，未生成正式分析结果。
