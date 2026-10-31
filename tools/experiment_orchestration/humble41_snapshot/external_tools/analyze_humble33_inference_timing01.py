"""Read only33 timing logs/optional decoded diagnostics; never read a bag.

Writes one exclusive JSON report. Successful execution is analysis completion,
not flight success/readiness. Missing, malformed and ambiguous evidence remains.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import sys

MARKER='INFERENCE_JOB_TIMING '
MAX_INPUT_BYTES=64*1024*1024
MAX_LINE_BYTES=256*1024
SLOW_WALL_S=.5
ANSI=re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
METRICS=('production_work_before_timing_log_wall_s','measured_prefix_thread_cpu_s')
SOURCE_METRICS=('acquisition_to_submit_source_s','acquisition_gap_source_s','submit_gap_source_s',
    'acquisition_to_rgb_callback_source_s','acquisition_to_depth_callback_source_s',
    'submit_to_entry_lock_sample_source_s','entry_to_publication_lock_sample_source_s',
    'acquisition_to_publication_lock_sample_source_s')


def require(condition,message):
    if not condition:raise ValueError(message)


def finite(value):
    if type(value) not in (int,float):return False
    try:return math.isfinite(value)
    except (OverflowError,TypeError):return False


def nonnegative(value):return finite(value) and value>=0


def canonical(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def quantile(values,q):
    if not values:return None
    values=sorted(values);index=(len(values)-1)*q;lower=math.floor(index);upper=math.ceil(index)
    return values[lower]+(values[upper]-values[lower])*(index-lower)


def stats(values,denominator):
    values=[v for v in values if finite(v)]
    return {'denominator':denominator,'known_count':len(values),'unknown_count':denominator-len(values),
        'p50':quantile(values,.5),'p95':quantile(values,.95),'max':max(values) if values else None}


def load_lines(path,suffixes,consumer):
    """Bounded single pass; SHA covers bytes read, with mutation made explicit."""
    path=Path(path)
    require(path.is_file() and not path.is_symlink() and path.suffix.lower() in suffixes,
        'Input must be a named regular log/JSONL file, never a bag or directory')
    before=path.stat()
    require(before.st_size<=MAX_INPUT_BYTES,'Input exceeds64MiB bounded analysis limit')
    digest=hashlib.sha256();consumed=0;line_number=0;issues=[];last_terminated=True
    with path.open('rb') as stream:
        while True:
            raw=stream.readline(MAX_LINE_BYTES+1)
            if not raw:break
            consumed+=len(raw);digest.update(raw);line_number+=1
            require(consumed<=MAX_INPUT_BYTES,'Input grew beyond64MiB while reading')
            too_long=len(raw)>MAX_LINE_BYTES
            if too_long:
                while not raw.endswith(b'\n'):
                    raw=stream.readline(MAX_LINE_BYTES+1)
                    if not raw:break
                    consumed+=len(raw);digest.update(raw)
                    require(consumed<=MAX_INPUT_BYTES,'Input grew beyond64MiB while reading')
                issues.append({'line':line_number,'code':'LINE_TOO_LONG','timing_presence_unknown':True})
                continue
            last_terminated=raw.endswith(b'\n')
            try:text=raw.decode('utf-8')
            except UnicodeDecodeError:
                issues.append({'line':line_number,'code':'INVALID_UTF8','timing_presence_unknown':True});continue
            consumer(line_number,ANSI.sub('',text.rstrip('\r\n')))
    after=path.stat()
    changed=(before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(
        after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)
    if changed:issues.append({'line':None,'code':'INPUT_CHANGED_DURING_READ'})
    if consumed and not last_terminated:issues.append({'line':line_number,'code':'UNTERMINATED_LAST_LINE'})
    return {'path':str(path.resolve()),'initial_bytes':before.st_size,'consumed_bytes':consumed,
        'sha256_of_consumed_bytes':digest.hexdigest(),'input_changed_during_read':changed,
        'lines_read':line_number,'issues':issues}


def decode_json(text):
    def number(token):
        value=float(token);require(math.isfinite(value),'Nonfinite JSON number:'+token);return value
    return json.loads(text,parse_float=number,
        parse_constant=lambda token:(_ for _ in ()).throw(ValueError('Nonfinite JSON:'+token)))


def key(value):
    return tuple(value) if isinstance(value,list) and len(value)==2 and all(type(n) is int and n>=0 for n in value) else None


def profile(row,line):
    issues=[]
    def issue(message):issues.append(message)
    identity=key(row.get('job_key'))
    acquisition,submitted=row.get('acquisition_s'),row.get('submitted_source_s')
    identity_source_s=identity[1]*1e-9 if identity is not None and finite(identity[1]) else None
    source_valid=(nonnegative(identity_source_s) and nonnegative(acquisition) and nonnegative(submitted)
        and abs(acquisition-identity_source_s)<=1e-9 and submitted+1e-9>=acquisition)
    if not source_valid:issue('INVALID_JOB_KEY_OR_SOURCE_PAIR')
    scope=(type(row.get('schema_version')) is int and row['schema_version']==1
        and row.get('scope')=='production_work_before_timing_log'
        and row.get('stage_sum_excludes_inclusive_lock_holds') is True
        and row.get('thread_cpu_scope')=='calling_worker_thread_only_not_all_native_workers')
    if not scope:issue('INVALID_OR_PARTIAL_TIMING_SCOPE')
    outcome=row.get('status')
    if outcome not in ('completed','early_return','exception'):issue('UNKNOWN_JOB_OUTCOME')
    if not isinstance(row.get('reason'),str) or not row['reason']:issue('MISSING_OR_INVALID_OUTCOME_REASON')
    stages=row.get('stages');stages=stages if isinstance(stages,dict) else {}
    totals=[row.get(name) for name in METRICS]
    wall_valid=nonnegative(totals[0]) and nonnegative(row.get('measured_prefix_wall_s'))
    cpu_valid=nonnegative(totals[1])
    if wall_valid and not math.isclose(totals[0],row['measured_prefix_wall_s'],rel_tol=1e-6,abs_tol=1e-6):wall_valid=False
    for dimension,total_index in (('wall_s',0),('thread_cpu_s',1)):
        values=[part.get(dimension) if isinstance(part,dict) else None for part in stages.values()]
        valid=bool(values) and all(nonnegative(v) for v in values) and nonnegative(totals[total_index])
        valid=valid and math.isclose(sum(values),totals[total_index],rel_tol=1e-6,abs_tol=1e-6)
        if dimension=='wall_s':wall_valid=wall_valid and valid
        else:cpu_valid=cpu_valid and valid
    if not wall_valid:issue('INCOMPLETE_OR_INCONSISTENT_EXCLUSIVE_WALL_PARTITION')
    if not cpu_valid:issue('INCOMPLETE_OR_INCONSISTENT_WORKER_THREAD_CPU_PARTITION')
    holds=row.get('input_lock_holds')
    if not isinstance(holds,dict):issue('MISSING_OR_INVALID_INCLUSIVE_LOCK_MAPPING')
    holds=holds if isinstance(holds,dict) else {}
    for name,part in holds.items():
        if (not isinstance(part,dict) or part.get('scope')!='inclusive_not_part_of_stage_sum'
                or not nonnegative(part.get('wall_s')) or not nonnegative(part.get('thread_cpu_s'))):
            issue('INCOMPLETE_INCLUSIVE_LOCK_HOLD:'+name)
    source={name:None for name in SOURCE_METRICS}
    if source_valid:source['acquisition_to_submit_source_s']=max(0.,submitted-acquisition)
    return {'line':line,'job_key':list(identity) if identity else None,'outcome':outcome,'reason':row.get('reason'),
        'original':row,'issues':issues,'duplicate_job_key':False,'identity_and_source_valid':source_valid,
        'scope_valid':scope,'outcome_valid':outcome in ('completed','early_return','exception'),
        'wall_partition_valid':bool(wall_valid),'thread_cpu_partition_valid':bool(cpu_valid),
        'slow_job_wall_ge_0_5s':bool(totals[0]>=SLOW_WALL_S) if scope and wall_valid else None,
        'source_alignment':source,'diagnostic_alignment':{'status':'NOT_PROVIDED'},
        'source_e2e_to_estimator_or_state_s':None,'e2e_status':'UNKNOWN_NO_OBSERVATION_DELIVERY_OR_STATE_EVIDENCE'}


def source_pair(row,diagnostic=False):
    a,s=(row.get('stamp_s'),row.get('submitted_s')) if diagnostic else (row.get('acquisition_s'),row.get('submitted_source_s'))
    return (round(a*1e9),round(s*1e9)) if nonnegative(a) and nonnegative(s) and finite(a*1e9) and finite(s*1e9) else None


def align_diagnostics(jobs,diagnostics):
    """Global one-to-one matching; diagnostics carry no clock epoch."""
    job_map=defaultdict(list);diagnostic_map=defaultdict(list)
    for job in jobs:
        pair=source_pair(job['original'])
        if pair is not None:job_map[pair].append(job)
    for row in diagnostics:
        pair=source_pair(row['original'],True)
        if pair is not None:diagnostic_map[pair].append(row)
    for pair,entries in job_map.items():
        matches=diagnostic_map.get(pair,[])
        for job in entries:
            if not matches:
                job['diagnostic_alignment']={'status':'MISSING_DIAGNOSTIC'};continue
            if len(entries)!=1 or len(matches)!=1 or job['duplicate_job_key'] or not job['identity_and_source_valid']:
                job['diagnostic_alignment']={'status':'AMBIGUOUS_SOURCE_PAIR','candidate_lines':[r['line'] for r in matches]};continue
            decoded=matches[0]['original'];problems=[]
            metrics=job['source_alignment']
            acquire=job['original']['acquisition_s'];submitted=job['original']['submitted_source_s']
            worker,publication=decoded.get('worker_started_s'),decoded.get('completed_s')
            pairs=(('acquisition_to_rgb_callback_source_s',acquire,decoded.get('rgb_received_s')),
                ('acquisition_to_depth_callback_source_s',acquire,decoded.get('depth_received_s')),
                ('submit_to_entry_lock_sample_source_s',submitted,worker),
                ('entry_to_publication_lock_sample_source_s',worker,publication),
                ('acquisition_to_publication_lock_sample_source_s',acquire,publication))
            for name,start,end in pairs:
                if not nonnegative(start) or not nonnegative(end):problems.append('MISSING:'+name)
                elif end+1e-9<start:problems.append('SOURCE_ORDER_INVALID:'+name)
                else:metrics[name]=max(0.,end-start)
            job['diagnostic_alignment']={'status':'MATCHED' if not problems else 'MATCHED_INCOMPLETE',
                'line':matches[0]['line'],'issues':problems,'original':decoded,
                'publication_lock_sample_source_s':publication if nonnegative(publication) else None,
                'submit_snapshot_to_before_decode_wall_s':decoded.get('worker_wait_wall_s') if nonnegative(decoded.get('worker_wait_wall_s')) else None,
                'decode_to_diagnostic_dictionary_wall_s':decoded.get('inference_wall_s') if nonnegative(decoded.get('inference_wall_s')) else None,
                'completed_s_is_final_publication':False}
            matches[0]['matched_job_key']=job['job_key']
    for row in diagnostics:
        pair=source_pair(row['original'],True)
        if pair is None:row['alignment_status']='INVALID_SOURCE_PAIR'
        elif len(diagnostic_map[pair])>1 or len(job_map.get(pair,[]))>1:row['alignment_status']='AMBIGUOUS_SOURCE_PAIR'
        elif not job_map.get(pair):row['alignment_status']='UNMATCHED'
        elif row.get('matched_job_key') is not None:row['alignment_status']='MATCHED'
        else:row['alignment_status']='NOT_MATCHED_INVALID_JOB'


def summarize(jobs,denominator):
    eligible=lambda j:bool(j['job_key']) and not j['duplicate_job_key'] and j['scope_valid'] and j['outcome_valid']
    result={'denominator':denominator,
        'production_work_before_timing_log_wall_s':stats([
            j['original'].get(METRICS[0]) for j in jobs if eligible(j) and j['wall_partition_valid']],denominator),
        'measured_worker_thread_cpu_s':stats([
            j['original'].get(METRICS[1]) for j in jobs if eligible(j) and j['thread_cpu_partition_valid']],denominator),
        'stages':{},'inclusive_input_lock_holds':{},'timer_lock_wall_s':{},'source_time':{}}
    def mapping(job,name):
        value=job['original'].get(name)
        return value if isinstance(value,dict) else {}
    stage_names=sorted({name for j in jobs for name in mapping(j,'stages')})
    lock_names=sorted({name for j in jobs for name in mapping(j,'input_lock_holds')})
    for output,names,field in ((result['stages'],stage_names,'stages'),
            (result['inclusive_input_lock_holds'],lock_names,'input_lock_holds')):
        for name in names:
            output[name]={}
            for dimension,validity in (('wall_s','wall_partition_valid'),('thread_cpu_s','thread_cpu_partition_valid')):
                values=[]
                for job in jobs:
                    mapping=job['original'].get(field);mapping=mapping if isinstance(mapping,dict) else {}
                    part=mapping.get(name);part=part if isinstance(part,dict) else {}
                    if eligible(job) and job[validity] and nonnegative(part.get(dimension)):
                        if field!='input_lock_holds' or part.get('scope')=='inclusive_not_part_of_stage_sum':values.append(part[dimension])
                output[name][dimension]=stats(values,denominator)
    for name in ('timer_input_lock_wait_wall_s','timer_input_lock_snapshot_hold_wall_s'):
        result['timer_lock_wall_s'][name]=stats([j['original'].get(name) for j in jobs
            if eligible(j) and nonnegative(j['original'].get(name))],denominator)
    for name in SOURCE_METRICS:
        result['source_time'][name]=stats([j['source_alignment'][name] for j in jobs
            if eligible(j) and j['identity_and_source_valid']],denominator)
    return result


def analyze(log,diagnostics_jsonl=None):
    jobs=[];issues=[];marker_count=0
    def log_line(number,text):
        nonlocal marker_count
        if MARKER not in text:return
        marker_count+=1
        try:
            row=decode_json(text.split(MARKER,1)[1]);require(isinstance(row,dict),'Timing payload must be an object')
            jobs.append(profile(row,number))
        except (ValueError,TypeError,KeyError,OverflowError) as e:
            issues.append({'line':number,'code':'UNDECODABLE_TIMING_RECORD','reason':str(e),'payload_prefix':text[:2048]})
    log_binding=load_lines(log,{'.log','.txt'},log_line)
    grouped=defaultdict(list)
    for job in jobs:
        identity=key(job['job_key'])
        if identity is not None:grouped[identity].append(job)
    for same in grouped.values():
        if len(same)>1:
            for job in same:job['duplicate_job_key']=True;job['issues'].append('DUPLICATE_JOB_KEY_RETAINED_NOT_DEDUPLICATED')
    previous={}
    for job in jobs:
        if not job['identity_and_source_valid'] or job['duplicate_job_key']:continue
        epoch=job['job_key'][0];row=job['original'];prior=previous.get(epoch)
        if prior:
            a=row['acquisition_s']-prior['acquisition_s'];s=row['submitted_source_s']-prior['submitted_source_s']
            if a<=0 or s<0:job['issues'].append('SOURCE_ORDER_REGRESSION_WITHIN_EPOCH')
            else:job['source_alignment'].update(acquisition_gap_source_s=a,submit_gap_source_s=s)
        previous[epoch]=row
    diagnostics=[];diagnostic_binding=None
    if diagnostics_jsonl is not None:
        def diagnostic_line(number,text):
            if not text.strip():return
            try:
                value=decode_json(text);require(isinstance(value,dict),'Decoded diagnostic must be a flat object')
                diagnostics.append({'line':number,'original':value})
            except (ValueError,TypeError) as e:issues.append({'source':'diagnostics','line':number,'code':'UNDECODABLE_DIAGNOSTIC','reason':str(e)})
        diagnostic_binding=load_lines(diagnostics_jsonl,{'.jsonl'},diagnostic_line)
        align_diagnostics(jobs,diagnostics)
    completed=[j for j in jobs if j['outcome']=='completed']
    slow=[j for j in jobs if j['slow_job_wall_ge_0_5s'] is True]
    incomplete=bool(issues or log_binding['issues'] or any(j['issues'] for j in jobs)
        or diagnostic_binding and diagnostic_binding['issues'])
    status=('INCOMPLETE_TIMING_EVIDENCE' if incomplete else
        'NO_TIMING_SAMPLES' if marker_count==0 else 'LOG_TIMING_ANALYZED_E2E_UNAVAILABLE')
    return {'schema_version':1,'scope':'READ_ONLY_HUMBLE33_LOG_TIMING_NOT_RUNTIME_OR_CAUSAL_ACCEPTANCE',
        'status':status,'inputs':{'ros_log':log_binding,'decoded_diagnostics_jsonl':diagnostic_binding},
        'counts':{'timing_marker_lines':marker_count,'decoded_timing_records':len(jobs),
            'undecodable_timing_records':marker_count-len(jobs),'distinct_job_keys':len(grouped),
            'duplicate_job_key_records':sum(j['duplicate_job_key'] for j in jobs),
            'outcomes':dict(Counter(str(j['outcome']) for j in jobs)),
            'slow_job_records_wall_ge_0_5s':len(slow),'diagnostic_rows':len(diagnostics)},
        'quantile_definition':'Linear interpolation at index (known_count-1)*q; unknown entries stay in denominator',
        'all_observed_timing_records':summarize(jobs,marker_count),
        'completed_outcome_records':summarize(completed,len(completed)),
        'other_outcome_records':{name:summarize([j for j in jobs if j['outcome']==name],
            sum(j['outcome']==name for j in jobs)) for name in ('early_return','exception')},
        'diagnostic_alignment_counts':dict(Counter(j['diagnostic_alignment']['status'] for j in jobs)),
        'slow_threshold_wall_s':SLOW_WALL_S,'slow_jobs':[{'line':j['line'],'job_key':j['job_key'],
            'outcome':j['outcome'],'wall_s':j['original'].get(METRICS[0]),'issues':j['issues'],
            'duplicate_job_key':j['duplicate_job_key'],'source_alignment':j['source_alignment'],
            'stages':j['original'].get('stages')} for j in slow],
        'jobs':jobs,'diagnostics':diagnostics,'parse_issues':issues,
        'limits':{'inclusive_lock_holds_added_to_exclusive_total':False,
            'timer_lock_holds_part_of_worker_exclusive_partition':False,
            'timer_snapshot_hold_is_prefix_before_submit_and_release':True,
            'acquisition_source_time_is_rgb_for_all_callback_differences':True,
            'worker_thread_cpu_includes_all_native_workers':False,
            'cpu_le_wall_asserted':False,'own_timing_log_serialization_write_in_total':False,
            'worker_busy_release_in_total':False,'wall_time_converted_to_source_time':False,
            'log_prefix_used_as_source_or_delivery_time':False,'completed_s_is_final_publication':False,
            'source_e2e_to_estimator_or_state_status':'UNKNOWN_REQUIRES_SEPARATE_DELIVERY_STATE_EVIDENCE',
            'all_submitted_jobs_denominator':None,'submitted_job_logging_coverage':None,
            'source_gap_scope':'Between consecutive identifiable nonduplicate logged jobs within one epoch; not sensor frame spacing or coverage of all accepted jobs',
            'optional_diagnostics_complete_coverage_claimed':False,
            'missing_stage_assumed_zero':False,'bag_payload_reads':False,
            'runtime_success_claimed':False,'bottleneck_causality_claimed':False,'readiness_claimed':False}}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log',type=Path,required=True)
    parser.add_argument('--diagnostics-jsonl',type=Path,help='Optional already-decoded original diagnostic data, one flat JSON object per line; never a bag')
    parser.add_argument('--output',type=Path,required=True,help='New exclusive JSON file in an existing output directory')
    args=parser.parse_args(argv)
    try:
        output=args.output
        require(output.suffix=='.json' and output.parent.is_dir() and not output.exists()
            and not output.is_symlink(),'Output must be a new JSON file in an existing directory; no overwrite')
        report=analyze(args.log,args.diagnostics_jsonl)
        require(output.resolve() not in {args.log.resolve(),args.diagnostics_jsonl.resolve() if args.diagnostics_jsonl else None},
            'Output cannot replace input')
        with output.open('x',encoding='utf-8') as stream:
            json.dump(report,stream,indent=2,allow_nan=False);stream.write('\n')
        print(json.dumps({'output':str(output),'status':report['status'],'counts':report['counts'],
            'runtime_success_claimed':False}));return 0
    except (OSError,ValueError,TypeError,KeyError) as e:
        print(json.dumps({'status':'ANALYSIS_REFUSED','reason':str(e),'runtime_success_claimed':False}),file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
