# Humble41 源码交付清单草稿 02

草稿01只在交付准备清单序列化上失败：跨 JavaScript 传递把部分 `1000.0` 等浮点数变成整数，使6个嵌套 manifest 快照无法重算声明的 canonical SHA256。01原件保留，不作为发布候选；49个原源码文件的字节、已验证的工具本身和实际飞行均未改变。草稿02在同一 Python 进程内取得原始 manifest 对象、保留浮点类型并保存，且从最终落盘 JSON 独立重算全部11个 canonical。

本清单从11个实际工具manifest、递归同目录import和已核实AST fixture推导。包含49个原源码/测试/用法文件，全部按原始字节复制；不复制机器结果，也不创建准入。准确SHA、大小与tool canonical见同名JSON。

## 最小闭包

- 40个工具manifest直接绑定文件。
- 同目录读取器 `bridge_formal280_events01.py` 与formal测试所需 `formal280_serial_guard01.py`。
- `verify_humble33_imports.py` 仅供 `test_reviewed_freeze_build.py` 读取AST，不导入、不执行。
- 另外保留2个借用依赖回归测试和4份原使用/命令说明，共49个原文件。

原工具manifest还绑定完整主仓库内的动态依赖；主工程提交 `8d542aff7827fded5b371971795796ce751a17aa` 必须另行克隆。这里并未把少量工具文件描述为完整运行系统。

## 环境前提

当前入口绑定 Ubuntu22.04 / ROS2 Humble / Gazebo Harmonic、`UAVHumble22`、`/mnt/d/WSL/UAVHumble22-validation`、`/root/uav_tracking_fullplan_v4_humble41` 和 `/root/uav_humble22` 下真实构建的venv/PX4/ROS桥/消息/agent安装。源码兄弟文件必须保持原名和字节；Git须保留已提供的 `.gitattributes`。

owner要求真实私有tmpfs `/dev/shm/uav_tracking_runtime_health` 及UID/0700校验，D盘归档必须在实际root/results内；不允许用普通目录伪装tmpfs或以归档候选状态代替实际owner终态。

## 本机历史依赖，不随源码发行

- generic review依赖closed32及前序capsule与其真实哈希/审查关系。
- assembler仅适用于本机source40→41转换，绑定前序提交 `0f75efc724875647e8c15d264e64da9f4fa0af78` 与原40的3PASS/1INFRA_ERROR/8PENDING。
- 原40失败槽 `/root/uav_tracking_fullplan_v4_humble40/results/reliability_v4_humble40_probe01_seed004_matrix/slots/person_stage3_midpoint_seed004.json`，历史SHA256 `605c7cf97ee8745c30068a7ed324753f3468c4bb8fb11642de2ef3edd4f52ef1`。
- 原始失败spool `/root/uav_tracking_bag_spool/trial_ygxppdk1`。压力前提会核stat/provenance及真实独立41压力回执；无该原始历史时不能把源码克隆当作压力前提已满足。
- 历史磁场override `/root/uav_tracking_fullplan_v4_humble29/config/px4_magnetic_runtime.json`，SHA256 `3c4f9693cfab51c6b2049af619bfb6e3edbd22a8328468b7e84f75053485c66b`。运行配置数值应可复现；此历史29路径/证据绑定是本机溯源。
- 独审回执、build/pressure/owner结果、registry/contracts/seals、PID创建token、storage inventory、物理卷/VHD身份及原32/40结果都属于本机审计数据，不是新机器可重复使用的许可。

本清单仅记录以上角色/名字/已知绑定，不复制或重新读取上述大工件。新机器须使用新的独立环境/版本和真实结果重新登记及封存；不得修改旧证据路径/SHA制造可迁移性。

## 验证与进度

本次仅核对49个小型原文件逐字节SHA、Python AST闭包、11个无动作tool manifest身份。没有新增飞行、build、WSL、注册、seal或大文件hash。

README保留 `2026-10-31T08:49:14.544247+00:00` 的core41快照1PASS/1RUNNING/10PENDING，明确它不是最终验收。源码文件的既有用法文档可能包含更早的状态描述，其原字节被保留；以真实最新结果及当前审查绑定为准。
