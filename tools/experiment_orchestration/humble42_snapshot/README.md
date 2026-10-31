# Humble42 外部编排工具源码快照

本目录保存当前独立复核过的外部工具、测试、说明和小型来源元数据，供 GitHub 代码审阅。它不是独立系统发行版，也不授予新机器运行准入。打包没有启动实验、读取录包、运行校准或修改 Git；没有复制权重、实验大包、视频、遥测、认证信息或机器运行日志。

在 **2026-10-31 16:50:10 UTC（北京时间 2026-11-01 00:50:10）** 对真实 Humble42 核心计划的小型槽 JSON 做只读扫描时，12 个槽为 **1 started / 0 terminal / 11 unattempted**，首槽为 `person_stage1_velocity_seed004`。这是带时间的观察快照，后续状态应查原始实验记录或进度页面；它不是通过率，也不表示阶段或项目已验收。进度桥只转发原始状态，保留 FAIL 和 UNKNOWN，PID 退出不会产生 PASS。

`snapshot_manifest01.json` 列出每个新文件的原始字节数和 SHA256、全部 8 组实际工具 manifest/canonical，以及与已提交 `../humble41_snapshot/external_tools/` 中逐项同 SHA 的旧依赖。旧依赖未重复复制。源码和 JSON 元数据使用 `.gitattributes -text` 保留原始换行字节。旧说明/独审保留各自创建时的状态，最终身份以快照 manifest 和最终独审为准。

新工具包括 core12、512 资源检查、构建补充、safety4、extension16、完成录包的 stat-only 容量统计、两个具名 seed004 velocity 录包的校准包装和通用只读进度桥；另有 source/candidate PENDING 组装器及其现有测试。正式迁移/注册工具未纳入。校准仅在实际同候选 core12+safety4+extension16 全 PASS 且原监控 owner 健康退出后，才可能执行独立审过的三条命令；产物必须仍为 `CANDIDATE_NOT_REGISTERED`。其独审 24 项小测试通过，进度桥 6 项小测试通过，均不等同真实实验完成。

**本快照无法直接在一台新机器上运行。** Python 源码要求旧、新外部依赖位于同一具名目录；当前快照有意通过 manifest 引用旧目录，未增加自动安装或复制入口。生产 shell 仍绑定 WSL `UAVHumble22`、Ubuntu 22.04 / ROS 2 Humble、Gazebo Harmonic、PX4/px4_msgs/ROS bridge/venv、`ROS_DOMAIN_ID=73` 及本机目录。运行还依赖完整主仓库源代码、权重、真实构建/运行库证明、完整历史原始证据、实体卷容量和有效准入/实际合同。JSON 中保留的本机绝对路径和旧 SHA 是历史来源信息；复制或改写路径不能代替这些事实。

新机器必须先配置环境和模型，重新测量并独立复核 source/build/runtime/storage，再按各工具原始要求生成真实证据、审过的候选和实际合同。源码归档和当前机器的历史元数据不能授权新机器；也不能从示例重建缺失证据。请勿批量 import/自动执行本目录或旧目录：部分历史辅助文件有顶层校验，生产入口可启动真实任务。

借用旧闭包时，先逐项核对 manifest 所列仓库路径、字节数和 SHA，再在受控环境中审查恢复布局；不要在源码快照上改 root 常量或重写旧证据以绕过绑定。完整的主工程仍是必要依赖。`metadata/` 是小型来源及独审证明的副本，所引用的大型原始证据、作者机器日志、运行目录和动态 watch 输出均未上传。快照 manifest 列明这些缺口；没有声称已复现或已完成未来安全/扩展/正式280实验。
