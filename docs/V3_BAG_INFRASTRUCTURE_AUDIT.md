# v3 汽车位置控制 seed08：rosbag 读取异常独立审计

审计日期：2026-10-27。范围只包含
`fullplan_v3_position_compatibility_car_position_adaptive_kf_seed08`，
另用同组 seed09 的 PASS 记录验证解码工具。未重跑飞行、未执行整场离线评价，未修改冻结源码、原始记录或正式实验结论。

## 结论与边界

seed08 的 zstd 帧没有正常结束。独立 libzstd 增量解码仍输出完整、可通过 SQLite 完整性检查的数据库；ROS 原生 `SequentialCompressionReader` 则在新建的 D 盘副本中再次输出一个少了末尾 128 KiB 的数据库，并重现 SQLite error 11。原生输出是独立输出的逐字节前缀。

因此，本次异常的直接证据是“压缩帧不完整，以及原生解压路径丢失尾部输出”，不能归为目标跟踪算法失败，也不能断言原始 SQLite 内容本身损坏。独立输出与元数据消息数完全一致。此次审计没有确定压缩帧为何未正常结束；记录进程 exit 0 及结束日志不足以解释这一原因。

正式试验原有基础设施异常仍保留；独立数据库只是外部诊断衍生物，没有替代原始 rosbag 或正式评价文件，也没有将该试验改判为 PASS。

## 原始记录

目录：`results/frozen_fullplan_v3/fullplan_v3_position_compatibility_car_position_adaptive_kf_seed08/rosbag`。

| 项目 | 证据 |
|---|---|
| 压缩文件 | `rosbag_0.db3.zstd`，449,012,485 bytes |
| 原始压缩 SHA-256 | `e37d3bafe701297952ffa92746cb5cc826911eff8005651aaf076175ee804c20` |
| metadata SHA-256 | `531c57db3dab7875bff0d59aaa68d84da345fc859107ebc21dd4c93c31fe50d7` |
| 元数据消息数 | 53,366 |
| 元数据模式 | SQLite3，FILE zstd，单文件 |
| 原始读取错误 | SQLite error (11): database disk image is malformed |

每次独立审计均校验原始压缩文件及 metadata 的 SHA、大小、mtime、设备和 inode，前后完全一致。原生探针使用实际复制的压缩文件，没有使用硬链接；该副本前后 SHA 也相同。

## 对照与独立解码

现有 `libzstd.so.1` 1.5.5 由 Python ctypes 调用；未安装新依赖。流解码使用 1 MiB 输入、4 MiB 输出缓冲区，先只计算输出长度和 SHA，不分配数据库。独立帧扫描通过只读文件的私有映射调用 `ZSTD_findFrameCompressedSize`，不修改原文件。

| 检查项 | seed08 异常记录 | seed09 PASS 对照 |
|---|---:|---:|
| 压缩输入字节数 | 449,012,485 | 451,741,608 |
| 流解码实际消耗字节数 | 449,012,485 | 451,741,608 |
| 完成帧数 | 0 | 1 |
| EOF 时 libzstd 返回值 | 3 | 0 |
| 独立帧扫描 | `Src size is incorrect` | 正常，单帧覆盖整个文件 |
| 输出字节数 | 1,361,575,936 | 1,370,173,440 |
| 输出 SHA-256 | `03652332502da7bb5431d9fc6ed48acaa4d33a0d34305008d0dad13e6d7ead4b` | `e7a97a3ea6bdd99811511577c3f858b076980f96d4fb0ff19009bab51a5f70f1` |

返回值 3 是解码器的剩余输入提示，不能据此断言原文件恰好缺了 3 个字节。两份帧头均未声明内容长度，也未启用帧校验和。

seed08 在 D 盘独立解码后：

- `PRAGMA integrity_check` 返回唯一结果 `ok`。
- `SELECT count(*) FROM messages` 为 53,366，与元数据相同；分 topic 计数见机器报告。
- 页面大小 4,096，页面数 332,416，乘积等于文件大小 1,361,575,936。
- 数据库使用 `mode=ro&immutable=1`、`query_only=ON`、`temp_store=MEMORY`；读取后 SHA 不变。
- 流式不落盘输出与落盘输出 SHA 完全一致。

## 原生 ROS 读取复现

探针加载 `/opt/ros/jazzy/setup.bash` 与冻结项目的
`/root/uav_tracking_fullplan_v3/ros2_ws/install/setup.bash`，仅执行原生压缩 reader 的 open/topics 探针，没有启动飞行或重算整场指标。

新建 D 盘目录中复制 metadata 和压缩文件，保留原生解压产物：

| 项目 | 独立 libzstd 输出 | 原生 ROS 输出 |
|---|---:|---:|
| 大小 | 1,361,575,936 bytes | 1,361,444,864 bytes |
| SQLite 完整性 | `ok` | SQLite error 11 |
| SHA-256 | `03652332502da7bb5431d9fc6ed48acaa4d33a0d34305008d0dad13e6d7ead4b` | `f8c54c8ab9666f80948cd87a8299c54849fa7fd78afa5983beb833111dd87adb` |

逐字节比较覆盖 1,361,444,864 bytes，没有任何差异。原生输出缺少独立输出的最后 131,072 bytes，等于 128 KiB。新建 D 盘目录能重现原始报错，证据不支持把异常仅解释为原始临时目录的一次性故障。

## 磁盘与执行限制

首次 Windows 检查 C 可用约 5.59 GB；WSL 的 ext4 `df` 显示约 993 GB 可用，是虚拟容量，不能用来判断 Windows C 的实际安全余量。工具先测完整流长度，并为 ext4 设置“实际主机 C 空间 + 2 GiB 预留 + 128 MiB 分配余量”准入检查及每 64 MiB 重检。

本机 WSL 不能执行 Windows PowerShell（`Exec format error`），因此实时主机空间探针失败后，工具拒绝 ext4 写入。此次没有 ext4 解压或 ext4 原生 reader 对比，所有数据库衍生物均位于 D 盘；不能声称完成了 ext4/DrvFS 对比。

审计结束时 Windows C 可用 5,540,225,024 bytes，D 可用 253,596,680,192 bytes。未删除任何材料，所有生成的缓存保留。重型审计进程已结束。

## 保存的证据与工具

- `results/infrastructure_audit_v3_seed08_attempt03/report.json`：独立解码、SQLite 检查、输入前后指纹、ext4 失败关闭原因；保留完整独立数据库。
- `results/infrastructure_audit_v3_seed08_control/report.json`：同一解码器对 seed08 与 PASS seed09 的流式对照，均不写数据库。
- `results/infrastructure_audit_v3_seed08_native/report.json`：原生 ROS 读取探针及保留产物的 SQLite 检查。
- `results/infrastructure_audit_v3_seed08_native/derivative_comparison.json`：两个产物的逐字节前缀比较。
- `scripts/audit_compressed_rosbag.py`：主审计工具，支持 `--pass-control`、`--stream-only`、`--native-only`。
- `scripts/run_bag_reader_audit.sh`：加载冻结 ROS 环境后调用审计工具。
- `scripts/compare_bag_derivatives.py`：只读比较两个诊断产物。

另保留了两次工具完善过程的尝试：`results/infrastructure_audit_v3_seed08`、`results/infrastructure_audit_v3_seed08_attempt02`。首次在完整性结论落盘前中止，第二次记录流未结束异常；二者没有生成数据库，也不能作为 SQLite 完整性结论。其原始输入前后指纹保持一致。最终结论以上述三份正式诊断报告和前缀比较为依据。

后续如需利用独立解码产物补充评价，应在另一独立诊断目录中执行并清楚标注来源，保留正式试验的原始基础设施异常；不应无声替换原始 bag、原始评价结果或重跑整个实验矩阵。
