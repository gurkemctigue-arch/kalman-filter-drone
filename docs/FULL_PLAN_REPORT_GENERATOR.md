# 中文研究结果报告生成器

2026-10-28 交付更新：正式 `v3` 主研究 166/166 槽、主离线、独立工程扩展及补充后处理均已终态；最终报告已从实际台账生成，并绑定当前来源摘要。最新交付状态和本地报告入口见 [三阶段交付状态](DELIVERY_STATUS.md)。工程失败、证据不完整和不适用项均保留，完成报告不等于所有性能验收通过。

## 历史工具协议与进度快照

以下保留报告生成器准备期间的说明和示例；“尚未完成”“未使用实际正式汇总生成报告”等句子属于当时状态。复现时以当前脚本接口与交付状态中的实际工件为准。

当前正式研究为 `v3`：冻结 Linux 环境 531 项测试、四个 ROS 包构建和导入路径隔离均通过。2026-10-27 首个外部守卫槽 PASS 后的检查点为主 101/166 终态（67 PASS、34 FAIL、65 PENDING），剩余槽已开始逐槽续跑；主离线队列及独立 16 项扩展尚未完成。以下路径对应当前冻结目录，最终完成度以原始清单和评价 JSON 为准。冻结 SHA 与运行方法见 [研究运行说明](FULL_PLAN_RESEARCH_RUNBOOK.md)，完整最终交付顺序见 [v3 交付命令](FULLPLAN_V3_DELIVERY_COMMANDS.md)。

旧 `v1` 的 8 次正式尝试按原评价仍为 7 PASS、1 FAIL，v1/v2 原计划、录制、报告和失败保留，不计入 v3 的 166 次分母。评价修订 3 已对原汽车 raw bag 独立核对为 PASS，并另存报告及 SHA 审计；原始 FAIL 和修订 2 FAIL 继续保留，见 [评价修订 3](EVALUATION_REVISION_3.md)。当前 car position seed08 的原 FAIL 属于独立确认的压缩/原生解压证据异常，不能作为完整可评分算法性能样本；真实诊断范围见 [bag 审计](V3_BAG_INFRASTRUCTURE_AUDIT.md)。

`scripts/build_full_plan_report.py` 是独立后处理工具，只读取已经保存的小型 JSON，并检查显式指定的证据文件是否存在。它使用 Python 标准库，不导入 ROS、NumPy、YOLO、绘图工具或正式实验总入口；不读取 bag，也不重新计算 bootstrap。

该文件位于 Windows 主副本，供正式研究结束后的交付使用。不得将主版工具的后续修改同步进已经开始执行的冻结研究。当前未使用实际正式汇总生成报告，不把测试夹具算作研究结果。

## 最终生成

以下命令在 Windows 项目根目录运行。路径以实际交付目录为准，保持原始 JSON 和失败记录完整。不存在的可选输入会明确标为缺失；给出的 JSON 若损坏则拒绝生成。

```powershell
python scripts/build_full_plan_report.py `
  --summary results/frozen_fullplan_v3/full_plan_research_v3/summary.json `
  --engineering-manifest results/frozen_fullplan_v3/extended_engineering_v3_matrix/manifest.json `
  --engineering-summary results/frozen_fullplan_v3/extended_engineering_v3_matrix/summary.json `
  --plan results/frozen_fullplan_v3/full_plan_research_v3/plan.json `
  --environment results/frozen_fullplan_v3/environment_manifest_before_formal.json `
  --trial-root results/frozen_fullplan_v3 `
  --output results/frozen_fullplan_v3/研究结果报告.md
```

`--environment` 使用正式运行前保存在冻结 results 根目录的 `environment_manifest_before_formal.json`，不是 `freeze_validation/environment.json`；本轮 [v3 环境清单](../results/frozen_fullplan_v3/environment_manifest_before_formal.json) 已生成，实际为 Ubuntu 24.04.1 / ROS 2 Jazzy / PX4 v1.17.0 / Gazebo Harmonic，不能写成 Ubuntu 22.04/Humble 已验证。历史检测评价默认读取主副本的 `results/detection_research/detection_report.json` 与 `visual_review.json`，可用 `--detection`、`--review` 改为归档位置。

每个 `--video <路径>` 增加一个演示视频链接；每个 `--evidence <路径>` 增加一个其他证据链接，例如验收网页、图表清单、接触表或复现说明。工具不解码视频、不检查播放质量，也不递归搜索结果目录。生成报告和证据建议放在同一个磁盘卷，链接按报告位置转换为相对路径；空格、中文路径会编码。跨卷证据明确提示重新安置报告，不生成伪装成相对路径的链接。

输出为中文 Markdown 和同名 `.sources.json`。来源清单记录读取的 JSON 路径、是否存在、字节数和 SHA-256，以及生成脚本与 Markdown 的 SHA-256。拒绝输出覆盖任何输入 JSON。

## 报告中的判断约定

- 166 次主研究与额外 16 次工程试验分别统计。166 中包含 160 次重复研究与 6 次工程安全检查；额外 16 的每个条件只有 1 次。
- 执行台账完整需要主 166 个不同条目及额外 16 个不同、绑定冻结计划的条目都进入终态，并有 166 个主研究离线终态。终态可包含 FAIL、INCOMPLETE、INTERRUPTED；完成记录不表示全部通过。`NOT_APPLICABLE_NO_SELECTED_TASK` 表示唯一实例歧义试验有意没有被选目标。
- 缺失、PENDING、运行中、未知状态或汇总/清单绑定不一致会使报告明确显示未完成。汇总状态计数与逐次清单冲突会在报告中列出。
- 阶段一按真实逐飞行的类别、控制模式和估计方法计算终态非 PASS 率及 Wilson 95%CI，排除 PENDING、运行中和未知状态，零终态的率与区间缺失。性能均值及其缺失数仍引用原 groups；原保存失败率仅作来源诊断，非全终态时隐藏其率及区间。adaptive − baseline 的全可测配对和双方 PASS 条件配对继续直接引用，保留 n、排除数和区间，不选择性隐藏不利比较。
- 阶段三采用 active − midpoint 的实际同 seed 配对，并按类别、云台模式从逐飞行结果计算终态非 PASS 率及 Wilson 95%CI，列出全部条目、终态分母、PASS、非 PASS 终态、PENDING 和其他/运行中数量；零终态的率和区间保留缺失。
- 阶段二同时显示检测机会、任务机会、CORRECT、WRONG、UNKNOWN、NOT_OBSERVED/NO_FRESH 和缺失物理报告。失败率主结果从同类别 crossing 的 `summary.trials`（缺少时用该组 `per_seed`）计算，仅终态进入分母；PENDING、运行中、未知状态排除，零终态保持缺失，不含 6 次工程安全检查。原 `failure_rate` 的分子/分母只作来源诊断；只有可核对逐飞行条目全部终态时才显示其原率及 Wilson 95%CI。没有观察到错误匹配不能认证未知区间。
- 未稳定为右删失，缺失窗口单列。条件稳定时间和显式重选确认时间必须与删失数同时阅读，任务窗口不能当作独立重复。
- 视觉误差条件于检测框可观测。延迟终点是跟踪命令，使用仿真时间，不称为 PX4/执行器响应、墙钟实时或实机验证。
- 历史静态 132 标签的当前批准数从审核 JSON 读取，检测指标逐录制引用，不把它们扩展为遮挡、多目标或真实世界指标，也不把 AP 简单平均称为合并 AP。

失败附录使用主汇总内已有原因，并链接本地原始 JSON。若汇总没带细项，报告明确写明“不能据此编造原因”。扩展试验另有逐次状态及失败原因表。视频未显式提供或文件缺失时，不把视频列为已交付。

## 轻量验证

```powershell
python -m unittest tests.test_full_plan_report
```

测试仅创建临时小 JSON 和空视频占位文件，验证未完成、负结果、配对分母、身份未知、右删失、来源哈希与相对链接。它不会调用正式汇总、绘图、仿真、YOLO 或 bag 读取。
