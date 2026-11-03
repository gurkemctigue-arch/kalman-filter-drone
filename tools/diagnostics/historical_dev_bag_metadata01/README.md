# 历史开发压缩录包：Windows 元数据清单

本次仅枚举 `results/frozen_fullplan_v4_humble01` 至 `humble53` 的直接子试验目录下，`rosbag` / `raw_rosbag` 内直接普通文件的 `.zstd` / `.zst` 文件名、逻辑长度和修改时间。未递归扫描其他目录，未打开压缩录包、计算哈希、启动 WSL、压缩或删除。活动的 humble54、final55、旧 v3/formal 和 reparse/symlink 均不进入本次范围；对可能仍写入的近期文件另设10分钟修改时间排除。旧目录未作进程存活证明。

实际浅层扫描耗时约 **0.73 秒**，无错误、截断或额外结构；扫描文件的长度/mtime均再次核对一致。结果见 [inventory.json](inventory.json)：完整53根汇总、245个试验的逐文件元数据、按大小排序的前20个试验，以及明确的测量边界。

- 53个历史根中40个有匹配压缩包，共 **245个试验、245个文件**。
- 逻辑长度合计 **106,008,772,735 字节，约98.73 GiB**；前20个试验合计约14.96 GiB。

| 历史根 | 压缩文件数 | 逻辑大小 GiB |
|---|---:|---:|
| humble43 | 33 | 16.070 |
| humble25 | 14 | 8.409 |
| humble18 | 14 | 5.610 |
| humble17 | 14 | 5.600 |
| humble38 | 13 | 5.366 |
| humble28 | 14 | 5.269 |
| humble32 | 14 | 5.211 |
| humble50 | 12 | 4.936 |

只对最大的4个试验读取各自已知、唯一的约54 KB原slot终态，未扩搜其他路径或复验其payload/digest：

| humble43 原试验ID | 逻辑 GiB | 小终态原status |
|---|---:|---|
| car_extension_depth_noise_seed004 | 1.181 | PASS |
| person_extension_depth_noise_seed004 | 1.131 | PASS |
| car_extension_combined_seed004 | 0.998 | FAIL |
| person_extension_combined_seed004 | 0.976 | FAIL |

以上仅为原小终态中的已保存状态，其余试验状态均标为未读未知；不据此推断验收或档案完整性。失败数据和原件仍须保留。

**逻辑长度不是NTFS实际分配量，也不是删除后能收回的空间估计。** 本清单不判断文件是否冗余、是否仍为报告/审计依赖，不构成删除清单或删除许可。任何后续清理都须另列具体文件、核实保留方案并取得用户具体决定。

JSON 使用 UTF-8。请通过 `json.loads(path.read_bytes())` 或显式 `encoding="utf-8"` 读取；Windows 默认编码会误解码其中的中文路径。[路径复核](scope_correction01.json)已通过原始字节和文件身份确认，本清单属于正确工作区；另一乱码目录在本次精确范围内没有对应历史根。原 inventory 字节未改动。
