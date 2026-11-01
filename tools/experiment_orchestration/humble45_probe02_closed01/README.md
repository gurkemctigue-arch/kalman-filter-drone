# Humble45 probe02 单场开发试验闭合快照

汽车远距离、seed004、75秒的这一场开发诊断完成原工程验收：原 slot/engineering 为 PASS，outer returncode=0，唯一原始尝试、无残留进程，owner 完成归档。这里只登记这场已闭合结果，不推断核心12、重复试验可靠性、全部阶段或项目通过；本场不消耗正式种子，正式实验进度仍为0。

source-clock 和 native-startup 原报告均为 PASS，source-clock 独立匹配9235组三流样本。导航原状态保留为 RECORDED_WITH_CENSORED_FAILURES：完整752格均有真值，其中64格控制未激活；不删除、不改写为无删失结果。全区间 base_link 距离RMSE为0.6727508112480098米，高度RMSE为0.1657141983373969米；距离与高度两轴在结尾均满足原持续稳定条件，原稳定时间分别35.7秒、32.2秒。

[独审原件](independent/humble45_probe02_closed_independent01.json) 的 SHA 为 eb652fb71132dc1838904b07aa510869b0c9eaa4721f78c7e95890a65ce6c379。四份评价报告、summary、录包闭包/完整性、退出码、停止观察、实际recording QoS/policy，以及原slot/outer/attempt和owner终态/manifest均按原字节复制。所有原POSIX路径与证据引用保持不变。

本次只读取和复制已闭合的小型报告/元数据；未重新评价、未启动WSL或飞行，未复制frames JSONL、telemetry、bag、ROS日志或owner健康大日志。完整原件仍在原结果目录，本快照不包含全部外部证据负载，不能单独回放或代替完整原始归档。此前probe01规划失败与probe02准备快照均保持原样。

来源、字节数和SHA见 [manifest.json](manifest.json)，逐文件校验见 [SHA256SUMS](SHA256SUMS)。
