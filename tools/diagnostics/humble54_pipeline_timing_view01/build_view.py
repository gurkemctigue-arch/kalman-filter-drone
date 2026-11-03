"""Build a standalone view from copied closed native timing summaries only."""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "results/diagnostics/humble54_pipeline_timing_view01"
DIRECTORY = re.compile(r"humble54_pipeline_timing_(?:run.*|full_?person.*|full_?car.*)$")


def numeric(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def stats(values):
    values = sorted(values)
    return {"n": len(values), "median": statistics.median(values) if values else None,
            "p95": values[int((len(values)-1)*.95+.5)] if values else None,
            "max": max(values, default=None)}


def prepare(path):
    raw = path.read_bytes()
    data = json.loads(raw)
    commands, rgbs = data.get("commands"), data.get("rgb_opportunities")
    command_rows = commands if type(commands) is list else []
    rgb_rows = rgbs if type(rgbs) is list else []
    checks = []
    def check(label, actual, expected):
        if actual is not None and expected is not None:
            checks.append({"label": label, "actual": actual, "expected": expected, "pass": actual == expected})
    total, candidate, unknown = (data.get(k) for k in ("adapter_callback_count", "candidate_command_count", "unknown_command_count"))
    if commands is not None:
        check("命令明细 / 全部适配器回调", len(command_rows), total)
        check("候选命令明细 / 摘要计数", sum(r.get("status") == "CANDIDATE_SOFTWARE_LATENCY" for r in command_rows), candidate)
        check("UNKNOWN 命令明细 / 摘要计数", sum(r.get("status") == "UNKNOWN" for r in command_rows), unknown)
    if all(type(x) is int for x in (candidate, unknown, total)):
        check("候选 + UNKNOWN / 全部命令", candidate + unknown, total)
    if rgbs is not None:
        check("RGB 明细 / 全部收到的 RGB", len(rgb_rows), data.get("received_rgb_count"))
        check("有候选的 RGB 明细 / 摘要计数", sum(r.get("outcome") == "CANDIDATE" for r in rgb_rows), data.get("rgb_with_candidate_count"))
        check("各 RGB 的候选命令数之和", sum(r.get("candidate_command_count", 0) for r in rgb_rows), candidate)
    categories = data.get("command_categories", {})
    if categories and type(total) is int:
        check("命令类别计数 / 全部命令", sum(categories.values()), total)
    opportunities = data.get("opportunity_counts", {})
    replay = data.get("replayed_input_counts_by_kind", {})
    if replay:
        check("回放输入类型计数之和", sum(replay.values()), opportunities.get("replay_input"))
    edges = {}
    for phase, edge in data.get("edges", {}).items():
        pairs = edge.get("pairs", [])
        check(phase + "：候选 + UNKNOWN / take", edge.get("candidate_count", 0) + edge.get("unknown_count", 0), edge.get("take_count"))
        check(phase + "：配对明细 / take", len(pairs), edge.get("take_count"))
        check(phase + "：候选明细 / 候选计数", sum(r.get("status") == "OBSERVED_CANDIDATE" for r in pairs), edge.get("candidate_count"))
        edges[phase] = {k: edge.get(k) for k in ("publish_count", "take_count", "candidate_count", "unknown_count", "graph_max_observed_gap_ns")}
        edges[phase]["reasons"] = dict(Counter(reason for row in pairs for reason in row.get("reasons", [])))
    latencies = [r["latency_ns"] for r in command_rows if r.get("status") == "CANDIDATE_SOFTWARE_LATENCY" and numeric(r.get("latency_ns"))]
    first = [r["first_candidate_latency_ns"] for r in rgb_rows if numeric(r.get("first_candidate_latency_ns"))]
    calculated = stats(latencies)
    if commands is not None:
        check("可画图的候选命令 / 候选计数", len(latencies), candidate)
    for key in ("median", "p95", "max"):
        reported = data.get("candidate_subset_statistics_ns", {}).get(key)
        check("候选时延 " + key + " / 原摘要", calculated[key], reported)
    name = path.parent.name
    label = re.sub(r"^humble54_pipeline_timing_", "", name)
    record = {"id": name, "label": label, "path": path.relative_to(ROOT).as_posix(),
              "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
              "status": data.get("status", "未提供"), "native_complete": data.get("native_complete"),
              "error": data.get("error"), "process_exit_codes": data.get("process_exit_codes", {}),
              "cleanup_errors": data.get("cleanup_errors", []), "owned_group_status": data.get("owned_group_status", {}),
              "opportunities": opportunities, "replay": replay, "edges": edges,
              "adapter_callback_count": total, "candidate_command_count": candidate, "unknown_command_count": unknown,
              "received_rgb_count": data.get("received_rgb_count"), "rgb_with_candidate_count": data.get("rgb_with_candidate_count"),
              "categories": categories, "unknown_reasons": data.get("unknown_reasons", {}),
              "commands": [{k: row.get(k) for k in ("adapter_callback_event_id", "status", "command_category", "reasons", "latency_ns")} for row in command_rows],
              "rgbs": [{k: row.get(k) for k in ("rgb_callback_event_id", "image_token", "selected_snapshot_count", "candidate_command_count", "first_candidate_latency_ns", "outcome", "reason")} for row in rgb_rows],
              "commands_available": commands is not None, "rgbs_available": rgbs is not None,
              "latencies_ns": latencies, "first_latencies_ns": first,
              "statistics_ns": calculated if commands is not None else {"n": None, "median": None, "p95": None, "max": None},
              "first_statistics_ns": stats(first) if rgbs is not None else {"n": None, "median": None, "p95": None, "max": None},
              "physical_e2e": data.get("physical_e2e", "未提供"), "checks": checks}
    return record


HTML = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>独立软件回放 · 计时链路诊断</title>
<style>
:root{color-scheme:dark;--bg:#101820;--panel:#17232d;--line:#2c3d4a;--text:#e9f1f5;--muted:#a6b8c5;--teal:#60dec5;--amber:#f7cc85;--red:#ffaaa6;--gray:#526371}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.65 "Segoe UI","Microsoft YaHei",sans-serif}main{max-width:1420px;margin:auto;padding:28px 32px 56px}h1{font-size:32px;letter-spacing:.02em;margin:8px 0}h2{font-size:19px;margin:0 0 14px}h3{font-size:15px;margin:0 0 8px}p{margin:8px 0}.muted,.caption{color:var(--muted)}.caption{font-size:13px}.eyebrow{color:var(--teal);letter-spacing:.15em;font-size:12px}.top{display:flex;justify-content:space-between;gap:20px;align-items:flex-start}.pill{display:inline-block;background:#263440;border:1px solid var(--line);padding:5px 11px;border-radius:8px;font-size:13px}.formal{color:var(--amber);white-space:nowrap}.controls{display:flex;gap:20px;flex-wrap:wrap;margin:24px 0 16px;align-items:end}label{display:block;font-size:13px;color:var(--muted)}select,button{font:inherit;color:var(--text);background:#1c2d39;border:1px solid #466071;border-radius:7px;padding:8px 12px}select{min-width:210px}button{cursor:pointer}button:disabled{opacity:.4;cursor:default}a{color:var(--teal)}.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:20px;margin:16px 0}.statusline{display:flex;gap:12px;flex-wrap:wrap;align-items:center}.ok{color:var(--teal)}.warn{color:var(--amber)}.bad{color:var(--red)}.badge{font-family:Consolas,monospace;font-size:13px;overflow-wrap:anywhere}.facts{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:18px}.fact{border-left:2px solid #4b6574;padding-left:12px}.value{display:block;font-size:27px;line-height:1.4;font-variant-numeric:tabular-nums}.subvalue{font-size:13px;color:var(--muted)}.pipeline{display:grid;grid-template-columns:repeat(5,1fr);gap:14px}.stage{position:relative;background:#1b2c37;border:1px solid var(--line);border-radius:9px;padding:16px}.stage:not(:last-child):after{content:"→";position:absolute;right:-14px;top:24px;color:var(--teal);z-index:1}.stage p{font-size:13px;color:var(--muted)}.stage strong{font-size:21px;color:var(--text)}.two{display:grid;grid-template-columns:1fr 1fr;gap:18px}.coverage{height:24px;display:flex;background:var(--gray);border-radius:6px;overflow:hidden;margin:12px 0}.coverage .observed{background:var(--teal)}.legend{display:flex;gap:18px;flex-wrap:wrap;font-size:13px}.swatch{display:inline-block;width:10px;height:10px;margin-right:7px;background:var(--teal)}.swatch.gray{background:var(--gray)}.metricrow{display:flex;gap:26px;flex-wrap:wrap;margin:12px 0 18px}.metricrow strong{display:block;font-size:23px;font-weight:600}.chart{width:100%;height:auto;display:block;min-height:140px}.chart text{font:12px "Segoe UI","Microsoft YaHei",sans-serif;fill:var(--muted)}.empty{min-height:170px;display:flex;align-items:center;justify-content:center;color:var(--muted);text-align:center;border:1px dashed #405767;border-radius:8px;padding:20px}.tablewrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:500}td.num{text-align:right;font-variant-numeric:tabular-nums}.mono{font:12px/1.6 Consolas,monospace;overflow-wrap:anywhere}.reasons{display:grid;gap:7px}.reason{display:flex;justify-content:space-between;gap:18px;font-size:13px;overflow-wrap:anywhere}.reason span:last-child{font-variant-numeric:tabular-nums;white-space:nowrap}.notice{border-left:3px solid var(--amber);padding-left:15px;margin:16px 0}.pagination{display:flex;gap:12px;align-items:center;justify-content:flex-end;margin-top:15px}.foot{font-size:12px;color:var(--muted);overflow-wrap:anywhere}details summary{cursor:pointer;color:var(--muted)}.dataset{max-width:100%;overflow-wrap:anywhere}
@media(max-width:1050px){.pipeline{grid-template-columns:repeat(3,1fr)}.stage:after{display:none}.facts{grid-template-columns:repeat(2,1fr)}}@media(max-width:750px){main{padding:20px 14px}.top,.two{display:block}.formal{margin-top:10px}.pipeline{grid-template-columns:1fr 1fr}.panel{padding:16px}h1{font-size:26px}.facts{gap:16px}.value{font-size:23px}.two>.panel{margin-top:16px}.stage p{margin-bottom:0}}
</style></head><body><main>
<header class="top"><div><div class="eyebrow">INDEPENDENT SOFTWARE REPLAY</div><h1>计时链路诊断</h1><p class="muted">从完整分母查看候选链路、未知样本与时延分布。</p></div><div class="pill formal">正式验收：0 / 280</div></header>
<div class="notice caption">本页仅收录已闭合并复制的独立软件回放摘要。它不推进正式验收计数；物理 E2E 未观测，历史 strict 1857/1857 UNKNOWN 保留。失败与完整但无候选的运行均保留。</div>
<div class="controls"><div><label for="run">运行</label><select id="run"></select></div><div><label for="denominator">查看完整分母</label><select id="denominator"><option value="commands">全部适配器命令回调</option><option value="rgb">全部收到的 RGB 回调</option></select></div><div><label for="population">时延样本口径</label><select id="population"><option value="commands">全部候选命令</option><option value="first">每 RGB 的首个候选</option></select></div></div>
<section id="status" class="panel" aria-live="polite"></section>
<section class="panel"><h2>传感输入 → 检测 → 估计 → 控制 → 适配器</h2><p class="caption">每个节点的事件单位不同。控制 tick 可以复用旧图像，箭头不表示一张图像只产生一条命令。回放发布与传感回调仅分别计数，没有逐图 DDS 身份连接。</p><div id="pipeline" class="pipeline"></div></section>
<div class="two"><section class="panel"><h2 id="coverage-title">完整分母</h2><div id="coverage"></div><p class="caption">未形成候选不等于算法失败。未激活、非 FOLLOW、缺少证据等都可能保留为 UNKNOWN。</p></section><section class="panel"><h2>命令类别与 UNKNOWN 原因</h2><div id="categories"></div><div id="unknown-reasons" style="margin-top:16px"></div><p class="caption">FAILSAFE 是摘要中的命令类别。非 FOLLOW 命令数不能直接解读为算法失败次数；一条 UNKNOWN 也可对应多个原因。</p></section></div>
<section class="panel"><h2>三条 DDS 边的关联证据</h2><div id="edges"></div><p class="caption">每条边最多为 OBSERVED_CANDIDATE。图轮询不能证明所有瞬时外部写者均不存在，候选关联不升级为 KNOWN。</p></section>
<section class="panel"><h2 id="distribution-title">候选子集时延</h2><p id="distribution-caption" class="caption"></p><div id="metrics" class="metricrow"></div><div class="two"><div><h3>时延分布 · 直方图</h3><div id="histogram"></div></div><div><h3>累积分布 · ECDF</h3><div id="cdf"></div></div></div><p class="caption">t0 为实际选入快照的 RGB/Depth 回调 hook 入口较晚值，t1 为适配器回调 hook 入口。包含插桩开销；候选子集不能代表总体时延，更不能外推原飞行或物理 E2E。每 RGB 首个候选仅使用摘要已有 first_candidate_latency_ns，缺失时不补算。</p></section>
<section class="panel"><h2 id="detail-title">分母明细</h2><p id="detail-caption" class="caption"></p><div id="detail" class="tablewrap"></div><div class="pagination"><button id="previous">上一页</button><span id="pageinfo" class="caption"></span><button id="next">下一页</button></div></section>
<section class="panel"><h2>原始结果与校验</h2><div id="provenance"></div><details style="margin-top:12px"><summary>展开计数一致性检查</summary><div id="checks" class="tablewrap"></div></details></section>
<footer class="foot">生成于 <span id="built"></span>。离线页面无外部依赖；闭合的新摘要复制后重新运行 build_view.py 即可更新。<a href="build_manifest.json">源文件与输入 SHA 清单</a></footer>
</main><script type="application/json" id="dataset">__DATASET__</script><script>
"use strict";
const DATA=JSON.parse(document.getElementById("dataset").textContent),$=id=>document.getElementById(id),esc=s=>String(s??"—").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const number=x=>typeof x==="number"&&Number.isFinite(x),fmt=x=>number(x)?x.toLocaleString("zh-CN"):"—",ms=x=>number(x)?(x/1e6).toFixed(2)+" ms":"—",pct=(a,b)=>number(a)&&number(b)&&b>0?(100*a/b).toFixed(1)+"%":"—";
const labels={FOLLOW:"FOLLOW",FAILSAFE:"FAILSAFE",HOLD:"HOLD",SEARCH:"SEARCH",OTHER:"其他",UNCLASSIFIED_MISSING_EDGE:"关联缺失，无法分类"};
let page=0;const SIZE=25,params=new URLSearchParams(location.search);
for(const run of DATA.runs){const option=document.createElement("option");option.value=run.id;option.textContent=run.label+" · "+(run.native_complete?"已完成":"未完成")+" · "+(run.candidate_command_count==null?"计数未取得":fmt(run.candidate_command_count)+" 候选");$("run").append(option);}
if(DATA.runs.length){const complete=r=>r.native_complete===true&&r.status==='CANDIDATE_OBSERVED_IN_THIS_BENCH_ONLY'&&r.candidate_command_count>0;const preferred=DATA.runs.find(r=>/^humble54_pipeline_timing_full_?car/.test(r.id)&&complete(r))??DATA.runs.find(r=>/^humble54_pipeline_timing_full_?person/.test(r.id)&&complete(r))??DATA.runs.filter(r=>/^humble54_pipeline_timing_run/.test(r.id)).slice(-1)[0]??DATA.runs[DATA.runs.length-1];$("run").value=DATA.runs.some(r=>r.id===params.get("run"))?params.get("run"):preferred.id;}
if(["commands","rgb"].includes(params.get("denominator")))$("denominator").value=params.get("denominator");
if(["commands","first"].includes(params.get("population")))$("population").value=params.get("population");
$("built").textContent=DATA.built_utc;
const reasons=(items,empty="摘要未记录该类原因")=>Object.keys(items??{}).length?'<div class="reasons">'+Object.entries(items).sort((a,b)=>b[1]-a[1]).map(([k,v])=>'<div class="reason"><span>'+esc(k)+'</span><span>'+fmt(v)+'</span></div>').join("")+"</div>":'<p class="caption">'+empty+"</p>";
function table(headers,rows){return '<table><thead><tr>'+headers.map(h=>"<th>"+esc(h)+"</th>").join("")+"</tr></thead><tbody>"+rows.map(row=>"<tr>"+row.map(cell=>"<td>"+cell+"</td>").join("")+"</tr>").join("")+"</tbody></table>";}
function chart(values,kind){if(!values.length)return '<div class="empty">没有可画图的候选样本。原始失败与 UNKNOWN 分母仍显示在上方。</div>';
 const v=values.map(n=>n/1e6).sort((a,b)=>a-b),W=560,H=240,L=52,R=20,T=20,B=42,cw=W-L-R,ch=H-T-B,lo=Math.floor(v[0]/10)*10,hi=Math.max(lo+1,Math.ceil(v[v.length-1]/10)*10),x=n=>L+(n-lo)/(hi-lo)*cw;
 let shapes='',ymax=1;
 if(kind==='hist'){const bins=12,counts=Array(bins).fill(0);v.forEach(n=>counts[Math.min(bins-1,Math.floor((n-lo)/(hi-lo)*bins))]++);ymax=Math.max(...counts);counts.forEach((n,i)=>{const left=lo+(hi-lo)*i/bins,right=lo+(hi-lo)*(i+1)/bins;shapes+='<rect x="'+(L+i*cw/bins+1)+'" y="'+(T+ch-n/ymax*ch)+'" width="'+(cw/bins-2)+'" height="'+(n/ymax*ch)+'" fill="#60dec5"><title>'+left.toFixed(1)+'–'+right.toFixed(1)+' ms：'+n+' 个样本</title></rect>';});}
 else{const steps=v.map((n,i)=>'H'+x(n)+' V'+(T+ch-(i+1)/v.length*ch));shapes='<path d="M'+L+','+(T+ch)+' '+steps.join(' ')+' H'+(W-R)+'" fill="none" stroke="#60dec5" stroke-width="2.5"/>';}
 let axes='<line x1="'+L+'" y1="'+(T+ch)+'" x2="'+(W-R)+'" y2="'+(T+ch)+'" stroke="#526371"/>';
 for(let i=0;i<=4;i++){const yy=T+ch-i/4*ch;axes+='<line x1="'+L+'" y1="'+yy+'" x2="'+(W-R)+'" y2="'+yy+'" stroke="#2c3d4a"/>'+'<text x="'+(L-8)+'" y="'+(yy+4)+'" text-anchor="end">'+(kind==='hist'?Math.round(ymax*i/4):i*25+'%')+'</text>';const xx=L+i/4*cw;axes+='<text x="'+xx+'" y="'+(H-19)+'" text-anchor="middle">'+(lo+(hi-lo)*i/4).toFixed(0)+'</text>';}
 return '<svg class="chart" viewBox="0 0 '+W+' '+H+'" role="img" aria-label="'+(kind==='hist'?'候选时延直方图':'候选时延累积分布')+'">'+axes+shapes+'<text x="'+(W-R)+'" y="'+(H-3)+'" text-anchor="end">时延 / ms</text></svg>';}
function renderDetails(run){const rgb=$("denominator").value==='rgb',available=rgb?run.rgbs_available:run.commands_available,rows=rgb?run.rgbs:run.commands;page=Math.max(0,Math.min(page,Math.max(0,Math.ceil(rows.length/SIZE)-1)));
 $("detail-title").textContent=rgb?'全部收到的 RGB · 分母明细':'全部适配器命令回调 · 分母明细';
 $("detail-caption").textContent=available?'保留所有已记录机会，分页只改变显示范围。':'该运行未取得可评价明细；不把缺失明细填为零。';
 $("detail").innerHTML=available?table(rgb?['序号 / RGB 回调','选入快照数','候选命令数','首个候选时延','结果 / 原因']:['序号 / 命令回调','命令类别','链路结果','候选时延','UNKNOWN 原因'],rows.slice(page*SIZE,(page+1)*SIZE).map((r,i)=>rgb?[esc(page*SIZE+i+1)+'<div class="mono">'+esc(r.rgb_callback_event_id)+'</div>',fmt(r.selected_snapshot_count),fmt(r.candidate_command_count),ms(r.first_candidate_latency_ns),esc(r.outcome)+'<div class="caption">'+esc(r.reason??'')+'</div>']:[esc(page*SIZE+i+1)+'<div class="mono">'+esc(r.adapter_callback_event_id)+'</div>',esc(labels[r.command_category]??r.command_category??'未分类（摘要未提供）'),esc(r.status),ms(r.latency_ns),esc((r.reasons??[]).join('; '))])):'<div class="empty">本次未取得该分母明细。</div>';
 $("pageinfo").textContent=available?(rows.length?`${page*SIZE+1}–${Math.min(rows.length,(page+1)*SIZE)} / ${fmt(rows.length)}`:'0 条已记录明细'):'不可用';$("previous").disabled=!available||page===0;$("next").disabled=!available||(page+1)*SIZE>=rows.length;
}
function render(){if(!DATA.runs.length){$("status").innerHTML='<h2>尚无已复制的闭合摘要</h2>';document.body.dataset.rendered='true';return;}const r=DATA.runs.find(x=>x.id===$("run").value),rgb=$("denominator").value==='rgb',first=$("population").value==='first';
 const bad=r.checks.filter(x=>!x.pass),good=number(r.candidate_command_count)&&r.candidate_command_count>0;
 $("status").innerHTML='<div class="statusline"><strong>'+esc(r.label)+'</strong><span class="badge '+(good?'ok':r.native_complete?'warn':'bad')+'">'+esc(r.status)+'</span><span class="pill">'+(r.native_complete?'执行完整':'执行未完成')+'</span></div>'+(r.error?'<p class="bad dataset">'+esc(r.error)+'</p>':'')+'<div class="facts"><div class="fact"><span class="caption">全部适配器命令回调</span><span class="value">'+fmt(r.adapter_callback_count)+'</span></div><div class="fact"><span class="caption">FOLLOW 全链候选 / 全部命令</span><span class="value">'+fmt(r.candidate_command_count)+' / '+fmt(r.adapter_callback_count)+'</span><span class="subvalue">'+pct(r.candidate_command_count,r.adapter_callback_count)+'</span></div><div class="fact"><span class="caption">收到的全部 RGB</span><span class="value">'+fmt(r.received_rgb_count)+'</span></div><div class="fact"><span class="caption">形成候选的 RGB / 全部 RGB</span><span class="value">'+fmt(r.rgb_with_candidate_count)+' / '+fmt(r.received_rgb_count)+'</span><span class="subvalue">'+pct(r.rgb_with_candidate_count,r.received_rgb_count)+'</span></div></div>'+(bad.length?'<p class="bad">计数一致性有 '+bad.length+' 项差异，请核对原摘要。</p>':'');
 const o=r.opportunities,e=r.edges,stages=[['传感输入',`回放总记录 <strong>${fmt(o.replay_input)}</strong>`,`回放 RGB ${fmt(r.replay.rgb)} / Depth ${fmt(r.replay.depth)}<br>收到 RGB ${fmt(r.received_rgb_count)}；传感回调合计 ${fmt(o.sensor_callback)}`],['检测',`检测帧发布 <strong>${fmt(e.detection?.publish_count)}</strong>`,`快照 ${fmt(o.snapshot)}；工作线程启动 ${fmt(o.worker_start)}`],['估计',`状态发布 <strong>${fmt(e.state?.publish_count)}</strong>`,`导航更新尝试 ${fmt(o.navigation_update)}；投影 ${fmt(o.navigation_project)}`],['控制',`命令发布 <strong>${fmt(e.command?.publish_count)}</strong>`,`FOLLOW ${fmt(r.categories.FOLLOW)}；FAILSAFE ${fmt(r.categories.FAILSAFE)}`],['适配器',`命令回调 <strong>${fmt(r.adapter_callback_count)}</strong>`,`全链候选 ${fmt(r.candidate_command_count)}；UNKNOWN ${fmt(r.unknown_command_count)}`]];
 $("pipeline").innerHTML=stages.map(([title,main,sub])=>'<div class="stage"><h3>'+title+'</h3><p>'+main+'</p><p>'+sub+'</p></div>').join('');
 const total=rgb?r.received_rgb_count:r.adapter_callback_count,part=rgb?r.rgb_with_candidate_count:r.candidate_command_count,rest=number(total)&&number(part)?total-part:null;
 $("coverage-title").textContent=rgb?'全部收到的 RGB：候选覆盖':'全部命令：全链候选覆盖';$("coverage").innerHTML='<div class="metricrow"><div><span class="caption">候选 / 完整分母</span><strong>'+fmt(part)+' / '+fmt(total)+'</strong></div><div><span class="caption">覆盖比例</span><strong>'+pct(part,total)+'</strong></div></div>'+(number(total)&&total>0&&number(part)?'<div class="coverage" role="img" aria-label="'+esc(part)+' 个候选，共 '+esc(total)+' 个机会"><div class="observed" style="width:'+Math.max(0,Math.min(100,100*part/total))+'%"></div></div>':'<div class="caption">该运行没有可用的分母计数。</div>')+'<div class="legend"><span><i class="swatch"></i>候选 '+fmt(part)+'</span><span><i class="swatch gray"></i>其余 / UNKNOWN '+fmt(rest)+'</span></div>';
 $("categories").innerHTML=Object.keys(r.categories).length?table(['类别','全部命令中的计数'],Object.entries(r.categories).map(([k,v])=>[esc(labels[k]??k),fmt(v)])):'<p class="caption">未取得命令分类计数，不能推测为 FOLLOW 或 FAILSAFE。</p>';
 $("unknown-reasons").innerHTML='<h3>全链 UNKNOWN 原因</h3>'+reasons(r.unknown_reasons);
 const names={detection:'检测 → 估计',state:'估计 → 控制',command:'控制 → 适配器'};
 $("edges").innerHTML=Object.keys(e).length?table(['DDS 边','发布次数','take 次数','候选','UNKNOWN','原因'],Object.entries(e).map(([k,v])=>[esc(names[k]??k),fmt(v.publish_count),fmt(v.take_count),'<span class="ok">'+fmt(v.candidate_count)+'</span>',fmt(v.unknown_count),reasons(v.reasons,'无已记录原因')])):'<div class="empty">该运行未进入可评价的 DDS 关联区间。</div>';
 const s=first?r.first_statistics_ns:r.statistics_ns,values=first?r.first_latencies_ns:r.latencies_ns,den=first?r.received_rgb_count:r.adapter_callback_count;
 $("distribution-title").textContent=first?'每 RGB 首个候选 · 时延分布':'全部候选命令 · 时延分布';$("distribution-caption").textContent=!number(s.n)?'本次未取得该口径的时延明细，不填零，也不绘制时延分布。':first?`仅使用摘要已有 first_candidate_latency_ns：${fmt(s.n)} 个 RGB 有首候选，全部收到 RGB 为 ${fmt(den)}。不为缺失图像补值。`:`${fmt(s.n)} 条候选命令进入分布；全部命令为 ${fmt(den)}。同一 RGB 可被多条控制命令复用，因此这些命令不是独立图像样本。`;
 $("metrics").innerHTML=[['样本数 / 完整分母',fmt(s.n)+' / '+fmt(den)],['中位数',ms(s.median)],['P95',ms(s.p95)],['最大值',ms(s.max)]].map(([title,value])=>'<div><span class="caption">'+title+'</span><strong>'+value+'</strong></div>').join('');$("histogram").innerHTML=chart(values,'hist');$("cdf").innerHTML=chart(values,'cdf');
 renderDetails(r);$("provenance").innerHTML='<p><a href="../'+encodeURI(r.id)+'/native_summary.original.json">打开原始摘要</a></p><p class="mono">'+esc(r.path)+'<br>SHA-256 '+esc(r.sha256)+'</p><p class="caption">进程退出码：'+esc(JSON.stringify(r.process_exit_codes))+'<br>清理错误：'+esc(JSON.stringify(r.cleanup_errors))+'；物理 E2E：'+esc(r.physical_e2e)+'</p>';
 $("checks").innerHTML=r.checks.length?table(['检查','实际值','摘要 / 期望值','结果'],r.checks.map(c=>[esc(c.label),fmt(c.actual),fmt(c.expected),'<span class="'+(c.pass?'ok':'bad')+'">'+(c.pass?'一致':'差异')+'</span>'])):'<p class="caption">该运行没有可交叉检查的评价计数；不能据此补零。</p>';
 document.body.dataset.rendered='true';document.body.dataset.run=r.id;document.body.dataset.denominator=$("denominator").value;document.body.dataset.population=$("population").value;
 try{const query=new URLSearchParams({run:r.id,denominator:$("denominator").value,population:$("population").value});history.replaceState(null,'','?'+query);}catch(error){}
}
for(const id of ['run','denominator','population'])$(id).addEventListener('change',()=>{page=0;render();});$("previous").addEventListener('click',()=>{page--;render();});$("next").addEventListener('click',()=>{page++;render();});
try{render();}catch(error){document.body.dataset.error=String(error);$("status").textContent='页面读取失败：'+error;}
</script></body></html>'''


def main():
    diagnostics = ROOT / "results/diagnostics"
    paths = sorted((p / "native_summary.original.json" for p in diagnostics.iterdir()
                    if p.is_dir() and DIRECTORY.fullmatch(p.name) and (p / "native_summary.original.json").is_file()),
                   key=lambda path: (path.stat().st_mtime_ns, path.parent.name))
    runs = [prepare(path) for path in paths]
    built = datetime.now(timezone.utc).isoformat()
    payload = json.dumps({"built_utc": built, "runs": runs}, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    payload = payload.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    document = HTML.replace("__DATASET__", payload)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "index.html").write_text(document, encoding="utf-8", newline="\n")
    source = Path(__file__)
    manifest = {"built_utc": built, "scope": "COPIED_CLOSED_NATIVE_SUMMARIES_ONLY_NOT_FORMAL_ACCEPTANCE",
                "formal_progress": "0/280_UNCHANGED", "physical_e2e": "NOT_OBSERVED",
                "source": {"path": source.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
                "inputs": [{"path": r["path"], "sha256": r["sha256"], "bytes": r["bytes"], "status": r["status"]} for r in runs],
                "output": {"path": (OUTPUT / "index.html").relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(document.encode()).hexdigest()},
                "checks": [{"run": r["id"], "checks": r["checks"]} for r in runs]}
    (OUTPUT / "build_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8", newline="\n")
    failures = [(r["label"], c["label"]) for r in runs for c in r["checks"] if not c["pass"]]
    print(json.dumps({"output": str(OUTPUT / "index.html"), "runs": len(runs), "checks": sum(len(r["checks"]) for r in runs),
                      "count_mismatches": failures, "source_sha256": manifest["source"]["sha256"],
                      "inputs_read_bytes": sum(r["bytes"] for r in runs), "formal_progress": "0/280_UNCHANGED"}, ensure_ascii=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
