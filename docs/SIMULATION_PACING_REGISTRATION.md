# 仿真资源节奏与 PX4 adapter 发布频率登记

当前主协议候选采用 v2，历史冻结及其原始结果保持独立。旧协议不含 `simulation_pacing_registration` 时仍使用 RTF `0.25`、飞行墙钟预算 `600 s`、adapter 默认 `20 Hz` 源时间发布。v1 的完整字典及隐含 `20 Hz` 语义不变。

当前机器的检测处理耗时可能使测量供给低于仿真源时间中的目标频率。新增固定修订允许将仿真请求节奏降至 RTF `0.125`，为同一段物理运动提供更多 CPU 墙钟时间；飞行预算对应增加至 `1000 s`。这是仿真资源配置，不代表已改善闭环结果，也不证明实机实时性能。

三个版本必须分别登记，不能互用准入证据：

| 版本 | 请求 RTF | 飞行墙钟预算 | adapter 源时间发布 |
|---|---:|---:|---:|
| 无登记的历史协议 | 0.25 | 600 s | 默认 20 Hz |
| `simulation_rtf0125_wall1000_v1` | 0.125 | 1000 s | 默认 20 Hz |
| `simulation_rtf0125_wall1000_adapter50_v2` | 0.125 | 1000 s | 显式 50 Hz |

v2 的完整声明如下：

```json
{
  "real_time_factor": 0.125,
  "flight_wall_timeout_s": 1000.0,
  "simulation_pacing_registration": {
    "revision": "simulation_rtf0125_wall1000_adapter50_v2",
    "real_time_factor": 0.125,
    "flight_wall_timeout_s": 1000.0,
    "follow_duration_s": 75.0,
    "max_inference_rate_hz": 10.0,
    "physical_identity_sample_period_s": 0.1,
    "scope": "simulation_cpu_wall_resource_and_adapter_heartbeat_only",
    "px4_adapter_publish_rate_hz": 50.0,
    "safety_source_time_gates": "unchanged"
  }
}
```

v1 保留原 scope `simulation_cpu_wall_resource_only`，不包含 `px4_adapter_publish_rate_hz`。缺字段、额外字段、其他修订、任意数值、布尔代替数字、NaN/Inf，或顶层配对值与登记不一致，均拒绝。v1/v2 的开发与正式计划都固定 `1000 s`，禁止命令行覆盖为其他预算。旧协议保留原有开发探针预算覆盖能力。

核心和扩展计划的默认飞行预算读取已验证协议；登记复制到每条 trial 规格。v2 同时显式写入 trial 的 `px4_adapter_publish_rate_hz`，仅发送一次 `--px4-adapter-publish-rate-hz 50.0`，保存到 `run_config.json`，并覆盖实际 YAML 中 `uav_tracking_px4_adapter.publish_rate_hz`。两处实际归档或 argv 缺失、重复、值漂移均拒绝。v1/旧协议不新增 trial 字段或 argv；旧实际归档省略该参数时仅按原默认 20 Hz 解释，任何显式 50 Hz 证据均拒绝。

controller 与 supervisor 保持原 `20 Hz` 源时间循环，实际 YAML 显式保存其默认值。v2 同时要求 YAML 显式保存原心跳预发送门 `1.2 s`、native 起飞预算 `40 s` 源时间和 `180 s` 墙钟；历史归档允许省略原默认字段，但任何显式漂移均拒绝。supervisor 的心跳最大间隔仍为 `0.4 s` 墙钟；均未放宽。50 Hz 源时间在请求 RTF 0.125 时名义对应 6.25 Hz 墙钟发布，但实际间隔必须测量，不能把请求 RTF 当作已达到的时钟换算。

命令、`run_config.json`、supervisor YAML 与实际世界文件中的 RTF 仍需一致。停飞后处理与评价预算各保留 `1800 s`，v1/v2 外层 trial 总预算为 `2800 s`。四安全专项同时校验协议、实际 argv、配置与 adapter/原循环频率；历史 frozen runner 仅能证明自己的旧默认频率，新 v2 必须具有相应共享验证器。

75 秒跟随任务、每仿真秒的运动速度、10 Hz 推理上限、固定 10 Hz 身份评价网格、观测与预测源时间门、马氏门和丢失重选保护保持原值。独立原生起飞和源时钟检查仍按原规则执行；降低 RTF 不能跳过这些检查。

开发关口对登记绑定完整 `simulation_pacing_sha256`，核心、扩展、云台重评价及 runner 正式准入均比较完整有效节奏。即使 RTF/飞行预算相同，v1 与 v2 也不能互相准入；旧 RTF 0.25 与两版登记也均不能互用。核心/扩展完整协议、前瞻登记、留出种子及原失败保留规则继续适用。必须经过新来源冻结、构建和实际开发验证，才可评价发布频率修订的效果。
