# Humble44 recorder QoS 原生低流量冒烟快照

本目录暂存一次真实Humble ROS与`ros2 bag record`的合成消息冒烟，证据范围为 `SMOKE_SYNTHETIC_NOT_FLIGHT_NOT_ROOT_CAUSE`。原生脚本退出0，运行于2026-11-01 14:50:19.815522至14:50:25.553140 UTC；本次未执行仿真或飞行。

主树`config/recording_qos.yaml`的原字节快照通过真实CLI参数传入recorder，SHA为`d56c368ecba5e77a7343a7832be4ec234a4cd4576e367aaa9a808c356cf76824`。使用独立ROS_DOMAIN_ID=74及5个真实类型publisher，等待唯一typed recorder endpoint/GID与实际RMW匹配稳定后发布2秒已知序列：clock 500条，raw/timing/adapted各250条，phase 40条。

原生reader核对全部1,290条记录，各流完整key集合与次数精确一致，缺失0、额外或重复0。发布实际持续2.000901374秒；recorder仅收到一次自身进程组SIGINT，exit0、直接子进程已reap且无残留。原始细节见[result.json](result.json)、[started.json](started.json)与[recorder.log](recorder.log)。图发现中的history/depth按实际可见值保留；不能将请求深度当作已直接测得的接收队列容量。

该结果证明本次指定YAML可被实际Humble CLI使用，且所选兼容writer的低流量已知序列完整记录。它不证明默认depth失败已复现，也不证明压力场景、飞行可靠性、source-clock修复或共同根因。此前独立的20项原生工具测试不计入本次冒烟结果。

脚本、实际运行壳、result、started、YAML、日志及[rosbag metadata](rosbag/metadata.yaml)均为原字节副本，来源与SHA见[manifest.json](manifest.json)，文件校验见[SHA256SUMS](SHA256SUMS)。未复制db3；原db3保留在external原目录，字节数与SHA仍在原result中。因此本目录中的rosbag子目录仅为metadata快照，不能单独回放。

运行壳保留已执行时的原生环境与绝对路径，仅作历史记录；原输出目录已经存在，脚本拒绝复用。本次快照整理仅在external完成，此暂存步骤未写入main。随后复制入仓库前，应为最终快照目录配置`-text whitespace=cr-at-eol`以保留原字节。
