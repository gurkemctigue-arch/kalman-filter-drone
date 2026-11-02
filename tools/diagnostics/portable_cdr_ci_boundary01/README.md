# 无ROS便携CI中的真实CDR测试分流修复

提交`d4e473a`的[原Actions运行](https://github.com/gurkemctigue-arch/kalman-filter-drone/actions/runs/41401412315)在Python3.10及3.12均失败。每组1819项、1失败、5跳过，唯一失败是`test_exclusive_navigation_cdr`的真实子进程缺少`rclpy`。后续replay步骤未执行。两份完整原始job日志保存在本机外部目录，公开只复制精确失败片段及审计收据，原件路径和SHA见收据。

`policy/`保留此次精确候选补丁，实际公开测试源码位于[CDR测试](../../../tests/test_exclusive_navigation_cdr.py)。只在未登记原生配置且包确实不存在时，允许专用退出码和精确标记触发SKIP；已安装损坏、已登记原生缺依赖或CDR断言失败仍为FAIL。未修改飞行算法、冻结50、运行合同或已完成实验。

`evidence/`保存原失败片段、只读GitHub审计和Windows人工边界观察。Windows原测试仍按平台跳过；人工观察仅临时执行现有方法，验证“可选缺包会跳过、原生必需却缺包会失败”，不是两次成功原生测试。独立修复审查见`review/`，字节一致清单见`manifest.json`。没有把旧失败提升为通过；修复后的实际Linux CI结果须另行读取。

当前运行和后续final复制都读取冻结50的副本，public main的补丁不自动进入该来源。完整来源重验依旧逐项执行，最终原生构建与正式实验不能由本目录或便携CI代替。环境边界详见[说明](../../../docs/CI_NATIVE_CDR.md)。
