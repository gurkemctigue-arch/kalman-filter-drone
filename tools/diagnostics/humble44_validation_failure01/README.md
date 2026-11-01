# Humble44 全量验证失败原始快照

Humble44 的独立冷构建成功，但本次全量验证失败。这里按原字节保留四份原始结果，不重试、不改写冻结44，也不将后续修复结果并入44。

- 原始 build 动作：status=PASS，direct_child_returncode=0；仅表示四包构建完成。
- 原始 validate 外层动作：status=FAILED，direct_child_returncode=2。
- 原始内层单元测试摘要：status=FAIL，returncode=1；这与外层返回码是不同字段。
- 原日志：Ran 1767 tests in 86.449s；FAILED (errors=3, skipped=5)。总数1767包含5项跳过；1759项通过是按「1767 - 3 ERROR - 5 skipped - 0 failures」推导的值，不是原摘要字段。
- 构建与验证均只执行一次，进程组清空、直接子进程已回收；原记录为 runtime_acceptance=NOT_EVALUATED、formal_seeds_consumed=false。

三个 ERROR 均来自 test_simulation_seed.SeedRunnerTests 的旧临时夹具未提供 config/recording_qos.yaml，在生产入口读取该配置时抛出 FileNotFoundError：

1. test_closure_failure_still_closes_and_archives_failed_trial
2. test_observer_cleanup_reporting_fault_still_preserves_and_archives_failed_trial
3. test_recording_closure_precedes_recorder_stop_and_archive

这些是测试夹具 ERROR；本次结果没有提供新飞行或闭环可靠性结论。完整失败栈保留在 [unittest.log](unittest.log)。文件来源、字节数和 SHA256 见 [manifest.json](manifest.json)，逐文件校验见 [SHA256SUMS](SHA256SUMS)。本快照不包含 rosbag 或其他原始元数据副本。

## 后续45独立定向验证

[followup45](followup45/) 原字节保留后续主树夹具修复后的 Linux 定向验证日志、四个输入源文件的哈希清单及实际执行脚本。日志为 Ran 13 tests in 1.517s、OK，无跳过；范围仅为 tests.test_simulation_seed 与 tests.test_recording_qos。执行者另行观察到退出码0；这三个文件中没有独立的终态退出码凭据。

此13项只属于后续45定向验证，不能计作44通过，也不能替代45全量构建或测试。本目录不包含45全suite结论。原 .sha256 文件绑定四个输入源文件，并不是日志哈希清单；快照内日志本身的 SHA 另列于本目录 manifest/SHA256SUMS。44原全量FAIL保持不变。
