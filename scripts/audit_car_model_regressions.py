"""Independent model-free pairwise FP/FN/unknown/coverage audit for236or24.

Reads bound existing metrics,frozen inputs and raw model outcomes only. Never
loads a model, changes inference/scoring outputs,or decides model admission.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime,timezone
import hashlib,json,math
from pathlib import Path

BASELINE='original_m960'
CANDIDATE='train20_04_best_m960'
META=('frame_index','image','source_group','split','source_view_id')


def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def exact(path,digest):
 if not isinstance(digest,str) or len(digest)!=64 or sha(path)!=digest:raise ValueError('Bound input changed: '+str(path))
def write(path,value):
 with Path(path).open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,ensure_ascii=True,allow_nan=False);f.write('\n')
def geometry(box,gt):
 intersection=max(0.,min(box[2],gt[2])-max(box[0],gt[0]))*max(0.,min(box[3],gt[3])-max(box[1],gt[1]))
 a=(box[2]-box[0])*(box[3]-box[1]);b=(gt[2]-gt[0])*(gt[3]-gt[1])
 return dict(iou=intersection/(a+b-intersection),gt_coverage=intersection/b,prediction_to_gt_area_ratio=a/b)
def indexed(rows,key):
 if not isinstance(rows,list):raise ValueError('Full ordered rows list required')
 result={key(r):r for r in rows}
 if len(result)!=len(rows):raise ValueError('Duplicate source/model-image key')
 return result


def model_frame(frame,detail,outcome):
 if any(detail[k]!=frame[k] for k in META) or detail['gt_count']!=len(frame['gt_objects']):raise ValueError('Metric frame/GT provenance differs')
 if any(outcome[k]!=frame[k] for k in ('frame_index','image','source_group','split','source_view_id')):raise ValueError('Raw model outcome provenance differs')
 if outcome['raw_png_sha256']!=frame['png_sha256'] or outcome['label_sha256']!=frame['label_sha256'] or detail['prediction_status']!=outcome['prediction_status']:raise ValueError('Raw prediction hash/status differs')
 if detail['status']!='SCORED':
  if outcome['prediction_status']=='RECORDED' or not outcome.get('error') or any(detail[k] is not None for k in ('tp','fp','fn')):raise ValueError('Unknown must retain explicit error and null counts')
  return dict(status=detail['status'],prediction_status=outcome['prediction_status'],error=outcome['error'],tp=None,fp=None,fn=None,
              unscored_gt_boxes=len(frame['gt_objects']),matched_gt_indices=[],unmatched_predictions=None,gt_details=[])
 if outcome['prediction_status']!='RECORDED' or outcome.get('error') is not None:raise ValueError('Scored frame requires recorded prediction')
 boxes=outcome['all_model_returned_boxes']
 cars=[p for p in boxes if p['class_id']==2 and p['confidence']>=.45]
 if cars!=outcome['car_candidates_at_045'] or len(cars)!=outcome['car_count_at_045']:raise ValueError('Fixed raw car.45 filter differs')
 for k in ('tp','fp','fn'):
  if type(detail[k]) is not int or detail[k]<0:raise ValueError('Scored counts must be nonnegative integers')
 matches=detail['matches'];unmatched=detail['unmatched_pred_indices']
 pi=[m['pred_index'] for m in matches];gi=[m['gt_index'] for m in matches]
 if (detail['tp']!=len(matches) or detail['fp']!=len(unmatched) or detail['tp']+detail['fn']!=len(frame['gt_objects']) or
     len(set(pi))!=len(pi) or len(set(gi))!=len(gi) or len(set(unmatched))!=len(unmatched) or set(pi)&set(unmatched) or
     set(pi)|set(unmatched)!=set(range(len(cars))) or any(not 0<=i<len(frame['gt_objects']) for i in gi)):raise ValueError('Complete one-to-one TP/FP/FN accounting differs')
 gt_details=indexed(detail['gt_details'],lambda r:r['gt_index'])
 if set(gt_details)!=set(range(len(frame['gt_objects']))):raise ValueError('Every GT detail required')
 for i,obj in enumerate(frame['gt_objects']):
  item=gt_details[i]
  if item['bbox_xyxy']!=obj['bbox_xyxy'] or item['matched']!=(i in gi):raise ValueError('Per-GT matched/box evidence differs')
  pred=item['matched_prediction']
  if pred is not None:
   if pred['pred_index'] not in pi or cars[pred['pred_index']]['bbox_xyxy']!=pred['bbox_xyxy'] or cars[pred['pred_index']]['confidence']!=pred['confidence']:raise ValueError('Matched raw prediction differs')
   if item['passed_iou_but_low_gt_coverage']!=(pred['gt_coverage']<.8):raise ValueError('Existing coverage diagnostic differs')
  elif item['matched'] or item['passed_iou_but_low_gt_coverage']:raise ValueError('Missing accepted prediction evidence')
 fps=[dict(car_candidate_index=i,**cars[i],per_gt_overlap=[dict(gt_index=g,**geometry(cars[i]['bbox_xyxy'],obj['bbox_xyxy'])) for g,obj in enumerate(frame['gt_objects'])]) for i in unmatched]
 return dict(status='SCORED',prediction_status='RECORDED',error=None,tp=detail['tp'],fp=detail['fp'],fn=detail['fn'],
             unscored_gt_boxes=0,matched_gt_indices=sorted(gi),unmatched_predictions=fps,gt_details=detail['gt_details'])


def audit_pairs(frames,results,outcomes):
 source=indexed(frames,lambda r:r['frame_index']);n=len(frames)
 if set(source)!=set(range(n)):raise ValueError('Full frozen frame index range required')
 models=indexed(results,lambda r:r['candidate_id'])
 if set(models)!={BASELINE,CANDIDATE}:raise ValueError('Exactly original and frozen train20_04 candidate required')
 raw=indexed(outcomes,lambda r:(r['candidate_id'],r['frame_index']))
 if set(raw)!={(model,i) for model in (BASELINE,CANDIDATE) for i in range(n)}:raise ValueError('Every paired raw model-image outcome required')
 details={}
 for model in (BASELINE,CANDIDATE):
  detail=indexed(models[model]['frames'],lambda r:r['frame_index'])
  if set(detail)!=set(source) or models[model]['original_opportunities']!=n:raise ValueError('Missing/repeated per-model metric pair')
  details[model]=detail
  good=[r for r in detail.values() if r['status']=='SCORED']
  if models[model]['unknown_prediction_opportunities']!=n-len(good) or any(models[model][k]!=sum(r[k] for r in good) for k in ('tp','fp','fn')):raise ValueError('Aggregate metrics disagree with complete frame inventory')
 pairs=[]
 for i in range(n):
  frame=source[i];old=model_frame(frame,details[BASELINE][i],raw[BASELINE,i]);new=model_frame(frame,details[CANDIDATE][i],raw[CANDIDATE,i]);flags=[]
  entry=dict(**{k:frame[k] for k in META},gt_count=len(frame['gt_objects']),original=old,candidate=new,
             pair_status='SCORED' if old['status']==new['status']=='SCORED' else 'UNKNOWN',
             delta_candidate_minus_original=None,gt_changes=[])
  if entry['pair_status']=='UNKNOWN':flags.append('UNKNOWN_PREDICTION_PAIR_RETAINED')
  else:
   delta={k:new[k]-old[k] for k in ('tp','fp','fn')};entry['delta_candidate_minus_original']=delta
   for key in ('fp','fn'):
    if delta[key]>0:flags.append('CANDIDATE_'+key.upper()+'_INCREASE')
    elif delta[key]<0:flags.append('CANDIDATE_'+key.upper()+'_DECREASE')
   if delta['fp']>0 and old['tp']>0 and set(old['matched_gt_indices'])<=set(new['matched_gt_indices']):flags.append('ORIGINAL_TP_RETAINED_CANDIDATE_HAS_ADDITIONAL_FP')
   for before,after in zip(old['gt_details'],new['gt_details']):
    if before['gt_index']!=after['gt_index']:raise ValueError('GT ordering differs between model pairs')
    old_shrink=before['passed_iou_but_low_gt_coverage'];new_shrink=after['passed_iou_but_low_gt_coverage']
    changes=dict(gt_index=before['gt_index'],original_matched=before['matched'],candidate_matched=after['matched'],
                 fn_introduced=before['matched'] and not after['matched'],fn_removed=not before['matched'] and after['matched'],
                 original_low_gt_coverage=old_shrink,candidate_low_gt_coverage=new_shrink,
                 shrink_flag_introduced=not old_shrink and new_shrink,shrink_flag_removed=old_shrink and not new_shrink)
    entry['gt_changes'].append(changes)
   if any(r['shrink_flag_introduced'] for r in entry['gt_changes']):flags.append('CANDIDATE_NEW_LOW_GT_COVERAGE_DIAGNOSTIC')
   if any(r['shrink_flag_removed'] for r in entry['gt_changes']):flags.append('CANDIDATE_REMOVED_LOW_GT_COVERAGE_DIAGNOSTIC')
  entry['flags']=flags;pairs.append(entry)
 complete=[r for r in pairs if r['pair_status']=='SCORED'];unknown=[r for r in pairs if r['pair_status']=='UNKNOWN']
 summary=dict(total_pairs=n,complete_pairs=len(complete),unknown_pairs=len(unknown),total_model_image_opportunities=2*n,
  aggregate_metrics={m:{k:models[m][k] for k in ('tp','fp','fn','unknown_prediction_opportunities')} for m in (BASELINE,CANDIDATE)},
  paired_delta_candidate_minus_original={k:sum(r['delta_candidate_minus_original'][k] for r in complete) for k in ('tp','fp','fn')},
  local_fp_increase_pairs=sum(r['delta_candidate_minus_original']['fp']>0 for r in complete),
  local_fp_decrease_pairs=sum(r['delta_candidate_minus_original']['fp']<0 for r in complete),
  local_fn_increase_pairs=sum(r['delta_candidate_minus_original']['fn']>0 for r in complete),
  local_fn_decrease_pairs=sum(r['delta_candidate_minus_original']['fn']<0 for r in complete),
  gross_fp_increase=sum(max(0,r['delta_candidate_minus_original']['fp']) for r in complete),
  gross_fp_decrease=sum(max(0,-r['delta_candidate_minus_original']['fp']) for r in complete),
  original_tp_retained_candidate_additional_fp_pairs=sum('ORIGINAL_TP_RETAINED_CANDIDATE_HAS_ADDITIONAL_FP' in r['flags'] for r in pairs),
  new_low_gt_coverage_flags=sum(g['shrink_flag_introduced'] for r in complete for g in r['gt_changes']),
  removed_low_gt_coverage_flags=sum(g['shrink_flag_removed'] for r in complete for g in r['gt_changes']))
 regressions=[r for r in pairs if any(flag in r['flags'] for flag in ('CANDIDATE_FP_INCREASE','CANDIDATE_FN_INCREASE','CANDIDATE_NEW_LOW_GT_COVERAGE_DIAGNOSTIC'))]
 return dict(summary=summary,pairs=pairs,local_regressions=regressions,unknown_pairs=unknown)


def audit(args):
 root=args.comparison_dir.resolve();output=args.output_dir.resolve()
 if output.exists():raise FileExistsError('Exclusive new sidecar output only; no overwrite/retry')
 metrics_path=root/'operating_point_metrics01.json';receipt_path=root/'frozen_inputs01.json'
 exact(metrics_path,args.metrics_sha256);exact(receipt_path,args.receipt_sha256)
 metrics=read(metrics_path);receipt=read(receipt_path);n=len(receipt['frames'])
 if n not in (24,236) or metrics['receipt_sha256']!=args.receipt_sha256 or metrics['driver_sha256']!=receipt['driver_sha256'] or metrics['image_opportunities_per_model']!=n or metrics['total_model_image_opportunities']!=2*n:raise ValueError('Actual236/24 metrics and frozen receipt binding required')
 if metrics['thresholds']!={'car_confidence':.45,'matching_iou':.5,'diagnostic_gt_coverage':.8}:raise ValueError('Original confidence/IoU/coverage policy required')
 terminal_path=root/'predictions01/terminal.json';outcomes_path=root/('predictions01/all'+str(2*n)+'_outcomes.jsonl')
 exact(terminal_path,metrics['input_inference_terminal_sha256']);terminal=read(terminal_path)
 if terminal['receipt_sha256']!=args.receipt_sha256 or terminal['driver_sha256']!=metrics['driver_sha256'] or terminal['total_opportunities']!=2*n or terminal['all_outcomes_sha256']!=metrics['all_outcomes_sha256']:raise ValueError('Original raw prediction terminal binding differs')
 exact(outcomes_path,metrics['all_outcomes_sha256']);outcomes=[json.loads(line) for line in outcomes_path.read_text().splitlines()]
 result=audit_pairs(receipt['frames'],metrics['results'],outcomes)
 output.mkdir()
 for name,values in [('all_pairs.jsonl',result['pairs'])]:
  with (output/name).open('x',encoding='utf-8') as f:
   for value in values:f.write(json.dumps(value,allow_nan=False)+'\n')
 write(output/'local_regressions.json',result['local_regressions']);write(output/'unknown_pairs.json',result['unknown_pairs'])
 fields=['frame_index','source_group','source_view_id','image','pair_status','gt_count','original_tp','original_fp','original_fn','candidate_tp','candidate_fp','candidate_fn','delta_fp','delta_fn','flags','candidate_fp_confidences']
 with (output/'all_pairs.csv').open('x',encoding='utf-8-sig',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
  for pair in result['pairs']:
   delta=pair['delta_candidate_minus_original'];row={k:pair[k] for k in ('frame_index','source_group','source_view_id','image','pair_status','gt_count')}
   row.update({m+'_'+k:pair[m][k] for m in ('original','candidate') for k in ('tp','fp','fn')});row.update(delta_fp=delta['fp'] if delta else None,delta_fn=delta['fn'] if delta else None,flags=';'.join(pair['flags']),candidate_fp_confidences=json.dumps([p['confidence'] for p in pair['candidate']['unmatched_predictions']] if pair['candidate']['unmatched_predictions'] is not None else None));writer.writerow(row)
 write(output/'summary.json',dict(utc=datetime.now(timezone.utc).isoformat(),status='COMPLETE_PAIRED_AUDIT_WITH_UNKNOWN_PAIRS' if result['unknown_pairs'] else 'COMPLETE_PAIRED_REGRESSION_AUDIT',
  audit_source_sha256=sha(__file__),comparison_dir=str(root),input_sha256={str(p):sha(p) for p in (metrics_path,receipt_path,terminal_path,outcomes_path)},
  **result['summary'],artifacts={name:sha(output/name) for name in ('all_pairs.jsonl','all_pairs.csv','local_regressions.json','unknown_pairs.json')},
  notes=['Aggregate FP improvement does not imply no local FP regression.','Old paired_differences FN/coverage list is not a complete FP-regression audit.','Full original denominators and unknown pairs retained; unknown counts are null.','Diagnostic coverage threshold unchanged; no model admission or fresh-view gate decision.'],
  models_loaded=False,inference_rerun=False,original_outputs_modified=False,model_admission_decision=False,formal_seeds_used=[],runtime_weights_changed=False))
 print(json.dumps(dict(output=str(output),summary_sha256=sha(output/'summary.json'),**result['summary'])))

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--comparison-dir',type=Path,required=True);p.add_argument('--metrics-sha256',required=True);p.add_argument('--receipt-sha256',required=True);p.add_argument('--output-dir',type=Path,required=True);audit(p.parse_args())
if __name__=='__main__':main()
