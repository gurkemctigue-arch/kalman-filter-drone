# v3 剩余阶段二、三飞行的外部逐槽守卫

主版源码已通过 15 项守卫纯夹具测试，基础设施分类器通过 23 项，退出清理工具通过 26 项（Windows Python，2026-10-27）。真实守卫飞行尚未执行。必须等待 rosbag/临时解码诊断结束并确认环境可继续后再启动；不能与诊断、仿真或离线分析并行。

原 v3 已记录的 100 个阶段一终态保持原样，包括 `car position seed08` 的原始失败。那次评价器曾报告 SQLite error 11 并未生成评价 JSON。[独立解码审计](V3_BAG_INFRASTRUCTURE_AUDIT.md)已确认 zstd 帧未正常结束，独立解码得到完整 SQLite，ROS 原生路径少输出最后 128 KiB 并重现错误；压缩未结束的原因未知。这是评价基础设施/证据问题，不能写成原始 SQLite 内容损坏或跟踪算法误差，不覆盖或重试该正式试验。

`scripts/run_guarded_full_plan.py` 从 Windows 主版运行，调用原有冻结 `/root/uav_tracking_fullplan_v3/scripts/run_full_plan_research.py`，每次严格传入 `--phase flights --resume --stop-after 1`，只推进一个原有 PENDING 槽。默认只读计划并打印命令，不启动进程或创建输出。它不复制新代码到冻结根、不导入或替换冻结 master，也不改变预注册、模型、控制参数和 166 次分母。

## 执行前后的检查

守卫校验准确的主计划 SHA、166 个名字、100+66 阶段分组、源码 SHA 与预注册 SHA。原计划的 `--output results/full_plan_research_v3` 保持相对路径原样，矩阵清单的相对路径始终以冻结根解释。

首次只接受原有 100 个阶段一槽全部终态；不重新评价历史失败。每次调用前后比较全部 trial row：只能有被选中的一个 PENDING 槽变成终态，其他 165 行必须不变。第一次创建 66 槽清单时，以主计划绑定的规范 PENDING 逻辑行比较，允许清单物化而不误报其他 65 项被修改。已有 PENDING 目录、RUNNING/未决清单、重复或外来槽均拒绝。任何新失败都保留，不重试失败名字。

整个守卫会话持有冻结根名字派生的 `/tmp/uav_tracking_guard_*.lock`。每次启动前、结束后再检查原正式研究 writer lock 和 `/proc` 进程空闲；启动子进程前释放 writer lock，让原 master 自己取得锁。若其他 writer 抢先启动，原 master 的锁会拒绝并使守卫停止。守卫不会批量杀进程来制造空闲状态。

新槽必须具备各自预期的评价报告、执行日志、returncode 和相互一致的记录，且符合现有 schema：阶段二 safety 为 schema 1，auto-unique 为 schema 2，云台为 schema 3，阶段三 flight 为 schema 3。报告须绑定本次 bag、类别、云台模式或安全/跟随配置；终态还须符合原冻结运行器的退出码与评价结论公式。

轻量输入下限为：bag metadata 声明正数车辆里程计消息、报告中核心消息类型可用和正数已解码 clock、没有解码错误或不可用类型、独立 runtime telemetry 确有车辆样本。阶段三 flight 报告还必须给出正数已解码 `/vehicle/odometry` 计数。阶段二 safety schema 1 没有通用的 bag 里程计解码计数字段，这一限制保留在守卫报告中，不能把类型清单说成已验证的解码计数；auto-unique 尾窗速度样本为空可属于尾窗覆盖度失败。

正常完成的 `FAIL`、`INCOMPLETE_EVIDENCE`、`FAIL_OR_INCOMPLETE` 属于性能或覆盖度结果，继续后续 PENDING。阶段二/auto-unique 因负面结论返回 2 是已知行为。SITL 返回 1 只有在 monitor 正常时限结束、全部报告完整且存在已解码的负面结论、没有基础设施异常时才允许继续。ABORTED、crash、其他异常码、SQLite/archive/I/O 报错、解码错误、异常 traceback、缺失或格式错误的报告均停止，不启动下一槽；外层 master 非零也停止。

主版基础设施分类器只读取小型 JSON、telemetry 和每份评价日志至多 256 KiB 的头尾样本，不打开 bag 数据库。它报告的是评价器出现的异常，不能据此单独判定原始 bag 的固有损坏。没有评价尝试时缺少报告属于未知，不在起飞前误报；已经尝试却异常退出或没有完成报告则停止。

## 待执行命令

下面命令使用冻结环境启动主版工具。默认计划检查无需 `--execute`；正式继续时必须使用全新审计目录，已存在目录会拒绝，不覆盖历史会话。守卫执行前的 v3 只读检查为 PASS 66、FAIL 34、PENDING 66，历史 car position seed08 仍为 FAIL，主计划和原飞行小清单前后 SHA 不变。

2026-10-27 首个真实守卫槽 `s2_person_crossing` seed000 已 PASS，外部 guard 返回 0、`assessment.stop=false`、`errors=[]`，录制进程返回 0，decoded clock 样本为 15,385、runtime vehicle 样本为 290。原 100 行未改变，该检查点为 67 PASS、34 FAIL、65 PENDING；随后新的 `fullplan_v3_guarded_continuation_v2` 会话开始续跑剩余 65 槽。首次 `fullplan_v3_guarded_continuation_v1` 审计已存在，下面命令保留为启动语法示例，后续执行须改用不存在的新审计目录。该单槽安全 PASS 不替代尚未完成的物理身份/状态精度离线统计。

v3 绑定值为：主计划 SHA `58f509351f6f2efba6da33ea394feff0e81f10b5fde03ba2866de2ab5232af28`；预注册 SHA `1e2430af7eb5c89f3b7cc1b45ece0c9855bb5ca27b33be9c11d4753f0d3ecf78`；207 项源码摘要 map 的规范 JSON SHA `2da787b1824d519b678cc511b01e5ec03e6c0b6c009b3eac5c00c1a61eec139b`。执行前守卫会核对 map 中每个实际文件及预注册文件，冻结 master 也在每次子调用前验证原计划。已只读核对冻结 master 实际 SHA 等于计划中的 `7949eb7b75a552a3cfb421cb8f09254d585fe0014f8d130834e3073e046135d8`。

```bash
bash /root/uav_tracking_fullplan_v3/scripts/run_research_session.sh \
  /mnt/d/基于yolo和卡尔曼滤波/scripts/run_guarded_full_plan.py \
  --frozen-root /root/uav_tracking_fullplan_v3 \
  --study-output results/full_plan_research_v3 \
  --expected-plan-sha 58f509351f6f2efba6da33ea394feff0e81f10b5fde03ba2866de2ab5232af28

# 仅在诊断结束且环境经确认可以继续后执行；审计目录必须全新。
bash /root/uav_tracking_fullplan_v3/scripts/run_research_session.sh \
  /mnt/d/基于yolo和卡尔曼滤波/scripts/run_guarded_full_plan.py \
  --frozen-root /root/uav_tracking_fullplan_v3 \
  --study-output results/full_plan_research_v3 \
  --expected-plan-sha 58f509351f6f2efba6da33ea394feff0e81f10b5fde03ba2866de2ab5232af28 \
  --audit-output /mnt/d/基于yolo和卡尔曼滤波/results/fullplan_v3_guarded_continuation_v1 \
  --execute
```

`--max-new-flights 1` 可以只继续一个新槽用于工程复核；默认 0 逐槽继续全部剩余 PENDING。它始终逐次调用冻结 master 的 `--stop-after 1`。如果会话因新异常停止，应保留本次审计、失败槽和 PENDING 清单，诊断后使用新的审计目录继续 PENDING；不能修改旧槽结果或自动重试。

审计目录记录 `session.json`、逐槽 master 日志及实时刷新的 `events.jsonl`。计划和外部工具源码在飞行中变化也会停止。试验终态和统计结果仍由原冻结研究维护；守卫的独立判断不改写 trial row。所有飞行结束后才进入主离线、扩展和补充步骤，最后再运行独立的 [退出清理验证](CLEANUP_ENGINEERING_PROBES.md)。
