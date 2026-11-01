# Humble43 扩展槽时间边界诊断快照

本目录保存最后汽车远距离槽 `car_extension_far_distance_seed004` 的一次真实原生只读诊断。运行时间为2026-11-01 14:28:00.747903至14:28:39.616187 UTC，原生进程退出0，结果为 `DIAGNOSTIC_COMPLETE_ORIGINAL_FAILURES_RETAINED`。诊断成功表示原异常已定位；原工程、source-clock、native-startup及外层owner失败均保留。

脚本、实际运行壳、[started.json](started.json)和[diagnostic.json](diagnostic.json)均按原字节复制。来源路径、字节数与SHA见[manifest.json](manifest.json)，本目录文件校验见[SHA256SUMS](SHA256SUMS)。原始停止记录另见[此前快照](../humble43_extension_stop_snapshot01/README.md)。未复制bag、图像、深度、完整遥测或原frames侧文件；诊断JSON保留其输入引用。

本次证据支持以下结论：

- source原4话题记录包含9,173条raw、9,173条timing和9,174条adapted。原9,173个frame字典逐项重算一致，唯一未消耗adapted的原header为2.740000000秒、记录交付clock为2.792秒。完整原4流中没有该sample对应的raw/timing，同header的adapted仅此一条；不能解释为同header adapted重复。
- 1,846条phase中仅1条越界：原字符串包含 `source_sim_s=2.756000000`，该条前最近记录clock为2.700秒，随后clock为2.764秒。按原规则计算age约为-0.056秒，即future 56毫秒，超过原50毫秒容限。完整字符串、原序号和前后clock均保留在JSON中。
- 两套原过滤序列的首clock均为sequence 0，首clock前记录数均为0，因此“首clock前未定时记录被拆分”不能解释这两条异常。

两条异常在时间上邻近，尚未证明具有共同根因。上述结果也不单独证明真实PX4时钟域错误、控制失效、录制丢失的具体机制或任何修复有效性。未更换匹配、放宽原门或改写原FAIL。

诊断分别调用未修改的source-clock原4话题reader一次及native-startup原9话题reader一次，严格保留各自过滤序号；source使用原`evaluate`及原frames匹配。两个读取均无read error，压缩包在每次读取前后与原integrity SHA一致，原生临时cache恢复baseline。没有启动ROS节点，也未反序列化图像、深度或GT。

运行壳保留已执行时的原生环境、绝对路径及明确TMPDIR，仅作历史记录。原输出目录已经存在，脚本会拒绝复用；不要直接重跑本快照壳来覆盖原结果。本快照不代表新实验通过、完整28格健康闭合、容量准入或正式280实验开始。
