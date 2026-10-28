"""Numerically compare portable metrics to pinned official TrackEval code.

Loads only the metric class AST, strips instrumentation decorators, and maps
removed NumPy dtype aliases to builtins. Formula bodies remain unchanged.
SciPy's assignment is replaced by our separately brute-force-tested solver;
the comparison therefore checks metric algebra, not solver independence.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys
from urllib.request import urlopen
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from uav_tracking.research_metrics import identity_metrics,maximum_assignment,iou_matrix
COMMIT="12c8791b303e0a0b50f753af204249e622d0281a"


class Compatibility(ast.NodeTransformer):
    def visit_FunctionDef(self,node):
        node.decorator_list=[d for d in node.decorator_list if isinstance(d,ast.Name) and d.id=="staticmethod"]
        return self.generic_visit(node)
    def visit_Attribute(self,node):
        if isinstance(node.value,ast.Name) and node.value.id=="np" and node.attr in ("float","int"):
            return ast.copy_location(ast.Name(id=node.attr,ctx=ast.Load()),node)
        return self.generic_visit(node)


def official(name):
    url=f"https://raw.githubusercontent.com/JonathonLuiten/TrackEval/{COMMIT}/trackeval/metrics/{name.lower()}.py"
    source=urlopen(url,timeout=30).read().decode()
    tree=ast.parse(source)
    tree.body=[node for node in tree.body if isinstance(node,ast.ClassDef) and node.name==name]
    tree=ast.fix_missing_locations(Compatibility().visit(tree))
    def assignment(cost):
        pairs=maximum_assignment(-cost)
        return np.asarray([i for i,j in pairs],dtype=int),np.asarray([j for i,j in pairs],dtype=int)
    scope={"np":np,"_BaseMetric":object,"linear_sum_assignment":assignment,"__name__":"trackeval_reference"}
    exec(compile(tree,url,"exec"),scope)
    cls=scope[name]
    metric=cls() if name=="HOTA" else cls.__new__(cls)
    if name=="Identity":
        metric.fields=["IDTP","IDFN","IDFP","IDF1","IDR","IDP"];metric.threshold=.5
    if name=="CLEAR":
        metric.fields=["CLR_TP","CLR_FN","CLR_FP","IDSW","MT","PT","ML","Frag","CLR_Frames","MOTP_sum"]
        metric.threshold=.5
    return metric,{"url":url,"source_sha256":hashlib.sha256(source.encode()).hexdigest()}


def official_data(frames):
    gt=sorted({o["id"] for frame in frames for o in frame["gt"]})
    pred=sorted({o["id"] for frame in frames for o in frame["pred"]})
    result={"num_gt_ids":len(gt),"num_tracker_ids":len(pred),"num_gt_dets":sum(len(f["gt"]) for f in frames),
            "num_tracker_dets":sum(len(f["pred"]) for f in frames),"num_timesteps":len(frames),"gt_ids":[],"tracker_ids":[],"similarity_scores":[]}
    for frame in frames:
        result["gt_ids"].append(np.asarray([gt.index(o["id"]) for o in frame["gt"]],dtype=int))
        result["tracker_ids"].append(np.asarray([pred.index(o["id"]) for o in frame["pred"]],dtype=int))
        result["similarity_scores"].append(iou_matrix([o["bbox"] for o in frame["gt"]],[o["bbox"] for o in frame["pred"]]))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    hota,hmeta=official("HOTA");identity,imeta=official("Identity");clear,cmeta=official("CLEAR")
    rng=np.random.default_rng(1973)
    cases=[]
    for seed in range(60):
        frames=[]
        for tick in range(15):
            gt=[];pred=[]
            for object_id in range(3):
                if rng.random()>.15:
                    x=object_id*8+tick*.5
                    gt.append({"id":str(object_id),"bbox":[x,0,x+12,20],"class_name":"person"})
                if rng.random()>.25:
                    x=object_id*8+tick*.5+float(rng.normal(0,3))
                    pred.append({"id":str((object_id+(tick//5 if seed%2 else 0))%3),"bbox":[x,0,x+12,20],"class_name":"person"})
            frames.append({"gt":gt,"pred":pred})
        ours=identity_metrics(frames)
        data=official_data(frames)
        official_h=hota.eval_sequence(data);official_i=identity.eval_sequence(data);official_c=clear.eval_sequence(data)
        np.testing.assert_allclose([r["hota"] for r in ours["hota_by_alpha"]],official_h["HOTA"],rtol=0,atol=1e-12)
        np.testing.assert_allclose([r["tp"] for r in ours["hota_by_alpha"]],official_h["HOTA_TP"],rtol=0,atol=0)
        np.testing.assert_allclose([r["fn"] for r in ours["hota_by_alpha"]],official_h["HOTA_FN"],rtol=0,atol=0)
        np.testing.assert_allclose([r["fp"] for r in ours["hota_by_alpha"]],official_h["HOTA_FP"],rtol=0,atol=0)
        np.testing.assert_allclose(ours["idf1"],official_i["IDF1"],rtol=0,atol=1e-12)
        assert ours["id_switches"]==official_c["IDSW"],(ours["id_switches"],official_c["IDSW"])
        assert ours["tp"]==official_c["CLR_TP"]
        cases.append({"seed_index":seed,"hota":ours["hota"],"idf1":ours["idf1"],"idsw":ours["id_switches"]})
    result={"result":"PASS","fixture_sequences":len(cases),"frames_per_sequence":15,
            "official_commit":COMMIT,"official_sources":[hmeta,imeta,cmeta],"comparisons":"HOTA all 19 alpha values and counts, IDF1, CLEAR IDSW and TP; abs tolerance 1e-12",
            "compatibility_changes":"AST keeps class only, drops timing decorators and maps np.float/np.int aliases; metric formula bodies unchanged; both use separately brute-force-tested portable Hungarian solver",
            "limitations":"No benchmark-dataset preprocessing/crowd/visibility validation is implied. Correct formulas do not validate ground-truth annotations.","cases":cases}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+"\n")
    print(f"PASS {len(cases)} official metric fixture comparisons; {args.output}")


if __name__=="__main__":
    main()
