"""Plot the unchanged primary grid; no evaluator, gate or window is modified."""
from pathlib import Path
import hashlib
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import numpy as np


def main():
    folder = Path(__file__).resolve().parent
    root = folder.parents[2]
    diagnosis_path = folder / 'phase_decomposition.json'
    diagnosis = json.loads(diagnosis_path.read_bytes())
    evidence = next(row for row in diagnosis['inputs'] if row['path'].endswith('.frames.jsonl'))
    source = root / evidence['path']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == evidence['sha256']
    rows = [json.loads(line) for line in source.read_text(encoding='utf8').splitlines()]
    assert len(rows) == 752 and all(row['base_link_distance_error_m'] is not None for row in rows)
    time = np.array([row['time_s'] for row in rows])
    error = np.array([row['base_link_distance_error_m'] for row in rows])
    valid = np.array([row['active'] for row in rows], dtype=bool)
    rmse = float(np.sqrt(np.mean(error ** 2)))
    assert abs(rmse - diagnosis['whole_physical_distance']['rmse_m']) < 1e-12
    assert int(valid.sum()) == 602
    font = FontProperties(fname='C:/Windows/Fonts/msyh.ttc')
    plt.rcParams.update({'font.family':font.get_name(), 'axes.unicode_minus':False,
                         'pdf.fonttype':42, 'font.size':10})
    fig, (ax, state) = plt.subplots(2, 1, figsize=(11, 5.6), sharex=True,
                                    gridspec_kw={'height_ratios':[4, 1]})
    ax.plot(time, error, color='#186b91', linewidth=1.8, label='水平目标距离 − 5 m')
    ax.axhline(0, color='#7f8b95', linewidth=.8)
    for axis in (ax, state):
        axis.axvspan(34.9, 49.9, color='#aab1bb', alpha=.22)
        axis.axvspan(29.8, 30.080000000000002, color='#e4a641', alpha=.5)
        axis.axvspan(42.800000000000004, 45.88, color='#db7856', alpha=.28)
        axis.axvline(49.8, color='#8d4c9c', linestyle='--', linewidth=1)
        axis.grid(axis='y', alpha=.15)
    ax.set_title('组合扰动：提前丢失与重选恢复期间的距离误差', loc='left', fontsize=14)
    ax.text(.01, .95, f'原始全窗口 RMSE = {rmse:.3f} m；原门限 = 1.000 m',
            transform=ax.transAxes, va='top', fontsize=10)
    ax.text(35.1, 6.8, '首次 LOST\n34.86 s', color='#414c58')
    ax.text(43.8, 1.4, '长遮挡\n请求时段', ha='center', fontsize=9, color='#8c472d')
    ax.text(50.4, 7.7, '显式重选\n49.8 s', fontsize=9, color='#733c81')
    peak = int(np.argmax(np.abs(error)))
    ax.scatter([time[peak]], [error[peak]], color='#b93c3c', s=20, zorder=5)
    ax.annotate(f'峰值 {error[peak]:.2f} m（{time[peak]:.1f} s）',
                xy=(time[peak],error[peak]), xytext=(58,6.5),
                arrowprops={'arrowstyle':'-', 'color':'#9b5c5c'}, fontsize=9)
    ax.set_ylabel('跟随距离误差 / m')
    ax.set_ylim(-.8, 8.8)
    ax.legend(loc='upper right', frameon=False)
    state.step(time, valid.astype(int), where='post', color='#3b8b75', linewidth=1.5)
    state.fill_between(time, 0, valid.astype(int), step='post', color='#3b8b75', alpha=.13)
    state.set_yticks([0,1], labels=['无有效目标状态','可用于导航'])
    state.set_ylim(-.12, 1.12)
    state.set_xlim(17.8, 92.928)
    state.set_xlabel('仿真时间 / s')
    fig.text(.01, .015, '保留全部 752/752 时间格；有效导航 602/752。遮挡区域为请求时段。单次开发诊断，原 FAIL 和完整统计窗口不变。', fontsize=9)
    fig.tight_layout(rect=(0,.04,1,1))
    outputs=[]
    for suffix in ('png','pdf'):
        output=folder / ('original_distance_timeline.' + suffix)
        assert not output.exists()
        fig.savefig(output, dpi=160)
        outputs.append({'file':output.name,'bytes':output.stat().st_size,
                        'sha256':hashlib.sha256(output.read_bytes()).hexdigest()})
    plt.close(fig)
    with (folder / 'plot_receipt.json').open('x', encoding='utf8') as handle:
        json.dump({'kind':'ORIGINAL_GRID_VISUALIZATION_NOT_NEW_EVALUATION',
            'source':evidence,'samples':len(rows),'active_samples':int(valid.sum()),
            'reproduced_rmse_m':rmse,'outputs':outputs},handle,indent=2)
        handle.write('\n')
    print(json.dumps({'samples':len(rows),'rmse_m':rmse,'outputs':outputs}))


if __name__ == '__main__':
    main()
