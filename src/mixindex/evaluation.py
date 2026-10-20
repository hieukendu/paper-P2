"""Evaluator-only references and metrics. No reference object enters scheduling."""

import numpy as np
import pytrec_eval


def agreement_at_10(rankings, full_new_exact, weights=None):
    if len(rankings) != len(full_new_exact):
        raise ValueError("Evaluation query populations differ")
    values = np.array([len(set(a[:10]) & set(b[:10])) / 10
                       for a, b in zip(rankings, full_new_exact)], dtype=np.float64)
    if weights is None:
        return values
    weights = np.asarray(weights, dtype=np.float64)
    if len(weights) != len(values) or np.any(weights < 0) or weights.sum() <= 0:
        raise ValueError("Invalid evaluation weights")
    return float(np.average(values, weights=weights))


def ndcg_hit_nfr(rankings, qrels, reference):
    # Monotonic rank scores preserve the explicit ID tie-break in the supplied ranking.
    queries = list(rankings)
    positive_qrels = {qid: {did: int(grade) for did, grade in qrels.get(qid, {}).items()}
                      for qid in queries if any(grade > 0 for grade in qrels.get(qid, {}).values())}
    run = {qid: {did: -rank for rank, did in enumerate(rankings[qid][:10], 1)} for qid in queries}
    ndcg = pytrec_eval.RelevanceEvaluator(positive_qrels, {"ndcg_cut_10"}).evaluate(run) if positive_qrels else {}
    results = []
    for qid in queries:
        relevant = {did for did, grade in qrels.get(qid, {}).items() if grade > 0}
        top, full = rankings[qid][:10], reference[qid][:10]
        results.append({"query_id": qid, "ndcg_at_10": ndcg.get(qid, {}).get("ndcg_cut_10", 0.0),
                        "hit_at_10": float(bool(relevant & set(top))),
                        "nfr_at_1": float(bool(full and full[0] in relevant and (not top or top[0] not in relevant))),
                        "zero_idcg": not bool(relevant)})
    return results


def retained_metric(values, reference):
    denominator = float(np.mean(reference))
    return float(100 * np.mean(values) / denominator) if denominator else None


def quality_auc(fractions, quality, retained_percent=False):
    x, y = np.asarray(fractions), np.asarray(quality)
    if len(x) < 2 or len(x) != len(y) or np.any(np.diff(x) <= 0):
        raise ValueError("AUC requires increasing observed checkpoint fractions")
    if retained_percent:
        y = y / 100
    return {"auc": float(np.trapezoid(y, x) / (x[-1] - x[0])),
            "lower": float(x[0]), "upper": float(x[-1])}


def paired_analysis(differences, draws=10000, seed=20261020):
    # Input is one mean difference per query group, already averaged across seed cells.
    values = np.asarray(differences, dtype=np.float64)
    if values.ndim != 1 or not len(values) or not np.isfinite(values).all():
        raise ValueError("Expected finite per-query differences averaged over seed cells")
    rng = np.random.default_rng(seed)
    observed = values.mean()
    boot, extreme = [], 0
    for _ in range(draws):
        boot.append(float(rng.choice(values, len(values), replace=True).mean()))
        signed = (values * rng.choice([-1, 1], len(values))).mean()
        extreme += abs(signed) >= abs(observed)
    return {"effect": float(observed), "ci95": np.quantile(boot, [0.025, 0.975]).tolist(),
            "p_raw": (1 + extreme) / (draws + 1), "queries": len(values), "draws": draws,
            "unit": "query_group_conditional_on_seed_grid",
            "null_assumption": "method labels exchangeable within query groups"}


def holm(p_values):
    values = np.asarray(p_values, dtype=float)
    order = np.argsort(values)
    adjusted = np.empty(len(values))
    largest = 0
    for rank, index in enumerate(order):
        largest = max(largest, (len(values) - rank) * values[index])
        adjusted[index] = min(1.0, largest)
    return adjusted.tolist()
