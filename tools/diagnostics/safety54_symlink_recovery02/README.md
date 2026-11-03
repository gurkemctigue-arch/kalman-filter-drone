# safety54 路径修复与实际原生诊断

本目录保留原 producer，并归档 11 份原始小文件，共 128143 字节。复制件与原件已逐字节比较，SHA 均一致；[清单](source_manifest.json)和[独立审查回执](review_receipt.json)记录来源、绑定及范围。

- [实际原生测试日志](originals/native_tests/native02.log)：2 项真实 symlink 单元测试通过，0.896 秒、无跳过；[保存退出码](originals/native_tests/exit_code.txt)为 0。
- [实际 recovery02 回执](originals/repair/native_recovery02.json)：生成 [contract02](originals/contracts/contract02.json)，原 helper 验证首份快照；另两份以原始字节、SHA 和完整映射相等核对。旧命令的 lexical 路径拒绝被复现，physical 路径只读命令合同诊断通过。
- 仅外置 driver 的命令合同参数增加 `directory.resolve(strict=True)`；其余流程保留 lexical 路径。[原 driver](originals/repair/original_driver.py)和 [contract01](originals/contracts/contract01.json)保留。回执 `bundle_before` 是替换后的基线。
- [原 safety01 终态](originals/failure01/execution_terminal.json)仍是 `STOPPED_FAULT`，首槽仍为 `INFRASTRUCTURE_ERROR`；未重写或升级。

这是两项单元测试和原生合同、快照及只读命令诊断的证据，不能代替新飞行、安全四场、完整旧槽重评或正式准入。独立归档审查未启动 WSL、重跑测试或读取模型、bag 载荷；Linux 固定工具前后 SHA 来自实际原生回执。
