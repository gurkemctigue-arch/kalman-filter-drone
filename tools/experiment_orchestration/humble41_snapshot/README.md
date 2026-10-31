# Humble41 外部仿真工具源码快照02及扩展进度补充

原快照02已提交至本仓库；原 manifest 保留创建时的草稿状态和时间，不改写历史清单。最新执行情况见[当前进度](../../../docs/LIVE_PROGRESS.md)，下文原时间快照保留。

草稿01只在交付准备清单序列化上失败：跨 JavaScript 传递把部分 `1000.0` 等浮点数变成整数，使6个嵌套 manifest 快照无法重算声明的 canonical SHA256。01原件保留，不作为发布候选；49个原源码文件的字节、已验证的工具本身和实际飞行均未改变。草稿02在同一 Python 进程内取得原始 manifest 对象、保留浮点类型并保存，且从最终落盘 JSON 独立重算全部11个 canonical。

本目录补充主工程未纳入 Git 的外部工具、测试和使用说明。它必须与主仓库 https://github.com/gurkemctigue-arch/kalman-filter-drone 配合使用；本目录不是独立的无人机跟随系统发行版。

主工程基准提交：`8d542aff7827fded5b371971795796ce751a17aa`（`Isolate runtime health sampling from archive I/O with explicit tmpfs output`）。本包创建没有修改主工作区、旧工具、冻结根或远端；也没有启动飞行。

## 实际进度与证据边界

在 `2026-10-31T08:49:14.544247+00:00` 只读核对原 core41 小型槽 JSON 时：12 格中 **1 PASS / 1 RUNNING / 10 PENDING**。已完成 `person_stage1_velocity_seed004`，当时运行 `person_stage1_position_seed004`。这是带时间戳的历史进度快照，不是独立审计，也不是本包生成时的新一次扫描；后续状态由原结果记录确定。

原 core40 保留 **3 PASS / 1 INFRA_ERROR / 8 PENDING**；原失败槽和原始 spool 不重评、不改写。本包没有宣称阶段一至三、四安全、扩展16、正式280、20×4离线比较或项目最终验收全部完成。

formal41 adapter 已有 Windows 18 项 pure/fake 测试和 root 实际 Linux 18 项 fake 测试通过记录，以及独立静态审查；这些机器上的历史记录未复制进本源码包，也不等于正式飞行通过。只存在工具源码不能建立准入。

## 内容

- `external_tools/`：原快照02的49个文件保持逐字节不变，包含43个最小闭包文件、2个依赖回归测试和4份使用/命令参考；另有下述独立进度补充的3个文件。
- `delivery_manifest41_draft02.json`：逐文件大小、SHA256、依赖理由、11个实际工具 manifest 快照及 canonical SHA256。
- `delivery_manifest41_draft02.md`：恢复要求及本机历史依赖说明。
- `.gitattributes`：为 `external_tools/**` 禁用 Git 文本换行转换。旧依赖中存在 CRLF，不能全目录转 LF。

## 扩展16进度补充01

`extension_progress_manifest01.json` 单独绑定新增的 `bridge_humble41_extension_events01.py`、其测试和 `humble41_followup_progress_connection01.md`。它引用原 manifest 的文件SHA，未修改原49个文件或运行中的核心进度桥。

新桥仅把原 `EXTENSION_PROBE` 两类八条件、seed004的完整16槽记录转换为现有页面事件，复用原扫描器、PID身份检查和末次扫描。九项私有JSON测试通过，独立静审已完成；工具canonical为 `6cc8c7c7a536767c615f9904103b6f376ddba8fb0558b492173157fe98c27429`。它不启动仿真，也不授予安全、扩展或正式实验准入。实际扩展计划、PID和桥尚未创建或启动。

恢复时把这三个补充文件与原49个文件放在同一目录；`watch` 必须显式绑定真实原计划文件SHA、同OS的生产者PID和创建token，以及全新输出目录，**没有 `--kind` 参数**。接线说明保留作者提交时“待独审”的时间状态；本节及补充清单记录随后取得的独审。安全4仍只能用原monitor观察命令心跳和退出状态，不能套用核心或扩展桥伪造槽计数。

需要重现这组小型测试时，从 `external_tools` 目录运行 `python -B -W error::ResourceWarning -m unittest -v test_bridge_humble41_extension_events01`。测试只使用私有JSON和模拟PID，不读取真实计划或启动WSL；通过不等于实际扩展实验完成。

40个直接绑定文件之外，必须额外保留 `bridge_formal280_events01.py`、`formal280_serial_guard01.py` 和 `verify_humble33_imports.py`。最后一个文件只为 `test_reviewed_freeze_build.py` 的 AST fixture 保留；**不要导入或执行它进行清单检查**，它的顶层代码会调用历史 build review。

部分运行 manifest 明确绑定测试文件的哈希，因此测试文件也属于工具身份闭包。这里没有复制所有旧33脚本：若某文件只出现在历史保留映射或未使用的旧 CLI 字符串中，不据此把整段历史工具链当成当前运行依赖。

## 新机器环境与可迁移性

主仓库全部源文件仍是必要条件，包括 `uav_tracking/`、ROS workspace源码、launch/config/world/model元数据、`scripts/`、`tools/`、补丁和构建说明。只拿本包中的 guard、runner 或 collector 不能飞行。

现有 `.sh` 和部分 Python 入口绑定以下实际布局：

- WSL distro `UAVHumble22`，Ubuntu 22.04、ROS 2 Humble、Gazebo Harmonic。
- 外部工具同目录 `/mnt/d/WSL/UAVHumble22-validation`；Windows 对应 `D:\WSL\UAVHumble22-validation`。
- 开发根 `/root/uav_tracking_fullplan_v4_humble41`。
- Python venv `/root/uav_humble22/venv/bin/python`；PX4 `/root/uav_humble22/PX4-Autopilot-v4mag`。
- `ros_gz_shutdown_A01_ws`、基础 `ros_gz_ws`、`px4_msgs_ws` 和 `agent_install` 及其真实可验证构建。
- `ROS_DOMAIN_ID=73`、`GZ_PARTITION=uav_humble22_validation`、`GZ_IP=127.0.0.1`。
- 真正的私有 tmpfs `/dev/shm/uav_tracking_runtime_health`，有效 UID/0700 权限；归档位置必须在实际 root/results 的 `/mnt/d` 下。

从 GitHub 克隆不会自动恢复本机的32/40历史保留证据、独立审查、压力验证、PID创建身份、注册、最终seal、物理卷与容量事实。它们不是可从源码推导的许可，也不能用示例文件补造。新机器需要实测环境和独立的新版本/配置，重新进行源与构建验证、开发/安全验证、存储预算、校准、登记及封存。不得只替换旧证据中的绝对路径或SHA来假装迁移成功。

`assemble_humble41_source01` 特别描述本机的 source40→41 observer-only 过渡；压力前提还引用本机原40失败 spool。没有该真实历史备份时，这些固定入口不能在干净克隆上当作通用新安装脚本运行。详见 manifest guide。

权重、bag、遥测、视频、原实验结果、机器日志、身份/认证文件和工具二进制不在本包内。权重来源/训练与运行库环境按主仓库说明单独准备；不能声称这些已随本包提供。

## 参考说明的新旧状态

`external_tools/humble41_core_followups_commands01.md`、两份桥接 usage 和 serial usage 都保留原字节，因此其中某些状态陈述是创建当时的历史快照。例如 followups 第11节称 formal41 adapter 正在准备，早于随后完成的18项测试与独审。保留原文便于追溯；不能以它代替当前真实结果或最终运行授权。

core41 bridge 固定两类×六组 seed004 的12分母，不能拿它监测任意矩阵。formal280 bridge 需要真实120/160两份计划、文件SHA和同OS生产者PID/创建token。

## formal41 串行入口模板（仅供审阅，未执行）

只有真实开发与安全证据、最终根冷构建、容量预算、三份登记、120/160正式计划和实际sealed admission manifest全部满足后，才能填入下面的实际值。`ACTUAL_*` 是占位符，不能原样执行。没有默认 final root；adapter 从实际 sealed manifest 获取最终根与原guard。

```bash
python -B /mnt/d/WSL/UAVHumble22-validation/formal280_serial_guard01.py \
  --manifest ACTUAL_FINAL_ADMISSION.json \
  --output NEW_EXTERNAL_BATCH_DIRECTORY \
  --guard-command \
  /bin/bash /mnt/d/WSL/UAVHumble22-validation/formal41_guard_adapter01.sh \
  --manifest-sha256 ACTUAL_SEALED_MANIFEST_FILE_SHA256 \
  --reviewed-tools-sha256 dad2f80df700805f65b7bbb4cbcb80b6a1ca856527eb4eaa5f51e814ab2d6fbb
```

`--guard-command` 必须为最后一组选项；serializer 只追加 `run-one --manifest PATH`。adapter 保留原guard选槽、准入、容量、锁和argv，通过真实owner包装命令执行。owner原始终态必须落盘，native tmpfs停止先于有界D盘归档；归档候选副本本身不足以证明owner闭合。原算法FAIL保留；基础设施/owner失败触发STOP且不自动重试。

上述工具canonical只指向本包内这组精确源码。真实manifest文件SHA、最终根、state、计划、容量和证据必须来自实际独审；本包未生成或提供这些未来结果。

## 纯测试与安全清单检查

恢复源文件时逐项核对JSON中的相对路径、字节数和SHA256；本包创建仅执行源文件哈希、AST解析及无动作manifest函数核对，没有运行WSL、真实guard、build、Gazebo或SITL。

需要在新环境重跑pure/fake测试时，先显式指定完整主工程源根：多数fixture使用 `STAGE1_PROJECT_ROOT`，core41 bridge使用 `HUMBLE41_BRIDGE_TEST_PROJECT_ROOT`，formal bridge使用 `UAV_BRIDGE_PROJECT_ROOT`。这些路径只为测试注入项目源码，不能消除生产入口的固定历史证据要求。不要对目录做会导入历史生产校验文件的全模块自动执行。

源码发布以本仓库实际提交为准；源码归档、工具测试和进度页面均不能替代原始验收证据。
