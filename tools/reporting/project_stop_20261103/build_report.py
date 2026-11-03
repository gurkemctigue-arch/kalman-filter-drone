"""Build a stop-time project report from existing small artifacts only.

This script does not run ROS, simulators, inference, replay, or evaluators.
The document is a status report, not a final acceptance certificate.
"""
from __future__ import annotations

import hashlib
import html
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'docs/project-overview-20261103'
DEV = ROOT / 'results/frozen_fullplan_v4_humble54'
SOURCES: dict[str, dict] = {}


def source(relative: str, title: str | None = None):
    path = ROOT / relative
    raw = path.read_bytes()
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError(f'Report input exceeds small-artifact limit: {relative}')
    SOURCES[relative] = {
        'path': relative, 'title': title or path.name, 'bytes': len(raw),
        'sha256': hashlib.sha256(raw).hexdigest(),
    }
    return json.loads(raw) if path.suffix == '.json' else raw.decode('utf-8-sig')


GROUPS = {
    'stage1_velocity': '阶段一·速度控制', 'stage1_position': '阶段一·位置控制',
    'stage2_crossing': '阶段二·交叉', 'stage3_midpoint': '阶段三·云台中位',
    'stage3_active': '阶段三·主动云台', 'stage3_multi_active': '阶段三·多目标主动',
}
CONDITIONS = {
    'depth_noise': '深度噪声', 'depth_holes': '深度空洞', 'dropout': '检测丢帧',
    'latency': '通信延迟', 'combined': '组合故障',
    'speed_changes_velocity': '加减速·速度控制',
    'speed_changes_position': '加减速·位置控制', 'far_distance': '远距离',
}


def load_slots(matrix: str):
    result = []
    for path in sorted((DEV / matrix / 'slots').glob('*.json')):
        raw = path.read_bytes()
        row = json.loads(raw)
        if 'status' not in row:
            continue
        source(path.relative_to(ROOT).as_posix(), '原始开发槽终态')
        evidence = row.get('engineering_evidence', {})
        result.append({
            'id': row['id'], 'class': row['id'].split('_')[0],
            'status': row['status'], 'execution_status': row['execution_status'],
            'flight_exit_code': row['flight_exit_code'],
            'infrastructure_stop': row['infrastructure_stop'],
            'measured': evidence.get('measured', {}),
            'checks': evidence.get('checks', {}),
            'slot_source': path.relative_to(ROOT).as_posix(),
            'trial_dir': f'results/frozen_fullplan_v4_humble54/{row["name"]}',
        })
    return result


def paragraph(text):
    return {'type': 'paragraph', 'text': text}


def table(headers, rows, widths=None):
    return {'type': 'table', 'headers': headers,
            'rows': [[str(v) for v in row] for row in rows], 'widths': widths}


def figure(name, caption, width=980):
    return {'type': 'figure', 'path': 'figures/' + name, 'caption': caption, 'width': width}


def build_figures(core, extension, identity, gimbal):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties, fontManager
    font_path = Path('C:/Windows/Fonts/msyh.ttc')
    if font_path.exists():
        fontManager.addfont(str(font_path))
        plt.rcParams['font.family'] = FontProperties(fname=str(font_path)).get_name()
    plt.rcParams.update({'axes.unicode_minus': False, 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'savefig.facecolor': 'white'})
    (OUT / 'figures').mkdir(parents=True, exist_ok=True)
    colors = ['#26766c', '#c65b4b', '#c49938']
    fig, ax = plt.subplots(figsize=(10.6, 3.5), layout='constrained')
    names = ['核心开发（12槽）', '安全专项（4槽）', '扩展开发（16槽）']
    for i, counts in enumerate([(12, 0, 0), (4, 0, 0), (11, 4, 1)]):
        start = 0
        for count, color in zip(counts, colors):
            if count:
                ax.barh(i, count, left=start, height=.52, color=color)
                ax.text(start + count / 2, i, str(count), ha='center', va='center', color='white', weight='bold')
            start += count
    ax.set_yticks(range(3), names); ax.invert_yaxis(); ax.set_xlim(0, 17)
    ax.set_xlabel('开发槽数｜绿色 PASS，红色 FAIL，黄色证据不完整；安全4单列')
    ax.set_title('最新 Humble54 开发结果｜正式实验 0/280', loc='left', weight='bold')
    fig.savefig(OUT / 'figures/development_status.png', dpi=165); plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(10.6, 4.25), layout='constrained', sharex=True)
    xs = list(range(6)); labels = ['速度', '位置', '交叉', '中位', '主动', '多目标主动']
    for cls, color, offset, label in [('person', '#26766c', -.16, '行人'), ('car', '#426c9e', .16, '汽车')]:
        rows = {r['id'].replace(cls + '_', '').replace('_seed004', ''): r for r in core if r['class'] == cls}
        for ax, key in zip(axes, ['base_link_distance_rmse_m', 'base_link_height_rmse_m']):
            values = [rows[g]['measured'][key] for g in GROUPS]
            ax.bar([x + offset for x in xs], values, width=.3, label=label, color=color)
            ax.grid(axis='y', alpha=.15); ax.set_axisbelow(True)
    axes[0].set_ylabel('距离 RMSE / m'); axes[1].set_ylabel('高度 RMSE / m')
    axes[0].set_ylim(0, 1.08); axes[1].set_ylim(0, .21)
    axes[0].axhline(1.0, color='#c65b4b', linestyle='--', linewidth=1)
    axes[0].legend(frameon=False, ncol=2, loc='upper left')
    axes[1].set_xticks(xs, labels)
    axes[0].set_title('核心12槽原始物理误差｜每场仅开发 seed004，非重复统计', loc='left', weight='bold')
    fig.savefig(OUT / 'figures/core_errors.png', dpi=165); plt.close(fig)

    fig, ax = plt.subplots(figsize=(10.6, 3.5), layout='constrained')
    rows = identity['multi_target_slots']
    labels = {'car_stage2_crossing_seed004': '汽车·交叉', 'car_stage3_multi_active_seed004': '汽车·多目标主动',
              'person_stage2_crossing_seed004': '行人·交叉', 'person_stage3_multi_active_seed004': '行人·多目标主动'}
    for i, row in enumerate(rows):
        t = row['time_grid']; n = t['scheduled_samples']; known = t['correct'] / n
        ax.barh(i, known * 100, color=colors[0], height=.55)
        ax.barh(i, t['unknown'] / n * 100, left=known * 100, color=colors[2], height=.55)
        ax.text(2, i, f'{t["correct"]}/{n} 正确（{known:.2%}）', color='white', va='center')
        ax.text(known * 100 + 1, i, str(t['unknown']) + '未知', va='center', fontsize=9)
    ax.set_yticks(range(len(rows)), [labels[r['id']] for r in rows]); ax.invert_yaxis()
    ax.set_xlim(0, 100); ax.set_xlabel('完整请求任务时间格百分比；0 已知错误不能排除未知期间跟错')
    ax.set_title('身份覆盖｜3014格中2551正确、463未知', loc='left', weight='bold')
    fig.savefig(OUT / 'figures/identity_coverage.png', dpi=165); plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(10.6, 3.7), layout='constrained')
    for mode, color, offset, label in [('midpoint', '#8da6bf', -.17, '中位'), ('active', '#26766c', .17, '主动')]:
        axes[0].bar([i + offset for i in range(2)],
                    [gimbal[(c, mode)]['navigation_center']['rmse'] for c in ['person','car']],
                    width=.32, color=color, label=label)
        axes[1].bar([i + offset for i in range(2)],
                    [gimbal[(c, mode)]['metrics']['true_image_horizon_error_rad']['rmse'] for c in ['person','car']],
                    width=.32, color=color, label=label)
    axes[0].set_title('新鲜选中检测框中心 RMSE'); axes[0].set_ylabel('归一化误差')
    axes[1].set_title('独立物理画面水平 RMSE'); axes[1].set_ylabel('rad')
    for ax in axes:
        ax.set_xticks([0,1], ['行人','汽车']); ax.grid(axis='y', alpha=.15); ax.set_axisbelow(True)
    axes[0].legend(frameon=False)
    fig.suptitle('云台同种子描述性比较｜不代表可靠性或因果优势', weight='bold')
    fig.savefig(OUT / 'figures/gimbal_comparison.png', dpi=165); plt.close(fig)


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    git = subprocess.run(['git','rev-parse','HEAD'], cwd=ROOT, capture_output=True, check=True, text=True).stdout.strip()
    core = load_slots('reliability_v4_humble54_core12_probe01_matrix')
    extension = load_slots('reliability_v4_humble54_extension16_probe02_matrix')
    assert len(core) == 12 and all(r['status'] == 'PASS' for r in core)
    assert len(extension) == 16
    assert {s: sum(r['status'] == s for r in extension) for s in ['PASS','FAIL','INCOMPLETE_EVIDENCE']} == {'PASS':11,'FAIL':4,'INCOMPLETE_EVIDENCE':1}
    assert all(not r['infrastructure_stop'] and r['flight_exit_code'] == 0 for r in core + extension)
    for row in core + extension:
        nav_path = row['trial_dir'] + '/navigation_reference_evaluation.json'
        nav = source(nav_path, '原槽绑定的导航物理/视觉指标')
        original_slot = json.loads((ROOT / row['slot_source']).read_bytes())
        artifact_matches = [(k, v) for k, v in original_slot['artifact_hashes'].items()
                            if k.split('/')[-1] == 'navigation_reference_evaluation.json']
        assert len(artifact_matches) == 1 and artifact_matches[0][1] == SOURCES[nav_path]['sha256']
        row['navigation_metrics'] = nav['whole_interval']['metrics']
        row['visual_metrics'] = nav['visual_control_metrics']
        row['final_stability'] = nav['whole_interval']['transients']['base_link']
    plan = source('results/frozen_fullplan_v4_humble54/reliability_v4_humble54_core12_probe01_matrix/plan.json', '核心开发原计划与登记阈值')
    source('results/frozen_fullplan_v4_humble54/reliability_v4_humble54_extension16_probe02_matrix/plan.json', '扩展开发原计划')
    identity = source('results/diagnostics/humble54_identity_coverage_readonly01/identity_coverage.json', '完整任务身份覆盖')
    source('results/diagnostics/humble54_identity_coverage_readonly01/car_detailed_review01.json', '汽车身份未知原因细分')
    budget = source('results/frozen_fullplan_v4_humble54/full280_storage_budget_probe02_after07_01/budget.json', '完整280槽存储预算原件')
    budget_review = source('results/diagnostics/humble54_after28_budget_review01/review01.json', '容量准入拒绝分析')
    build_receipt = source('results/frozen_fullplan_v4_humble54/freeze_validation/native_build_supplement02.json', 'Humble54真实冷构建与完整测试')
    r0 = source('results/frozen_fullplan_v4_humble54/reliability_v4_humble54_development_calibration_probe02_after07_01/R0_candidate.json', '开发集R0候选，未登记')
    source('results/frozen_fullplan_v4_humble54/full28_storage_measurement_probe02_after07_01/summary.json', '完整28槽文件容量实测')
    timing = {c: source(f'results/diagnostics/humble54_pipeline_timing_full_{c}01/review01.json', f'{c}完整软件回放诊断') for c in ['person','car']}
    compression = source('results/diagnostics/humble54_lossless22_bench_execution01/review01.json', '无损压缩实测终态')
    source('tools/experiment_orchestration/humble54_core12_closed01/review_receipt.json', '核心12槽闭合审计')
    source('tools/experiment_orchestration/humble54_safety4_closed03/originals/audit/development_validation_summary.json', '安全4槽原汇总')
    source('docs/DELIVERY_STATUS.md', '历史v3正式归档口径')
    source('docs/CONFIDENCE_TIER_MAINTENANCE.md', '汽车弱检测维护实现与边界')
    source('docs/V4_RESULT_SUMMARY.md', '新版结果与配对统计定义')
    source('results/diagnostics/humble54_probe02_person_dropout_input_extract03/visual_review_native03.json', '行人丢帧合同短窗已有独立阅图')
    source('tools/diagnostics/humble54_probe02_car_dropout_review01/visual_review_native01.json', '汽车丢帧合同短窗已有独立阅图')
    source('tools/diagnostics/humble54_probe02_combined_raw_review01/actual_review.json', '行人组合故障事后诊断窗已有阅图，非合同短窗')
    source('tools/diagnostics/humble54_pipeline_timing_bench01/README.md', '软件候选延迟端点与观察开销')
    source('planning/reliability-v4-estimator-replay-preregistration.json', '四法正式比较尚未冻结或执行')
    source('docs/DETECTION_EVALUATION_PROVENANCE.md', '检测精度独立可见标签前提')
    source('tools/staging/final55_capacity_refresh_candidate01/stage_after_refresh.py', '默认禁用的容量后暂存候选')
    source('results/diagnostics/humble54_pipeline_timing_full_person01/foreground_execution01.json', '行人回放真实退出')
    source('results/diagnostics/humble54_pipeline_timing_full_car01/foreground_execution01.json', '汽车回放真实退出')
    source('results/diagnostics/humble54_lossless22_bench_execution01/native_idle_after_execution01.json', '上一重任务结束后的原生空闲记录')
    gimbal = {}
    for c in ['person','car']:
        for mode in ['midpoint','active']:
            gimbal[(c,mode)] = source(f'results/frozen_fullplan_v4_humble54/reliability_v4_humble54_core12_probe01_{c}_stage3_{mode}_seed004/gimbal_evaluation.json', '原始云台评价')
            core_row = next(r for r in core if r['id'] == f'{c}_stage3_{mode}_seed004')
            gimbal[(c,mode)]['navigation_center'] = core_row['visual_metrics']['detected_center_normalized_error']
    for r in extension:
        if r['status'] != 'PASS':
            if r['id'].endswith('speed_changes_position_seed004'):
                continue
            flight = source(r['trial_dir'] + '/flight_evaluation.json', '扩展原始遮挡行为评价')
            r['occlusion_evidence'] = [{k: e.get(k) for k in ['kind','first_predicted_s','first_lost_s','first_hover_s','detector_interruption_observed','prediction_observed','no_loss_during_short_occlusion']} for e in flight['occlusions']]
    build_figures(core, extension, identity, gimbal)
    free_gib = shutil.disk_usage(ROOT).free / 1024**3
    required = budget_review['GiB']['required_bytes']
    shortfall = required - free_gib
    stop = {
        'kind': 'USER_REQUESTED_EXPERIMENT_STOP_REPORT', 'created_utc': now,
        'user_instruction': '没有空间了，实验停止吧，给我写一个整体报告',
        'experiment_goal_status': 'paused', 'automatic_resume_authorized': False,
        'new_experiments_started_for_report': False,
        'linux_read_only_process_query': {
            'utc': '2026-11-03T14:35:12.508842+00:00', 'matching_processes': [],
            'query_source': 'tools/reporting/project_stop_20261103/query_native_stop.py',
            'scope': 'Related argv patterns only; WSL idle tail processes are not experiments.',
        },
        'source_code_commit_before_report': git,
        'formal_completed': 0, 'formal_planned': 280,
        'disk_snapshot': {'free_GiB': free_gib, 'original_required_GiB': required,
                          'arithmetic_shortfall_GiB': shortfall,
                          'new_capacity_admission_executed': False},
        'original_experiment_data_modified': False,
    }
    write_json(OUT / 'stop_state.json', stop)
    sections = []
    def section(title, blocks):
        sections.append({'title':title, 'blocks':blocks})
    section('一、整体结论与停止范围', [
        paragraph('本项目已形成可运行的三阶段仿真系统，完成了行人/汽车检测、RGB-D三维定位、目标身份管理、卡尔曼状态估计、PX4闭环跟随和三轴云台协同。最新 Ubuntu 22.04 / ROS 2 Humble 开发核心12槽全部通过，独立歧义安全专项4槽全部通过；扩展16槽中11通过、4失败、1证据不完整。全项目最终验收尚未完成。'),
        paragraph('按用户最新要求停止实验，持续实验目标已设为 paused。停止时没有相关仿真、飞控、回放或实验运行器进程；不会因之后磁盘空间变化而自动续跑。本报告只整理已有资料和生成文档，不启动新的仿真、录包、推理、重放或实验评价。'),
        table(['证据层级','已完成','尚不能代表'], [
            ['三阶段功能实现','三阶段功能和仿真闭环均已存在','全部场景可靠或实机可直接飞行'],
            ['Humble54开发验证','核心12/12；安全4/4；扩展16/16终态','正式多种子验收或总体成功率'],
            ['v4正式实验','0/280；120核心＋160扩展均未执行','280次已失败、已完成或已得到统计结论'],
            ['历史v3归档','主研究166次＋独立扩展16次已登记','最新Humble版本的验证结果'],
        ], [2000,3900,3800]),
        figure('development_status.png','图1　最新开发结果。核心＋扩展为28槽（23 PASS、4 FAIL、1 INCOMPLETE）；安全4槽另列。'),
        paragraph('最准确的项目定位是：三阶段仿真原型已实现，最新核心开发验证通过；压力工况与证据完整性仍有缺口，正式重复研究和最终统计交付未完成。本报告是停止时点的整体报告，不是全部验收通过证明。'),
    ])
    section('二、研究目标、范围与三阶段实现', [
        paragraph('研究对象为携带RGB-D云台相机的仿真无人机，目标类别为行人和汽车。核心任务是在可见性、身份和数据时效满足条件时估计选定目标的三维位置/速度，并保持设定跟随距离和高度；遇到歧义或持续失锁时进入保护状态。'),
        table(['阶段','已实现内容','停止时验证边界'],[
            ['阶段一','YOLO11、深度ROI质量检查、坐标变换、6维KF、速度/位置控制、短遮挡预测、长丢失悬停与重选','两类速度/位置核心场景通过；多种子可靠性未验证'],
            ['阶段二','唯一实例自动锁定；多候选歧义；初始框选指定个体；三维关联、任务UUID与轨迹ID分离；禁止自动换目标','交叉核心两场和独立安全4场通过；仍有463个身份未知时间格'],
            ['阶段三','三轴物理云台、编码器反馈、图像采集时刻动态TF、视线跟踪、画面水平、机体慢偏航回正','中位、主动、多目标主动共6核心槽通过；未形成正式重复优势结论'],
        ],[1300,5150,3250]),
        paragraph('唯一实例模式要求只有一个符合类别且满足初始化条件的候选，多于一个时拒绝自动选择。指定个体模式由用户或脚本先选框，之后持续维护该任务身份；短时失去观测可以预测，超期丢失则悬停并等待显式重选。稳定的target_uuid只是任务标识，不能作为真实物理身份正确的证明。'),
        paragraph('第一版没有完整外观ReID，因而不承诺长时间离开画面后自动认回原个体。自动避障、开放环境搜索、真实机飞行以及更多类别均不在本次已验证范围。框选入口已经实现，但正式研究中的自动脚本选框与完整交互式用户体验是不同验收对象。'),
        paragraph('系统按可迁移的接口划分算法和环境依赖；这种结构有利于移植，但迁移到真实RGB-D相机、云台和飞控后仍须重新校准内外参、深度范围、时间同步、坐标约定、噪声模型、控制参数和失效保护。仿真通过不等于免验证的实机可用。'),
    ])
    section('三、技术架构、坐标与安全策略', [
        paragraph('运行管线：RGB-D图像 → YOLO11检测 → 二维/三维轨迹关联 → 目标选择 → 深度反投影 → 采集时刻相机/世界变换 → 三维状态估计 → 跟随控制 → PX4 Offboard。云台通过关节反馈提供动态相机姿态，独立的离线真值通道负责评价。'),
        table(['接口/模块','职责与实现边界'],[
            ['SensorAdapter','RGB、Depth、CameraInfo、同步时间戳与TF；拒绝无效深度和不完整几何证据'],
            ['VehicleStateAdapter / PX4Adapter','有效位置/姿态/速度、源时钟和reset保护；统一ENU/FLU与NED/FRD转换'],
            ['TargetManager','track_id与target_uuid分离；高置信度初始化、保守三维关联、歧义与LOST锁'],
            ['StateEstimator','状态[x,y,z,vx,vy,vz]；位置观测、协方差、新鲜度与马氏距离门控'],
            ['FollowController','世界坐标下距离/高度跟随；速度和位置设定值按参数择一发布'],
            ['GimbalAdapter','三轴命令、真实关节反馈和动态TF；云台视线与机体跟随分工'],
        ], [3000,6700]),
        paragraph('指定目标的表面三维测量与飞行导航参考不是同一物理量。目标可见面会随视角变化，直接把表面点当成固定目标中心容易引入跟随距离偏差。新版引入地面投影参考、汽车可见面几何和相机/机体位姿不确定性，并分开报告base_link、model_origin与表面锚点误差。'),
        paragraph('安全规则保持原值：最大观测年龄0.60 s、最大预测时长0.75 s、登记马氏门9.21；丢失后必须显式重选，不自动选最近目标或最高置信度目标。运行目标关联禁止读取Gazebo实体名称和真值身份；真值只用于离线检查。模型族尺寸先验属于事先固定的建模条件，应披露其仿真依赖，不能称为任意车辆都适用。'),
        paragraph('相机跟随图像视线，机体按世界坐标相对位置保持距离/高度，机体偏航再慢速回正，避免云台长期触限。云台和无人机没有同时把同一个图像中心误差直接当成独立飞行控制输入。'),
    ])
    section('四、验证环境与本轮主要修复', [
        paragraph('历史v3正式归档使用Ubuntu 24.04 / ROS 2 Jazzy。后续已建立独立的Ubuntu 22.04 / ROS 2 Humble WSL2环境，并在Humble54完成真实冷构建、导入隔离、生成CDR与完整Linux测试。原计划中的22.04/Humble已获得开发级实际证据，尚没有该环境下的280次正式研究。'),
        table(['项目','已有证据','限制'],[
            ['ROS 2与构建','Humble；4个ROS软件包冷构建与来源隔离检查通过','不能用Windows测试代替Linux运行检查'],
            ['完整Linux测试','2021项：2016通过、5项平台条件跳过','跳过不计为通过；仅指该冻结版本'],
            ['仿真与飞控','Gazebo Harmonic、PX4 v1.17系列、uXRCE-DDS、匹配px4_msgs；独立运行清单','含本项目兼容补丁和独立二进制，不能简化为无补丁原版'],
            ['资源策略','llvmpipe CPU渲染；请求仿真倍率0.125；75 s任务窗口','没有证据证明1倍实时运行或满足实机延迟预算'],
            ['汽车检测','实际核心计划为仿真微调YOLO11m，512输入、4线程','基础YAML默认值不代表原场真实运行配置'],
        ],[1800,4550,3350]),
        table(['修复方向','具体工作及得到的证据'],[
            ['汽车检测与关联','诊断推理尾延迟；调整输入/线程；高阈值0.45初始化、低阈值0.25仅维护已有三维轨迹；不允许弱框出生或解除LOST'],
            ['物理跟随与稳定性','区分可见面/地面参考/机体控制点；位置设定值加入实际机位反馈；末段稳定按持续有效窗口判断'],
            ['PX4与时间链','原生起飞后再Offboard；磁坐标与动态库来源登记；源时间和独立墙钟停流保护；时钟桥和数据桥分离'],
            ['录包与生命周期','关键证据流QoS、完整关闭、压缩字节往返与原生读回；进程创建身份、终态、清理和监督器接续审计'],
            ['评价与缺失处理','物理距离/高度、固定10 Hz身份分母、缺证/删失单列；保留旧FAIL，不拼接不同冻结来源的成功槽'],
        ],[1900,7800]),
        paragraph('这些改动的效果由后面的开发结果限定。已有单元测试、构建和进程退出证明工程链条的相应部分有效，不能单独代替飞行行为、目标身份或论文统计结论。'),
    ])
    core_table=[]
    for c in ['person','car']:
        for group,label in GROUPS.items():
            r=next(r for r in core if r['id']==f'{c}_{group}_seed004'); m=r['measured']
            core_table.append(['行人' if c=='person' else '汽车',label.replace('阶段一·','').replace('阶段二·','').replace('阶段三·',''),
                               f'{m["base_link_distance_rmse_m"]:.4f}',f'{m["base_link_height_rmse_m"]:.4f}',f'{m["valid_state_coverage"]:.2%}','PASS'])
    section('五、最新核心12场开发结果', [
        paragraph('以下数据全部来自Humble54同源核心开发批次，开发seed004，每个任务持续75 s。12槽原始终态均为PASS，来源时钟、原生启动、对应行为检查以及末段距离/高度稳定检查已闭合。每行是一种场景的一次开发试验，不是10次重复的均值。'),
        table(['类别','场景','距离RMSE/m','高度RMSE/m','导航覆盖','原结果'],core_table,[800,2200,1700,1700,1500,1000]),
        figure('core_errors.png','图2　原始物理误差。两类使用不同期望距离：行人5 m、汽车9 m；不能按RMSE大小直接判定类别难易。'),
        paragraph('登记的主要工程要求为距离RMSE≤1.0 m、高度RMSE≤0.4 m、有效导航覆盖≥0.80、独立真值覆盖≥0.99，并要求末段持续稳定；指定个体组还要求完整任务身份覆盖≥0.80。工程PASS是多个检查的合取，不表示任务中从未丢失、没有未知区间或每个局部窗口都通过。'),
        paragraph('本批可支持“修复后的核心场景已在一个开发种子上跑通并通过登记门槛”。它不能支持汽车可靠性达到100%、不同运动/目标外观都适用、原v3失败已被消除，或正式总体成功率已提高。'),
    ])
    ext_rows=[]
    for condition,label in CONDITIONS.items():
        statuses=[]
        for c in ['person','car']:
            r=next(r for r in extension if r['id']==f'{c}_extension_{condition}_seed004')
            statuses.append('证据不完整' if r['status']=='INCOMPLETE_EVIDENCE' else r['status'])
            m = r['navigation_metrics']
            statuses.append(f'{m["base_link_distance_error_m"]["rmse"]:.4f} / {m["base_link_height_error_m"]["rmse"]:.4f}')
        ext_rows.append([label,*statuses])
    section('六、扩展工况与保留的失败', [
        paragraph('最新扩展probe02覆盖两类别×8条件，共16个开发槽，均有终态：11 PASS、4 FAIL、1 INCOMPLETE_EVIDENCE。本批原槽均完成飞行、flight_exit_code=0且未登记基础设施停止；进程正常结束不改变行为失败或证据不完整的判定。'),
        table(['扩展条件','行人结果','行人距/高RMSE·m','汽车结果','汽车距/高RMSE·m'],ext_rows,[2300,1250,2450,1250,2450]),
        paragraph('上表物理误差直接取各原槽绑定的导航报告，保留丢失/悬停尾段；不是尚未执行的final55完整28槽导航重评。行人组合故障约2.222 m、汽车丢帧约3.073 m和汽车组合故障约2.037 m的距离RMSE均超过1.0 m要求，这些失败的高误差没有从统计中删除。'),
        table(['未通过项','原始证据与应当怎样解释'],[
            ['行人·检测丢帧（证据不完整）','短遮挡的detector_interruption_observed为null；已有原图能支持画面遮挡，但未补齐原评价所需检测中断证据，不能改判PASS'],
            ['行人·组合故障（FAIL）','长遮挡prediction_observed=false；窗内未观察到预测阶段，未完整验证跟踪→预测→丢失悬停流程；其余保护及重选检查通过，原FAIL保留'],
            ['汽车·检测丢帧（FAIL）','短遮挡no_loss_during_short_occlusion=false，长遮挡prediction_observed=false；短期观测中断仍可能越过预测预算'],
            ['汽车·组合故障（FAIL）','长遮挡prediction_observed=false；原surface_flight失败保留，不能用录包读通或后续重选成功抵消'],
            ['行人·加减速位置控制（FAIL）','距离RMSE约0.6493 m达标，但final_distance_settled=false；高度及其他登记数值门通过，持续稳定问题仍存在'],
        ],[2800,6900]),
        paragraph('行人/汽车丢帧合同短窗已分别有原始图像提取和独立阅图记录；组合故障的合同短窗提取/阅图及完整四槽正式绑定尚未齐全。事后诊断窗、原图可见性和行为验收是不同证据，不能互相替代。现有失败首先提示测量连续性、预测期限与任务工况之间的关系，尚不能用单一根因解释全部失败。'),
        paragraph('扩展失败会保留在本报告和原台账中。没有通过减少工况、提高预测期限、放宽0.60/0.75 s安全限制、删除失败试验或重飞原槽来制造全通过结果。'),
    ])
    section('七、四个主要剩余问题的解决程度', [
        table(['问题','已经做到','仍然缺少'],[
            ['汽车跟随可靠性','汽车6个核心场景全部PASS；延迟、噪声/空洞、变速两控制模式、远距离扩展通过','丢帧与组合故障仍FAIL；未做正式多种子重复，不能给总体成功率'],
            ['距离/高度稳定性','核心12场末段稳定全部通过；汽车两变速控制扩展通过','行人加减速位置控制末段距离持续稳定验收未通过；低RMSE不足以说明这一项已解决'],
            ['主动云台整体效果','两类中位/主动/多目标主动核心均PASS；新鲜框中心与画面水平有实测改善','没有正式10对重复；居中改善尚不能推出身份、闭环可靠性或所有误差均改善'],
            ['身份与算法结论','固定完整任务分母、未知原因细分与证据保护已实现；4多目标槽已可核查','463个身份未知格、独立可见标签复核、正式四法配对比较和统计结论仍未完成'],
        ],[1800,3850,4050]),
        figure('gimbal_comparison.png','图3　云台中位/主动的原始同种子观察。检测中心只统计新鲜选中检测框，不能替代完整任务/身份指标。'),
        paragraph('行人中位/主动的归一化中心RMSE分别为0.118654/0.029227（有效717/719个样本）；汽车为0.169487/0.020818（713/707个样本）。中心指标统一取原槽绑定navigation_reference_evaluation的visual_control_metrics；gimbal_evaluation有自己的时窗/样本数，不能混用。独立物理画面水平RMSE取云台评价，分别为行人0.005764/0.003428 rad、汽车0.006573/0.004484 rad。'),
        paragraph('汽车中位/主动距离RMSE分别为0.733114/0.739092 m，后者略大；行人为0.750936/0.745811 m。两个任务均已通过工程门，但数据不支持“主动云台在所有闭环指标上更好”。这里没有可估计的重复间变异或显著性区间。'),
    ])
    id_rows=[]
    for r in identity['multi_target_slots']:
        t=r['time_grid']; id_rows.append([r['id'].replace('_seed004',''),t['correct'],t['wrong'],t['unknown'],t['scheduled_samples'],f'{t["known_coverage"]:.2%}'])
    section('八、身份覆盖、未知样本与评价边界', [
        paragraph('“未知样本”指评价系统无法用独立证据确定当时是否跟随原指定物理个体的时间格。例如某0.1 s格内只有预测状态，没有新鲜目标检测；或目标被遮挡、多个物体都可能解释当前框。UUID没变、预测轨迹平滑，都不足以把该格标为正确。未知不是已证实跟错，也不能按正确处理。'),
        table(['开发槽（均seed004）','正确','已知错','未知','总格','已知覆盖'],id_rows,[3900,1000,1000,1000,1000,1300]),
        figure('identity_coverage.png','图4　全部未知保留在分母；原离线几何评价尚有独立图像可见性复核边界。'),
        paragraph('四槽描述性合计为3014个时间格，2551正确、0已知错误、463未知；已知覆盖约84.64%，未知约15.36%。3014格不是3014次独立试验，不能据此计算实验级可靠性置信区间。其余24个核心/扩展槽没有指定身份摘要，不等于24次身份失败。'),
        paragraph('分母从首次显式REQUEST到最后记录的/clock，按固定10 Hz划分；REQUEST前起飞不在其中。之后的未确认、清除/重置、任务切换、长时失锁悬停和缺独立新证据时段均保留，不按FOLLOW筛掉，不前向填充身份标签。任务重选会开启新任务，不能称为原个体自动ReID成功。'),
        paragraph('汽车交叉114个未知格：尚未确认2、格内无证据13、已有证据仍未知99；汽车多目标主动139格：2、41、95，另任务边界1格。逐检测帧另有“无新鲜选中检测”73/70帧、“遮挡已知或无法排除”26/25帧；逐帧与时间格是两个分母，不能相加。'),
        paragraph('当前正确/错误标签来自原离线几何与遮挡保护评价，不能自动升级为完整独立可见图像真值。0已知错只说明已有可判定证据中未报告错误，不能证明未知时段没有切换，也不能推出全程ID Switch=0。IDF1/HOTA、重捕获率/时间必须注明标签协议、分母和缺失，不应从UUID稳定或单幅图像补算。'),
    ])
    section('九、卡尔曼滤波、检测与论文结论', [
        paragraph('计划中的主线比较为原始三维测量、EMA或α-β、固定参数KF、自适应观测噪声KF。新版已具备真实录包导出、同测量重放、源一致性检查、参数定标和配对统计工具；两类开发录包导出与R0候选也已完成。R0仍明确为CANDIDATE_NOT_REGISTERED / DEVELOPMENT_ONLY，尚未正式登记采用。'),
        table(['研究问题','当前可用材料','本报告允许的结论'],[
            ['四估计器误差比较','历史v3统计、开发导出/候选参数、重放工具','有比较基础；新版正式留出集结果尚不存在'],
            ['自适应观测噪声','表面检测/深度质量链；导航几何与位姿不确定性链','两套观测模型应分别解释；不能把geometry自适应等同置信度/深度质量模型'],
            ['闭环收益','最新飞行采用登记方案，各场景原误差可查看','同录包离线重放只能给条件估计误差比较，不能证明不同滤波器闭环因果收益'],
            ['检测Precision/Recall/mAP','已有检测来源/标签/评价工具及相关历史材料','尚无本轮最终独立可见标签完整精度结论，不能由检测可用率推算mAP'],
            ['速度、FPS与延迟','仿真FPS、墙钟推理时间、软件候选延迟各有定义','分别标明时间域和分母；不合并为实机实时性'],
        ],[2300,3700,3700]),
        paragraph('历史v3已有一次主研究归档和四基线材料，应按原失败、证据完整性与其实际环境引用。现有材料不支持“自适应KF在所有指标上更好”。论文应报告在哪些距离、噪声、运动和遮挡条件下误差降低或升高，以及输出缺失/失锁的代价。'),
        paragraph('若将来恢复正式研究，应先固定R0/α-β/EMA参数、模型权重、评价协议和源码，再使用留出种子1000–1009；相同轨迹/种子/控制参数下配对。统计单位是trial/seed，不是同一飞行内的帧。失败、未知、缺失与右删失必须保留，并与可评分算法错误分开报告。'),
        paragraph('本次停止后不再补做上述研究。报告可以作为系统设计、实现与开发验证章节材料，但不能作为280次正式研究已经完成的论文依据。'),
    ])
    time_rows=[]
    for cls in ['person','car']:
        o=timing[cls]['observed']; stats=o['candidate_subset_statistics_ns']
        time_rows.append(['行人' if cls=='person' else '汽车',o['opportunity_counts']['replay_input'],
                          f'{o["candidate_command_count"]}/{o["adapter_callback_count"]}',o['unknown_command_count'],
                          f'{o["rgb_with_candidate_count"]}/{o["received_rgb_count"]}',
                          f'{stats["median"]/1e9:.3f}',f'{stats["p95"]/1e9:.3f}',f'{stats["max"]/1e9:.3f}'])
    section('十、软件时序诊断与性能优化', [
        paragraph('为查清检测、估计、控制与适配器间的数据路径，已对两类已有输入进行独立完整软件回放。两次都回放50,117条输入，相关进程正常退出。软件时延起点是所用RGB/Depth中较晚的原始回调入口，终点是适配器TrackingCommand订阅回调入口；不含物理曝光与PX4执行器响应，且存在观察钩子开销。下表只统计形成全链候选关联的FOLLOW命令，非FOLLOW和无候选RGB全部保留。'),
        table(['类别','输入条数','FOLLOW候选/命令','非FOLLOW','有链RGB/全部','中位/s','p95/s','最大/s'],time_rows,[650,1200,1900,1050,1700,1000,1000,1000]),
        paragraph('行人的三条DDS边候选数为752/4511/1857，汽车为747/4508/1854。受控环境中的候选匹配说明相应发送/接收记录可连接；图查询是轮询式的，不能完全证明外部writer从未存在，因此不能把“candidate”升级为严格已证实链路。'),
        paragraph('物理端到端时延仍为NOT_OBSERVED。这里没有相机物理曝光至PX4实际执行的完整独立时钟/身份闭合证据；旧严格统计1857/1857 UNKNOWN保留。477/480条非FOLLOW命令不等于相同比例的算法失败，它们可能是保护状态命令，分母和任务语义必须另看。'),
        paragraph('回放时延表是本台架、该候选子集及其墙钟条件下的诊断统计，不能当作正式飞行控制延迟、全部RGB帧延迟或实际硬件实时预算。最新仿真采用0.125倍率，也不能将仿真频率直接解释为1倍实时运行能力。'),
        paragraph('已将trace汇总改为索引查询、严格区间二分及分块读取。对完整行人原trace复算，27项归约字段与原结果精确一致，原件SHA不变；调用约55.484 s，采样RSS约6.10 GiB。没有原归约器单独计时，因而不报告实测加速倍数。六摘要可视化页已通过5个浏览器视图和13项交互检查。'),
    ])
    section('十一、停止原因与存储优化的实际结果', [
        paragraph(f'完整280次实验的已生成预算需要244.9361 GiB。报告生成时D盘可用约{free_gib:.2f} GiB，与原要求相减仍缺约{shortfall:.2f} GiB。这是对原预算的算术对照，不是重新执行容量准入；磁盘尚有可用空间，但不足以承载已约定的完整研究及预留。'),
        table(['预算组成','需要空间/GiB'],[
            ['280槽持久结果与证据',f'{budget_review["GiB"]["full_280_persistent_bytes"]:.4f}'],
            ['后续构建与交付预留','22.0000'],
            ['临时峰值预留',f'{budget_review["GiB"]["temporary_reserve_bytes"]:.4f}'],
            ['合计',f'{required:.4f}'],
        ],[6600,3100]),
        paragraph('完整28槽文件占用实测、两类开发录包导出和定标候选已经完成；原测量经历7步后失败，再由另一个显式续接完成6个命令，最终仍被正容量条件拒绝。不能把它写成“完整流程12步成功”。ext4逻辑容量能够满足，但D盘宿主物理卷容量不足，后者是实际阻断。'),
        paragraph('无损压缩19/22级比较也已实际运行：首个汽车基础包19级完成字节一致性和原生读回验证；22级因固定900 s总预算耗尽而超时，另外两个候选未尝试。完成配对数为0，可证明并计入预算的容量收益为0，生产压缩策略未改变。该次停止不是已证实内存不足。'),
        paragraph('所有原始归档和失败记录均保留；没有因本次生成报告删除项目数据或用户其他文件。没有新增正容量复核、没有实际final55冷构建或正式矩阵。默认关闭且未登记的暂存候选只是准备工具，不能当作正式环境已经存在。'),
        paragraph('本次停止是用户明确决定，并由现实存储缺口支持；不是正在飞行的任务被隐瞒中止。停止时最后的重任务已经退出，Linux只读进程查询无匹配；Windows中残留的WSL idle tail只是环境保活，不表示实验仍在执行。后续必须由用户明确要求恢复，才重新核验空间、环境和原证据链。'),
    ])
    section('十二、历史成果、本次交付与查看方式', [
        paragraph('历史v3已经有报告、计划书、视频、图表、指标与原始归档。其执行完毕不代表全部工程验收通过；本轮Humble54开发成功也不反向改变历史失败。以下原结果保留，用于说明最初问题和研究沿革。'),
        table(['历史v3范围','终态','PASS','FAIL','中断'],[
            ['阶段一','100/100','66','34','0'],['阶段二','26/26','19','7','0'],
            ['阶段三','40/40','22','17','1'],['主研究合计','166/166','107','58','1'],
            ['独立工程扩展','16/16','2','14','0'],
        ],[3900,1700,1300,1300,1500]),
        paragraph('历史主离线台账为160 RECORDED、4 INCOMPLETE_EVIDENCE、2 NOT_APPLICABLE_NO_SELECTED_TASK；扩展补充为15 RECORDED、1 INCOMPLETE_EVIDENCE。工程FAIL包含可评分行为失败、基础设施失败和证据不全等情况，不能直接当成检测/跟踪算法失败率。'),
        table(['资料','本机入口（相对仓库根目录）','作用'],[
            ['本次报告','docs/project-overview-20261103/index.html；同目录Word/PDF/Markdown','停止时点整体状态、图表、结论和来源'],
            ['最新开发成果','results/diagnostics/humble54_development_view01/index.html','开发录像、场景与原报告'],
            ['扩展终态页','results/monitor_humble54_probe02_owner07/index.html','16槽闭合结果；不是运行中的任务'],
            ['计时可视化','results/diagnostics/humble54_pipeline_timing_view01/index.html','6份软件诊断摘要，可切换分母/样本'],
            ['身份原因细分','results/diagnostics/humble54_identity_coverage_readonly01/','身份计数、未知原因与绑定原件'],
            ['历史统一交付','results/frozen_fullplan_v3/交付入口.html','5页计划书、144页归档报告、8段视频和6组图表'],
            ['源码仓库','https://github.com/gurkemctigue-arch/kalman-filter-drone','源码、测试、文档；不等于原始录包备份'],
        ],[1800,5400,2500]),
        paragraph('原始bag、权重、ROS构建目录和多数results数据不随常规Git提交；克隆GitHub后不能期待全部本机录像与实验原始数据自动出现。本次报告的来源清单只记录所用小工件的相对路径、大小和SHA，不包含用户磁盘清理清单或其他私人目录信息。'),
    ])
    section('十三、未完成清单与恢复条件', [
        paragraph('以下是停止时保留的工作清单，不是已获指令自动续跑的队列。本次交付后不再继续实验。当前没有足够资源和正式验证结果，不能给出有依据的最终完成日期。'),
        table(['顺序','待完成工作','完成条件'],[
            ['1','实验容量复核','实际可用宿主物理空间满足完整预算与峰值预留；原生空闲/清单/预算重新产生真实回执'],
            ['2','独立final55暂存与冷验证','实际源码/环境/模型清单、4包冷构建、Linux与来源隔离检查闭合'],
            ['3','导航与传感器证据','完整28槽导航复评与真实sensor4合同绑定；组合故障短窗阅图补齐，原FAIL不改'],
            ['4','定标和前瞻登记','R0/其他参数、正式120核心/160扩展、身份恢复/检测补充协议在正式START前冻结'],
            ['5','正式实验280次','留出种子1000–1009；逐槽仅按登记尝试，保留失败、中断、缺证及原始数据'],
            ['6','算法/身份/检测统计','20条正式录制的四法配对；标签审查、IDF1/HOTA和重捕获指标；完整分母与区间'],
            ['7','最终交付与论文','用正式结果更新图表/视频/报告/计划书；逐项核验，写明未过门或不适用项'],
        ],[650,3100,5950]),
        paragraph('如以后资源仍有限，可以另立规模更小的新研究协议，但应明确它与本次280次计划不同；不能直接减少原计划分母、沿用“全部正式实验完成”的标题或把开发种子改称留出种子。本次并未执行这种变更。'),
        paragraph('对毕业设计当前最有价值的可交付成果，是三阶段完整仿真原型、Humble环境实际构建/运行证据、核心场景开发通过、压力工况失败分析和可追溯评价方法。最需要谨慎的研究主张，是总体可靠性、任意遮挡下指定身份保持、实机实时性以及自适应KF的普遍优越性。'),
        paragraph('最终结论：本次工作已从早期低可靠性归档推进到同源核心开发12/12及独立安全4/4通过，但扩展仍有4 FAIL和1证据不完整，身份存在463个未知时间格，新版正式研究为0/280。按用户要求现停止实验并保留所有现有材料；全项目不标记为验收完成。'),
    ])
    appendix_rows = [
        ['A01','历史v3结果口径','docs/DELIVERY_STATUS.md'],
        ['A02','最新核心12闭合','tools/experiment_orchestration/humble54_core12_closed01/README.md'],
        ['A03','独立安全4闭合','tools/experiment_orchestration/humble54_safety4_closed03/README.md'],
        ['A04','扩展probe02与核心原终态','results/frozen_fullplan_v4_humble54/（两个matrix/slots目录）'],
        ['A05','真实Humble54冷验证','results/frozen_fullplan_v4_humble54/freeze_validation/native_build_supplement02.json'],
        ['A06','完整28槽容量实测','results/frozen_fullplan_v4_humble54/full28_storage_measurement_probe02_after07_01/summary.json'],
        ['A07','原完整280预算','results/frozen_fullplan_v4_humble54/full280_storage_budget_probe02_after07_01/budget.json'],
        ['A08','容量拒绝说明','results/diagnostics/humble54_after28_budget_review01/review01.json'],
        ['A09','定标候选','results/frozen_fullplan_v4_humble54/reliability_v4_humble54_development_calibration_probe02_after07_01/R0_candidate.json'],
        ['A10','身份覆盖与汽车细分','results/diagnostics/humble54_identity_coverage_readonly01/'],
        ['A11','完整两类软件回放','results/diagnostics/humble54_pipeline_timing_full_person01/；同前缀car01/'],
        ['A12','压缩实测停止','results/diagnostics/humble54_lossless22_bench_execution01/review01.json'],
        ['A13','本次停止记录与来源SHA','docs/project-overview-20261103/stop_state.json；report.sources.json'],
    ]
    section('附录：主要证据与阅读口径',[
        paragraph('本报告仅整理已存在的小JSON、配置和文档；没有重评原始bag、重新推理图像或将新诊断写回旧结果。完整来源指纹见同目录report.sources.json，逐槽结构化表见report_data.json。表中“已实现”“开发PASS”“正式完成”“证据完整”是不同判断。'),
        table(['编号','证据','相对仓库根目录路径'],appendix_rows,[650,2200,6850]),
        paragraph('冻结实验根/root/uav_tracking_fullplan_v4_humble54没有因本报告被修改。源码检查点为'+git+'（报告生成之前）；后续文档提交不会使该检查点成为新的正式实验版本。'),
        paragraph('图表全部从表内同批次已有结果生成，未作跨版本配对；空值不填0，未知不删除。部分旧状态页包含过去“正在运行”的历史文字，应以本报告日期和stop_state.json为停止状态入口。'),
    ])
    for path, row in SOURCES.items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Source changed during report generation: ' + path)
    pack = {'schema_version':1, 'kind':'PROJECT_STOP_TIME_OVERVIEW_NOT_FINAL_ACCEPTANCE',
            'title':'RGB-D无人机目标跟踪与自主跟随系统',
            'subtitle':'三阶段项目整体报告｜实验停止时点',
            'date':'2026年11月3日', 'status':'实验已按用户要求停止；全项目尚未完成最终验收',
            'sections':sections, 'core_rows':core, 'extension_rows':extension,
            'formal_progress':{'completed':0,'planned':280},
            'identity_totals':identity['descriptive_pooled_time_grid_counts'],
            'code_commit_before_report':git}
    write_json(OUT/'report_data.json',pack)
    write_json(OUT/'report.sources.json',{'kind':'REPORT_SOURCE_FINGERPRINTS_NOT_REEVALUATION',
               'generated_utc':now,'inputs':list(SOURCES.values()),
               'large_bag_model_trace_read':False,'source_data_modified':False})
    write_markdown(pack); write_html(pack)
    print(json.dumps({'output':str(OUT),'sections':len(sections),'sources':len(SOURCES),
                      'core':len(core),'extension':len(extension),'formal':'0/280'},ensure_ascii=False))


def write_json(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def write_markdown(pack):
    lines=['# '+pack['title'], '', '**'+pack['subtitle']+'**', '',pack['date'], '', '**'+pack['status']+'**','']
    for section in pack['sections']:
        lines+=['## '+section['title'],'']
        for block in section['blocks']:
            if block['type']=='paragraph': lines += [block['text'],'']
            elif block['type']=='table':
                clean=lambda x:str(x).replace('|','\\|')
                lines += ['| '+' | '.join(map(clean,block['headers']))+' |',
                          '| '+' | '.join(['---']*len(block['headers']))+' |']
                lines += ['| '+' | '.join(map(clean,row))+' |' for row in block['rows']]+['']
            elif block['type']=='figure': lines += [f'![{block["caption"]}]({block["path"]})','',block['caption'],'']
    (OUT/'项目整体报告_20261103.md').write_text('\n'.join(lines),encoding='utf-8')


def write_html(pack):
    esc=html.escape
    navigation=''.join(f'<a href="#s{i}">{esc(s["title"])}</a>' for i,s in enumerate(pack['sections']))
    parts=[]
    for i,sec in enumerate(pack['sections']):
        parts.append(f'<section id="s{i}"><h2>{esc(sec["title"])}</h2>')
        for b in sec['blocks']:
            if b['type']=='paragraph': parts.append('<p>'+esc(b['text'])+'</p>')
            elif b['type']=='table':
                parts.append('<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+esc(c)+'</th>' for c in b['headers'])+'</tr></thead><tbody>')
                parts.extend('<tr>'+''.join('<td>'+esc(c)+'</td>' for c in row)+'</tr>' for row in b['rows'])
                parts.append('</tbody></table></div>')
            elif b['type']=='figure':parts.append(f'<figure><img src="{esc(b["path"])}" alt="{esc(b["caption"])}"><figcaption>{esc(b["caption"])}</figcaption></figure>')
        parts.append('</section>')
    page='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>项目整体报告 · 实验停止时点</title><style>
    :root{color-scheme:light;--ink:#213747;--muted:#586c7a;--accent:#26766c;--line:#dce5ec}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif;color:var(--ink);background:#f2f5f8;line-height:1.8}header{padding:52px max(5vw,24px);background:#142d40;color:#fff}header h1{max-width:1080px;margin:0 auto;font-size:clamp(25px,4vw,38px);line-height:1.45}header p,.top-links{max-width:1080px;margin:14px auto}header p{color:#d7e6ef}.pill{display:inline-block;padding:5px 14px;border:1px solid #ccab73;border-radius:5px;color:#ffe1a7}.top-links a{display:inline-block;margin-right:22px;color:#fff}.layout{max-width:1430px;margin:24px auto;display:grid;grid-template-columns:240px minmax(0,1fr);gap:24px;padding:0 24px}nav{position:sticky;top:14px;align-self:start;max-height:94vh;overflow:auto;font-size:13px;padding:10px}nav a{display:block;padding:7px;color:#405c6b;text-decoration:none;border-left:2px solid var(--line)}nav a:hover{color:var(--accent);border-color:var(--accent)}section{scroll-margin-top:20px;background:#fff;border:1px solid var(--line);padding:30px;margin-bottom:22px;border-radius:9px}h2{font-size:23px;line-height:1.45;margin:0 0 20px;color:#193b50}p{margin:0 0 18px;text-align:justify}table{width:100%;border-collapse:collapse;font-size:13px;line-height:1.65}th,td{padding:10px 12px;border:1px solid var(--line);text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#eaf0f4;font-weight:600}tr:nth-child(even){background:#f8fafc}.table-wrap{overflow-x:auto;margin:20px 0}figure{margin:24px 0}figure img{width:100%;height:auto;display:block}figcaption{font-size:12px;color:var(--muted);margin-top:9px}footer{padding:28px;text-align:center;color:var(--muted);font-size:13px}a{color:#236f89}.viewer-links{display:flex;flex-wrap:wrap;gap:12px;margin-top:16px}.viewer-links a{padding:7px 11px;background:#eaf3f2;border-radius:5px;text-decoration:none;font-size:13px}@media(max-width:950px){.layout{display:block;padding:0 12px}nav{position:static;max-height:none;display:flex;flex-wrap:wrap;font-size:12px}nav a{width:50%;padding:5px}section{padding:20px}table{min-width:600px}}@media print{body{background:white}.layout{display:block;padding:0}nav,.top-links,.viewer-links{display:none}header{padding:20px;background:white;color:#142d40}header p{color:#526a78}.pill{color:#72511a}section{border:0;padding:0;margin:22px 0;break-before:page}table{font-size:9pt}thead{display:table-header-group}tr,figure{break-inside:avoid}a{color:inherit}footer{display:none}}
    </style></head><body>'''
    page+=f'<header><h1>{esc(pack["title"])}</h1><p>{esc(pack["subtitle"])} · {esc(pack["date"])}</p><p><span class="pill">{esc(pack["status"])}</span></p><div class="top-links"><a href="项目整体报告_20261103.docx">下载 Word</a><a href="项目整体报告_20261103.pdf">查看 PDF</a><a href="项目整体报告_20261103.md">Markdown</a><a href="report.sources.json">来源指纹</a></div></header>'
    page+='<div class="layout"><nav aria-label="报告目录">'+navigation+'</nav><main>'+''.join(parts)
    page+='''<section><h2>本机可视化成果</h2><p>以下链接指向已有本机结果，GitHub克隆不包含原始results目录。</p><div class="viewer-links"><a href="../../results/diagnostics/humble54_development_view01/index.html">最新开发录像与场景</a><a href="../../results/diagnostics/humble54_pipeline_timing_view01/index.html">计时诊断可视化</a><a href="../../results/frozen_fullplan_v3/交付入口.html">历史v3统一交付</a></div></section></main></div><footer>报告整理已有数据；未启动新实验，未改变原始结果。正式研究 0/280。</footer></body></html>'''
    (OUT/'index.html').write_text(page,encoding='utf-8')


if __name__=='__main__':
    build()
