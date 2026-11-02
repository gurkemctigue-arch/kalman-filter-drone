# Humble54 原生构建与独立复核

2026-11-03，北京时间。本记录区分构建、补充审计和飞行验收。原 Humble53 保持 **7 PASS / 1 FAIL / 4 PENDING**，正式研究仍为 **0/280**。

Humble54 冻结自提交 `a32060d`。Ubuntu 22.04 / ROS 2 Humble 原生四包冷构建完成，colcon 用时 23.5 秒；完整 unittest 为 **2021 项，2016 通过、5 项平台跳过**，原公开构建和测试命令退出 0。实际 FastCDR 来自 `/opt/ros/humble/lib/cmake/fastcdr`，生成消息的 480 字节 CDR 往返与模块、ament 路径隔离通过。

原外层监视器保持 `STOPPED_FAULT`，原 `native_build_supplement.json` 保持 FAIL。原因是补充审计解析器错误要求 unittest 的 `OK` 为日志末行；stderr 测试摘要之后还有两行缓冲 stdout JSON。不能把这个原失败改写成通过。

只在当前工作区修复解析器后，另存独立 `native_build_supplement02.json`，结果 PASS。它重新核对原命令退出码、原构建和测试日志、原复制映射、当前完整冻结树、实际 FastCDR 和 CDR。**1585 个冻结条目均未变化**，未重新冻结或修改 Humble54 源码。修复后解析器另在 Humble 原生完成 5/5 定向测试；该修复不冒称已纳入之前的 2021 项完整套件。

原小文件的逐字节快照、SHA 和边界见 [构建快照](../tools/diagnostics/humble54_build_snapshot01/README.md)。本机完整原件位于 `results/frozen_fullplan_v4_humble54/freeze_validation/`。

本记录创建时，汽车位置模式 seed004 的新 75 秒失败等价复验仍在运行，尚无工程终态。其真实 ROS launch 参数位于 `/tmp`，确认临时目录继承修复已进入生产调用。构建和组件测试通过不能替代该场或后续核心 12、安全 4、扩展 16 及正式重复研究。

实时观察入口：[当前复验进度](../results/project_progress/humble54_car_position_run01/index.html)。静态 GitHub 文档中的“运行中”仅表示上述记录创建时状态，最终以原 owner 终态、原槽及独立评价为准。
