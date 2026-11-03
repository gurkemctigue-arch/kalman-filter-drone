# fixed05：新 JSON 文件完整后再发布

原生 short01 已真实退出为 `NOT_OBSERVED_INCOMPLETE_EXECUTION`。原 summary 的直接错误为 `JSONDecodeError: Expecting value: line 1 column 1 (char 0)`，并非 480 秒 readiness timeout。原实现先以 `x` 创建 ready 文件，再写 JSON；主进程检查 `is_file()` 后可能读到空或尚未完整的内容。随后主进程清理造成 adapter 的 KeyboardInterrupt 和 detector 的强杀退出，不能把它们当成最初故障。原输出保留不变。

本次只修改 bench.py 的 `write_new()`：在目标同目录创建私有暂存文件，序列化完整并关闭后，以 `os.link` 原子发布最终名字，再删除暂存名字。若目标已存在，硬链接操作直接失败，保留不可覆盖语义；没有使用可覆盖现存目标的 replace 或 POSIX rename。此操作要求目标文件系统支持硬链接，原生输出目录为 ext4。没有声称 fsync 级持久化保证。

没有改变算法源码、消息链路、ready 判定、timeout、清理门或计时结论。所有 fixed04 清单文件与测试记录已逐字节保存到 `archive_fixed04/`，归档收据 SHA 为 `ee68ea185703b6cc9a27139effbae8eb2c9579f4c597d67af2f588e12d4939b3`；原 short01 清单未变。

回归使用真实文件系统、并发写者与读者：序列化被有意暂停时，读者不得看到部分最终 JSON；竞争写者只能有一个成功，之后任何写入都不得覆盖已发布字节。原 20 项测试与两项新回归一并运行，另以归档 fixed04 的原函数作失败负对照。实际结果见 `validation_windows05.json`。

fixed05 尚未运行 native。下次原生回放须使用新的 short02 输出目录，并在 root 独审后执行；short01 的失败及历史 strict UNKNOWN、physical E2E 边界不变。
