# Humble54：前六场行人开发槽小文件闭合快照

本目录保存 canonical12 前六个 **person、seed004、75 秒开发试验**的原始小文件。这六场原槽均为工程 `PASS`，实际飞行命令退出 0，`infrastructure_stop=false`，清理记录无残留。结论限于该六场，不把独立汽车位置模式探针拼入 canonical12，也不表示核心 12 场、安全 4 场、扩展 16 场或正式研究已完成。

[review_receipt.json](review_receipt.json) 保存本轮审查过程与结论；[manifest.json](manifest.json) 为逐文件原路径、字节数和 SHA256；[collect_snapshot.py](collect_snapshot.py) 为只读取小型存档的收集程序。`originals/` 中 **269 个原件、3,900,113 字节**逐字节复制自本机原件，包含原计划、六个原 slot 及 started 标记、六组 navigation/source-clock/native-startup 报告、三组云台报告、两组 stage2 行为报告、配置和运行来源归档、闭合/录包/退出小报告及评价小日志。原件和 Git index 均未修改。

前三场详细检查复用已存在的独审收据：SHA256 `edfd8ceb84b7d66c805d961c3986debfeca62ac08aa8c54da517add9e07a9019`。该收据此前核对 127 个小型 JSON/log；本轮核对其 SHA、三场原 slot 和必要快照小件，**没有重新遍历并计算那 127 件完整集合**。既有收据及说明以原字节保存在 `originals/prior_first3/`，其中第三场逐任务数字来自 root 的独立大报告读取，其边界继续保持。

本轮对新增第 4—6 场独立核对了原 slot 自摘要与原计划绑定、共 **130 个小型 JSON/log 的实际 SHA（43 + 43 + 44）**、原评价退出码和脚本/依赖摘要、原运行参数与实际命令、源码快照、运行来源小归档及清理/录包/闭合记录。六场导航报告的六项工程门槛均由保存的原报告重新比较，且与原 slot 所记录检查一致。

上述 130 项校验由收集程序直接读取本机原件完成，逐项结果保存在收据中。Git 快照保存必要原件子集，未复制全部 130 项，例如部分运行日志和 graph-startup 报告未收入。因此仅凭本目录副本可复核已复制证据，不能声称离线重新计算了全部 130 项原件摘要；缺项的原路径、字节数和本轮实际摘要仍见收据。

| 原场景 | 距离 RMSE/m | 高度 RMSE/m | 有效导航样本/分母 | 六项工程门槛 |
| --- | ---: | ---: | ---: | --- |
| person stage1 velocity | 0.772993 | 0.149616 | 688/752，91.49% | 全部符合 |
| person stage1 position | 0.758464 | 0.166427 | 689/752，91.62% | 全部符合 |
| person stage2 crossing | 0.885960 | 0.173842 | 670/752，89.10% | 全部符合 |
| person stage3 midpoint | 0.750936 | 0.155455 | 688/752，91.49% | 全部符合 |
| person stage3 active | 0.745811 | 0.161307 | 689/752，91.62% | 全部符合 |
| person stage3 multi active | 0.871259 | 0.160355 | 668/752，88.83% | 全部符合 |

六场真值覆盖均为 752/752，距离和高度的最终持续稳定标记均为真。导航原状态全部保持 `RECORDED_WITH_CENSORED_FAILURES`，无效、丢失和悬停区间仍在完整分母中；工程 PASS 不表示每个区间都成功，也不能直接换算为算法总体成功率。

新增三场的 source-clock、native-startup、surface-flight、gimbal 原报告为 PASS，原 stage2 multi-active 行为报告也为 PASS；源时钟与原生启动的小报告脚本/依赖摘要符合计划，源码快照对应原冻结 map 的扫描规则及模型/DDS 摘要，保留 17 个原有额外副本。`owned_stop_observer` 为 `EVIDENCE_COMPLETE`，其 `runtime_acceptance=NOT_EVALUATED_EXISTING_PROCESS_AUDIT_REMAINS_REQUIRED` 原标记保留，未被改成运行验收。

身份仅引用小 slot 内嵌摘要，完整请求时段与诊断帧采用各自分母：

| 场景 | 完整任务正确/错误/未知 | 完整任务覆盖 | 另一组诊断正确/错误/未知 |
| --- | --- | ---: | --- |
| person stage2 crossing | 649/0/104，共 753 | 86.1886% | 651/0/101，共 752 |
| person stage3 multi active | **648/0/106，共 754** | **85.9416%** | 650/0/103，共 753 |

诊断帧数字不能替代完整请求时段。第三场 1,663,576 字节、第六场 1,692,013 字节的 `physical_identity.json` 均超过本轮 1 MiB 边界，**本轮没有读取、计算其实际摘要或独立核对逐任务身份数据**。原 slot 中记录的大报告 SHA 仍只是原记录，不能算本轮重新校验。第三场 root 另有逐任务来源说明，本目录不将其提升为本轮独审结论；第六场也不声称每个任务分别超过 80%。stage2 行为报告自身仍明确 `physical_identity.evaluated=false`，任务 UUID 保持不等于物理身份已核实。

本轮没有启动或导入 WSL、ROS、native、原评估器或项目算法模块，没有读取或计算任何 bag、JSONL、telemetry、模型二进制、VHD、大 ROS 日志或大身份报告的摘要。来源/退出/云台/行为/归档结论限于已保存原报告的检查；源码清单不能证明每个历史飞行进程实际导入的位置，也没有重新评价原始录包。

本轮收据 SHA256：`b72182446ccd1be9bcfb77a9b684b5414db6abd160650b01404995f6f7ef4cad`。快照清单 SHA256：`7fec24229759613d5185003cf62e3874ee68aa296d4050c6f7f89c8b7165de4c`。收集程序 SHA256：`670269d573c95765ff99d0bfd71965e8e957d69993a55480f8e17e32df219e1e`。

这六场属于同一随机种子的行人开发证据；汽车效果、全部可靠性问题和自适应 KF 优越性尚不能由此得出结论。正式研究仍为 0/280。
