# 独立 16 项工程扩展的外部逐槽守卫

`scripts/run_guarded_engineering.py` 位于 Windows 主副本，使用主版增强基础设施分类器读取小型报告、metadata、runtime telemetry 和有限日志样本，不打开 bag 数据库。它不修改冻结源码、不导入冻结算法、不创建工程计划、不重试终态槽，也不改写主 166 条结果。

2026-10-27 授权空闲窗口中，新守卫的 13 项纯夹具全部通过，相关补充后处理与报告夹具 25 项全部通过；独立静态审阅未发现明确阻断问题。独立 16 项真实运行仍未执行，必须等待主 166 飞行和主离线分析结束。夹具通过不能代替真实工程验收。

执行顺序及完整 v3 命令见 [交付命令](FULLPLAN_V3_DELIVERY_COMMANDS.md)。必须先完成主 166 条飞行、主 166 条离线分析及汇总，再通过原冻结 `run_extended_engineering.py --plan-only` 新建独立工程 manifest。已有 manifest 使用原参数恢复，不能覆盖或创建另一个同名清单。

## 约束与结果解释

守卫读取准确的主计划 SHA，逐项确认原始三个矩阵中全部 166 条记录已为终态，再确认主 summary 的名字、状态、数量与实际记录一致。offline manifest 必须准确包含同一组 166 个名字，全部为 `RECORDED`、`INCOMPLETE_EVIDENCE`、`INTERRUPTED` 或 `NOT_APPLICABLE_NO_SELECTED_TASK`，且 summary 的离线计数一致。一个汇总布尔字段不能代替这些检查。

独立工程计划必须有 16 个不同名字和 ID，slot/trial 顺序完全绑定、计划 digest 正确、源摘要及预注册和资源参数与原主计划一致。这 16 项仍为每条件一次，不能混入 166 次主研究分母，也不能宣传为每故障或远距离条件十次独立重复。PENDING 槽已有结果目录、RUNNING/未知状态或主研究同名槽均拒绝。

每个子调用只执行原冻结入口 `--resume --stop-after 1`。会话与主守卫使用同一个冻结根派生的外部 guard lock；起止取得原 writer lock 并扫描仿真/研究进程。子入口运行时由原入口持有 writer lock。其他 15 条 slot 行必须完全不变；主计划、summary、offline manifest 和原主矩阵文件的 SHA 在整个工程会话中保持不变，外部守卫、共享助手、分类器的 SHA 也固定。

原 16 项入口只要历史有 FAIL/INTERRUPTED 就返回 2。因此，本次守卫用全清单实际终态计算预期外层退出码，允许“历史有 FAIL、本次新槽 PASS、外层仍为 2”的正常行为；非预期退出码停止。

每个新槽须具备本次精确路径的 SITL 与 flight_eval 日志、schema-3 安全报告、报告原文 SHA、类别/距离/高度/整段评价配置，以及实际 run_config 的资源、检测器、控制模式、随机种子、命令和故障参数。报告 bag、runtime telemetry 和 monitor summary 路径必须指向该槽，不能借用其他槽的报告。报告必须有正数已解码 clock 与里程计计数、核心消息类型且无解码异常；独立 runtime 必须有车辆样本；metadata 必须声明正数核心消息数。

正常完成的 FAIL 或 INCOMPLETE_EVIDENCE 保留并继续后续 PENDING。安全评价器完成正面或负面报告时都应返回 0。SITL=1 只有 monitor 正常时限结束且已有可信负面报告才可继续；其他异常码、缺失报告、SQLite/archive/I/O 错误、崩溃和异常 traceback 均在下一槽前停止。不能为了继续而删除失败、清空终态或修改正式判据。

## 验证范围

`tests/test_guarded_engineering.py` 使用临时小型夹具，覆盖主/离线完整性、计划和路径绑定、逐槽不变量、历史失败退出码、普通负面结果继续、报告配置/SHA/外部日志错误停止以及保留 PENDING。它不启动 ROS/PX4/Gazebo，不执行评价器或解压真实 bag。

本轮已在空闲窗口执行以下命令，结果 13/13 PASS。后续只有新改动或未解决问题需要重查时才重复：

```powershell
python -B -m unittest discover -s tests -p test_guarded_engineering.py -v
```

夹具通过后仍需在真实 Linux 环境先做只读校验和单槽运行，再检查审计 `session.json`、`events.jsonl` 与原始工程 manifest。首槽通过且没有基础设施停止后，使用新的审计目录继续剩余槽。完成执行只代表所有计划证据已尝试并保留，不能替代全部验收条件通过的结论。
