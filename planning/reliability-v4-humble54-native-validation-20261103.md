# Humble54 原生构建与独立复核

2026-11-03，北京时间。本记录区分构建、补充审计和飞行验收。原 Humble53 保持 **7 PASS / 1 FAIL / 4 PENDING**，正式研究仍为 **0/280**。

Humble54 冻结自提交 `a32060d`。Ubuntu 22.04 / ROS 2 Humble 原生四包冷构建完成，colcon 用时 23.5 秒；完整 unittest 为 **2021 项，2016 通过、5 项平台跳过**，原公开构建和测试命令退出 0。实际 FastCDR 来自 `/opt/ros/humble/lib/cmake/fastcdr`，生成消息的 480 字节 CDR 往返与模块、ament 路径隔离通过。

原外层监视器保持 `STOPPED_FAULT`，原 `native_build_supplement.json` 保持 FAIL。原因是补充审计解析器错误要求 unittest 的 `OK` 为日志末行；stderr 测试摘要之后还有两行缓冲 stdout JSON。不能把这个原失败改写成通过。

只在当前工作区修复解析器后，另存独立 `native_build_supplement02.json`，结果 PASS。它重新核对原命令退出码、原构建和测试日志、原复制映射、当前完整冻结树、实际 FastCDR 和 CDR。**1585 个冻结条目均未变化**，未重新冻结或修改 Humble54 源码。修复后解析器另在 Humble 原生完成 5/5 定向测试；该修复不冒称已纳入之前的 2021 项完整套件。

原小文件的逐字节快照、SHA 和边界见 [构建快照](../tools/diagnostics/humble54_build_snapshot01/README.md)。本机完整原件位于 `results/frozen_fullplan_v4_humble54/freeze_validation/`。

本记录创建时，汽车位置模式 seed004 的新 75 秒失败等价复验仍在运行，尚无工程终态。其真实 ROS launch 参数位于 `/tmp`，确认临时目录继承修复已进入生产调用。构建和组件测试通过不能替代该场或后续核心 12、安全 4、扩展 16 及正式重复研究。

实时观察入口：[当前复验进度](../results/project_progress/humble54_car_position_run01/index.html)。静态 GitHub 文档中的“运行中”仅表示上述记录创建时状态，最终以原 owner 终态、原槽及独立评价为准。

## 03:37 原复验终态与新核心计划

原单场 owner 已 COMPLETED，原槽 **PASS**，`infrastructure_stop=false`、实际飞行及四个评价命令均退出 0，运行参数错误与残留仿真进程均为空。独立 base_link 距离/高度 RMSE 为 **0.703947/0.170043 米**，导航有效覆盖为 **0.916223**，真值覆盖为 **1.0**，距离、高度末端持续稳定均通过。源时钟、原生启动、遮挡行为、录包完整性与闭合检查通过。

导航报告仍为 `RECORDED_WITH_CENSORED_FAILURES`，保留长丢失、悬停等无效区间；工程 PASS 来自已登记的六项独立检查，不能把它改称所有区间均成功。原始小文件与 SHA 见 [单场终态快照](../tools/experiment_orchestration/humble54_car_position_closed01/README.md)。

随后公开 CLI 新建同源、两类各六组、seed004、每场 75 秒的完整 12 场 PROBE，计划 digest 为 `3e34bdfae710f7b518a5f5fd1506054b03d3275c89e2f827ae136bfa2f682a31`。创建时全部 12 PENDING；正常 core owner 已开始串行执行，任何核心非 PASS 都停止后续。上述单场不拼进新核心 12，原 Humble53 和正式 0/280 不变。新实时入口：[核心 12 执行进度](../results/project_progress/humble54_core12_run01/index.html)。

## 06:09 核心开发检查点

本批原始终态为 **8 PASS / 4 尚未终态**。行人六组与汽车速度、位置两组均已完成，原 owner 仍在运行，第九场为 `car_stage2_crossing_seed004`。本批未改冻结算法源；后续四场没有预记通过。

汽车位置模式于北京时间 06:08:20 完成 `COMPLETED / PASS`，独立 base_link 距离 RMSE 为 **0.704895 米**、高度 RMSE 为 **0.165654 米**，导航有效覆盖 **0.913679**，真值覆盖 **1.0**。六项工程门、源时钟、原生启动、遮挡行为及录包检查均通过，无基础设施停止、配置错误或残留进程。导航报告仍保留 `RECORDED_WITH_CENSORED_FAILURES`，不把条件达标解释为全部时段都有有效跟踪。

行人多目标主动云台的完整请求时间网格为 **648 正确 / 0 已知错误 / 106 未知，共 754 格**；覆盖为 0.859416。逐诊断帧统计有不同分母，不用于替代完整任务网格；总体覆盖不能证明每个重选任务分别达标。六个行人的小文件原件与独审边界见 [person6 快照](../tools/experiment_orchestration/humble54_person6_closed01/README.md)。

只有实际核心 12 全部通过并完成进程清理后，才执行原生审计、四项歧义安全及新的 16 个扩展工况。正式研究仍为 **0/280**，后续容量、定标、登记、封存、重复实验和统计交付尚待执行。
