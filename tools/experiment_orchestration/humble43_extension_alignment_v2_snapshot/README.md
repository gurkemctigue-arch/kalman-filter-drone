# Humble43 扩展合同对齐 v2：工具与验证证据快照

这里保存外部验证目录实际部署的 revision02 版本：10 个 v2 工具文件、首版与修订版闭合清单，以及必要的小型验证记录。归档时逐文件核对了实际部署字节与 revision02 清单；此目录用于源码审查和结果追溯，组件验证不能代替飞行验收。

## 对齐了什么

原冻结研究协议允许扩展压力场景保留算法 FAIL，前提是运行完整、证据可评价、安全条件成立，且由原判定函数重新计算并精确披露全部允许的失败。原始 FAIL 必须继续作为 FAIL 进入分母、统计和报告。后加外部包装器要求扩展 16 项全部 PASS，本次 v2 去掉这一额外限制。

核心 12 项和安全 4 项仍必须全部 PASS。缺失证据、无效报告、基础设施中断、不安全的丢失/悬停/重选行为，不能包装成允许的算法失败。源、模型、时钟、原生启动、录制闭合、进程退出、原报告绑定及安全检查继续由原冻结代码判定；没有新增失败白名单或降低阈值。

v2 校准只使用原来指定的行人、汽车 `stage1_velocity_seed004` 两条核心 PASS 录制。完整扩展合同通过与“全部工程项 PASS”分别记录，实际状态、计数及每项失败披露保持可见。正式实验仍需要实际注册、完整安全证据、源封存、容量准入及原 guard 校验。

政策决定的时间为 **2026-10-31 23:07:05 UTC**。协调器当时确认 extension43 尚未规划或执行；这是在新扩展结果产生之前固定的规则。`policy/PRE_OUTCOME_DECISION.md` 等文件保留当时的历史措辞，当前验证状态以下表及原始证据为准。

## 已有验证与未完成部分

| 批次 | 原始结果 | 解释 |
| --- | --- | --- |
| Windows01 首轮 | 校准 3 个 ERROR；连接 15 个 ERROR，其中含 14 个子测试错误 | 原错误日志和结果保留在 `evidence/windows01/`。之后只修测试夹具与平台处理，没有重写首轮结果。 |
| Windows02 revision02 | 85 项：78 PASS、7 个明确的平台跳过 | 9 项真实冻结判定集成测试全部通过；3 项惰性 describe 的实际摘要与闭合清单一致。 |
| Humble native02 | 85 项：76 PASS、9 ERROR、0 跳过 | 校准 30 项与 seal 15 项全通过；连接 31 项通过，9 项真实判定集成测试在构造合成矩阵时遇到全机 SITL 锁忙。 |

native02 的 9 个 ERROR 都停在原 `run_lock` 的非阻塞 `fcntl.flock(..., LOCK_EX | LOCK_NB)`，异常为 `BlockingIOError: [Errno 11]`。当时原 core driver 正在占用全机锁。测试未进入这些场景的判定断言；原错误保持 ERROR，不能改判 PASS。获取失败仅关闭本次句柄，没有删除锁文件、强行释放其他进程的锁或发送飞行控制命令。独立诊断见 `evidence/native02_lock_contention_diagnostic01.json`。

**仍需补验：**等原 core12 driver 完全退出、owner 正常闭合且无仿真/录包/飞行残留后，在 Humble 使用新的输出目录，原样运行全部 85 项及 3 项惰性 describe，再独立审查结果。不要修改或绕过原锁，不要把部分平台上的通过合并成一次完整原生验收。

这份快照不表示 core12、安全4、扩展16或正式280次飞行已验收通过，也不授予新的 admission、计划或飞行权限。

## 目录与追溯

| 路径 | 内容 |
| --- | --- |
| `external_tools/` | 实际部署的 revision02 工具字节，共 10 文件。 |
| `manifests/` | 首版和 revision02 的闭合清单；首版清单用于保留版本历史，当前工具按 revision02 核对。 |
| `policy/` | 事前政策说明、最小语义差异、版本并存策略、测试边界和 revision02 夹具差异。 |
| `evidence/windows01/` | 首轮两组错误的原结果与原始日志。 |
| `evidence/windows02/` | root 汇总、三组结果与日志、三项 describe。 |
| `evidence/native02/` | Humble root 汇总、三组结果与原始日志，包含原锁冲突错误。 |
| `ARCHIVE_MANIFEST.json` | 归档文件、来源、字节数和 SHA256；保留原文件中的外部路径作为历史绑定。 |
| `SHA256SUMS` | 归档载荷与归档清单的 SHA256，不包含它自身。 |

revision02 的实际连接摘要为 `556d5fcd280a92ac50e7cbad2c7e0b634841e046172fa29a0ec1274a075f9531`，校准摘要为 `02ed94b29a4aa207b9860474c595e382d29ef7eada314c46a2eaedaa0754eb8c`。seal 源内固定绑定该连接摘要。

原证据中的 `path` 指向执行时的外部位置；归档不改写这些字节。归档清单提供这些原始文件到本目录的映射。只归档了说明上述结论所需的小证据，未复制 1940 文件总清单、私人磁盘盘点、模型权重、rosbag、遥测大文件或完整冻结源树。

## 环境与依赖边界

实际工具运行目录是 Windows 的 `D:/WSL/UAVHumble22-validation`，对应 Linux 的 `/mnt/d/WSL/UAVHumble22-validation`。实际原生验证环境是隔离的 `UAVHumble22`，使用其 Humble Python、已核验冻结源和固定 PX4/Gazebo/桥接环境。

这些工具依赖同一外部目录中未变的 `development_runner`、`development_safety`、`development_extension`、`reviewed_freeze_build`、`reviewed_timing_diagnostic`、`local_runtime_observer41`、`bounded_humble33_action` 以及原 prepare/build/publisher、skip contract、candidate assembler 等具名工具和传递依赖。实际依赖身份由各 manifest 的固定摘要与 origin 检查共同约束；这 10 个文件并不是独立运行环境。

**不能直接在任意克隆中运行这份快照。** 归档路径不是生产工具目录，借用依赖、固定路径、实际环境和独立审查输入均不在此自动重建。不要通过改全局模块别名、删校验、覆盖 v1 或重写旧 admission 来适配路径。需要复现时应先建立完整、具名、可核对的环境与证据连接。

归档过程只复制和校验小文件，未执行导入、测试、WSL 命令、计划或仿真，也未提交 Git。
