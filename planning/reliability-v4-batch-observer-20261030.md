# Humble28 批次监控修订与原始尝试保留

2026-10-30，北京时间10:28快照。此修订只改变外部批次编排，不修改冻结28的飞行、跟踪、控制、归档、独立评价或任何安全门。正式仍0/280。

## 具体问题和已执行处置

原独立观察器每个进程最多运行7200墙钟秒。原核心driver用同一个观察器覆盖12槽，但首槽实际835.94秒，完整12槽预计超过该时限。观察器到期会被正确识别为失去监控，并中断当时活动试验；因此在到期之前处理编排限制。

在第2槽所有评价完成后，具名行政watcher仅暂停原driver，验证PID及创建身份、SIGINT处置、完整事件前缀、原两份正常outer回执、无活动runner/仿真进程及剩余10槽均PENDING，再请求原driver退出。没有对飞行、录包、压缩或评价子进程发信号。原driver的`KeyboardInterrupt`、returncode2及观察器`driver_exception=true / healthy_cleanup=false`均保留，不改成正常整批完成。

原两槽分别为`person_stage1_velocity_seed004`与`person_stage1_position_seed004`，原始终态均PASS，外层runner均return0、error为null且无清理信号。新`serial_driver02`继续同一个不可变plan的10个原PENDING槽，不创建替代槽，不换种子，不重飞前两槽。其最终聚合会分别核对两段完整证据，当前尚无完整12槽终态。

## 新监控合同和验证

新外部`RollingIndependentObserver`保留原观察器的7200秒命令、10秒新鲜度、接收线程健康及日志检查。生产轮换间隔5400秒：先启动新观察器、确认首个新鲜样本，同时再次检查旧观察器，然后正常结束旧观察器，再检查新观察器。所有会话和交叠回执分别保存；替换失败或任一观察器异常均停止后续试验。原飞行600秒、原生起飞180墙钟/40源秒、每项评价1800秒及outer子超时不变。

已完成4项小型mock验证，覆盖交叠顺序、替换失败、过期/未来/非有限时间及原日志变化拒绝；6项聚合schema验证覆盖原失败保留、活动suffix拒绝、partial事件/后续START拒绝、行政异常不可漂白及实际python命令解析。实际Humble28只读先验核验确认原两槽完整且10槽未尝试。

另在真实ROS环境执行了三个观察器进程的启动、交叠和正常收尾诊断。仅该具名诊断在进程内将轮换间隔加速为5秒，便于验证生命周期；原7200秒命令及10秒门保持，生产文件仍为5400秒。该诊断未启动Gazebo/PX4、未飞行、未读包，不能替代闭环验收。

## 可复核位置

- 原计划、两槽与行政停止原终态：`results/frozen_fullplan_v4_humble28/reliability_v4_humble28_probe_seed004_matrix/serial_driver/`和同级`slots/`。
- 续行事件与最终回执：同一矩阵下`serial_driver02/`，当前正在运行。
- 真实ROS生命周期：`results/frozen_fullplan_v4_humble28/reliability_v4_humble28_rolling_observer_lifecycle02/`。
- 外部源码、具名request/result、两份fixture与独立review：本机`D:/WSL/UAVHumble22-validation/`内`pause_humble28_core_boundary01*`、`humble28_rolling_observer02.py`、`humble28_core_completion02.py`、`run_humble28_core_serial02*`、`humble28_core_continuation_review02*`。

原冻结566文件和base20 helper保持原字节。后续安全及16扩展同样采用独立的新外部02版本，先绑定新依赖及完整核心终态，再发布additive review；旧准备文件不改，不提前填写完成结果。
