# Stage 3 person midpoint seed004 rosbag audit

审计对象：`fullplan_v3_stage23_s3_person_gimbal_midpoint_seed004`（正式冻结槽）。

审计时间：2026-10-27（Asia/Shanghai）。本审计只读原始槽；没有重飞、重试同名槽、修改压缩包或补写任何正式评分。

## 结论

该槽的飞行本身完成，`summary.json` 的 `basic_flight_passed=true`、`termination_reason=follow_duration_reached`，但两个离线评估器都因 rosbag SQLite 读取失败退出，未生成 `flight_evaluation.json` 或 `gimbal_evaluation.json`。因此该槽不能获得正式离线评分，应在正式台账中保留为 FAIL/基础设施异常，不能按飞行成功推导跟踪或云台指标。

问题定位到录制压缩文件的完整性，而不是评估脚本选择条件或指标判定：评估日志明确报告 `SQLite error (11): database disk image is malformed`，并指向该槽的 `rosbag_0.db3`；同一压缩文件的独立 zstd 完整性检查也报告 `Read error (39): premature end`。

## 原始证据

`rosbag/metadata.yaml` 声明：SQLite storage、zstd FILE 压缩、73,776 条消息、单文件 `rosbag_0.db3.zstd`。原文件大小为 414,030,971 bytes，SHA-256：

`7C4B4D4EA1E78ABB5CE4B8280B2A2F5679AE00C79872CA0879BC4CF51B42FAA4`

相关原始文件 SHA-256：

- `metadata.yaml`: `3D5B2F1F0D879D866C9E1EE6E823BCE4E63B47386F045400E55B725C256A7A0E`
- `bag.log`: `244EDB00729674F05196E7DBE821BB36A1847C78F6A8402DB9045A61B40852C4`
- `summary.json`: `8756DA29AB04E7819136D8132B64D212B5E325805C034B45C99A00C5333B52DB`

录制日志显示 rosbag2 在停止时正常完成“Writing remaining messages from cache”并开始 `Compressing file`，随后报告 `Recording stopped`；这只能证明录制进程正常退出，不能证明压缩帧完整。

冻结 guard 事件中两个评估器均返回码 1、无报告，并记录同一 SQLite malformed 错误。评估日志 SHA-256：

- flight evaluator log: `3B97FC6B53EE5CD2FA3A91A620959065A02A9767350FD4D191BA33A385226624`
- gimbal evaluator log: `2442A283E319DBC72397FD5878481741A055D0E9B3F07229C2225CEFD7D4B2EF`

## 独立解压检查

在源文件之外的临时目录执行 `zstd.exe -t`，结果为退出码 1、`Read error (39): premature end`。为确认不是 rosbag2 评估器路径特有的问题，又以 `zstd -d -c` 独立流式解码到临时文件。zstd 仍以退出码 1 结束，但产生 1,320,943,616-byte 的部分 SQLite 文件；SQLite 头为 `SQLite format 3`，页大小 4096、页数 322,528，按头部应有 1,321,074,688 bytes，实际少 131,072 bytes（32 页）。

对该独立部分文件运行 `sqlite3 .tables` 和 `PRAGMA quick_check` 均返回 `database disk image is malformed`（错误码 11）。因此独立解压不能得到可供 rosbag2/SQLite 读取的完整数据库；它只能证明源压缩数据能解出前缀，不能恢复缺失尾部，也不能生成正式指标。

## 处理边界

本审计没有对压缩文件追加零页、重建数据库、修复 SQLite、重新运行评估器或修改正式槽。任何从部分前缀“恢复”的消息都不应进入正式台账。应保留该槽及其失败原因，并在新的唯一 trial 名称中重新执行录制/评估；重试结果不能覆盖本槽的历史证据。

机器可读摘要见 `results/audit_stage3_person_midpoint_seed004_bag.json`。
