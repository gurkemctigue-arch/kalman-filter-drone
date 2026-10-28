"""Render standalone research figures from frozen JSON; no ROS/YOLO/bag reads."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
METHODS=("raw","ema","fixed_kf","adaptive_kf")
COLORS=("#758496","#d59b39","#27889a","#6751b5")
CONDITIONS=("recorded","depth_noise","depth_holes","frame_dropout","communication_delay","combined")
LABELS=("Recorded\nn=1","Depth noise\nn=10","Depth holes\nn=10","Frame dropout\nn=10","Delay\nn=10","Combined\nn=10")


def save(fig,folder,name):
    fig.savefig(folder/f"{name}.png",dpi=180,bbox_inches="tight")
    fig.savefig(folder/f"{name}.svg",bbox_inches="tight")
    plt.close(fig)


def plot_replay(data,folder):
    for metric,label,filename in (("common_support_position_rmse_m","Common-support surface-anchor position RMSE (m)","paired_replay_position"),
                                   ("coverage","Available output / all opportunities","paired_replay_coverage")):
        fig,axes=plt.subplots(2,2,figsize=(14,8),sharex=True)
        for ax,recording in zip(axes.flat,data["recordings"]):
            x=np.arange(len(CONDITIONS));width=.19
            for i,(method,color) in enumerate(zip(METHODS,COLORS)):
                stats=[recording["groups"][c]["methods"][method][metric] for c in CONDITIONS]
                values=[s["mean"] if s["mean"] is not None else np.nan for s in stats]
                deviations=[s["std"] if s["std"] is not None else 0 for s in stats]
                ax.bar(x+(i-1.5)*width,values,width,color=color,label=method,yerr=deviations,capsize=2)
            ax.set_title(recording["source_trial"].replace("stage1_final_v2_", ""))
            ax.set_xticks(x,LABELS);ax.set_ylabel(label);ax.grid(axis="y",alpha=.2)
            if metric=="coverage":ax.set_ylim(0,1.05)
        handles,labels=axes.flat[0].get_legend_handles_labels();fig.legend(handles,labels,loc="upper center",ncol=4)
        fig.suptitle("Conditional replay of real recorded input; error bars = seed SD",y=1.02)
        fig.text(.5,-.01,"Four source recordings; 10 fault seeds are NOT independent closed-loop flights. Fixed surface-anchor reference can vary with viewpoint.",ha="center",fontsize=10)
        fig.tight_layout(rect=(0,0,1,.96));save(fig,folder,filename)
    fig,axes=plt.subplots(2,2,figsize=(12,8),sharex=True)
    for ax,recording in zip(axes.flat,data["recordings"]):
        for i,condition in enumerate(CONDITIONS[1:]):
            pair=recording["groups"][condition]["adaptive_minus_baseline_position_rmse_m"]["fixed_kf"]
            if pair["mean_difference"] is None:continue
            mean=pair["mean_difference"];lower,upper=pair["ci95"]
            ax.errorbar(mean,i,xerr=[[max(0,mean-lower)],[max(0,upper-mean)]],fmt="o",color=COLORS[-1],capsize=4)
            ax.text(mean,i+.17,f"{pair['pairs']} pairs",fontsize=8,ha="center")
        ax.axvline(0,color="#607080",linestyle="--");ax.set_yticks(np.arange(5),[s.split("\n")[0] for s in LABELS[1:]])
        ax.set_title(recording["source_trial"].replace("stage1_final_v2_", ""));ax.grid(axis="x",alpha=.2)
        ax.set_xlabel("Adaptive minus fixed-KF position RMSE (m)")
    fig.suptitle("Paired bootstrap 95% intervals, 10,000 seed resamples\nNegative favours adaptive; conditional on each recording, exploratory comparisons",fontsize=13)
    fig.tight_layout(rect=(0,0,1,.9));save(fig,folder,"paired_adaptive_minus_fixed")


def plot_detection(data,folder):
    fig,ax=plt.subplots(figsize=(10,5));labels=[];values=[]
    for recording in data["recordings"]:
        metrics=recording.get("reviewed_metrics")
        if not metrics:continue
        category=recording["target_class"];entry=metrics["classes"][category]
        labels.append(Path(recording["source_trial"]).name.replace("stage1_final_v2_", "")+f"\nreviewed n={recording['approved_eligible']}")
        values.append([entry["precision"],entry["recall"],entry["ap50_95"]])
    x=np.arange(len(labels));width=.25
    for i,(label,color) in enumerate(zip(("Precision @ .45","Recall @ .45","AP .50:.95"),COLORS)):
        heights=[v[i] for v in values];bars=ax.bar(x+(i-1)*width,heights,width,label=label,color=color)
        ax.bar_label(bars,fmt="%.3f",padding=3,fontsize=8)
    ax.set_xticks(x,labels);ax.set_ylim(0,1.15);ax.legend(ncol=3,loc="upper center");ax.grid(axis="y",alpha=.2)
    ax.set_title("Reviewed fully visible static simulation subset only\nAP uses frozen conf=.001 predictions; operational P/R use .45")
    fig.text(.5,-.015,"132 chronologically sampled eligible images, including operational misses. Not real-world, occluded-object, or overall-flight detector performance.",ha="center",fontsize=9)
    fig.tight_layout();save(fig,folder,"reviewed_detection_subset")


def plot_online(data,path,folder):
    timeline=data["ego_alignment"].get("timeline_approx_2hz",[])
    sidecar=path.with_suffix(".frames.jsonl")
    if not timeline or not sidecar.exists():return False
    frames=[json.loads(line) for line in sidecar.read_text().splitlines() if line.strip()]
    fig,axes=plt.subplots(3,1,figsize=(12,9),sharex=True)
    times=[r["time_s"] for r in timeline]
    axes[0].plot(times,[np.linalg.norm(r["aligned_position_error_vector_m"]) for r in timeline],label="Ego position error (m)",color=COLORS[0])
    axes[0].plot(times,[r["attitude_error_rad"] for r in timeline],label="Ego attitude error (rad)",color=COLORS[2])
    for reset in data["raw_px4_odometry_diagnostics"]["reset_counter_changes"]:
        axes[0].axvline(reset["time_s"],ls=":",color="#bb4e44",label="PX4 aggregate reset_counter change")
    axes[0].axvspan(data["ego_alignment"]["calibration_start_s"],data["ego_alignment"]["calibration_end_s"],color="gray",alpha=.12,label="Translation calibration only")
    axes[0].legend(fontsize=9);axes[0].set_ylabel("Ego residual, m / rad")
    for key,label,color in (("state_stamp_position_error_m","Actual online state, source stamp",COLORS[-1]),
                            ("receipt_clock_position_error_m","Same carried state, receipt clock",COLORS[1])):
        axes[1].plot([r["time_s"] for r in frames],[r.get(key,np.nan) for r in frames],label=label,color=color,alpha=.8)
    axes[1].legend(fontsize=9);axes[1].set_ylabel("Surface-anchor position error (m)")
    measured=np.asarray([r["state"] in (1,2) and r.get("state_stamp_position_error_m") is not None for r in frames],dtype=float)
    axes[2].step([r["time_s"] for r in frames],measured,where="post",color=COLORS[2]);axes[2].set_yticks([0,1],["Unavailable","Available"])
    axes[2].set_ylim(-.1,1.1);axes[2].set_xlabel("Simulation time (s)")
    for ax in axes:ax.grid(alpha=.2)
    metrics=data["online_state_accuracy"]["metrics"]
    fig.suptitle("Actual online state audit: source-declared ENU axes, first-5s ego translation only\n"+
                 f"Position RMSE={metrics['state_stamp_position_error_m']['rmse']:.3f} m; coverage={data['online_state_accuracy']['active_coverage']:.1%}; no GT extrapolation",fontsize=12)
    fig.text(.5,.005,"Frozen visible-surface anchor, not model-center accuracy. Unavailable/LOST states remain in the denominator; old attitude-rotation sensitivity is retained in JSON.",ha="center",fontsize=9)
    fig.tight_layout(rect=(0,.02,1,.94));save(fig,folder,"online_state_audit")
    return True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"results/research_figures")
    parser.add_argument("--replay",type=Path,default=ROOT/"results/recorded_estimator_research/research_report.json")
    parser.add_argument("--detection",type=Path,default=ROOT/"results/detection_research/detection_report.json")
    parser.add_argument("--online",type=Path,default=ROOT/"results/stage1_final_v2_person_velocity/online_state_accuracy_v2.json")
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({"font.size":10,"axes.spines.top":False,"axes.spines.right":False})
    plot_replay(json.loads(args.replay.read_text()),args.output)
    plot_detection(json.loads(args.detection.read_text()),args.output)
    online_plotted=plot_online(json.loads(args.online.read_text()),args.online,args.output) if args.online.exists() else False
    inputs={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in (args.replay,args.detection,args.online) if path.exists()}
    result={"schema_version":1,"inputs_sha256":inputs,"online_plotted":online_plotted,
            "figures":[str(p.relative_to(args.output)) for p in sorted(args.output.glob("*.png"))],
            "claim_boundary":"Standalone PNG and SVG; source reports retain all failures, missing values and conditional/online distinctions. Plots consume existing JSON only and never trigger simulator, detector, bag replay or GT-assisted runtime."}
    (args.output/"manifest.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":main()
