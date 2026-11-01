# Humble45 probe02 已完成准备证据快照

本快照登记 v2 单场工具测试、不可变计划、PENDING/FINAL 契约和已结束的规划观察器证据。它不登记飞行结果。root 委派本次快照时，probe02 实际飞行仍在进行；这里未复制当前 run driver、slot started 或实时文件，也未提前记为 PASS。

原生测试观察记录为33项、0跳过、退出码0。该原记录明确说明：测试 stdout/stderr 当时由执行工具直接观察，未另行重定向为日志；本目录保留的是观察收据，不补造测试输出。

v2 修正旧单场适配器调用 legacy640/.25/600 校验的问题，改为核对实际冻结候选协议的路径/SHA、完整协议相等及原 class policy。原 probe01 的零飞行规划失败及其 owner 二次错误另保留在 Humble45 构建验证快照；原失败、旧工具和冻结源未修改。

本次原规划终态为 returncode=0、flights_started=0、前后 entry 相等、final_errors=[]、residual_processes=[]；其 owner 为 COMPLETE、archive 为 VERIFIED_COPY、archive process returncode=0。FINAL 契约相对 PENDING 仅修改 status，独审收据单独保留。这些只表示单场计划及契约准备完成，不代表飞行、核心12或正式实验通过。

[manifest.json](manifest.json) 列出原始来源、字节数、SHA及范围；[SHA256SUMS](SHA256SUMS) 校验全部其他文件。16份原件均按字节复制，所有原POSIX路径保持不变。external_tools 供审阅来源；未打包其全部外部依赖，本目录不是可独立执行的部署环境。
