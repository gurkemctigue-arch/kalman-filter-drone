# 仿真 CPU 资源节奏登记

本改动只提供可选登记能力，未修改现有协议、冻结版本或正式实验状态。旧协议不含 `simulation_pacing_registration` 时仍固定使用 RTF `0.25`、飞行墙钟预算 `600 s`。

当前机器的检测处理耗时可能使测量供给低于仿真源时间中的目标频率。新增固定修订允许将仿真请求节奏降至 RTF `0.125`，为同一段物理运动提供更多 CPU 墙钟时间；飞行预算对应增加至 `1000 s`。这是仿真资源配置，不代表已改善闭环结果，也不证明实机实时性能。

只有新的独立协议完整声明以下内容，才接受新配对值：

```json
{
  "real_time_factor": 0.125,
  "flight_wall_timeout_s": 1000.0,
  "simulation_pacing_registration": {
    "revision": "simulation_rtf0125_wall1000_v1",
    "real_time_factor": 0.125,
    "flight_wall_timeout_s": 1000.0,
    "follow_duration_s": 75.0,
    "max_inference_rate_hz": 10.0,
    "physical_identity_sample_period_s": 0.1,
    "scope": "simulation_cpu_wall_resource_only",
    "safety_source_time_gates": "unchanged"
  }
}
```

缺字段、额外字段、其他修订、任意数值、布尔代替数字、NaN/Inf，或顶层配对值与登记不一致，均拒绝。新登记的开发与正式计划都固定 `1000 s`，禁止命令行覆盖为其他预算。旧协议保留原有开发探针预算覆盖能力。

核心和扩展计划的默认飞行预算读取已验证协议；新修订也写入每条 trial 规格。命令、`run_config.json`、supervisor YAML 与实际世界文件中的 RTF 均需一致。停飞后处理与评价预算各保留 `1800 s`，新外层 trial 总预算为 `2800 s`。四安全专项沿用从最终协议读取 RTF 和飞行预算的既有检查。

75 秒跟随任务、每仿真秒的运动速度、10 Hz 推理上限、固定 10 Hz 身份评价网格、观测与预测源时间门、马氏门和丢失重选保护保持原值。独立原生起飞和源时钟检查仍按原规则执行；降低 RTF 不能跳过这些检查。

开发关口对新修订绑定 `simulation_pacing_sha256`，并双向比较开发证据与最终计划的有效节奏。旧 RTF 0.25 的证据不能作为新 RTF 0.125 的同节奏准入证据，反向也不能。核心/扩展完整协议、前瞻登记、留出种子及原失败保留规则继续适用。下一步必须经过新来源冻结、构建和实际开发验证，才可评价该资源修订的效果。
