"""Prove recording stream quiescence and final correspondence after world pause.

The independent evaluator still checks every recorded sample. This observer
only coordinates closing the recorder after producers and the adapter drain.
"""
from __future__ import annotations

import math
from pathlib import Path
import xml.etree.ElementTree as ET


def declared_truth_frames(world_path):
    """Read logging frame declarations, never online target association input."""
    world=ET.parse(Path(world_path)).getroot().find('world')
    if world is None:raise ValueError('missing runtime world')
    found={'target':[],'vehicle':[]}
    for model in world.findall('model'):
        for plugin in model.findall('plugin'):
            topic=plugin.findtext('topic','')
            if plugin.get('name')=='gz::sim::systems::PosePublisher':
                if topic=='/ground_truth/poses':found['target'].append(model.get('name'))
                elif topic=='/ground_truth/vehicle_poses':found['vehicle'].append(model.get('name'))
    for include in world.findall('include'):
        uri=include.findtext('uri','')
        name=include.findtext('name','')
        if uri in {'model://target_person','model://target_car'}:found['target'].append(name)
        elif uri in {'model://x500_stage1','model://x500_stage3'}:found['vehicle'].append(name)
    if not found['target'] or len(found['vehicle'])!=1 or any(not n for names in found.values() for n in names):
        raise ValueError('runtime world lacks explicit unique evaluation frame declarations')
    for names in found.values():
        if len(names)!=len(set(names)):raise ValueError('duplicate evaluation frame declaration')
    return found


def seconds_to_integer(value, scale):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('invalid source seconds')
    scaled=value*scale
    rounded=round(scaled)
    if abs(scaled-rounded)>.25:
        raise ValueError('source seconds do not represent an integer timestamp')
    return rounded


class StreamDrainState:
    """Require observed final correspondence and actual quiescence after ACK."""
    def __init__(self, quiet_wall_s=.5, expected_truth_frames=None):
        if not math.isfinite(quiet_wall_s) or quiet_wall_s<=0:raise ValueError('invalid quiet wall budget')
        self.quiet_wall_s=quiet_wall_s
        self.pause_ack_wall_s=None
        self.clock_ns=None
        self.last_raw=None
        self.diagnostics={}
        self.last_diagnostic_key=None
        self.odometry_headers=set()
        self.counts=dict(clock=0,raw=0,timing=0,adapted=0)
        self.last_change=dict(clock=None,raw=None,timing=None,adapted=None)
        self.errors=[]
        self.expected_truth_frames={key:tuple(value) for key,value in (expected_truth_frames or {}).items()}
        self.truth_stamps={key:{name:set() for name in names} for key,names in self.expected_truth_frames.items()}
        for key in self.expected_truth_frames:
            self.counts['truth_'+key]=0
            self.last_change['truth_'+key]=None

    def truth(self, kind, transforms, wall_s):
        """Observe declared logging headers only; no pose or ID feeds control."""
        if kind not in self.expected_truth_frames:return
        self.counts['truth_'+kind]+=1
        self.last_change['truth_'+kind]=wall_s
        for frame,stamp_ns in transforms:
            canonical=frame.strip('/')
            matches=[name for name in self.expected_truth_frames[kind]
                     if canonical==name or canonical.endswith('::'+name) or canonical.rsplit('/',1)[-1]==name]
            if len(matches)>1:
                self.errors.append('ambiguous_declared_truth_frame')
            elif matches:
                stamps=self.truth_stamps[kind][matches[0]]
                stamps.add(stamp_ns)
                if len(stamps)>256:stamps.remove(min(stamps))

    def clock(self, source_ns, wall_s):
        self.counts['clock']+=1
        if source_ns!=self.clock_ns:
            self.clock_ns=source_ns
            self.last_change['clock']=wall_s

    def raw(self, sample_us, publication_us, wall_s):
        self.counts['raw']+=1
        self.last_change['raw']=wall_s
        self.last_raw=(sample_us,publication_us)

    def timing(self, diagnostic, wall_s):
        self.counts['timing']+=1
        self.last_change['timing']=wall_s
        try:
            key=tuple(seconds_to_integer(diagnostic.get(field),1_000_000)
                for field in ('source_sample_s','source_publication_s'))
            if not isinstance(diagnostic.get('accepted'),bool):raise ValueError('missing accepted flag')
            if diagnostic['accepted']:
                seconds_to_integer(diagnostic.get('odometry_header_s'),1_000_000_000)
            self.diagnostics[key]=dict(diagnostic)
            self.last_diagnostic_key=key
            while len(self.diagnostics)>256:del self.diagnostics[next(iter(self.diagnostics))]
        except ValueError as error:
            self.errors.append(str(error))

    def adapted(self, header_ns, wall_s):
        self.counts['adapted']+=1
        self.last_change['adapted']=wall_s
        self.odometry_headers.add(header_ns)
        if len(self.odometry_headers)>256:self.odometry_headers.remove(min(self.odometry_headers))

    def pause_ack(self, wall_s):
        self.pause_ack_wall_s=wall_s

    def assess(self, wall_s):
        failures=[]
        if self.pause_ack_wall_s is None:failures.append('world_pause_not_acknowledged')
        if self.clock_ns is None:failures.append('clock_not_observed')
        if self.last_raw is None:failures.append('raw_not_observed')
        diagnostic=self.diagnostics.get(self.last_raw)
        expected_header=None
        if self.last_raw is not None and diagnostic is None:
            failures.append('last_raw_without_corresponding_diagnostic')
        elif diagnostic is not None and diagnostic['accepted']:
            expected_header=seconds_to_integer(diagnostic['odometry_header_s'],1_000_000_000)
            if expected_header not in self.odometry_headers:
                failures.append('last_accepted_diagnostic_without_adapted_odometry')
        if self.last_diagnostic_key is not None and self.last_diagnostic_key!=self.last_raw:
            failures.append('latest_diagnostic_does_not_match_last_raw')
        if self.errors:failures.append('malformed_diagnostic_observed')
        missing_truth=[]
        for kind,frames in self.truth_stamps.items():
            for name,stamps in frames.items():
                if self.clock_ns is None or self.clock_ns not in stamps:
                    missing_truth.append(kind+':'+name)
        if missing_truth:failures.append('missing_truth_at_final_clock')
        baseline=max([self.pause_ack_wall_s if self.pause_ack_wall_s is not None else wall_s]+
                     [value for value in self.last_change.values() if value is not None])
        quiet=wall_s-baseline
        if quiet<self.quiet_wall_s:failures.append('source_streams_not_yet_quiet')
        return {'ready':not failures,'failures':failures,'counts':dict(self.counts),
            'last_clock_ns':self.clock_ns,'last_raw_source_us':list(self.last_raw) if self.last_raw else None,
            'last_raw_diagnostic':diagnostic,'expected_adapted_header_ns':expected_header,
            'expected_adapted_observed':expected_header in self.odometry_headers if expected_header is not None else None,
            'quiet_wall_s':quiet,'pause_ack_wall_s':self.pause_ack_wall_s,
            'missing_truth_frames_at_final_clock':missing_truth,
            'truth_latest_source_ns':{kind:{name:max(stamps) if stamps else None for name,stamps in frames.items()}
                                      for kind,frames in self.truth_stamps.items()},
            'errors':list(self.errors)}
