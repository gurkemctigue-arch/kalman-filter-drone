# Gazebo/PX4 磁传感器坐标合同审查

这是一项新的仿真传感器接口干预，尚未完成实际飞行比较。解析测试证明接口应满足的几何关系，不能单独证明已有航向误差或跟踪失败的主因。原 PX4、冻结 v3、nav01/nav02 结果均不修改，也不使用目标真值或固定航向补偿。

## 已钉住的实现

PX4 HEAD 为 `d6f12ad1c4f70ad3230afd7d86e971421e02fef4`。

- `GZBridge.cpp:88` 在初始化时订阅 Gazebo 磁传感器；228–238 行使用 `/world/<world>/model/<model>/link/base_link/sensor/magnetometer_sensor/magnetometer`。383–406 行回调发布 `sensor_mag`，设备 ID 为 197388，当前映射为 `[-msg.y, -msg.x, msg.z]`。
- `px4-rc.gzsim:198–201` 仅在 `SENS_EN_MAGSIM=1` 时启动独立 `sensor_mag_sim`。参数在 `sensor_mag_sim/parameters.c:43` 默认 0。`SensorMagSim.hpp:81` 也使用设备 ID 197388；其 WMM 值由仿真飞控自身的姿态/地理位置输入产生，不读取世界 `magnetic_field`。
- `rcS:143–161` 的 AUTOCNF 预置 CAL_MAG0_ID=197388 与 CAL_MAG1_ID=197644。197644 只改变地址为 4，不能凭这个校准项推断第二个实际 publisher 存在。`VehicleMagnetometer.cpp` 消费 `sensor_mag` 后发布 `vehicle_magnetometer`，EKF2.cpp:2506–2536 消费后者；EKF 选用实例仍应由实际运行证据核对。

当前 Jazzy 安装为 `ros-jazzy-gz-sim-vendor 0.0.13-1noble.20260905.073557`；其 package.xml 与 CMake 配置均声明 gz-sim 8.15.0。库 `/opt/ros/jazzy/opt/gz_sim_vendor/lib/gz-sim-8/plugins/libgz-sim8-magnetometer-system.so.8.15.0` 当前 SHA-256 为 `4e6e32b71016f5d35c25140e3b4b3c60230990f16bcd8a673a25558c767e2137`。当前 gz-sensors 为 8.2.2。它们对应的上游发布源码如下：

| 源码 | 发布 commit | 文件 SHA-256 |
| --- | --- | --- |
| [gz-sim Magnetometer.cc](https://github.com/gazebosim/gz-sim/blob/446a44335a45b704b4d36dabcc5508ee34eeb3d8/src/systems/magnetometer/Magnetometer.cc#L459) | `446a44335a45b704b4d36dabcc5508ee34eeb3d8`，tag gz-sim8_8.15.0 | `4c2eab47814932a4df6b6255f46e379b1aa0feb41b248fd0ee13213d56a3016d` |
| [gz-sensors MagnetometerSensor.cc](https://github.com/gazebosim/gz-sensors/blob/9348f9fe8a11b9d50381819f51e17e136aedab8a/src/MagnetometerSensor.cc#L162) | `9348f9fe8a11b9d50381819f51e17e136aedab8a`，tag gz-sensors8_8.2.2 | `c66d3dbf29d6d158eb010b22a44e8e06fb93c518ca00129bfb8ac3685be49592` |
| [Humble 安装对应的 gz-sensors MagnetometerSensor.cc](https://github.com/gazebosim/gz-sensors/blob/6d74c1fe96d7277c7dec96a54bbc79d5c752e63c/src/MagnetometerSensor.cc#L162) | `6d74c1fe96d7277c7dec96a54bbc79d5c752e63c`，tag gz-sensors8_8.3.0 | `c66d3dbf29d6d158eb010b22a44e8e06fb93c518ca00129bfb8ac3685be49592` |

Humble/Ubuntu22.04 使用官方 OSRF 的 gz-sim8.15.0、gz-sensors8.3.0 二进制包；Jazzy/Ubuntu24.04 使用 ROS vendor 包。8.3.0 的完整 `MagnetometerSensor.cc` 与 8.2.2 文件散列相同，坐标和单位逻辑相同，但其发布 commit 单独登记，不沿用 8.2.2 的 commit，也不将两种环境的 ELF 散列混用。

源码查表登记 `config/gazebo_magnetic_reference.json` 只保存源码、查表和几何合同。`audited_source_variants` 白名单包含上述两组完整版本/commit/源码散列；源码文件相同不能授权任意未登记 commit。每环境的磁库路径、SHA-256、包名、包版本和 dpkg 文件校验独立保存在 `config/gazebo_magnetic_runtime.json`（Jazzy）与 `config/gazebo_magnetic_runtime_humble22.json`（Humble）。两份登记都记录了实际 APT 来源和 InRelease 的 gpgv 签名验证。它们属于安装审计，不能冒充历史试验的实际加载记录。

`run_stage1_trial.py --magnetic-environment gazebo_enu` 使用 `--magnetic-library-registration` 指定预先审计的登记，默认 Jazzy 文件。Humble 必须显式选择其登记。runner 把它冻结为 `configuration/gazebo_magnetic_runtime_registration.json`。世界服务就绪后、PX4 启动前，`capture_gazebo_magnetic_libraries.py` 仅有界遍历本次 Gazebo session/group 的后代，在 `/proc/PID/maps` 定位两种实际磁库，并核对命名空间中的 inode/device、ELF 格式、路径与 SHA-256；不自动生成或接受新的登记。捕获文件 `configuration/gazebo_loaded_magnetic_libraries.json` 绑定登记路径、登记散列、环境 ID、实际库与所属进程证据。缺库最多重试十次，错误散列、来源或作用域立即拒绝启动。

gz-sim:138/141 默认 `use_units_gauss=true`、`use_earth_frame_ned=true`；257–267 行可以显式配置这两项。379 行只在创建传感器时设置世界 `magnetic_field`。459 行起，Update 每次根据传感器球面坐标读取本插件内置的旧磁表，471–481 行计算偏角、倾角和强度，506 行再次 SetWorldMagneticField。因此仅修改世界 XML 的磁向量不能保证改变实际稳定运行磁输入。

gz-sensors:162–165 将磁场按 `sensor_world_rotation.inverse()` 转到传感器坐标；198 行原样填入 field_tesla，命名并不能保证当前插件选用的数值单位。单位必须按明确的 gauss 配置解释。

nav02 两个探针四份 before/after BSON 均无 SENS_EN_MAGSIM、SENS_MAG_MODE、EKF2_MULTI_MAG 的非默认覆盖；日志显示 SYS_AUTOSTART=4001 和 gz_bridge 接到 stage1_uav。结合默认初始化，这支持预期使用 Gazebo 磁源。BSON 仅包含保存的非默认值，历史试验没有完整实际参数、模块列表、选用 mag 实例、被加载动态库路径及其 hash，不能把事后安装审查冒充这些缺失的运行证据。

## 磁传感器安装链

`x500_stage1/model.sdf:7` 与 `x500_stage3/model.sdf:4` 均 merge include `model://x500`；官方 `x500/model.sdf:4–6` 再 merge include `x500_base`。`x500_base/model.sdf:232–257` 的 magnetometer_sensor 直接属于 base_link，sensor 没有 pose，base_link 没有旋转 pose。x500_base 的模型 pose 只有 z=0.24 m，没有旋转。两层 include 没有引入旋转，也没有覆盖 base_link 或磁传感器。stage3 的旋转关节只属于新增相机链；mesh 的 visual yaw 也不改变 base_link 坐标。

所以当前磁传感器坐标与机体 FLU 对齐。`sensor_mount_evidence` 对这四个模型逐一检查，并保存实际文件路径和 hash；新增或改变安装外参时拒绝继续沿用这个合同。

## 任意姿态应满足的关系

令 R 表示机体 FLU 到世界 ENU 的旋转，h 为世界 ENU 中的真实磁向量。物理上正确的 PX4 机体 FRD 测量应为：

`h_FRD = C Rᵀ h_ENU`，其中 `C=diag(1,-1,-1)`。

当前桥接矩阵 `B=[[0,-1,0],[-1,0,0],[0,0,1]]` 的行列式为 −1，C 的行列式为 +1。仅把 Gazebo 插件切到 ENU，仍会得到 B Rᵀ h，而不是 C Rᵀ h。也不存在一个合法的固定刚性安装旋转能把这个反射变成所需旋转；对任意 roll/pitch/yaw，也无法靠一个固定世界向量修补。应成对修正插件配置与桥接映射。

旧 Gazebo 磁表在登记原点的 float32 源码转录结果为 D=2.5638489723°、I=63.2525863647°、强度48.0740089417 centigauss。PX4 查表 D=3.4057652950°，两表本来就不同。旧默认链在理想水平姿态下预测 ENU 航向误差为 `-(D_Gazebo+D_PX4)≈-5.96961427°`；这是假说模型，不能用来直接给估计航向加常数，也不能因接近已有误差就认定因果。

## 独立实验干预

新增 opt-in 合同 `gazebo_enu_flu_to_frd_v1`：

1. 新 runtime world 的磁插件设置 `use_earth_frame_ned=false`、`use_units_gauss=true`。世界 `magnetic_field` 数值保持原样，并明确记录其只作为初始化。
2. 独立 PX4 checkout 的 GZBridge 将磁测量从 sensor/body FLU 转为 FRD，即 `[msg.x,-msg.y,-msg.z]`；初始化输出唯一合同标记。
3. 保留 Gazebo 的真实旧查表来源、值和与 PX4 的约0.84191632°磁偏角差。这个版本不宣称两个 WMM 完全一致。移动后查询点会随传感器地理位置改变，原点数值只作登记参考。
4. SENS_EN_MAGSIM 必须保持 0，只允许这一路磁 publisher。实际 PX4 启动日志须包含 `magnetic frame contract: gazebo_enu_flu_to_frd_v1`，并归档实际可执行文件 hash。

补丁在 `patches/px4/gazebo_enu_flu_to_frd.patch`。原/补丁后 GZBridge.cpp 的 SHA-256 分别为 `8f6f1d7e450e341137be573a51674c6ffc518ef63badbdaa71667d0f462b8dfd` / `7d4ab7c529421865c86d5e463e5ec15eb66f580dbcc6e091ad99704815faa19d`。这不会修改原 PX4 或 ROS PX4Adapter。

已由主代理用 `copy_px4_sitl_source.py` 将原源码及Git缓存独立复制到 `/root/PX4-Autopilot-v4mag`，排除 build/install/log，保留7个已初始化、23个未初始化的递归子模块状态。随后授权执行如下仅应用补丁操作，已成功完成：

```bash
python scripts/prepare_px4_magnetic_compatibility.py apply-isolated \
  --original-root /root/PX4-Autopilot --px4-root /root/PX4-Autopilot-v4mag \
  --copy-manifest results/px4_v4mag_source_copy.json \
  --output results/px4_v4mag_patch_applied.json
```

应用前验证独立Git目录、无alternates、桥接文件不共享inode、双方clean/exactHEAD，以及存档和当前递归子模块状态/hash；应用后确认原源码before/after完全相同，隔离副本仅GZBridge.cpp改变，子模块保持原状。证据operation为 `PATCH_APPLIED_NOT_BUILT`，本步骤没有构建或运行PX4。后续编译由主代理协调。

以下是为其他独立源码目录保留的可选准备接口；不应在已经独立复制的目录上重复执行prepare。先生成只读计划，网络子模块初始化与构建需单独协调资源：

```bash
python scripts/prepare_px4_magnetic_compatibility.py plan \
  --px4-root /root/PX4-Autopilot --destination /root/PX4-Autopilot-mag-v4

python scripts/prepare_px4_magnetic_compatibility.py prepare \
  --px4-root /root/PX4-Autopilot --destination /root/PX4-Autopilot-mag-v4 \
  --initialize-dependencies --output NEW_EVIDENCE/px4_prepared.json
```

prepare 使用精确 commit 的独立浅 fetch，不复制 build/results、不使用共享 alternates，不修改原 checkout；依赖只跟随精确递归 gitlink，不使用 `--remote`。它不编译。后续在独立目录构建并执行 verify-runtime：

```bash
python scripts/prepare_px4_magnetic_compatibility.py verify-runtime \
  --px4-root /root/PX4-Autopilot-mag-v4 --output NEW_EVIDENCE/px4_runtime.json

python scripts/configure_gazebo_magnetic_contract.py \
  --input-world ORIGINAL.sdf --output-world NEW_TRIAL/runtime_world.sdf \
  --evidence NEW_TRIAL/magnetic_contract.json \
  --px4-runtime-manifest NEW_EVIDENCE/px4_runtime.json
```

运行后再用新的证据路径加 `verify-runtime --px4-log NEW_TRIAL/px4.log`，核对实际启动。ELF 标记及源文件证据仍不替代真正执行日志或飞行验证。

`tests.test_magnetic_frame_contract` 的15项测试覆盖128组任意姿态的物理投影、旧反射不能由刚性安装补偿、ENU-only不足、单位、理论水平偏差、模型安装、配置源保护及 ELF/log 校验，并用真实临时Git仓库验证隔离应用、依赖证据和初始/最终 runtime 证据冲突时拒绝。`tests.test_gazebo_library_provenance` 的10项测试在 Linux 全部通过，覆盖同进程组边界、映射去重、路径/散列冲突、两种登记与未审计 commit 拒绝；Windows 跳过其中4项依赖 Linux inode/device 的 fixture。

独立 `/root/PX4-Autopilot-v4mag` 已完成构建，`config/px4_magnetic_runtime.json` 保存了 `RUNTIME_ARTIFACT_VERIFIED` 证据。上述单元测试本身没有调用 Gazebo 或 PX4；构建及静态验证也不等于飞行比较。下一步必须保留独立阴性/阳性开发探针，用相同种子和参数做 ego-only 姿态误差与完整闭环比较，再决定是否纳入正式冻结。
