"""Five narrow synthetic fixtures for model-free paired regression sidecar."""
from copy import deepcopy
import hashlib,importlib.util,json,sys
import unittest
from pathlib import Path
B=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('audit_fixture',B/'scripts/audit_car_model_regressions.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def dataset(old_fp,new_fp,unknown_new=(),shrink_new=False):
 frames=[];models=[];outcomes=[]
 for i in range(len(old_fp)):
  frames.append(dict(frame_index=i,image='fixture'+str(i)+'.png',source_group='synthetic',split='fixture',source_view_id='fixture'+str(i),png_sha256='fixture-png',label_sha256='fixture-label',gt_objects=[dict(bbox_xyxy=[0.,0.,10.,10.])]))
 for mid,counts in [(m.BASELINE,old_fp),(m.CANDIDATE,new_fp)]:
  rows=[]
  for i,count in enumerate(counts):
   frame=frames[i];meta={k:frame[k] for k in m.META}
   if mid==m.CANDIDATE and i in unknown_new:
    rows.append(dict(**meta,gt_count=1,prediction_status='UNKNOWN_ERROR',status='UNSCORED_PREDICTION_UNKNOWN',tp=None,fp=None,fn=None,matches=[],gt_details=[],error='fixture prediction failed'))
    outcomes.append(dict(candidate_id=mid,**meta,raw_png_sha256=frame['png_sha256'],label_sha256=frame['label_sha256'],prediction_status='UNKNOWN_ERROR',error='fixture prediction failed',all_model_returned_boxes=None,car_candidates_at_045=None));continue
   box=[0.,0.,7.,10.] if mid==m.CANDIDATE and shrink_new else [0.,0.,10.,10.]
   cars=[dict(class_id=2,class_name='car',confidence=.95,bbox_xyxy=box)]+[dict(class_id=2,class_name='car',confidence=.52,bbox_xyxy=[20.+j*20,0.,30.+j*20,10.]) for j in range(count)]
   geom=m.geometry(box,frame['gt_objects'][0]['bbox_xyxy'])
   rows.append(dict(**meta,gt_count=1,prediction_status='RECORDED',status='SCORED',tp=1,fp=count,fn=0,matches=[dict(pred_index=0,gt_index=0,iou=geom['iou'])],unmatched_pred_indices=list(range(1,len(cars))),gt_details=[dict(gt_index=0,bbox_xyxy=frame['gt_objects'][0]['bbox_xyxy'],matched=True,matched_prediction=dict(pred_index=0,confidence=.95,bbox_xyxy=box,**geom),passed_iou_but_low_gt_coverage=geom['gt_coverage']<.8)]))
   outcomes.append(dict(candidate_id=mid,**meta,raw_png_sha256=frame['png_sha256'],label_sha256=frame['label_sha256'],prediction_status='RECORDED',error=None,all_model_returned_boxes=cars,car_candidates_at_045=cars,car_count_at_045=len(cars)))
  good=[r for r in rows if r['status']=='SCORED'];models.append(dict(candidate_id=mid,frames=rows,original_opportunities=len(frames),unknown_prediction_opportunities=len(rows)-len(good),**{k:sum(r[k] for r in good) for k in ('tp','fp','fn')}))
 return frames,models,outcomes

def test_new_fp_retained_with_correct_original_tp():
 r=m.audit_pairs(*dataset([0],[1]));p=r['pairs'][0]
 assert p['delta_candidate_minus_original']['fp']==1 and p['delta_candidate_minus_original']['fn']==0
 assert 'ORIGINAL_TP_RETAINED_CANDIDATE_HAS_ADDITIONAL_FP' in p['flags']
 assert p['candidate']['unmatched_predictions'][0]['confidence']==.52


def test_total_fp_lower_still_reports_local_fp_increase():
 r=m.audit_pairs(*dataset([0,3],[1,0]));s=r['summary']
 assert s['aggregate_metrics'][m.CANDIDATE]['fp']<s['aggregate_metrics'][m.BASELINE]['fp']
 assert s['local_fp_increase_pairs']==1 and s['gross_fp_increase']==1 and s['gross_fp_decrease']==3 and len(r['local_regressions'])==1


def test_unknown_pair_null_counts_and_full_denominator_retained():
 r=m.audit_pairs(*dataset([0,0],[0,0],unknown_new={1}));p=r['pairs'][1]
 assert r['summary']['total_pairs']==2 and r['summary']['unknown_pairs']==1 and p['delta_candidate_minus_original'] is None and p['candidate']['fp'] is None and p['candidate']['unscored_gt_boxes']==1


def test_missing_metric_pair_rejected():
 frames,models,outcomes=dataset([0,0],[0,0]);models[1]['frames'].pop()
 try:m.audit_pairs(frames,models,outcomes)
 except ValueError:pass
 else:raise AssertionError('Missing pair accepted')


def test_new_coverage_flag_kept_separate_from_fn_criterion():
 r=m.audit_pairs(*dataset([0],[0],shrink_new=True))
 assert r['summary']['new_low_gt_coverage_flags']==1 and r['summary']['local_fn_increase_pairs']==0
 assert 'CANDIDATE_NEW_LOW_GT_COVERAGE_DIAGNOSTIC' in r['pairs'][0]['flags']


def load_tests(loader, tests, pattern):
 """Include the preserved fixtures in the project's unittest discovery run."""
 return unittest.TestSuite(unittest.FunctionTestCase(test) for test in (
  test_new_fp_retained_with_correct_original_tp,
  test_total_fp_lower_still_reports_local_fp_increase,
  test_unknown_pair_null_counts_and_full_denominator_retained,
  test_missing_metric_pair_rejected,
  test_new_coverage_flag_kept_separate_from_fn_criterion,
 ))
