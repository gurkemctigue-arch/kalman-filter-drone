# Humble32 核心结果与 Humble33 验证边界

本记录是开发检查点。正式实验仍为 **0/280**，种子1000–1009未使用；原失败、UNKNOWN、删失及全部原始归档保留。

Humble32 的12个原计划槽于2026-10-30 17:21:59 UTC全部结束：**9 PASS、3 FAIL**。这是一个seed004开发批次，不能解释为重复实验成功率。外层返回0表示12次尝试及清理正常结束，不能代替工程验收结论。没有基础设施停止，源绑定前后相同，独立观察器正常收尾，残留进程为空。

| 场景 | 原结果 | 距离RMSE/m | 高度RMSE/m | 有效导航覆盖 |
| --- | --- | ---: | ---: | ---: |
| person stage1 velocity | FAIL | 1.311 | 0.190 | 0.773 |
| person stage1 position | PASS | 0.794 | 0.175 | 0.915 |
| person stage2 crossing | PASS | 0.885 | 0.166 | 0.888 |
| person stage3 midpoint | PASS | 0.773 | 0.161 | 0.915 |
| person stage3 active | PASS | 0.761 | 0.160 | 0.916 |
| person stage3 multi active | PASS | 0.910 | 0.154 | 0.888 |
| car stage1 velocity | PASS | 0.739 | 0.156 | 0.916 |
| car stage1 position | PASS | 0.731 | 0.167 | 0.915 |
| car stage2 crossing | FAIL | 4.553 | 0.161 | 0.695 |
| car stage3 midpoint | PASS | 0.755 | 0.162 | 0.916 |
| car stage3 active | PASS | 0.759 | 0.156 | 0.914 |
| car stage3 multi active | FAIL | 4.658 | 0.165 | 0.683 |

误差使用整段独立真值与base_link参考，保留失跟及悬停尾部；12组整段真值匹配覆盖均为1.0。导航覆盖按原固定10Hz网格计算。行人velocity的距离、高度持续稳定均右删失，不填成0。其他槽的末端稳定不能抹去此前失跟或整段大误差。

四组指定个体的任务身份评价从首次REQUEST到记录结束，采用固定10Hz时间分母，和导航分母不同：

| 场景 | 正确 | 错误 | 未知 | 总格数 | 已知覆盖 |
| --- | ---: | ---: | ---: | ---: | ---: |
| person crossing | 649 | 0 | 104 | 753 | 0.862 |
| person multi active | 647 | 0 | 107 | 754 | 0.858 |
| car crossing | 524 | 0 | 232 | 756 | 0.693 |
| car multi active | 492 | 0 | 264 | 756 | 0.651 |

零已知错误不证明未知区间身份正确。8个单目标槽没有相同身份报告，不补造指标。六个云台原子评价全部PASS，其中汽车multi-active整体仍FAIL；本轮也没有证明主动云台优于中位模式。

三项失败需要分别处理：

- 行人velocity在重新选框后的末段因观测超时进入LOST/HOLD。最后接受测量85.2秒，85.6秒候选的发布前时钟采样已为85.972秒，观测在85.980秒到达，超过旧测量原0.75秒期限。该采样时刻不等于最终发布或端到端完成时刻。具体耗时环节尚未确定，不能把原诊断工作段耗时称为纯YOLO耗时。
- 汽车crossing短遮挡本身PASS，但31.7秒起发生关联歧义，32.36秒进入LOST，直到显式重选；因此后续长遮挡缺少预测证据。第二次任务覆盖约0.947不能代替第一次任务失败。
- 汽车multi-active短遮挡期间已经LOST，后续长遮挡同样缺少预测证据。其云台PASS不能代替身份及跟随通过。

汽车crossing的只读检查发现：29.8→29.9秒，一个后车框IoU约0.947，但ROI深度从约14.16米跳到9.54米，随后生成竞争轨迹4。该候选实际内缩采深ROI完全位于另一候选框内。图片显示确有两辆车重叠，不能把后车当作重复框删除。31.5秒又出现轨迹6，31.7秒形成严格匹配歧义。这个证据支持深度归属风险；框并非像素级物体标签，不能只凭框包含就宣称所有深度来自前车。

需要同时检查三维测量可信度和未知候选的新生/关联语义：只将position_3d设为None仍会触发IoU回退，只删除LOST竞争轨迹也不足以安全修复。原观测0.60秒、预测0.75秒及身份丢失锁存保持不变。

Humble33 的目的仅为定位耗时。它从提交3639a3eac8d4aa2d4dfccd1693b990c9958c06ca冻结601个源文件，canonical SHA为4300490a223039cd5e58ca5403b92be09014b494837a27d4ef081fac277a3667。四包冷构建、FastCDR来源、11种真实消息CDR及模块/ament隔离通过；完整套件1543项中1534通过、4 ERROR、5项按原平台条件跳过。4个ERROR全部来自新增计时测试使用了Python3.11才支持的TestCase.enterContext，而Ubuntu22.04使用Python3.10。原33验证FAIL保留，未创建诊断计划或执行飞行。

主树测试改用标准ExitStack.enter_context并在进入patch前注册addCleanup(close)，测试内容、patch顺序、断言与生产源码不变。作者Windows29项0.162秒、独立Windows29项0.255秒及实际Ubuntu Python3.10的29项0.071秒均通过。此聚焦检查不代替下一来源的四包构建和完整套件。

为检查汽车深度，已从原生关闭录包精确提取29.8/29.9/31.5/31.7秒的RGB、Depth、CameraInfo：四组严格header整数纳秒配对通过，三个topic各932条，耗时13.245秒；原metadata及compressed归档未变，owned缓存已移除。输出原数组、无叠框RGB图、校准与收据；不读取GT指导关联。实际深度分析仍待完成，提取PASS不表示问题修复。

本机证据入口：

- 原12槽：results/frozen_fullplan_v4_humble32/reliability_v4_humble32_probe01_seed004_matrix。
- 原33失败验证：results/frozen_fullplan_v4_humble33/freeze_validation/build_validation_summary.json。
- 独立汇总：D:/WSL/UAVHumble22-validation/humble32_closed_core12_review01。
- 真实关键帧：D:/WSL/UAVHumble22-validation/humble32_car_roi_exact01。

原32 core终态SHA：a32d5ce34926f6da77f7343763aec2161b1cd30f714be726537f92d1aec4fbca。
原33完整测试日志SHA：cd586d5ab8b59d729d03de4206de18be0f8a3349e31cc71ba0240108450b5191。
真实关键帧收据SHA：91327d9113708fb29121f4e97289ac8c752bb5bee0ea2eb637bd263c22fefef4。

后续先完成测试兼容新来源及真实分段计时，再依据实际RGB-D证据实现关联修复；修复版仍需同源12核心、4安全、16扩展、定标和容量准入，再登记280正式实验及完成离线比较、检测/身份统计和最终交付。任何旧版本或短测成功都不补成新来源验收通过。
