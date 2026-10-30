# Humble31 构建、clean终态与线程诊断记录

本页为2026-10-30 12:33 UTC（北京时间20:33）的事实快照，不代表实时进程状态。Humble31构建与完整测试已通过；两类clean只完成一类准入，核心仍0/12，正式协议仍为DRAFT、正式0/280，三阶段项目尚未完成工程验收。

冻结源码提交为`fee12f856cf30a5f7e0c6c182c3f1380ee387503`，包含593个文件，source canonical为`c9be288ba551146bd0a4d6482c788976041017ba80a6b36a5c820c4432cfe9be`。四个ROS包、模块/ament隔离及11项真实消息CDR往返检查通过。完整套件共1532项，其中1527项通过，5项按原精确平台/工具条件跳过；跳过项没有计为通过。冻结源前后不变，原28、29、30保留证据不变。

## 两类clean的实际终态

批次`reliability_v4_humble31_clean20_serial01`于12:16:57 UTC停止，状态为`STOPPED_NO_AUTOMATIC_RETRY`，完整准入终态为1/2。

- 行人满足该20秒clean的证据及准入要求，导航结果PASS。没有设计遮挡的surface原报告仍为`INCOMPLETE_EVIDENCE`，不将其改写为完整遮挡验收通过。
- 汽车完成飞行，bag完整性、recording closure和source-clock评价通过；native启动评价为`INCOMPLETE_EVIDENCE`。唯一缺证项为`/tracking/state`：17.952→18.484秒间隔0.532秒，超过原0.5秒上限。原生起飞和交接检查通过，但不能据此补成完整记录覆盖通过。
- 汽车导航距离/高度RMSE约0.82748/0.32211米，导航覆盖率约0.78922；末段距离、末段高度稳定均为false。保留这些数值和失败，不用局部指标代替整体验收。

未运行31核心12格或正式试验。原28核心8 PASS/4 FAIL、原29两次clean失败及原30完整套件2 ERROR/5跳过的记录继续保留。

## 独立T1/T2资源诊断

以实际汽车四线程命令为基准，准备1线程T1和2线程T2两个新命名的20秒诊断。每条73项argv仅修改`--name`和`--inference-threads`；模型04、960输入、seed004、速度、RTF 0.25及原时效/起飞/几何门均保持。冻结源码和协议不改，原四线程clean不重跑，诊断不登记为canonical clean/core或正式通过。

T1于12:29:20 UTC开始，完整20秒仿真跟随时长达到`follow_duration_reached`，但`basic_flight=false`、monitor返回1；12:33:08 UTC主飞行返回1，外层返回2并标记`STOPPED_DIAGNOSTIC_FAULT`。bag/closure通过，outer error为null、observer健康且无残留；该标签不代表已经证实的基础设施故障。

T1全链耗时中位数为1.906秒，比原四线程1.079秒更慢；source latency中位数约0.540秒、p95约0.625秒，超时保护影响跟随，实际水平运动范围仅约0.235米。独立source-clock、native及navigation评价仍待执行，不提前声称通过。T2待这些评价完整后由root单独执行；两个入口不自动启动下一项或重试。

本机页面：[T1诊断进度](../results/project_progress/humble31_car_threads_t1_01/index.html)、[31 clean停止记录](../results/project_progress/humble31_clean20_01/index.html)。页面及原始实验文件保存在本机，不随GitHub代码仓库上传；实际后续状态以新原始终态和独立评价为准。

## 小文件证据

以下冻结结果路径相对于`results/frozen_fullplan_v4_humble31/`；外部文件位于`D:/WSL/UAVHumble22-validation/`。

| 证据 | SHA-256 |
|---|---|
| 外部`humble31_final_source_review.json` | `079c5e2098eba8da53f8892c7e55fa973c5af0edc78b8057f697f62fbccd4c9e` |
| `freeze_validation/source_freeze_manifest.json` | `1862411c1e37c4788c1b02209a9f8d846a441c0132938ffd26b7f0342543ae7a` |
| `freeze_validation/build_validation_summary.json` | `d4472010c9cee03ab37d6acb22b49e48f1089f7c51216826fc001ef80d2c244d` |
| `reliability_v4_humble31_clean20_serial01/execution_terminal.json` | `ffb0f91f9668312ef9ee081fbd9123c5f7baed789d791fe2f250c92ddca6e9e7` |
| `reliability_v4_humble31_clean20_serial01/car_evaluation01/native_startup_evaluation.json` | `455ee33075a2cd66cb55ece16e022b5dc8883c25184f5bfb93a57c2960be2bcd` |
| `reliability_v4_humble31_clean20_serial01/car_evaluation01/navigation_reference_evaluation.json` | `d83b194e17eded97b3fbac0424b8fd87102886f0e7866e293600e53927a54829` |
| `humble31_car_cpu_threads_diagnostic01/t1_driver/execution_terminal.json` | `4aa54ad865234ab6614864808cc368c52d171c55f4dcad75beac09a2d977e8a7` |
