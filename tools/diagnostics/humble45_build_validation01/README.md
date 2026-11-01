# Humble45 构建、候选发布与首次单场计划失败快照

此目录仅保存 20 件原始小型证据的逐字节副本，不执行构建、测试、WSL、仿真或录包。原路径、长度和 SHA256 见 `manifest.json`，目录校验见 `SHA256SUMS`。

45 的 prepare、copy、build、validate 四个原 action 均为 PASS，直接子进程退出码均为 0。原完整 Python suite 为 **1767 项，包含 5 项平台跳过**，因此 1762 是 `1767−5` 得到的通过项数，不是另一轮测试。原日志 footer 为 `Ran 1767 tests` / `OK (skipped=5)`；同时保留 source manifest、构建摘要、colcon 日志、生成消息 CDR、import/ament 隔离和 FastCDR 来源证据。

FINAL candidate SHA 为 `b20438f956f91cafe4e65e25b2f9341a0cf88a50abc6194372f0912065cdabe6`。source FINAL、source peer、candidate FINAL/peer 和真实 publication result 分别保留。候选发布及正常原生加载通过，仅表示构建候选成立，**不表示飞行、完整开发矩阵、正式准入或项目验收通过**。44 原 suite 的 3 项错误和失败结果仍保留于相邻 `../humble44_validation_failure01/`；45 成功不重写 44。

两个失败分别保存，不能覆盖或混为一谈：

- 系统 Python 发布调用返回 1，错误为 `Original archive process command/manifest binding differs`；该次尚未发布 FINAL。随后由正确 venv 发布成功，原失败 receipt 单独保留。
- 45 第一次单场 **plan** 返回 2，`flights_started=0`，`plan_pending=null`；原错误为 `Inherited resource/T4 timing envelope changed`，并保留 `final_errors` 中 `Owner outcome differs from original immutable D copy candidate`。其 owner execution/native terminal 同时复制。它是计划及 owner 闭合失败，没有产生一次飞行结果；后续修复必须另建证据，不能修改这里的失败。

本快照不是可独立执行的完整工具包。其 JSON 中原绝对路径、历史绑定和状态原样保留；复制不会使原 source/owner/归档证据获得新的准入资格。
