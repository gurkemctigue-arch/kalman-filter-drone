# Humble50 构建、原生测试与前三场开发证据

本目录是2026-11-02的最小字节一致快照。18个原始小文件共597146字节，各文件的原路径、字节数和SHA256见[manifest.json](manifest.json)。复制过程中逐项比较原件与副本，原件未修改。

- `build/`、`validate/`：真实受控构建和完整测试的外层终态与日志。
- `validation/`：四包构建、导入隔离、CDR/FastCDR、完整Linux套件与来源摘要。
- `registration/`：实际候选及核心执行合同。
- `initial_core_slots/`、`initial_core_attempts/`：前三场行人开发场景的原始槽和对应外层核验。

Linux1819项检查为1814通过、5项平台跳过。前三场原PASS不表示核心12已结束或整个项目已通过；正式研究仍为0/280。本快照不打包全部来源依赖、模型、录包或本机视频，不能单独作为完整复现包。

实时进度和解释见[本轮记录](../../../planning/reliability-v4-humble50-validation-20261102.md)。历史失败未被本目录覆盖或改判。
