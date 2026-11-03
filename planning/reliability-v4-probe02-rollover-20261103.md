# Probe02 原监督器闭合与同计划续接

2026-11-03 13:44（北京时间）实际检查点。整个项目仍在开发验证，正式实验为 **0/280**。核心开发12/12和独立安全03四场PASS保留，新扩展16尚未完成。

当前打开[owner05实时页](../results/monitor_humble54_probe02_owner05/index.html)。第三场`person_extension_dropout_seed004`已真实START；前两场深度噪声和深度空洞均原始PASS，另13场未尝试。不要重启当前owner或原04。

## 已实际闭合的 owner04

- 第二场原始终态为`PASS / COMPLETED / flight_exit_code=0 / infrastructure_stop=false`，结束于05:35:10.060983 UTC。完整任务距离/高度RMSE为0.743408/0.162414米，末段两项稳定检查均通过；这些是一个开发种子的结果。
- 13:23的受控信号只发送给原collector154647。原child164983完整执行到真实退出0，owner等待观察结束于05:35:14.167857 UTC。
- 原collector与Windows外层保持`STOPPED_FAULT`；monitor/WSL真实句柄退出均2，`closure_verified=true`、`errors=[]`。临时防休眠于05:35:15.327500 UTC释放。原collector的`collected`仍只有第一场，第二场没有补造`CHILD_EXIT`或`COMPLETE_SLOT`事件。
- 原Windows终态SHA256为`5dcdb2c3d5dbe09985173c2d463d23b0acd54fdd17f8f5919fef0ddcad124e0c`。原始记录位于`results/diagnostics/humble54_probe02_windows_owner04/`及原生`/root/uav_tracking_collection54_probe02_owner04/`。

## 已实际完成的续接审核

原生空闲查询于05:36:38 UTC退出0、`matching_processes=[]`。随后原始冻结runner和未改的collector05共同检查实际两场前缀，14个后续槽均未尝试。另一固定slot校验实现核对两场的原START/terminal、204项所选模型capture、录包、四项评价、快门及长时安全；无新未知值。

原STOPPED_FAULT与第二槽独立补审以外置链合同连接，未改任何原件。实际root review为`results/diagnostics/humble54_probe02_rollover04_to05_review01/root_review.json`，SHA256 `28afb08764dc3ace10a1156efb0cb253a829de65e05671f35ad93c0ac8130535`。实际profile仅绑定这条原闭合链，SHA256 `5ac96b104ac1e7ad24500657f38b329c968f9440e61f23e79d7bc27fc1df0bd0`。

注册时仅改变已审模板中的状态及实际profile/chain/gate常量，已逐字节核实没有其他差异。原生注册入口check-only于05:40:17 UTC通过，返回精确两场closed、十四场pending；它未启动实验。准备态35项slot/chain测试和10项gate/outer合同测试只证明各自源码行为，不计作飞行。

| 运行角色 | 固定SHA256 |
| --- | --- |
| 未改collector05 | `f6a01ac6d106ed89914745341b6faba6f1fe6dab92df6a651ae86e90adeb9ce1` |
| slot库 | `945717313097725eba537f9078297f3e91e32bfdde89e810ed01ae7a2a3d546f` |
| owner-chain库 | `9cbbfbbfccccac9096a5cc122a21d8578e0fcbb3148357602dcdb834b143d97a` |
| 实际registered gate | `cc22295766da78ff345f502e2f369af6527e359639a32b3d4d2f820ffc0989e3` |
| 实际Windows outer05 | `32479281e080e900f6eb7d5a98f2fd94865219672e59d35732ec387de53013fc` |

## 当前真实执行

外层session23853于05:40:42 UTC启动。Windows monitor29440、creation FILETIME134381580422253602；owned WSL47940、FILETIME134381580424256581。Linux gate和collector为同一进程176129，boot ID`f79204a4-99cd-42cf-b886-aa905b1cac6a`，start_ticks9429181；第三槽child176148，start_ticks9430259。临时防休眠请求已接受。

Windows与Linux对旧前缀的完整稳定链结果已实际比较一致。启动/admission五份原件位于[actual_start01](../tools/experiment_orchestration/humble54_pending_collector05_registered/actual_start01/manifest.json)；旧闭合链62份小原件、1,654,654字节已按原SHA归档于[prior_evidence](../tools/experiment_orchestration/humble54_pending_collector05_registered/actual_registration01/prior_evidence/manifest.json)。未读取bag或模型正文来制作此归档。

当前尚无owner05终态。任何新来源、基础设施、安全或未知证据仍会停止；`HISTORY={}`，没有给未来dropout预填例外。已知压力算法FAIL可保留，但不能当作工程PASS或掩盖新缺证。此监督器不能自动发聊天完成通知。

## 后续顺序与资源

1. 收集同计划剩余14场的真实终态；出现新未知先检查实际输入附件，不复制旧probe01豁免、不重飞已尝试槽。
2. 全16闭合后，按实际owner链核验完整覆盖，再执行followon05的全28容量测量、物理清单、两条指定开发录包导出和R0定标。
3. 原profile01暂存工具绑定旧probe01，不可使用；profile02生产暂存入口仍需以真实完整链和预算登记启用。之后执行最终根冷构建、完整回归、导航28与传感器4附件、开发及正式准入。
4. 最后执行正式120+160、20条录制四估计器配对、检测/身份/时序附件及新版文档视频交付。失败、未知和删失保留。

D盘约102GiB可用，尚不是正式预算通过。历史稳定文本18.297GiB只是透明压缩候选，未回收；两个固定样本的测量准备在`tools/diagnostics/text_storage_sample_preparation02/PLAN.md`，留到原生空闲窗口串行执行，不与当前仿真竞争。

GitHub通过命令级`http.sslBackend=schannel`、`http.curloptResolve=github.com:443:140.82.114.3`、`http.version=HTTP/1.1`恢复连接，保留HTTPS证书校验且未改全局配置。远端已实际核实至`b1f1197`；上述新增注册和启动记录仍待其后的提交推送。
