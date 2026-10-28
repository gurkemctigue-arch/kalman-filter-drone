"""Offline research metrics, with physical identities supplied by independent GT.

There is deliberately no ROS import here. A frame is a dict with ``gt`` and
``pred`` lists; every object contains ``id``, ``bbox`` (xyxy), ``class_name``.
Detection predictions additionally contain ``confidence``. Empty frames must
be retained. HOTA follows the global alignment and association definitions in
Luiten et al.; IDF1 uses a sequence-wide one-to-one identity assignment.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import math
from typing import Any, Iterable, Sequence

import numpy as np


def iou_matrix(first: Sequence[Sequence[float]], second: Sequence[Sequence[float]]) -> np.ndarray:
    a = np.asarray(first, dtype=float).reshape(-1, 4)
    b = np.asarray(second, dtype=float).reshape(-1, 4)
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("Boxes must be finite")
    if np.any(a[:, 2:] < a[:, :2]) or np.any(b[:, 2:] < b[:, :2]):
        raise ValueError("Boxes require x2>=x1,y2>=y1")
    low = np.maximum(a[:, None, :2], b[None, :, :2])
    high = np.minimum(a[:, None, 2:], b[None, :, 2:])
    intersection = np.prod(np.maximum(0.0, high-low), axis=2)
    area_a = np.prod(a[:, 2:]-a[:, :2], axis=1)
    area_b = np.prod(b[:, 2:]-b[:, :2], axis=1)
    union = area_a[:, None]+area_b[None, :]-intersection
    return np.divide(intersection, union, out=np.zeros_like(intersection), where=union > 0)


def maximum_assignment(scores: np.ndarray) -> list[tuple[int, int]]:
    """Rectangular Hungarian assignment; zero-score matches may be discarded.

    Implemented locally to keep the portable core independent of SciPy.
    """
    scores = np.asarray(scores, dtype=float)
    if scores.ndim != 2 or not np.isfinite(scores).all():
        raise ValueError("Assignment scores must be a finite matrix")
    if 0 in scores.shape:
        return []
    transpose = scores.shape[0] > scores.shape[1]
    cost = -scores.T if transpose else -scores
    n, m = cost.shape
    u, v = np.zeros(n+1), np.zeros(m+1)
    p, way = np.zeros(m+1, dtype=int), np.zeros(m+1, dtype=int)
    for i in range(1, n+1):
        p[0] = i
        j0 = 0
        minimum, used = np.full(m+1, np.inf), np.zeros(m+1, dtype=bool)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], np.inf, 0
            for j in range(1, m+1):
                if used[j]:
                    continue
                current = cost[i0-1, j-1]-u[i0]-v[j]
                if current < minimum[j]:
                    minimum[j], way[j] = current, j0
                if minimum[j] < delta:
                    delta, j1 = minimum[j], j
            for j in range(m+1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minimum[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    result = [(int(p[j]-1), j-1) for j in range(1, m+1) if p[j]]
    return [(j, i) for i, j in result] if transpose else result


def _similarity(gt: list[dict], pred: list[dict]) -> np.ndarray:
    similarity = iou_matrix([o["bbox"] for o in gt], [o["bbox"] for o in pred])
    for i, g in enumerate(gt):
        for j, p in enumerate(pred):
            if g["class_name"] != p["class_name"]:
                similarity[i, j] = 0.0
    return similarity


def detection_metrics(frames: Sequence[dict], confidence_threshold: float = 0.45) -> dict[str, Any]:
    """COCO-style 101-point AP at .50:.05:.95 (all areas, no crowd/maxDet).

    This reports the explicit subset convention instead of claiming the full
    COCO evaluator, which also splits object area and caps detections.
    """
    classes = sorted({o["class_name"] for f in frames for o in f["gt"]+f["pred"]})
    results = {}
    for name in classes:
        gt = [[o for o in f["gt"] if o["class_name"] == name] for f in frames]
        predictions = sorted([(float(o["confidence"]), fi, oi, o)
                              for fi, f in enumerate(frames) for oi, o in enumerate(f["pred"])
                              if o["class_name"] == name], key=lambda x: (-x[0], x[1], x[2]))
        n_gt, ap, operating = sum(map(len, gt)), [], None
        for threshold in np.arange(0.5, 0.951, 0.05):
            used = [set() for _ in frames]
            tp, fp = [], []
            for score, fi, _oi, obj in predictions:
                overlaps = iou_matrix([obj["bbox"]], [o["bbox"] for o in gt[fi]])[0]
                candidates = [(overlap, gi) for gi, overlap in enumerate(overlaps) if gi not in used[fi]]
                overlap, gi = max(candidates, default=(0.0, -1))
                matched = gi >= 0 and overlap >= threshold-1e-12
                if matched:
                    used[fi].add(gi)
                tp.append(int(matched)); fp.append(int(not matched))
            cumulative_tp, cumulative_fp = np.cumsum(tp), np.cumsum(fp)
            recall = cumulative_tp/max(n_gt, 1)
            precision = cumulative_tp/np.maximum(1, cumulative_tp+cumulative_fp)
            ap.append(float(np.mean([max(precision[recall >= r], default=0.0)
                                     for r in np.linspace(0.0, 1.0, 101)])) if n_gt else None)
            if abs(threshold-.5) < 1e-9:
                mask = np.array([p[0] >= confidence_threshold for p in predictions], dtype=bool)
                true_positive = sum(np.asarray(tp)[mask])
                false_positive = sum(np.asarray(fp)[mask])
                operating = {"tp": int(true_positive), "fp": int(false_positive), "fn": int(n_gt-true_positive),
                             "precision": float(true_positive/(true_positive+false_positive)) if true_positive+false_positive else None,
                             "recall": float(true_positive/n_gt) if n_gt else None}
        results[name] = {"ground_truth_objects": n_gt, "predicted_objects": len(predictions),
                         "ap50": ap[0], "ap50_95": float(np.mean(ap)) if n_gt else None,
                         "operating_point_iou": .5, "confidence_threshold": confidence_threshold, **(operating or {})}
    available = [r for r in results.values() if r["ground_truth_objects"]]
    return {"frames": len(frames), "classes": results,
            "map50": float(np.mean([r["ap50"] for r in available])) if available else None,
            "map50_95": float(np.mean([r["ap50_95"] for r in available])) if available else None,
            "convention": "101 recall points; IoU .50:.05:.95; all areas; no crowd/maxDet; only explicitly labelled frames"}


def identity_metrics(frames: Sequence[dict], iou_threshold: float = .5) -> dict[str, Any]:
    """Physical GT identities versus persistent tracker IDs, never task UUIDs."""
    gt_ids = sorted({str(o["id"]) for f in frames for o in f["gt"]})
    pred_ids = sorted({str(o["id"]) for f in frames for o in f["pred"]})
    g_index, p_index = {v:i for i,v in enumerate(gt_ids)}, {v:i for i,v in enumerate(pred_ids)}
    shape = (len(gt_ids), len(pred_ids))
    g_count, p_count = np.zeros(len(gt_ids)), np.zeros(len(pred_ids))
    potential, id_potential = np.zeros(shape), np.zeros(shape)
    prepared = []
    for frame in frames:
        gt, pred = frame["gt"], frame["pred"]
        gi = [g_index[str(o["id"])] for o in gt]
        pi = [p_index[str(o["id"])] for o in pred]
        if len(set(gi)) != len(gi) or len(set(pi)) != len(pi):
            raise ValueError("An identity may occur only once in a frame")
        similarity = _similarity(gt, pred)
        denominator = similarity.sum(axis=0)[None, :]+similarity.sum(axis=1)[:, None]-similarity
        normalized = np.divide(similarity, denominator, out=np.zeros_like(similarity), where=denominator > 0)
        for i, g in enumerate(gi):
            g_count[g] += 1
            for j, p in enumerate(pi):
                potential[g, p] += normalized[i, j]
                id_potential[g, p] += similarity[i, j] >= iou_threshold-1e-12
        for p in pi:
            p_count[p] += 1
        prepared.append((gi, pi, similarity))
    identity_true = sum(id_potential[i,j] for i,j in maximum_assignment(id_potential))
    id_fn, id_fp = g_count.sum()-identity_true, p_count.sum()-identity_true
    denominator = g_count[:, None]+p_count[None, :]-potential
    alignment = np.divide(potential, denominator, out=np.zeros_like(potential), where=denominator > 0)
    hota = []
    switches, last_matches, prior_frame = 0, {}, {}
    operating_tp, operating_fp, operating_fn = 0, 0, 0
    selected_correct, selected_wrong, selected_unmatched, selected_total = 0, 0, 0, 0
    # CLEAR is a separate frame-local matching problem. HOTA's sequence-wide
    # alignment must never be reused to label its switches as standard IDSW.
    for fi,(gi,pi,similarity) in enumerate(prepared):
        if not gi or not pi:
            operating_fn+=len(gi);operating_fp+=len(pi)
            # Match official TrackEval CLEAR's empty-frame early continue.
            continue
        score=similarity.copy()
        for i,g in enumerate(gi):
            for j,p in enumerate(pi):
                if prior_frame.get(g)==p:
                    score[i,j]+=1000
        score[similarity<iou_threshold-np.finfo(float).eps]=0
        pairs=[(i,j) for i,j in maximum_assignment(score) if score[i,j]>np.finfo(float).eps]
        operating_tp+=len(pairs);operating_fn+=len(gi)-len(pairs);operating_fp+=len(pi)-len(pairs)
        for i,j in pairs:
            g,p=gi[i],pi[j]
            switches+=int(g in last_matches and last_matches[g]!=p)
            last_matches[g]=p
        prior_frame={gi[i]:pi[j] for i,j in pairs}
        frame=frames[fi]
        if frame.get("selected_gt_id") is not None:
            selected_total+=1
            selected=str(frame.get("selected_track_id",""))
            matched=[(gt_ids[gi[i]],pred_ids[pi[j]]) for i,j in pairs if pred_ids[pi[j]]==selected]
            if not matched:
                selected_unmatched+=1
            elif matched[0][0]==str(frame["selected_gt_id"]):
                selected_correct+=1
            else:
                selected_wrong+=1
    # Explicit selected tasks on an empty-prediction frame remain failures.
    for fi,(gi,pi,_unused_similarity) in enumerate(prepared):
        if (not gi or not pi) and frames[fi].get("selected_gt_id") is not None:
            selected_total+=1;selected_unmatched+=1
    for alpha in np.arange(.05, .951, .05):
        match_count, tp, fn, fp, localization = np.zeros(shape), 0, 0, 0, 0.0
        for fi, (gi, pi, similarity) in enumerate(prepared):
            score = alignment[np.ix_(gi, pi)]*similarity
            pairs = [(i,j) for i,j in maximum_assignment(score) if similarity[i,j] >= alpha-1e-12]
            tp += len(pairs); fn += len(gi)-len(pairs); fp += len(pi)-len(pairs)
            for i,j in pairs:
                match_count[gi[i],pi[j]] += 1
                localization += similarity[i,j]
        association_den = g_count[:,None]+p_count[None,:]-match_count
        association = np.divide(match_count, association_den, out=np.zeros_like(match_count), where=association_den > 0)
        ass_a = float((match_count*association).sum()/tp) if tp else 0.0
        det_a = tp/(tp+fn+fp) if tp+fn+fp else 0.0
        hota.append({"alpha": round(float(alpha),2), "hota": math.sqrt(ass_a*det_a),
                     "det_a": det_a, "ass_a": ass_a, "loc_a": localization/tp if tp else 0.0,
                     "tp": tp, "fn": fn, "fp": fp})
    total = float(g_count.sum()+p_count.sum())
    return {"frames": len(frames), "gt_detections": int(g_count.sum()), "predicted_detections": int(p_count.sum()),
            "idtp": int(identity_true), "idfn": int(id_fn), "idfp": int(id_fp),
            "idf1": 2*identity_true/total if total else None,
            "id_switches": switches, "matching_iou": iou_threshold,
            "id_switch_convention":"TrackEval CLEAR frame assignment: continue prior-frame match when feasible, then IoU; IDSW compares last matched physical identity across gaps",
            "tp": operating_tp, "fp": operating_fp, "fn": operating_fn,
            "hota": float(np.mean([r["hota"] for r in hota])) if total else None,
            "hota_by_alpha": hota,
            "selected_identity": {"frames": selected_total, "correct": selected_correct, "wrong": selected_wrong,
                                  "unmatched": selected_unmatched, "retention_rate": selected_correct/selected_total if selected_total else None,
                                  "denominator":"All supplied frames explicitly within the selected task and marked selected_gt_id, including missing predictions. Caller must disclose visibility eligibility and split explicit new tasks; uuid is ignored."},
            "identity_source": "Independent physical GT ID matched to persistent track ID via image boxes; target_uuid is not an identity metric"}


def numeric_summary(values: Iterable[float | None]) -> dict[str, Any]:
    rows = list(values)
    good = np.asarray([float(v) for v in rows if v is not None and math.isfinite(float(v))])
    return {"count": len(rows), "valid_count": len(good), "missing_count": len(rows)-len(good),
            "mean": float(good.mean()) if len(good) else None,
            "std": float(good.std(ddof=1)) if len(good)>1 else None,
            "median": float(np.median(good)) if len(good) else None,
            "p95": float(np.percentile(good,95)) if len(good) else None}


def wilson_interval(failures: int, total: int, z: float = 1.959963984540054) -> dict[str, Any]:
    if not 0 <= failures <= total:
        raise ValueError("Expected 0 <= failures <= total")
    if not total:
        return {"failures": 0, "total": 0, "rate": None, "ci95": None}
    p, den = failures/total, 1+z*z/total
    center = (p+z*z/(2*total))/den
    half = z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/den
    return {"failures": failures, "total": total, "rate": p, "ci95": [max(0,center-half),min(1,center+half)],
            "ci_method": "Wilson score, Bernoulli trial unit"}


def paired_bootstrap(first: Sequence[float | None], second: Sequence[float | None],
                     *, seed: int = 20261026, resamples: int = 10000) -> dict[str, Any]:
    if len(first) != len(second):
        raise ValueError("Paired samples must have equal lengths")
    differences = np.asarray([float(a)-float(b) for a,b in zip(first,second)
                              if a is not None and b is not None and math.isfinite(float(a)) and math.isfinite(float(b))])
    if not len(differences):
        return {"pairs": 0, "excluded_pairs": len(first), "mean_difference": None, "ci95": None}
    rng = np.random.default_rng(seed)
    means = differences[rng.integers(0,len(differences),(resamples,len(differences)))].mean(axis=1)
    return {"pairs": len(differences), "excluded_pairs": len(first)-len(differences),
            "mean_difference": float(differences.mean()), "ci95": np.percentile(means,[2.5,97.5]).tolist(),
            "method": "paired nonparametric percentile bootstrap; first minus second; resample complete trial/seed units",
            "seed": seed, "resamples": resamples}
