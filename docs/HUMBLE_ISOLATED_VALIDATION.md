# Ubuntu 22.04 / ROS 2 Humble 独立验证

截至2026-10-29，Canonical官方Jammy WSL镜像已下载并完成官方SHA256比对；`UAVHumble22`已实际导入至`D:\WSL\UAVHumble22`，读取确认为Ubuntu22.04.5、Python3.10.12。Humble/Harmonic的签名APT包、rosdep缓存和独立Python依赖已安装，pip check已通过；官方ros_gz源码已克隆，PX4/px4_msgs/Agent源码已按commit从干净缓存转入。ros_gz的interfaces/sim/bridge三包、px4_msgs、Agent（含独立FastDDS）及本环境独立的patched PX4已实际编译通过。系统ABI与独立小世界RGB-D/时钟/服务桥接已通过。最终工程尚需同步原生起飞启动协议修复后，在独立冻结目录构建。**尚未启动这套环境的PX4飞行，也未完成完整闭环验收**。既有Ubuntu24.04/Jazzy试验仍属于既有环境，不能用来代替本验证；本轮导入与构建均等待了当前仿真释放资源。

## 隔离布局与准备证据

| 对象 | 独立位置 / 状态 |
| --- | --- |
| 当前发行版 | WSL `Ubuntu`；本任务不停止、卸载、导出或改动它 |
| 新发行版 | WSL `UAVHumble22`，WSL2，已导入 |
| 新发行版VHDX目录 | `D:\WSL\UAVHumble22`；不复用现有发行版目录 |
| 官方镜像缓存 | `D:\WSL\Downloads\Jammy` |
| Linux工作根 | `/root/uav_humble22`，位于新发行版ext4文件系统 |
| ROS underlay | 只允许 `/opt/ros/humble` |
| Harmonic专用桥接overlay | `/root/uav_humble22/ros_gz_ws` |
| PX4消息overlay | `/root/uav_humble22/px4_msgs_ws` |
| 工程独立快照 | `/root/uav_humble22/project`，不复制旧build/install/log/results |
| Python环境 | `/root/uav_humble22/venv`，Python3.10，允许读取Humble系统依赖 |
| 安装证据 | `D:\WSL\UAVHumble22-validation\logs`，新发行版`/root/uav_humble22/logs`链接至此 |
| 运行隔离 | `ROS_DOMAIN_ID=73`；独立`GZ_PARTITION` |

下载源为[Canonical官方Jammy WSL目录](https://cloud-images.ubuntu.com/wsl/jammy/current/)。镜像文件为 `ubuntu-jammy-wsl-amd64-ubuntu22.04lts.rootfs.tar.gz`，341,130,963字节（约325.3 MiB），页面修改日期2025-03-18。镜像初始内容较旧，因此导入后仍需从正常签名APT源更新必要软件；下载日期不表示镜像内容日期。

实际文件SHA256与同源HTTPS下载的`SHA256SUMS`一致：

```text
1483cc5c1dce13064f774834cbffdff226559fd522a67a381a8ea77d63fb4109
```

缓存中的`verified-image.json`记录URL、下载核验时间、大小和SHA；`SHA256SUMS.gpg`也已下载，但**没有完成GPG签名验证**。本阶段的真实性依据是Canonical HTTPS来源及其校验文件，不能把它写成已经独立认证了签名。镜像校验值固定在准备脚本中；未来`current`更新导致不匹配时脚本停止，不静默更换镜像。

准备时D盘可用空间约197 GiB。后续ROS/Gazebo、CPU PyTorch和PX4源码/构建还需数GB下载及约15–30 GiB工作空间，最终以APT安装计划和实际磁盘用量为准；325 MiB只是rootfs下载量。构建限制为单worker、最多2个编译任务（`HUMBLE22_BUILD_JOBS=1`可进一步降低），不与正式仿真同时进行。

## 官方兼容性依据

Humble在Ubuntu22.04上有官方二进制。Humble默认Gazebo组合是Fortress；[Gazebo官方组合说明](https://gazebosim.org/docs/harmonic/ros_installation/)将Humble+Harmonic列为可用但需谨慎的非默认组合。文档同时说明OSRF仓库提供`ros-humble-ros-gzharmonic`，它与默认`ros-humble-ros-gz*`包冲突。因此本验证不安装默认Fortress桥接包，也不把Jazzy的Harmonic vendor二进制复制进Jammy。

采用官方Harmonic库与Humble源码overlay：

| 组件 | 准备选择 | 尚需验证 |
| --- | --- | --- |
| Ubuntu | Canonical 22.04 amd64 WSL rootfs | 实际导入后的系统信息 |
| ROS | 官方ROS APT `ros-humble-ros-base=0.10.0-1jammy.20260915.225919`，rclpy3.3.22 | 消息及节点实际运行 |
| Gazebo | OSRF签名APT源`gz-harmonic=1.0.0-1~jammy` / libgz-sim8=8.15.0 | 渲染与插件实际运行 |
| ros_gz | 官方仓库Humble标签`0.244.27`，commit `856e319ee4da713609b3f6e58c74ac8db7662482` | `GZ_VERSION=harmonic`源码构建、服务/图像桥接 |
| PX4 | `v1.17.0` / `d6f12ad1c4f70ad3230afd7d86e971421e02fef4` | Jammy重新编译、SITL启动 |
| px4_msgs | 与release/1.17对应的`v1.17.0` / `86d8239e962f6939e05c3737784f60c02fa884db` | Humble重新生成消息及DDS联通 |
| XRCE Agent | `v2.4.3` / `73622810d984349b80bbac0ef55fc0b694d62222` | 单独前缀构建、PX4通信 |

官方[ros_gz Humble源码](https://github.com/gazebosim/ros_gz/tree/856e319ee4da713609b3f6e58c74ac8db7662482)的CMake有Harmonic分支：gz-transport13、gz-msgs10、gz-sim8；接口含`SetEntityPose`。这是源码可配置证据，不能代替实际ABI和运行验证。构建与rosdep阶段均显式设置`GZ_VERSION=harmonic`、清空旧`IGNITION_VERSION`，避免回到默认Fortress。

APT只使用Ubuntu、ROS和OSRF来源。ROS公钥从官方`https://repo.ros2.org/repos.key`取得，核对主指纹`C1CF6E31E6BADE8868B172B4F42ED6FBAB17C654`；ROS仓库使用`http://packages.ros.org/ros2/ubuntu`并强制`signed-by`。本机对该站HTTPS曾返回主机名不匹配，脚本不关闭TLS验证；HTTP上的APT仍要求签名Release元数据与软件包哈希。OSRF使用官方HTTPS源和专用keyring。禁止`trusted=yes`、`--allow-unauthenticated`及跨发行版安装。

实际安装后，两个仓库的缓存InRelease均经gpgv独立复核成功；OSRF主指纹为`D2486D2DD83DB69272AFE98867170598AF249743`。`D:\WSL\UAVHumble22-validation\logs\prepared_environment.json`保留包版本、系统、gz8.15.0输出和验证记录，完整包清单为同目录`packages.tsv`。它明确记录`source_overlay_built=false`和`sitl_run=false`。

本机WSL访问GitHub发生连接重置。rosdep初始化的失败日志保留；[官方元数据缓存脚本](../scripts/prepare_humble22_rosdep_cache.py)通过Windows正常HTTPS栈下载官方文件，原YAML和URL/SHA清单保存在`official-rosdep/`，派生列表改用这些本地文件。旧ROS1 Fuerte的gbpdistro条目会继续联系其它远程资源，故仅在派生列表中注释；它不提供Humble数据，原文件不变。随后仅更新Humble的rosdep缓存成功，没有改换第三方ROS包仓库。

ros_gz从官方GitHub成功克隆并核对commit。其它三个仓库采用既有Ubuntu环境的干净源码缓存：先只读核对HEAD和tracked状态，排除其build/install/log目录，导出到独立D盘缓存；再在新发行版解包，重核HEAD、tracked状态和PX4全部submodule状态指纹。`source-cache/source_cache_manifest.json`及`logs/source_import_manifest.json`记录来源、tar SHA与新路径。PX4原缓存30个submodule中有23个未初始化，属于NuttX、旧仿真器及其它可选组件；新副本完整保持这个状态，不把它称为全仓库递归初始化。SITL所需模块是否足够仍以新环境构建为准。没有复制旧ROS/桥接二进制，旧发行版的源码和安装未改动。

## 顺序执行

[准备脚本](../scripts/setup_humble22.ps1)默认只下载核验；已执行成功：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/setup_humble22.ps1 -Action Prepare
```

资源协调完成后才运行独立导入。脚本遇到已有同名发行版或已有目标目录会停止，不覆盖、不自动删除：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/setup_humble22.ps1 -Action Import
```

进入新发行版，使用挂载的Windows工程脚本顺序执行各阶段；每个命令单独运行，确认成功后再继续：

```powershell
wsl.exe --distribution UAVHumble22 --user root
```

```bash
task_source='/mnt/d/基于yolo和卡尔曼滤波'
bash "$task_source/scripts/setup_humble22.sh" packages
bash "$task_source/scripts/setup_humble22.sh" repositories "$task_source"
bash /root/uav_humble22/project/scripts/setup_humble22.sh python
bash /root/uav_humble22/project/scripts/setup_humble22.sh build
bash /root/uav_humble22/project/scripts/setup_humble22.sh verify
```

[Linux安装脚本](../scripts/setup_humble22.sh)只接受WSL名`UAVHumble22`和Ubuntu22.04，拒绝已经source其它ROS发行版的shell；不执行任何WSL管理命令。repositories阶段生成独立工程快照，若快照已存在会停止，不把旧二进制覆盖进新环境。依赖仓库按标签克隆并核对commit，不对已有仓库自动reset。所有日志位于`/root/uav_humble22/logs`；本次安装不升级既有Jazzy环境。

Python使用独立venv，并先装CPU PyTorch，避免其它依赖意外拉取CUDA发行版。NumPy固定1.26.4、Torch2.5.1+cpu、torchvision0.20.1+cpu、Ultralytics8.4.188。Jammy系统OpenCV低于Ultralytics声明的Python最低版本，因此venv单独固定opencv-python4.11.0.86，保留Ubuntu原C++库；必须通过cv_bridge图像往返转换、pip check和真实RGB-D运行验证，不能仅凭import成功宣称ABI兼容。

实际pip check补齐了Ultralytics声明的`nvidia-ml-py`和系统pygobject声明的`python3-cairo`，未安装CUDA；修复前后日志均保留。首次colcon还发现setuptools75与系统packaging21.3的API不匹配，因此venv明确固定`packaging==24.2`，不修改系统Python。随后ros_gz_interfaces构建成功。

第二次配置发现WSL自动附加的Windows PATH让CMake搜索到`/mnt/d/anaconda/Library/include`中的Windows protobuf/gflags头，虽本地APT protobuf3.12.4与Gazebo生成头本身一致，编译仍出现版本/DLL宏错误。安装和环境脚本因此在当前进程内固定Linux工具PATH、清除外来CMake/CPATH搜索变量，重试时清理独立overlay的CMake配置缓存。该处理不改Windows PATH、全局WSL设置或旧Ubuntu；最终是否完全排除污染仍须以完成构建后的依赖检查为准。

修复后ros_gz三包一次顺序构建通过（合计约5分10秒，bridge约4分53秒），随后px4_msgs消息生成与构建通过（约5分38秒）。日志在`build_20261028T203716Z.log`及两overlay的colcon日志中。Agent的GitHub依赖下载同样遇到TLS连接重置，因此从原环境依赖的Git对象/refs制作独立bare缓存，并对新发行版配置公开官方URL到本地缓存的映射。缓存来源、commit和路径见`source-cache/agent-dependencies/manifest.json`、`logs/agent_source_cache_import.json`及`logs/agent_nested_cache.json`。FastDDS的android-ifaddrs、asio、fastcdr和tinyxml2递归模块均已从本地对象正常检出；原CMake gitclone步骤实际成功生成stamp。只转入源码对象，没有转入原环境的Agent或FastDDS编译库。

为验证最终磁场坐标修复，另从新发行版的干净PX4源码独立copy2到`/root/uav_humble22/PX4-Autopilot-v4mag`，再应用登记的Gazebo ENU/FLU到FRD兼容补丁。原stock源码保持干净，递归submodule指纹保持一致。`logs/px4_v4mag_copy.json`和`logs/px4_v4mag_patch.json`记录此过程。后续构建和运行显式设置`HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag`，与默认stock路径区分；真实飞行启动日志仍须验证。

新环境的磁库另行实测登记在`config/gazebo_magnetic_runtime_humble22.json`，不使用Jazzy二进制的SHA白名单。Jammy实际安装的磁系统为gz-sim8.15.0、磁传感器为gz-sensors8.3.0；两ELF的SHA、dpkg归属/版本及md5sums一致性均已读取，APT policy指向OSRF官方Jammy源，其InRelease再经gpgv验证成功。8.3.0的官方commit为`6d74c1fe96d7277c7dec96a54bbc79d5c752e63c`；`MagnetometerSensor.cc`全文件SHA与已审查的8.2.2相同，因此相应磁场逆旋转/发布坐标约定一致。源码审查和已安装ELF的签名包来源是两条独立证据，不能据此声称已重现官方二进制编译。

原Ubuntu的新v4mag构建另外暴露了上游GNU Make事件扫描对`dds_topics.h`的跨target依赖问题，以及Micro-CDR公开仓库的网络连接重置。最终PX4构建将复用登记的`build_px4_magnetic_runtime.sh`：先运行上游`topic_bridge_files`生成target，再编译完整固件。`prepare_px4_microcdr_cache.py`可从干净v2.0.1 Git源码制作无hardlink的独立bare缓存，以仅当前构建环境的URL映射执行正常CMake clone步骤；它不复制生成头或库，不伪造stamp，也不修改原Ubuntu的全局Git配置。Humble环境已有同commit的Micro-CDR源码对象缓存，后续仍须实际完成其独立编译。

安装脚本保留`build`完整顺序，也提供`build-ros`、`build-agent`、`build-px4`、`build-project`，便于只在协调后的窗口恢复剩余步骤，不反复重配已完成的桥接overlay。所有子步骤仍限制为单package worker、最多2个编译任务，不能并发启动。

Agent在源码缓存修复后恢复构建成功，恢复段为2026-10-28 21:25:34–21:30:36 UTC（约5分02秒），日志`build-agent_20261028T212534Z.log`；没有复制既有环境的编译库。Humble PX4实际选择Ninja，完成独立的1137项构建任务；原Ubuntu的GNU Make图问题不应被描述为本环境也已发生。配置中GStreamer和Java缺失只影响本项目未用到的可选插件，不替代RGB-D桥接和实际飞行的验收。

PX4初次构建遇到上游`PX4-OpticalFlow`的GitHub下载TLS/timeout，所有失败日志保留。仅只读导出旧Ubuntu干净OpticalFlow与klt_feature_tracker的Git bundles，在Humble核SHA后建立独立bare缓存，以本次构建进程的URL映射完成正常CMake递归clone，原Ubuntu配置/工作树不改动，没有复制编译库。OpticalFlow冻结commit为`8758bd5567aadf2f8ab5deee97701d2c495d0756`，klt为`a2733b54f17b571dd958be498b57479a4104d8cd`；证据见`source-cache/px4-opticalflow/export_manifest.json`与`logs/opticalflow_cache_import.json`。上游请求的是移动`master`分支，因此应保留这两个实际源码commit用于复现。

修复后2026-10-28 21:41:26 UTC完成PX4构建，日志`build-px4_20261028T214110Z.log`，登记实证为`logs/px4_v4mag_runtime_20261028T214110Z.json`。ELF为56,970,272字节，SHA256为`6cf784c1cb4de2945b4291aa9391a2301c78315a1462ef3f51f541e119fd7ce7`；实际二进制含登记磁场合同标记，仅`GZBridge.cpp`有预期tracked修改。manifest明确`actual_startup_log_verified=false`，不能把ELF成功等同飞行成功。最终Humble冻结副本须使用这个环境的PX4 manifest，而不能沿用Windows主树中属于Jazzy的同名配置。

`HUMBLE22_PROJECT_ROOT`允许显式选择新的`/root/uav_tracking_fullplan_NAME`冻结目录，默认仍为准备目录；环境脚本先清除已有ROS/Python overlay前缀，再source Humble、消息、桥接及所选工程，防止冻结运行偷偷导入准备副本。

不启动传感器/仿真的系统ABI检查已通过，证据`logs/system_abi_verification.json`：venv NumPy1.26.4/OpenCV4.11.0与Humble cv_bridge完成RGB uint8、深度float32的精确图像往返；rclpy、px4_msgs和ros_gz_interfaces均从本环境导入；bridge与Agent的ldd无缺库及Jazzy路径，pip check通过。Agent ELF SHA256为`fc5afa7524e499cb82ccdbec69bda56f116d20b3ddecea404745340f7357959c`。这只覆盖系统消息/图像转换/链接边界，工程detector入口、真实渲染及DDS通信仍需最终冻结后验证。

colcon统一通过`/root/uav_humble22/venv/bin/python /usr/bin/colcon`执行，并显式传入CMake的Python路径。system-site-packages中的colcon包可被pip判为已满足，不保证自动生成venv/bin/colcon入口；显式调用避免此歧义。verify还要求安装后的`uav_tracking_nodes/detector`首行使用同一venv解释器，并记录实际torch模块路径，避免构建通过而运行节点看不到YOLO依赖。

## 分层验收与剩余入口

| Gate | 必须保留的实际证据 | 准备阶段状态 |
| --- | --- | --- |
| 0 镜像 | 官方URL、大小、SHA及核验记录 | 已完成，GPG签名未验证 |
| 1 系统/包 | os-release、Python3.10、签名APT、完整包版本 | 已完成；pip check通过 |
| 2 构建 | ros_gz/px4_msgs/工程colcon、Agent和PX4构建日志 | ros_gz三包、px4_msgs、Agent及patched PX4已通过；工程待同步最终启动修复后构建 |
| 3 算法/ABI | 完整核心测试、消息导入、pip check、cv_bridge往返、bridge ldd无缺库/跨ROS | 系统消息/服务导入、pip check、RGB及depth往返、bridge/Agent ldd已通过；最终工程测试/入口待执行 |
| 4 桥接 | 时钟、同步RGB/Depth/CameraInfo、真实有效深度、SetEntityPose成功 | 已实际通过独立小世界；完整跟随世界尚待闭环 |
| 5 PX4链路 | 本环境SITL与XRCE、VehicleOdometry/VehicleStatus、Offboard状态和时间戳 | 待执行 |
| 6 闭环 | 行人/汽车实际跟随、短遮挡同身份恢复、长丢失悬停/显式重选的rosbag与离线评价 | 待执行 |

Gate4使用[独立小场景桥接检查](../scripts/verify_humble22_bridge.sh)：

```bash
bash /root/uav_humble22/project/scripts/verify_humble22_bridge.sh
```

它不启动PX4或YOLO，只启动160×120、5Hz RGB-D小场景和Humble源码桥接，检查同步采集时间、CameraInfo、有效深度与服务ACK，输出`bridge_smoke.json`和进程日志。只有自己的独立进程组会被清理；不执行全局pkill、不停止其它发行版。成功服务ACK证明接口调用成功，不独立证明每一个像素的渲染可见性。

该gate于2026-10-28 21:44 UTC实际执行通过（exit0）：`logs/bridge_20261028T214405Z/bridge_smoke.json`记录3组RGB/Depth/CameraInfo完全相同的采集时间戳，RGB为120×160×3、深度为120×160的32FC1，深度有效率30.083%、有效像素中位数约2.750000m，收到105条Clock，SetEntityPose成功。进程已清理，日志保留。为使本gate真正独立，其入口只source已构建的Humble标准消息与ros_gz overlay，不要求尚未构建的工程安装目录，也不忽略任何缺失source错误。

主任务已为正式运行入口引入`source_ros_environment.sh`，通过`STAGE1_ROS_DISTRO`、`STAGE1_PX4_MSGS_WS`、`STAGE1_ROS_GZ_WS`及`STAGE1_PYTHON_EXECUTABLE`选择环境，默认保留Jazzy行为。[Humble环境脚本](../scripts/humble22_env.sh)设置全部新前缀。Gate5/6之前仍须同步这些更新到独立工程快照并记录哈希，实际检验所有被调用入口；不能用把Humble目录伪装成`/opt/ros/jazzy`的软链接规避问题。

`capture_environment.py`可记录完整APT/Python清单和指定依赖仓库；其中专门的`installed_ros_gz_packages`筛选目前仍偏向Jazzy，验收时要同时保存完整`packages.tsv`，不能把该筛选列表当作Humble全部包。跨ROS的MCAP也需要使用本环境重新生成/读取消息验证，不能直接复用Jazzy生成的Python消息模块。

全部gate通过后才能将Ubuntu22.04/Humble边界标为完成；多seed论文比较仍须注明每条记录所属环境，不把两套环境的失败与成功混成一组。当前已准备脚本通过PowerShell执行Prepare、Bash语法检查及差异空白检查，后续安装/构建脚本仍需在实际新环境执行，遇到依赖或API问题时保留失败日志继续修正。

官方来源：[Humble Ubuntu安装](https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html)、[Harmonic Ubuntu安装](https://gazebosim.org/docs/harmonic/install_ubuntu/)、[ROS/Gazebo组合](https://gazebosim.org/docs/harmonic/ros_installation/)、[PX4 v1.17源码](https://github.com/PX4/PX4-Autopilot/tree/v1.17.0)、[px4_msgs release/1.17](https://github.com/PX4/px4_msgs/tree/release/1.17)。
