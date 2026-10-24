"""Positive scalar calibration; held-out residuals define a score-space radius."""

from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class Calibration:
    a: float = 1.0
    b: float = 0.0
    radius: float | None = None
    reason: str = "identity"


def fit_score_calibration(s_fit, t_fit):
    s, t = np.asarray(s_fit, dtype=np.float64), np.asarray(t_fit, dtype=np.float64)
    if s.shape != t.shape or s.ndim != 1:
        raise ValueError("Invalid calibration pair shapes")
    if len(s) == 0 or not np.isfinite(s).all() or not np.isfinite(t).all():
        return Calibration(reason="nonfinite_or_empty")
    variance = np.mean((s - s.mean()) ** 2)
    if variance < 1e-12:
        return Calibration(reason="degenerate_variance")
    slope = float(np.mean((s - s.mean()) * (t - t.mean())) / variance)
    a = max(1e-6, slope)
    b = float(t.mean() - a * s.mean())
    if not np.isfinite(a + b):
        return Calibration(reason="nonfinite_fit")
    return Calibration(a, b, reason="slope_boundary" if a == 1e-6 else "ols")


def compute_radius(s_check, t_check, a, b, quantile=0.95):
    errors = np.sort(np.abs(np.asarray(t_check) - (a * np.asarray(s_check) + b)))
    if not len(errors) or not np.isfinite(errors).all() or not 0 < quantile <= 1:
        raise ValueError("Invalid cal-check residual population")
    return float(errors[math.ceil(quantile * len(errors)) - 1])


def calibrate_scores(raw, fidelity, cal):
    return np.where(fidelity, raw, cal.a * raw + cal.b)


def fit_with_roles(s_fit, t_fit, fit_qids, s_check, t_check, check_qids, cfg):
    if set(fit_qids) & set(check_qids):
        raise ValueError("Calibration query roles overlap")
    fit_valid = len(s_fit) >= cfg["min_pairs"] and len(set(fit_qids)) >= cfg["min_queries"]
    check_valid = len(s_check) >= cfg["min_pairs"] and len(set(check_qids)) >= cfg["min_queries"]
    cal = (fit_score_calibration(s_fit, t_fit) if fit_valid else Calibration(reason="insufficient_calibration"))
    if not cfg.get("enabled", True):
        cal = Calibration(reason="disabled")
    radius = compute_radius(s_check, t_check, cal.a, cal.b, cfg["quantile"]) if check_valid else None
    return Calibration(cal.a, cal.b, radius, cal.reason)


def make_calibration_proposal(op_map, cal_queries, old_vectors, doc_ids, caps, reserved,
                              cfg, seed=20261020):
    """Choose fixed pairs from the common OP's raw ranks 6–20, without target reads.

    cal_queries maps each role to {query_id: frozen new-query vector}. A caller may
    reuse this result across map variants/seeds, including calibration-off controls.
    """
    from .data.splits import finalize_calibration_pools, stable_key
    from .index import ExactIndex
    from .maps import transform_global

    fit_ids, check_ids = set(cal_queries.get("cal_fit", {})), set(cal_queries.get("cal_check", {}))
    if fit_ids & check_ids:
        raise ValueError("Calibration query roles overlap")
    mapped = transform_global(op_map, old_vectors, normalize=True)
    index = ExactIndex(mapped, doc_ids)
    proposals = {"cal_fit": [], "cal_check": []}
    for role in proposals:
        queries = cal_queries.get(role, {})
        ordered = sorted(queries, key=lambda q: stable_key(seed, f"{role}-proposal", q))
        # Stream query batches: do not retain a full Q x N score matrix or top-L log.
        for start in range(0, len(ordered), 32):
            batch = ordered[start:start + 32]
            result = index.search(np.stack([queries[q] for q in batch]), k=19, calibrated=False)
            for qid, rows in zip(batch, result.rows):
                proposals[role].extend((qid, int(row)) for row in rows[5:20])
    return finalize_calibration_pools(proposals, reserved, caps, cfg["max_pairs"], cfg["max_pairs_per_query"])


def validate_calibration_pools(pools, cal_queries, reserved, caps, cfg, n_documents):
    if set(cal_queries.get("cal_fit", {})) & set(cal_queries.get("cal_check", {})):
        raise ValueError("Calibration query roles overlap")
    used = set(map(int, reserved))
    query_ids = set()
    for role in ("cal_fit", "cal_check"):
        pool = pools[role]
        rows = set(map(int, pool["rows"]))
        pairs = [(str(q), int(row)) for q, row in pool["pairs"]]
        if (rows & used or len(rows) > caps[role] or
                any(row < 0 or row >= n_documents for row in rows)):
            raise ValueError("Calibration document pools overlap or exceed their cap")
        if set(row for _, row in pairs) != rows or len(pairs) != len(set(pairs)):
            raise ValueError("Calibration pool IDs do not match unique pair IDs")
        if len(pairs) > cfg["max_pairs"]:
            raise ValueError("Calibration pair cap exceeded")
        qcounts = {}
        for qid, _ in pairs:
            if qid not in cal_queries.get(role, {}) or qid in query_ids:
                raise ValueError("Calibration pair uses an unknown or crossed query role")
            qcounts[qid] = qcounts.get(qid, 0) + 1
        if any(count > cfg["max_pairs_per_query"] for count in qcounts.values()):
            raise ValueError("Too many calibration pairs for one query")
        used |= rows
        query_ids |= set(qcounts)


def score_shadow_pairs(pair_ids, M0, regional, query_vectors, paid_targets,
                       old_vectors, assignments):
    from .maps import map_documents
    if not pair_ids:
        return np.empty(0), np.empty(0), []
    rows = np.array([int(row) for _, row in pair_ids], dtype=np.int64)
    if any(int(row) not in paid_targets for row in rows):
        raise PermissionError("Calibration can score only previously paid targets")
    qids = [str(qid) for qid, _ in pair_ids]
    queries = np.stack([query_vectors[qid] for qid in qids])
    shadow = map_documents(rows, old_vectors, M0, regional, assignments)
    target = np.stack([paid_targets[int(row)] for row in rows])
    return np.sum(queries * shadow, axis=1), np.sum(queries * target, axis=1), qids


def refresh_calibration(state, regional=None):
    regional = state.regional if regional is None else regional
    scores = {}
    for role in ("cal_fit", "cal_check"):
        scores[role] = score_shadow_pairs(
            state.calibration_pools[role]["pairs"], state.M0, regional,
            state.calibration_queries, state.accessor.cache, state.old_vectors,
            state.regions["assignments"])
    s_fit, t_fit, fit_ids = scores["cal_fit"]
    s_check, t_check, check_ids = scores["cal_check"]
    return fit_with_roles(s_fit, t_fit, fit_ids, s_check, t_check, check_ids, state.cfg["calibration"])
