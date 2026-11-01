# Humble43 combined 提前失锁的观测间隔解释

本快照逐字节保存[既有小窗诊断](humble43_combined_early_loss_causal_window01.json)，用于解释`person_extension_combined_seed004`的原FAIL。原始槽、外层回执和先前诊断保留在[第五场失败快照](../../experiment_orchestration/humble43_extension_partial05_snapshot01/README.md)。本次只复制小JSON并核对哈希，未再次读取telemetry或bag，未重飞、重评、运行WSL或修改门限；原工程FAIL保持。

诊断引用的冻结故障桥与当前[主树源码](../../../scripts/sensor_fault_bridge.py)小文件SHA256相同：`c07b1b5e7a7addbe2b7b4ad63cb798503646a8f92cf14aa66a1fd35582a486f0`。该配置以200 ms时间窗、seed4、fraction0.1进行确定性哈希丢弃，RGB与Depth共用决定。窗171/172/173连续drop，对应源时间`[34.2, 34.8)`，覆盖0.6秒；10%参数不是逐帧独立丢弃，也不保证最大连续空窗小于0.75秒。

原小窗中最后接受的观测采集于34.1秒、轨迹提交于34.204秒；下一条观测采集于34.8秒、约34.9秒到达，与上述连续drop窗吻合。0.7秒采集间隔加约0.1秒源时间到观测输出的间隔，超过原0.75秒预测预算，与约34.85秒到期、34.86秒LOST一致。最后接受观测的马氏距离平方约0.00821、门限9.21，拒绝计数0；该窗口内已提交的选定轨迹尝试没有连续关联/KF门控拒绝证据。

这支持“既定combined故障配置造成连续观测间隔超预算”的解释，状态为`CAUSAL_WINDOW_OBSERVATION_NOT_ROOT_CAUSE_CERTIFICATE`。缺少桥输入/输出的逐帧独立交付账本，不能独立证明全部传输过程，也不能排除空窗内另有传输、调度、同步或检测输入丢弃。存活帧的时间匹配不补足这些证据。telemetry摘要仍引用原槽保存值，本次没有重新计算其哈希。

原件来自`D:/WSL/UAVHumble22-validation/humble43_combined_early_loss_causal_window01.json`，64,769字节，SHA256为`73a0785b491d8715f695ac09b2d834b749bf3db446a09e14da721740ae6bc783`。[来源清单](ARCHIVE_MANIFEST.json)记录复制来源、字节与摘要；[SHA256SUMS](SHA256SUMS)覆盖payload、README和manifest，排除自身。快照不改批次实时计数，不代表新的实验通过或正式准入。
