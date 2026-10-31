# 查看当前实验

2026-10-31 17:13（北京时间）快照：当前执行 **Humble41 同源核心12场景开发验证**。行人速度控制和位置控制两个场景完整评价均为 PASS，第三项行人多目标交叉正在运行；其余9项尚未尝试。正式120核心与160扩展实验均未开始。

本机请打开[Humble41实时进度页](../results/project_progress/humble41_core01/index.html)。页面显示任务进程身份、心跳时间、当前场景、原始终态计数和异常原因；以页面时间和状态为准。页面中的“命令完成”只指该批命令，不能解释为项目验收全部通过。

每个场景依次经历起飞、75秒仿真时间的跟随任务、关闭录包、归档完整性检查和离线评价。飞行完成后，计数会等原始评价终态产生再更新。仿真采用非实时运行配置，75秒仿真飞行与归档评价会占用更长的实际时间。

需要核对原始记录时，查看本机路径：

- `results/frozen_fullplan_v4_humble41/reliability_v4_humble41_probe01_seed004_matrix/slots/`：每个场景的开始记录和完整终态。
- `results/frozen_fullplan_v4_humble41/reliability_v4_humble41_probe01_seed004_matrix/observed_driver01/`：执行记录；整批结束后才能核实完整批次观察器的关闭结果。
- `results/frozen_fullplan_v4_humble41/reliability_v4_humble41_probe01_person_stage1_velocity_seed004/onboard.mp4`：已完成首项的机载画面。录像本身不代替定量评价。

旧 `results/project_progress/current/` 是此前Humble31任务的历史记录，其中的已结束状态不能用于判断Humble41是否运行。其他旧页面和失败记录保留。

进度页与视频属于本机结果，不随GitHub源代码提交；从GitHub新克隆后，没有本机结果时这些链接不可用。本文是带时间的入口说明，网页也不会自动向聊天发送完成通知。
