# 完整回放清单准备记录

两份清单仅已准备，没有启动 native 或 formal。运行源码仍固定为父目录 windows04；原 short01 清单未覆盖。仅读取并核对 20 份小文件（580171 bytes），没有读取 bag 或模型负载。`small_bindings01.json` 固定小文件 SHA，`preparation01.json` 记录来源、预算与尚未执行的边界，`prepared_files_sha256.json` 固定本目录交付文件。

| 清单 | 原闭合 trial | 实际原权重 | 录包记录时间跨度 | 所选输入记录数 |
|---|---|---|---:|---:|
| person004_full01.manifest.json | person_stage1_velocity_seed004 | yolo11n.pt | 752.502678728 s | 50117 |
| car004_full01.manifest.json | car_stage1_velocity_seed004 | yolo11m_car_sim_train20_04.pt | 752.561540850 s | 50117 |

两份都使用原速 `replay_rate=1.0`、`record_limit=null`、各自原捕获参数 YAML、独立 `/bench/..._full01` 命名空间；QoS reliability/durability 从各自原 metadata 核对。中文挂载路径由实际 `Path.cwd().name` 构造，新清单中的问号数量为零。模型 SHA 来自原计划，压缩包 SHA 来自被原终态 SHA 绑定的 integrity 报告；负载本身仍须显式 native preflight 检查。

windows04 原生 timeout 上限为 900 秒。以完整录包记录时间跨度作为回放上界，扣除 2 秒 drain 和 0.3 秒稳定等待后，行人约剩 145.197 秒，汽车约剩 145.138 秒，供四个节点启动、子进程 SHA 检查、模型加载、reader 解压及调度延误使用。元数据上名义可用，尚不能保证实际运行足够。主进程 preflight、清理、结束后的 SHA 复核及 reducer 不包含在该 900 秒内，所以总墙钟耗时可能超过 900 秒。本次未修改该上限或加速回放。

固定代码 preflight 对 ext4 scratch 的空闲量最低要求分别大于 3137419473 bytes 和 3150099435 bytes；这只是 reader 临时空间下限，不能代替整个项目的 actual28/R0/budget 容量核算。

实际执行顺序保持：原 collector 全部退出 → actual28/R0/budget 核对 → 原生短台架 → 确认真实 FOLLOW 链路和清理 → 再决定完整回放或开销补测。容量预算为负时应先解决容量并保留现有证据，不能因清单已准备而声称正式实验启动。

将来确实运行时，沿用父 README 的显式原生 CLI，分别选择这里的清单、新的外部输出目录和独立 domain，并显式给 `--timeout-s 900`；CLI 自己获取现有机器锁。不得使用默认 120 秒跑这两份完整清单。它们仍只服务于被插桩观察的独立软件回放，不能改写历史 strict UNKNOWN 或 physical E2E。
