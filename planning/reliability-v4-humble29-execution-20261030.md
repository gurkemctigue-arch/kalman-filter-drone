# Humble29 同源构建、启动修复与开发执行记录

2026-10-30，固定第二轮汽车权重与独立几何开关已进入新的 Humble29 冻结来源。四个 ROS 包实际构建和 Linux 检查通过；第一次 clean 在物理仿真恢复前因执行入口遗漏运行环境失败。修复入口后的 clean02 完成了 person 飞行，但收尾时钟证据未满足原验收契约，已停止后续运行。两次失败均保留。**这仍是开发验证，尚无 Humble29 工程验收通过结论；核心 0/12，正式协议仍为 DRAFT，正式 0/280。**

## 同源冻结与实际构建

冻结来源为提交 `9f714a664533fb42efb9ae6b1fd861e714abbe79`，包含 587 个冻结文件、285 个分类文件。汽车使用 `models/yolo11m_car_sim_train20_04.pt`，SHA-256 为 `bf7a56de4ae1658f8101fc6089247e8b984c2965b58d6b4963b4b5977e9ca00c`；`navigation_correlated_two_face_bound` 独立显式开启，行人不开启该几何选项。模型选择不隐式改变算法参数。

实际四包构建与验证均返回 0。Linux 全套共运行 **1505 项：1500 项通过，5 项按精确平台/工具条件跳过**；测试耗时 78.449 秒，验证总耗时 82.702 秒。跳过项为 Windows PowerShell、Windows 文件共享语义和当前验证环境缺少 Node/docx 的对应检查，原始测试 ID、理由与条件另存于构建收据，不能将其算作已通过测试。

9 个模块、4 个 ament 软件包均定位到冻结 29 来源；实际构建使用 `--merge-install`，四包前缀均为 `/root/uav_tracking_fullplan_v4_humble29/ros2_ws/install`。真实生成消息 CDR 往返 11 项检查全部通过。选定 A01 桥接的源文件和 ELF 验证通过，核对 71 个依赖及 1 个插件；这不替代飞行时实际映射验证。

全部 587 个冻结源文件前后字节不变。原 Humble28 的 89 个证据文件不变，核心结果仍为 **8 PASS / 4 FAIL**。新构建不能消除旧失败，也不能与旧来源的通过结果拼成新来源验收。

## 原 clean01：飞行前启动环境失败

原完整 12 格 seed004 PROBE 计划在 10:50:44 UTC 创建。10:51:13 UTC 开始 person clean20，约 9.70 秒后 flight 返回 1，10:51:24 UTC 批次停止；`terminal_count=0/2`，car 未尝试，核心 12 格均未运行。原计划、trial、终态、日志和 ext4 原始 spool 保留，没有覆盖或自动重试。

直接证据为 `agent.log` 中 `exec MicroXRCEAgent: not found`、Agent exit127，以及录包关闭证据中的 `physics_was_not_resumed`。原 01 wrapper 重置 PATH、手工 source overlays 后，遗漏冻结 `scripts/humble22_env.sh` 末尾的 Agent 路径与 ROS/Gazebo 通信域设置。故障发生在仿真恢复前，不能解释为目标检测或跟随算法失效。

独立 observer 进程正常退出、没有强制结束和新鲜度错误；聚合 `healthy_cleanup=false` 来自 driver 启动异常，不能误报为 observer 崩溃。清理后无残留仿真进程，冻结来源未变。原静态审查没有发现运行环境遗漏，其结论仅限当时的静态检查。

## 新 02 入口与已完成检查

新建五个独立 `development02` helper；原五个 01 helper、原构建入口、冻结 29 算法和旧收据一字不改。保持原先 base ros_gz → A01 overlay → px4_msgs → frozen29 的 source 顺序，补齐 canonical 环境：

- `ROS_DOMAIN_ID=73`、`GZ_PARTITION=uav_humble22_validation`、`GZ_IP=127.0.0.1`；
- `GZ_VERSION=harmonic`、`IGNITION_VERSION=''`；
- PATH 前置 `/root/uav_humble22/agent_install/bin`，动态库路径前置对应 `agent_install/lib`。

26 项 Windows 纯夹具通过，Bash 语法检查通过，独立差异审查未发现阻断项。实际 `--preflight-only` 返回 0，并完成以下查询：Agent 的 `command -v` 精确指向已核 SHA 的安装文件；`ldd` 动态库全部解析；冻结 `run_stage1_flight.sh check` 的 person/car 两类检查均通过；四包前缀均指向实际冻结 29 merged install。上述命令只做文件、命令发现和软件包查询，没有启动 ROS 节点、仿真、录包或飞行。

新 prefix 检查最初假设独立安装布局，首次只读 preflight 因此拒绝；查阅实际 `import_isolation.json` 后修正为本次真实 merged 前缀。该失败收据仍保留，没有创建计划或启动飞行。最终通过的 preflight 单独保存，未覆盖第一次结果。

新 helper manifest canonical 为 `a9e8a13ce7968c0637c8f8015e7e6c6ed559b44ec4941ecbd3012ecd86a21cf0`。每次实际 action 仍核同一冻结来源、构建收据、A01 bridge 和运行环境；轻量检查通过不等于闭环通过。

## 新开发计划、clean02终态与下一步

11:02:05 UTC，新完整 12 格 PROBE 计划实际创建成功，使用整数 seed004、两类各六组，不使用正式种子。新 plan 为 `reliability_v4_humble29_probe02_seed004_matrix/plan.json`，plan digest 为 `122f69541df6a02a8a871f275fa6f915305a7f8f03b20fb17903e3e217d71d7f`。它与原 plan01 分离，原 plan01 仍保持 0/12 已尝试。

新 clean 使用 `reliability_v4_humble29_clean20_serial02` 及 `clean20_02` trial 名，后续核心批次使用新 plan 目录下的 `core_serial02`。11:03:10 UTC，person clean20 开始；11:04:25 UTC 的 RUNNING 快照现为历史记录。飞行过程耗时 224.253 秒，返回 0；**11:07:45 UTC，独立评价未通过，批次停止为 `STOPPED_NO_AUTOMATIC_RETRY`**，停止原因为 `ValueError:Independent evaluation failed/incomplete: source_clock`。完整 clean 终态 0/2，car 未尝试，核心 12 格未运行。

源时钟原始、timing、adapted 三流各 3850 条，时钟域和坐标连续性检查通过，未缺证；原报告仍为 FAIL，存在 4 条 `diagnostic_delivery_outside_clock_contract`。原生启动报告仍为 FAIL，配置、起飞序列、起飞前就绪、交接稳定和视觉任务时序检查均通过，但 `full_recording_coverage=false`。收尾附近主包 `/clock` 比 timing/phase 落后约 56–80 ms，超过原 50 ms 门限；不能通过放宽门限、裁尾或只报飞行返回0改判。

导航记录覆盖率为 1.0，距离/高度 RMSE 约 0.298/0.338 m，末段稳定；这些局部数值不代替完整工程通过。归档的 60321 条消息完整性检查通过，冻结源前后不变，清理无残留。两次原始失败、两个原计划和全部评价报告保持原字节。

本机 `results/project_progress/humble29_clean20_02/index.html` 及原 `humble29_clean20/index.html` 分别保留 02 与 01 的停止记录，事件源为各冻结结果目录下的 `events.jsonl`；它们均不能表示30正在运行。

截至11:30 UTC，仅完成全新 Humble30 外部工具准备：复用成熟十件构建/复制/验证结构，另有两份最终源码登记入口和两份夹具文件。31项Linux轻量夹具通过，Python AST和两份Bash语法检查通过；独立绑定32份原29构建、两计划、双失败及相关小证据，其前后SHA一致，原29模板14件未变。原28的独立89件保留和8 PASS/4 FAIL不变，30磁场覆盖来源明确为冻结29。此时没有运行30源码登记、复制、构建、仿真或正式种子，两个30目标目录也未占用。生产收尾观察器、真实ROS探针及最终提交仍须完成，随后才能冻结新源；不能将工具夹具通过描述为修复已实机验证或新源闭环通过。

只有新同源两类 clean 完成、清理和证据检查正常，才执行核心 12 格；后续仍需 4 个歧义安全 probe、16 格扩展、定标、容量准入，以及冻结正式协议后的 280 次正式试验和完整交付。普通算法 FAIL/INCOMPLETE 保留并统计；基础设施、来源、observer 或残留进程错误停止批次，每个命名 attempt 只运行一次。

全部场景保持原 T4 与安全条件：RTF 0.25、flight wall 600 秒、观测 0.60 秒、预测/控制 0.75 秒、原生起飞 wall 180 秒及显式重选/身份保护，不通过延长期限掩盖失效。236 图 view038 的新增合并大框风险仍保留；新24单一 Prius 资产的检查不证明跨车型、实机或闭环泛化。

## 可核对的本机证据

下表 SHA-256 绑定实际原字节。冻结结果路径相对于本机 `results/frozen_fullplan_v4_humble29/`，外部 helper 收据路径相对于 `D:/WSL/UAVHumble22-validation/`。这些本机实验与机器环境证据没有作为代码仓库的公开附件上传。

| 证据 | SHA-256 |
|---|---|
| 外部 `humble29_final_source_review.json` | `4abde61e9cba0652b80755a194b608d1872f0db7dbab3417074d4c8e83bf1a1d` |
| 冻结来源 canonical | `ea0ed0cac924932d43a6b80b86aeaf279c46c6194f4e6d2347027d0818269dbc` |
| 冻结 source manifest | `5915439d116549717297380b5bc0f6f92502ed0aa2ef9646bf2895c12e9d1394` |
| `freeze_validation/build_validation_summary.json` | `af3fc5c1ac46cb4a285fcead13c873105a1ac1b7c326d36a9f09e81f955560d8` |
| `freeze_validation/unittest.log` | `6b8e87a00f5c71689d0bb1a95fa9a0acc0083850339543f0276e8e33a6677550` |
| `freeze_validation/generated_message_roundtrip.json` | `e8e5f287f812db113fbbf92b82e01eed8ac1235552ed0148b9c84bfda9043982` |
| 原 `reliability_v4_humble29_probe_seed004_matrix/plan.json` | `1544c32561be7b3981362a2fb5fb290ccde5ce1c5953ec8d26a22e26e5b85e7c` |
| 原 `reliability_v4_humble29_clean20_serial01/execution_terminal.json` | `171bfbfcc14a644823e73ed4fad94afa1b805ad394fa53ce027fa925e1272f9e` |
| 外部 `humble29_clean01_startup_diagnosis01.json` | `d41f935929e289e22e5dc1da15213b9f9209cc463c949c84f46ea4e4fc45a566` |
| 外部 `humble29_development_entry02_fixture02.json` | `55ca2ea124f1ce9f22ba8d2195abef23e466e6cc4ea97029d795cde6457874a8` |
| 外部 `humble29_development_entry02_preflight02.json` | `7e97edab5c1e6d5a27a74b8b6b3387e44f6ddd436f02998143e1cee83c4cce0b` |
| 外部 `humble29_development_entry02_independent_review01.json` | `af5dd5d345dcf672d680dd1c228cb0e0d6c5dd7528d8968cb540b1e2c87a1d23` |
| 新 `reliability_v4_humble29_probe02_seed004_matrix/plan.json` | `af8276f2f37c23dcc3ee5dafaffbe42af7a333643a6699cd3e48573075f86a3d` |
| 新 `reliability_v4_humble29_probe02_seed004_matrix/development_plan_receipt02.json` | `386f1aa6a3e654ee11ba8bd73bc319d2e63e7d0bbe3555a9983ad2d92a83b8e4` |
| 新 `reliability_v4_humble29_clean20_serial02/execution_terminal.json` | `10690c1ac1432176d6304ef1cf30a337d83054bc894a703835757bd184b0c4a3` |
| 新 `reliability_v4_humble29_clean20_serial02/person_evaluation02/px4_source_clock_evaluation.json` | `b6f12c6c8ca5aefc1fa837be5d551de47273332a3b9ad24ef4b14c22da76921b` |
| 新 `reliability_v4_humble29_clean20_serial02/person_evaluation02/native_startup_evaluation.json` | `0171b04400a6d5f60f18494b71157b44a048fabc1fb12679cffc78d7c52b1a48` |
| 外部 `humble30_helpers_preparation02.json`（31工具夹具及32份原29小证据） | `5d6ff2662b375511c501fd1b4b700523057febb246d8da04b3eb885b3fd125bd` |

本文件只记录此来源已经发生的构建、查询、失败和计划创建事实。后续实际状态以新目录的 `events.jsonl`、原始 slot 终态及小文件证据为准。
