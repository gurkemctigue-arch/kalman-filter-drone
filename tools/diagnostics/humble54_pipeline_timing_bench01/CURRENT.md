# 当前可审查版本

当前运行源码以 `source_sha256_windows04.json` 为准，清单原字节 SHA 为 `1992ccaa860bf129b80d3de30ec67d8ebf2baa1181efac79f711a9913a63dfd9`。独立复核记录在相邻的 `../humble54_pipeline_timing_review01/independent_review01.json`，其 SHA 为 `bd0f6228162694f7ed56be9cb3e0c11ddbecf68e7c9a0853b30222472e7e4316`。

`validation_windows04.json` 和 `test_windows04.log` 是这版实际的 Windows 假对象测试记录。01—03 文件只保留准备过程的历史摘要，不能用它们的源码摘要校验当前源码。README 末尾对 01 的引用属于初次准备说明；当前以本页和 04 清单为准。

这版通过了 20 项作者测试、独立破坏归因及端点隔离检查。当前尚未执行原生完整管线回放，实际软件时延样本仍为零。原生短回放必须等 collector07 及其子进程全部真实退出，再显式使用 README 中的命令。原命令自行持有项目锁，无需外层另加 flock。

原调用一次和对象保持的检查不证明没有开销。钩子包含取消息时的 Python profile、字段快照、JSON 编码、锁及队列操作；所得时延只描述被观察的独立软件回放。历史 strict UNKNOWN 和物理 E2E 结论均不变。未来实际运行状态以本次新输出目录中的原始日志和 summary 为准。
