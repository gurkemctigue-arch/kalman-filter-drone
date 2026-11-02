# Humble50：final-root-v2 三文件修复与证据快照

本目录保存已实际应用的三份 DDS48 工具源码、三份精确补丁、应用前备份及对应的小型验证证据。它是审查与复现用快照，不是新的运行入口，也不授予构建、注册或正式实验权限。`snapshot_manifest.json` 对每一份复制文件记录原始路径、字节数、SHA256、快照路径和逐字节比较结果。

## 本次修复

1. `applied_sources/build_development_final_root_v2.py` 修复同一目标根目录从冷构建环境切换到安装环境时的 DDS 校验：只允许原生工具定义的同根 `install/lib` 插入，保留原始冷构建证据，并绑定真实生成的 setup 文件。安装验证前调用已有的 CV2 preload-and-restore helper，核对完整环境恢复、模块来源、输入文件和前后 DDS 证据。原有 owner、2400 秒构建预算、编译、import、FastCDR、CDR 与完整测试边界继续保留。
2. `applied_sources/test_development_final_root_v2.py` 增加上述转换与 CV2 证据的元数据接收、拒绝和调用顺序用例，保留离线 `validate_completed_build` 不依赖调用者当前 DDS 环境、不额外执行 `source_check` 的原有约束。应用的是 candidate01；本快照没有收录或应用废弃的 candidate02 Windows 路径适配方案。
3. `applied_sources/seal_development_final_source_v2.py` 只替换 `CONNECTION_SHA` 一个字符串，使其绑定实际新 preparation canonical。sealer 保持独立 OWN 清单，不加入 preparation OWN，避免循环校验值。其余代码以及原 sealer 测试保持不变。

三份应用后源码 SHA256 分别为：

| 文件 | SHA256 |
| --- | --- |
| build_development_final_root_v2.py | `7405debd20fd1867858dba1b9a1baf507640fee3b4b2e77eb3df2e265ad60708` |
| test_development_final_root_v2.py | `bdf88c4cc55311faa2e46a403538e7df3d4245b2fd447b7dc14d498e1c77a7d9` |
| seal_development_final_source_v2.py | `02c9a91efcc3c1946e977727c162b5ca1ec401306c6d24f55b88e8ff0509297e` |

## 证据如何阅读

| 目录 | 内容与适用范围 |
| --- | --- |
| `applied_sources/` | 从实际 DDS48 生产路径按原始字节复制的三份已应用源码。 |
| `exact_patches/` | 之前审查过的三份精确补丁。 |
| `before_application/` | 本次应用保存的三份原始备份。 |
| `candidate03_history/` | candidate01 两文件的历史说明、审查记录，以及 candidate03 原生合成元数据测试的 runner、receipt 与原始 log。 |
| `sealer_static_derivation/` | sealer 唯一连接 pin 的静态推导、完整投影数据和当时的独立静态审查。 |
| `actual_application/` | 实际 application intent/result，以及调用真实工具清单函数的纯元数据脚本与原生检查 receipt。 |
| `independent_review/` | 对实际三文件、备份、受保护 SHA 映射及实际元数据证据的一次独立只读复核。 |

`candidate03_history/candidate_native_metadata_tests_attempt03.json` 与 `.log` 记录的是此前 candidate01 的 17 项原生 Linux 合成元数据测试：17 通过、0 失败、0 错误、0 跳过，用时 69.790 秒。它们没有使用 Windows 路径 adapter；测试通过外层 fixture 阻止真实编译、进程启动、ROS/CV2 import、DDS 运行环境获取及原完整测试套件。因此，这不是本次三份已应用文件执行完整测试的结果，也不证明真实 final-root 构建或运行已通过。

本次 `actual_application/native_actual_manifests01.json` 记录实际工具函数返回的完整清单与静态投影一致：preparation canonical 为 `e8585f14ece45335f24614a1794bedf1c205503a90cf587060ed25851c0bd0c9`；独立 sealer canonical 为 `ffa69d35ed1581c68e1b80ef0f3f5030be99178ea1236d5547c3fb4203268a41`。该原生检查仅获取 Python 元数据，未运行 runtime preflight、focused/full suite、真实冷构建、注册或正式实验。

## 当前来源与历史状态

本次只修改未来尚未使用的三个 helper。应用前已检查实际依赖关系与文件别名；应用记录和独立复核保留了 10 个受保护文件的前后相同 SHA。正在进行的 core 来源不变：core canonical 仍为 `2129fd88ec6f55625acaa1455919d516a364075394bd2e18efed3f108316a11a`，strict512 build canonical 仍为 `919a4483554c73cfbabb1efda910c2dd831e79b963443545bece5307fe51077e`。本快照不声明当前场次或 core 批次已结束、通过。

历史 candidate03 与 sealer 推导文件中的 `NOT_APPLIED`、未应用说明和原排序要求，描述的是其生成时状态，现按原字节保留。实际应用时间与提前应用这三个未被当前 core 引用文件的排序变化，见 `actual_application/application_intent.json` 和 `application_result.json`。后者的 native-pending 状态早于随后写入的 `native_actual_manifests01.json`。旧记录没有被重写；这些状态不会自动变为运行或验收授权。

仍需在 root 管理的空闲窗口执行现有适用 focused tests，并在独立的新 final root 完成真实冷构建、安装 DDS/CV2 证明及原 import/CDR/full suite。后续还包括真实协议、注册与容量准入以及正式 280 次实验。此快照不替代上述步骤，也不预填任何未来 PASS。

快照整理仅进行了 Windows 下指定小文件的读取、复制、哈希和逐字节比较；未运行 WSL、测试、仿真，未读取 rosbag、venv 或权重，也未修改原件、主文档或提交 Git。
