# 新录制的无损归档候选与停飞后处理预算

本次只修改未来新录制的归档方式，不重压缩、替换或重写任何旧包、旧 manifest、原失败记录或已冻结来源。新来源须经 root 审核、新 freeze 和统一 Linux 验证后才用于后续飞行。

## 实测依据

`D:\WSL\UAVHumble22-validation\humble25_lossless_compression_benchmark01\benchmark.json` 的 SHA-256 为 `17af48519967722462406920ff6d5ce1d8c1170574c22fb418bcde34517599c5`。完整开发样本为 Humble25 的 `car_stage1_position_seed004`，75 秒，原 `zstd -T1 -3 --check` 归档 728,303,603 bytes；原始 SQLite 为 2,139,459,584 bytes，SHA-256 为 `811835ee933d05b2e46559c67227d8335715c08d7fd381d0a4c27a1015069498`。

| 固定候选 | 归档 bytes | 比原包减少 | 压缩管线 wall 秒 |
| --- | ---: | ---: | ---: |
| `-T1 -15 --long=27 --check` | 698,033,410 | 4.1563% | 88.234 |
| `-T1 -19 --long=27 --check` | 496,177,751 | 31.8721% | 310.706 |

两候选都通过标准 CLI 检查、完整解压字节数与 SHA 对照，并由原冻结的 ROS `SequentialCompressionReader` 无过滤读完全部 148,711 条消息，逐话题计数相同。原包未改变。选定第二候选用于未来新录制。

测量采用“原压缩包解码到 stdout，再编码候选”的串行测试管线，不是直接从新 ext4 SQLite 归档的等价耗时测量。`-19` 编码器峰值 RSS 为 464,252 KiB；管线各进程独立峰值之和 468,732 KiB 不是同时测得的进程树峰值。128 MiB 的 long window 也不是总内存需求。其原生验证另耗时约 68.740 秒，缓存位于 D 挂载目录，不能解释为飞行实时性能。

这是一个干净汽车样本；不能把 31.8721% 外推为 RGB-D 噪声、空洞、双流扩展或最终 28 格的实测节省。最终 28 格容量门仍未通过，须用新来源完整样本、实际临时开销和刷新后的宿主/guest 空间预算判定。

## 实施与证据

- `recording_archive.py` 固定使用 `zstd -T1 -19 --long=27 --check`。保留 ext4 录制、recorder 正常关闭、SQLite 全检查、精确解压 byte/SHA、原生全流读取、原生解压 byte/SHA、发布副本 SHA、独立 spool 所有权和失败保留的全部检查。
- 为新归档新增实际 profile/argv、压缩时长、总后处理开始/结束与耗时证据；`configuration/recording_policy.json` 显式记录同一实际 profile。旧 schema 与 policy 标识不改，新增字段不伪造旧记录的参数。
- `run_reliability_v4.py` 为新计划冻结独立 `postprocessing_timeout_s=1800.0`，外层 `trial_timeout_s=wall_timeout_s+1800.0`，并严格验证预算与构造关系。旧 manifest 保留，由其原 frozen runner 解释。

1800 秒是停飞后的关闭、校验、归档与发布余量，不扩大飞行时间。`run_stage1_trial.py` 内原 flight deadline、monitor 的 `--wall-timeout`、源钟、观测/预测/状态时效、native 起飞与交接安全门、飞行命令及离线评价时限均保持原值。归档仍在全部飞行进程停止后开始。外层预算不保证任意未来双流数据都在时限内完成；超时或校验失败仍应保留失败证据，不重试或宣称通过。

## 本次验证边界

只运行主机专项测试与语法/差异检查，不运行完整 suite、WSL、原生 ROS、Gazebo、PX4 或新飞行。新压缩命令的 Linux 集成与新 freeze 由 root 统一串行验证。外部 Humble26 guard 的 runner AST 差异白名单、来源哈希/诊断绑定、计划重构和 fixture 需审查更新；本次不修改该 guard，也不放松其源码检查。
