# Humble54 冷构建与独立补充审计原件

本目录保留具名小原件，不包含模型、bag、视频或完整源码映射。逐文件来源、字节数和 SHA 见 `snapshot.json`；完整源码映射保留在原 `results/frozen_fullplan_v4_humble54/freeze_validation/source_integrity/`。

来源提交为 `a32060d`，新冻结根为 `/root/uav_tracking_fullplan_v4_humble54`。四包冷构建、模块/ament 隔离及原生完整套件实际通过：2021项中2016通过、5项平台跳过。原公开 freeze 的返回码为0，复制前后源码及冻结副本全树映射一致。

外层首次命令仍为 **STOPPED_FAULT**，原 `native_build_supplement.json` 仍为 **FAIL**：测试摘要写stderr，而两条缓冲stdout日志在摘要之后输出，原补充解析器要求OK处于文件末尾而误拒绝。该原FAIL、原日志和冻结源码均未修改。

修正后的独立解析器仅在工作区变更，原生5项定向测试及独立静态复审通过。它另写全新 `native_build_supplement02.json`：绑定自身实际SHA，核原构建/套件零退出及原映射摘要，调用原冻结完整性helper重算1585个文件以确认源码仍未变，并重新执行实际FastCDR、模块、CDR和环境核验。新收据为PASS；新解析器不冒充经过原2021项完整套件。

此证据仅覆盖构建和补充审计，不代表汽车跟随或任何阶段完整验收。随后新75源秒汽车位置跟随复验已启动，必须等待原飞行和独立评价终态。
