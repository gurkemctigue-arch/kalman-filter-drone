# Humble45 core12 第二场 position 中止：最小原始证据快照

本目录只保全原始小文件，不包含修复，也没有启动或重跑任何实验。
来源批次：`reliability_v4_humble45_probe01_seed004_matrix`。

## 原批次结果

原 `actual_slot_statuses/status_counts` 为 **1 PASS + 1 INFRASTRUCTURE_ERROR + 10 PENDING**；
正式研究 **0/280**。第1场行人速度模式保留原 PASS；第2场行人位置模式中止，
其余10场未开始。原外层为 `STOPPED_ORIGINAL_ATTEMPTS_RETAINED`，`returncode=2`。
原外层另存 `terminal_count=1`，此值原样保留；不能据此改写第2场已有的原始错误槽。
外层 shell 会话退出1与原工具 returncode2属于不同层，不能混写。

第2场 `flight_exit_code=1`，summary 为 `flight_aborted`、`monitor_success=false`、
`monitor_exit_code=1`。原槽 `evaluations=[]`：原计划的源时钟、原生启动、飞行、导航四项
评价未运行；不能根据原始过程计数或 `basic_flight_passed=true` 宣称这场验收通过。

## 已证的直接触发与时间语义

完整原字节的小型 `trial_position/monitor.log` 第14行记录：

- 监督器进入 `ABORTED`，原因 `flight guard: odometry_stale`；
- `odom_age_wall_s=0.733` 超过 `odom_limit_s=0.500`；
- 同条日志 `ros_now_ns=60252000000`、`odom_stamp_ns=60172000000`，相减为源时差0.080秒。

0.733秒是宿主单调墙时接收年龄；0.080秒是该日志所示ROS源时与里程计时间戳差。
这是不同时间尺度/新鲜度语义，不能互相替代。直接触发已记录，但尚未证明造成墙时
接收年龄超限的调度根因；本目录没有证明CPU争用、DDS、executor、阻塞I/O或其他
哪一项是原因，也没有证明可以放宽安全门。没有实施或认证修复。

## 独立保留的 owner 问题

原外层 `final_errors` 仍包含：
`observer:ValueError:Owner outcome differs from original immutable D copy candidate`。
原 owner native 为 `healthy_cleanup=false`、`driver_exception=true`；原 copy terminal
状态为 `COPY_VERIFIED_PENDING_OWNER_CLOSURE`。这些原字节都保留，不把copy成功
解释为owner闭合成功，也不将owner问题与飞行中止的直接原因混为一个已证根因。

## 文件与边界

`manifest.json` 记录每个原文件的来源、字节数和SHA256；`SHA256SUMS`覆盖原字节副本、
本说明及manifest。13个原小件均按字节复制，未重排JSON或修补任何原状态。
第1场独审回执是在当时outer尚未闭合时作出的局部审查，保留其原时间与边界。

完整telemetry、runtime health日志、bag负载、视频、ROS大日志和源码未复制。
archive_manifest/bag_integrity只作为原小型回执复制；本次未打开或验证bag负载。
第1场PASS只属于这份原45批次，不拼入下一批或其他来源来凑齐核心12。
所有原始失败和缺证继续保留；此快照不授权后续飞行、安全注册、扩展或正式实验。
