# Humble47：DDS 退出崩溃事故与独立修复构建

本记录保存原始失败及修复依据，不替代工程验收。当前 Humble47 原 core12 仍为 **11 PASS、1 INFRASTRUCTURE_ERROR**，正式实验仍为 **0/280**。独立前缀中的 Fast DDS 补丁库已完成整库构建，随后完成 **三种停止顺序各20轮、共60轮生产 `flight_tf` 退出诊断**，均未观察到崩溃；三角色真实进程映射 smoke 也已闭合。上述结果不包含新候选飞行验收，本轮没有新增飞行，安全4与扩展16尚未启动。

## 原始事故

原批次为 `reliability_v4_humble47_probe01`，来源提交为 `c2fa4f522f8e75485b26738f29616badf8c0bdd9`。第12槽 `car_stage3_multi_active_seed004` 的 ROS 日志报告 `flight_tf-3` 以 `-11` 退出。原父 ROS 进程退出码为0，飞行调用退出码为1；原检查正确登记 `ROS_CHILD_PROCESS_FAILURE`，没有把父进程正常退出当作所有子进程正常。

| 原记录 | 事实 |
| --- | --- |
| 槽记录 | `execution_status=COMPLETED`，`status=INFRASTRUCTURE_ERROR`，`engineering_result=FAIL` |
| 外层记录 | `returncode=2`，`STOPPED_ORIGINAL_ATTEMPTS_RETAINED` |
| 分母 | 计划12、尝试12；外层已审核接受11，实际槽状态为11 PASS＋1 INFRA |
| 清理与来源 | 无残留进程，前后来源绑定相同；这些事实不能消除退出故障 |

完整末槽原记录见 [core_last_slot.json](../tools/diagnostics/humble47_dds_exit01/core_last_slot.json)，外层必要字段见 [core_outer_selected.json](../tools/diagnostics/humble47_dds_exit01/core_outer_selected.json)。投影文件明确标注删减范围，原文件路径、字节数及完整文件 SHA256 保存在 [provenance.json](../tools/diagnostics/humble47_dds_exit01/provenance.json)。旧槽、attempt 和终态均未修改、补跑或升级为 PASS。

## 原生崩溃与第二层 owner 报错

实际 core 的故障线程位于 `StatefulReader::matched_writer_remove+503`，在解锁后重新读取 listener，再对空指针执行虚表访问。调用链经 UDP、`EDPSimplePUBListener`、`PDP::removeWriterProxyData` 和 `EDP::unpairWriterProxy`。同时，主线程经 `rmw_fastrtps_shared_cpp::decrement_context_impl_ref_count`、`destroy_subscription`、`DataReaderImpl::stop` 进入 `deleteUserEndpoint`。关键原始栈片段保存在 [original_core_backtrace.key_excerpt.log](../tools/diagnostics/humble47_dds_exit01/original_core_backtrace.key_excerpt.log)。

实际安装版本为 Fast DDS 2.6.12、rmw_fastrtps 6.2.10、rclpy 3.3.22；精确 Debian 版本与原始内核日志见 [native_metadata.json](../tools/diagnostics/humble47_dds_exit01/native_metadata.json)。这比仅从 Python 退出顺序推测原因提供了更直接的定位依据。

外层另有 `Owner outcome differs from original immutable D copy candidate`。这是原失败触发 `driver_exception=true` 后，健康完成专用 validator 拒绝 `NATIVE_FAILED_RAW_ARCHIVED` 的结果。实际 owner 按原写入规则从不可变 D 副本重建完全一致；与健康期待仅 `healthy_cleanup=false`、状态不是 `COMPLETE` 两项不同。归档子进程退出0、无强制停止或错误，副本绑定一致。故此报错不证明副本损坏；仍应保留原 INFRA，并继续拒绝下游验收。原副本与 native 终态也在本目录保存，未修改 guard。

## 上游依据与补丁范围

已核对两个确切上游修复：

- [0014b017b3cd1f001b0b39b759120073b37ed283 / #2857](https://github.com/eProsima/Fast-DDS/commit/0014b017b3cd1f001b0b39b759120073b37ed283)：EDP 在调用前保存 reader/writer listener，避免反复读取成员产生检查与使用之间的窗口。
- [2078f7f7e7068651b003b83a2f4713342bf51e6b / #2898](https://github.com/eProsima/Fast-DDS/commit/2078f7f7e7068651b003b83a2f4713342bf51e6b)：StatefulReader、StatelessReader 在锁内保存 listener，解锁后使用局部指针，并保护 DataReaderImpl listener 的访问。

`v2.6.12` 指向 `ac5c7b9014cd5b2bebf9c4b04dc229ca5a0a4338`，仍有本次命中的重新读取；已检查的当前 `2.6.x` 亦未包含该局部修复。已检查的 `v2.10.7` 和 master 包含局部快照，但这不构成整套中间件升级兼容性结论。

同族回移只修改五个相关文件，保留2.6.12及原依赖。原2022补丁有两个上下文不能直接应用，已按精确 Debian 源码适配；`git apply --check` 返回0。这只是静态适用性检查。上游原补丁与适配补丁见 [upstream](../tools/diagnostics/humble47_dds_exit01/upstream/)，适配补丁 SHA256 为 `a1de559704415dd11045cc30b7b51720c2740bcf4baf23f44fd4da382f17bddc`。

局部快照不等同于通用生命周期保证。正常 DDS 拥有的 listener 是 impl 成员；EDP 遍历持有 endpoint 列表共享锁，`deleteUserEndpoint` 取得独占锁后才能删除 endpoint，impl 的 stop 等待该删除完成。这为本次路径提供额外生命周期约束，但不能保证任意用户并发销毁 listener 的情况。新增 mutex 位于未安装的私有 `DataReaderImpl.hpp`；公共头仅前置声明并持有 opaque pointer，仍须整库一致重编、核查 ELF 和实际加载路径。

## 源码来源与验证边界

公开 ROS binary 索引与实际安装版本 `2.6.12-1jammy.20260723.233918` 一致。精确 source 为 `ros-humble-fastrtps_2.6.12-1jammy`，原 tar 为13,326,377字节，SHA256 为 `34384c79ad4902d5555a811956596b83c7da190bfa6142f2f09044f10cd2becb`。下载与解压均明确位于 D 盘，未使用 Windows C 默认缓存；五个相关原文件与上游 tag 逐字相同。

Packages/Sources 的 SHA256 与 InRelease 一致。root 已实际用原生 ROS 信任 keyring 执行 `gpgv`，退出0，报告 Open Robotics 的 Good signature，RSA fingerprint 为 `C1CF6E31E6BADE8868B172B4F42ED6FBAB17C654`。来源索引、签名文件、`.dsc` 和构建选项来源见 [package_source](../tools/diagnostics/humble47_dds_exit01/package_source/)；执行记录的来源和限制明确写入 provenance，未伪造日志摘要。

独立整库构建于 `2026-11-02T00:14:54.275481+00:00` 结束，命令退出0；真实监控终态副本见 [build_progress_terminal.json](../tools/diagnostics/humble47_dds_exit01/build_progress_terminal.json)。该终态的 `completion_scope=monitored_command`，只确认构建命令完成，不表示工程验收通过。真实原生产物及命令输出见 [native_build_artifacts01.json](../tools/diagnostics/humble47_dds_exit01/native_build_artifacts01.json)。补丁 ELF 位于 `/root/uav_humble22/fastdds_listener_A01/install/lib/libfastrtps.so.2.6.12`，197,433,472字节，SHA256 为 `e6397d6362f687f071c346600c643599710a5ae817d72f07fa503b75c66b4af6`。`readelf -d` 显示 SONAME 为 `libfastrtps.so.2.6`；记录中的 `ldd` 返回0，依赖解析使用原 Humble Fast CDR 1.0.29。产物与 `ldd` 检查本身只覆盖静态文件和该命令环境，实际生产进程的加载证据由下列诊断单独提供。Agent 使用 Fast DDS 2.14.7 及 Fast CDR 2.2.8，继续与 ROS 进程的依赖分别记录。

## 已完成的退出与真实映射诊断

新库诊断调用 Humble47 已安装的生产 `flight_tf` 入口及真实节点源码，使用数据 feeder 和四个 graph peer，分别执行以下停止顺序。每轮均记录生产进程实际 middleware mappings，确认加载独立前缀中的补丁 DDS 2.6.12 和系统 Fast CDR 1.0.29；60轮的 `errors` 与 `forced_kills` 均为空，三个 summary 状态均为 `NO_CRASH_OBSERVED_IN_FINITE_DIAGNOSTIC`。

| 停止顺序 | 已完成次数 | 外部原始记录 |
| --- | --- | --- |
| simultaneous | 20 | [probe_A01_simultaneous01/summary.json](D:/WSL/UAVHumble22-validation/humble47_tf_exit_diagnosis01/probe_A01_simultaneous01/summary.json) |
| child-first | 20 | [probe_A01_childfirst01/summary.json](D:/WSL/UAVHumble22-validation/humble47_tf_exit_diagnosis01/probe_A01_childfirst01/summary.json) |
| peers-first | 20 | [probe_A01_peersfirst01/summary.json](D:/WSL/UAVHumble22-validation/humble47_tf_exit_diagnosis01/probe_A01_peersfirst01/summary.json) |

原库 baseline20 次也未观察到崩溃，而且尚未命中受控竞争窗口。因此，这组有限诊断不能估计修复前后的崩溃概率差异，不能宣称概率下降或故障已彻底消除。更早一次诊断因 graph peer 的 `-2` 退出未闭合，仍保留其失败记录。原库两次诊断的小型投影见 `probe_simultaneous01_selected.json` 与 `probe_simultaneous02_selected.json`。

另外，`native_guard_smoke01` 真实启动生产 TF、`parameter_bridge` 和 Agent，由主项目 DDS 守护分别取得三个归属明确的 PID，`dds_runtime_actual.json` 的三项均为 `PASS` 且 `fixture_only=false`：TF 与 bridge 各自加载补丁 DDS 2.6.12、系统 CDR 1.0.29 和两项系统 `rmw_fastrtps`；Agent 独立加载其 DDS 2.14.7、CDR 2.2.8。原 ros_gz 守护仍使用 `08cbc9ea…` 注册，DDS 的 bridge 角色另行补充真实通信库映射检查，未替换或提升旧注册。

该 smoke 的 DDS preflight、actual 和 after 均通过，summary 为 `PASS`，诊断总状态为 `DIAGNOSTIC_CLOSED`，没有错误或强制 kill；原始退出码保留为 ROS 0、feeder 0、Agent -2。证据见 [dds_runtime_actual.json](D:/WSL/UAVHumble22-validation/humble47_tf_exit_diagnosis01/native_guard_smoke01/dds_runtime_actual.json)、[dds_runtime_summary.json](D:/WSL/UAVHumble22-validation/humble47_tf_exit_diagnosis01/native_guard_smoke01/dds_runtime_summary.json) 和 [diagnostic.json](D:/WSL/UAVHumble22-validation/humble47_tf_exit_diagnosis01/native_guard_smoke01/diagnostic.json)。这证明采样时的实际加载及本次诊断闭合，不覆盖 Gazebo/PX4 飞行、录包或 core PASS。

## Wrapper 环境顺序与补充验证

接入时发现另一个入口顺序问题：DDS helper 设置好库搜索顺序后，后续 `source ros2_ws/install/setup.bash` 会再次前置 colcon 安装路径，可能改变传给真实子进程的 DDS/CDR 搜索顺序。已对 `scripts/ros_python.sh` 和 `scripts/run_stage1_flight.sh` 作窄修：在项目 install setup 加载完成后，再调用本 root 的 `apply_humble22_dds_runtime.sh`，恢复 Agent lib 第一、独立补丁 DDS lib 第二，并绑定本 root 的注册配置。

原 [wrapper_order_actual02/report.json](D:/WSL/UAVHumble22-validation/humble47_tf_exit_diagnosis01/wrapper_order_actual02/report.json) 必须保留为 **FAIL**：薄夹具仅复制顶层包与 DDS 文件，缺少 `uav_tracking.core`，两个 case 均以 `ModuleNotFoundError` 退出2，真实 preflight 未完成。该次失败不能计为已通过，也不能据此判断真实生产入口的库顺序。

补齐真实包依赖后，[wrapper_order_actual03/report.json](D:/WSL/UAVHumble22-validation/humble47_tf_exit_diagnosis01/wrapper_order_actual03/report.json) 的 `parent_ros_python` 与 `component_wrapper_fake_agent` 两个 case 均退出0，`actual_real_preflight_passed=true`，总状态为 **PASS**。它复制真实 wrapper 字节，借用已有不可变47 merge-install 的真实 colcon 前置行为，并实际执行主 DDS preflight；两例均确认前两个 LD 路径为 Agent lib、补丁 DDS lib，以及夹具本 root 的配置路径。Agent 端点由 preflight 检查脚本替代，未启动真实 Agent、Gazebo、PX4 或飞行。

Windows 全套测试记录为 **1815项、11项平台跳过**，该记录产生于 shell 窄修之前，不能作为修后全套通过的证据。六个运行入口均已在最后一次项目 setup 后应用 DDS helper；之后完成 **4项 Linux Bash 行为测试和8份 shell 语法检查，全部通过**。行为测试覆盖加载顺序、重复加载、错误配置阻断和 Jazzy 环境。原始日志与范围说明见[测试记录](../tools/diagnostics/humble47_dds_exit01/test_validation/receipt.json)；实际 wrapper 的03验证范围以上述报告为准。

下一步是在明确来源与环境的新候选上完成独立构建、完整 Linux 测试及完整 core12；此后仍须真实通过安全4/full guard，才能进入扩展16。原库与补丁库尚未取得稳定触发竞争的对照，不能用新库60轮或 smoke 量化故障率改善。全部原失败与旧终态继续保留，不能仅凭构建、有限无崩溃次数或静态补丁检查宣布故障已彻底修复。

仓库内的诊断目录包含小型原始副本、字段投影、补丁、来源索引和上述验证记录。125 MB core、bag、模型、完整源码包和冗长搜索响应未复制。它不新增封存、验收或正式准入层。
