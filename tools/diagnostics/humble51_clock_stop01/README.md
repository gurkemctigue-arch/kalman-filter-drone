# Humble51 第四场停止原件快照

北京时间 **2026-11-02 19:10:29**，原核心命令监控为 `STOPPED_FAULT`、退出2；原槽为 **3 PASS、1 FAIL、8 PENDING**，正式 **0/280**。本目录逐字节复制8个原始小JSON，共 **98518字节**；真实源路径、原SHA-256和副本比较结果见[manifest.json](manifest.json)。

- `reports/`：原source-clock与native-startup报告。
- `slot/`、`attempt/`：第四场原FAIL与对应外层拒绝终态。
- `monitor/`：原命令停止监控终态。
- `owner/`：原小copy候选、native退出终态及归档清单。

source-clock原FAIL包含4次未来时间拒绝、1次诊断交付越界，另有2条raw/timing缺配对。native原FAIL为1次phase时间越界，其余起飞、模式、地面就绪与handoff检查true。

随后一次37.007秒的原生只读遍历已将所有异常定位到同一84.028秒附近窗口，原压缩包和小报告前后SHA不变。[native_readonly/summary.json](native_readonly/summary.json)及同目录脚本、421条窗口记录为后来产生的诊断附件，与上述8份原终态分别列在manifest中。Clock源步长完整，但84.028到84.032秒两条消息的recorder时间戳相隔0.916707468秒；这支持继续检查交付和排队，不能直接定位具体根因或更改原FAIL。

`owner/execution_terminal.json`明确是原始 `COPY_VERIFIED_PENDING_OWNER_CLOSURE` 候选；最终 `NATIVE_FAILED_RAW_ARCHIVED` 位于未打包的整批外层记录，属于后续失败路径状态。copy候选保持原字节，归档记录的local/archive SHA与字节一致，不能把成功路径验证拒绝失败owner解读成原件被篡改。

此快照不含bag、图像、视频、巨大outer或完整health记录；仅附少量派生窗口JSONL，不构成完整复现包，也不运行新验证框架。局部 `.gitattributes`禁止文本换行转换以保留原字节。历史PASS、FAIL、未知和缺配对均未修改。

详细数值、解释限度和下一步见[停止与诊断记录](../../../planning/reliability-v4-humble51-clock-stop-20261102.md)。下方原始文件名和状态均应按其生命周期阶段理解，不能用较早候选声称最终健康通过。
