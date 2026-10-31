# 补充协议前置检查：Humble系统Python组件复验

本目录补充[已审工具快照](../humble42_supplementary_preflight_snapshot/README.md)之后的实际平台组件验证。原快照的文件和清单保持不变；其“尚未验证Humble”描述属于归档时的状态。

在原Humble42核心批次停止、实际运行进程检查无残留后，使用`/usr/bin/python3` 3.10.12和`-I -B`，在仅含PATH、LANG、LC_ALL的环境中运行同一套40项合成测试。原生退出码0，40项通过，用时23.759785秒，四份组件/测试源码前后SHA一致。准确命令、源摘要和日志摘要见随附原始JSON；日志与JSON均按原字节归档。

测试创建的是临时小型计划、标记和审计数据，委托接口使用模拟回调。它验证实际系统Python下的组件兼容性，没有执行真实guard、adapter、serial、录包读取、推理、仿真或正式准入；真实Linux进程委托、信号链和正式串行接线仍需后续实际验证。这40项也不替代原核心批次的8 PASS、1 FAIL、3 PENDING结果。

`snapshot_manifest.json`绑定原平台回执、日志和本目录说明。原始文件在`D:/WSL/UAVHumble22-validation`，回执内的Linux绝对路径保留原来源。组件与依赖仍使用原快照说明的布局，本目录不是可独立部署的软件或正式飞行验收记录。
