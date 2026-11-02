# person1真实录制：DEVELOPMENT接线验证执行卡

状态：未来执行准备；没有读取真实bag/events，没有执行native。必须等core owner全部结束并完成原清理，由root在单重任务窗口执行。

目的仅是验证已选development person1的真实timing_v2导出schema与新lineage方法接线。它不是FORMAL120/160、事前协议或正式实验结果，不生成伪登记，也不替代现有正式评价路线。

当前lineage修订：

```text
method canonical 98c8ce9253fd1b46ef2bc5ec23f290918f4c1aa0d385d85939d050fe1fbb99dd
control_tick_lineage.py 5ef5d82999165ad2932c239f142dfa6b565cd4e43a2493c2f43c8c40be723247
test_control_tick_lineage.py d317356eeb23a23f0e05c9ed5346d4e0f950e09b3e7bb5aaf5f76d20f8ef2488
```

先由实际development plan/slot/terminal读取person1 trial路径、真实源根和原状态，保存外部执行receipt，明确`purpose=DEVELOPMENT_REAL_SCHEMA_AND_RECORDED_LINEAGE_ADAPTER_CHECK`。源根应是该试验实际使用的冻结54，不得为满足hash改挂其它源根。读取小run_config与原runtime_parameters证据确认`control_reference=ground_footprint`、controller `state_topic=/tracking/navigation_state`；此接线由实际run_stage1_trial.py953–962产生。未确认不能声称已验证控制器实际接收导航状态。

使用现有public CLI，毋须任何FORMAL计划/protocol/sidecar：

```bash
bash "$tracking_source_root/scripts/ros_python.sh" "$tracking_actual_timing_v2" export \
  --source-root "$tracking_source_root" \
  --trial "$tracking_actual_dev_person1_trial" \
  --output "$tracking_fresh_external_dev_export" \
  --protected-root "$tracking_actual_dev_plan_output"
```

变量均来自实际文件/路径；`tracking_actual_timing_v2`是已审`timing_v2/offline_pipeline_timing.py`实际Linux路径，SHA必须为`c6367a2dd7e7a733958a9c15bf6ee3bff6e2b1fa93205c303148f5523d39a4e2`，同级author test SHA须为`be4390929c5caac80a50cdc6c53c5f10a2e0476cd594414eb45e0378b3387617`。public export函数`export_native`和CLI均存在；它只要求实际源/试验、一个以上真实existing protected root，以及全新独立输出。

此DEV接线检验可不传job-log；lineage完全不使用job日志内容。原exporter仍按原样保存source/receipt/bag-metadata pins、原topic类型及完整计数，JSON-topic payload原样载入，没有`stamp_s`重命名。其context为`NATIVE_PIPELINE_TIMING_EXPORT_CONTEXT_NOT_ACCEPTANCE`，`formal_seed_use_authorized=false`。不修改context以伪装正式来源。

这是实际重任务：export读取整包至EOF。压缩包使用既有`evaluate_stage1_flight.open_bag_reader`，解压只写临时目录，退出后清理；不在原bag旁创建db3。届时由root选择已有合适TMPDIR/ROS_LOG_DIR与空间，不与core/SITL/其它提取同时运行。保留真实stdout/stderr、退出码、started/context或failed及部分输出，不覆盖失败后重新冒充同次成功。

导出成功后，计算实际`context.json`字节SHA，再运行标准库lineage分析（仍在可读取Linux原路径的环境）：

```bash
"$tracking_physical_python" -B "$tracking_actual_lineage" analyze \
  --events "$tracking_fresh_external_dev_export/events.jsonl" \
  --context "$tracking_fresh_external_dev_export/context.json" \
  --context-sha256 "$tracking_actual_dev_context_file_sha" \
  --output "$tracking_fresh_external_dev_lineage_report"
```

`tracking_actual_lineage`为以上已审修订的真实路径；output是外部新JSON，不能放入源根、原trial、protected plan/output或覆盖input。不要将事件拷贝后手改字段，也不要为提高覆盖率改匹配规则。

检验实际`/tracking/detection_diagnostics`保留`clock_epoch`、`acquisition_ns`、`stamp_s`；原消息`TargetState.prediction_age_s`/covariance及`TrackingStatus.time_since_measurement_s`是float32。分析核source/header时间实际转换的唯一整数ns逆，以及控制器真实float32公式；无法唯一确定的样本保持UNKNOWN。

输出仍只是记录约束解：逐原command保留分母，列known/unknown和具体原因；端点是controller tick开始，不是发布完成/订阅回调因果/PX4执行或wall E2E。真实数据首次运行即使known为0也须如实报告schema、缺流或量化等原因，不强制得到唯一结果。

最终外部DEV执行receipt绑定actual dev plan/slot、run_config/runtime参数小证据、exporter/method pins、原context/events、lineage report与真实退出状态，并明确`formal_result=false`、`formal_registration_created=false`。不把DEV attachment接入正式报告当正式结果。现有timing_v2工具、正式协议、冻结54算法和正式分母全部保持。
