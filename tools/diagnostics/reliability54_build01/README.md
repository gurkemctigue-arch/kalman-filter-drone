# Humble 原生构建薄入口

此入口只创建一个全新的源码、构建和结果目录；不启动仿真，也不对旧版本授予新结论。

```bash
bash /mnt/d/基于yolo和卡尔曼滤波/tools/diagnostics/reliability54_build01/prepare_and_validate.sh \
  /root/uav_tracking_fullplan_v4_humble54 \
  /mnt/d/基于yolo和卡尔曼滤波/results/frozen_fullplan_v4_humble54 \
  /root/uav_tracking_fullplan_v4_humble53
```

第三参只用于只读比较已经核验的运行时注册文件字节，**不会 source 其 install、复制其源码或写入其目录**。当前工作区的 DDS、数据桥、时钟桥、PX4 磁场、Gazebo 磁场五份注册须与参考一致；某份不同时直接失败，由执行者核查，不自动改注册。新目录已存在也会拒绝。

脚本先以 `env -i` 重新进入清洁进程，固定 `TMPDIR=/tmp`，选择 Humble、原生 venv、基础及修补的 ros_gz、px4_msgs underlay，限制构建与辅助数学库线程。原有工程 install 不进入初始 Python、ament、colcon 或 CMake 前缀。运行时 DDS 库仍使用已核注册；编译器的 FastCDR 单独显式选择 `/opt/ros/humble/lib/cmake/fastcdr`。

实际冻结、复制、colcon 构建、模块和 ament 来源隔离、完整 unittest 都复用公开 `scripts/freeze_full_plan_workspace.sh`。该脚本新增的可选 `STAGE1_FASTCDR_CMAKE_DIR` 只有在目录内确实存在 `fastcdr-config.cmake` 时才追加一个 `-Dfastcdr_DIR=...` 参数；不设置时保持原默认行为。公开入口在 source underlay 和 source 新 install 后分别重新 apply 当前 frozen 的 DDS 环境，完整套件启动前保存实际 `full_suite_environment.json`。这样记录的是测试继承的环境；末尾的 apply 不再被用来倒推此前测试环境。

公开入口成功返回后，再通过新 install 启动独立解释器生成 `results/freeze_validation/native_build_supplement.json`：核对接口包 CMakeCache 中实际 FastCDR 选择，保存配置和 cache SHA；核对公开 module/ament 隔离收据；运行真实生成类型的 CDR 往返，覆盖最大 uint64 epoch、表面支持标志、独立默认候选及三维点；读取真实完整测试日志，保留测试与跳过分母。完整套件原有 `test_exclusive_navigation_cdr.py` 仍负责 16384 点大云往返，此附加小收据不替代它。补充失败保留 FAIL 文件，不改旧结果。

本次只准备工具；实际构建、真实 ROS CDR 和原生完整测试由主执行代理另行运行。Windows 仅能验证纯 Python 收据解析与已有隔离逻辑；三个 POSIX 参数集成测试明确跳过，不据此宣称 Linux 编译通过。

## 源码和复制完整性补充

独审发现原公开入口的来源隔离并不证明复制完整。因此 wrapper 在单次 freeze 之前以公开 rsync 的**完全相同排除列表**生成全树 SHA 清单，包含未被 Git 跟踪的运行时注册和模型权重；链接记录目标、不跟随。排除规则与公开脚本不一致时拒绝开始，不能默默漏掉新算法文件。原始清单保存在一个全新 `/tmp/uav_freeze_integrity.*` 目录，避免在复制前创建目标结果目录。

单次 freeze 返回后，无论其成功或失败，都比较原 source 的 pre/post 完整清单及新 root 全树复制清单。报告完整列出 missing、added、changed；全树一致才授予**复制字节范围内**的 PASS，原构建返回码独立保留并决定 wrapper 失败退出。新 frozen 的 `results` 链接是公开入口创建的唯一额外链接，只有核对其精确声明的 D 盘目标后才作为生成物单独登记。其余新增算法文件不豁免。

清单、实际新树 map 和 `source_frozen_integrity.json` 以独占创建方式保存，并在新结果目录可用时原样发布至 `results/freeze_validation/source_integrity/`；已有报告不覆盖，失败版本不被改写。源码变化、遗漏文件或检查异常均保留 FAIL，不能继续运行补充 CDR 验证。该字节核查不代表构建或飞行已通过。
