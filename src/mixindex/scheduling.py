"""Weighted fixed-snapshot coverage and budget-safe scheduler controls."""

import heapq

import numpy as np


def build_candidate_sets(search_results, proxies, fidelity, radius, weights=None):
    result = {}
    if radius is None or radius <= 0:
        return result
    weights = weights if weights is not None else np.ones(len(search_results.rows))
    if np.any(np.asarray(weights) < 0):
        raise ValueError("Coverage weights must be nonnegative")
    for q, (rows, scores) in enumerate(zip(search_results.rows, search_results.scores)):
        if len(rows) < 11:
            continue
        proxy = set(rows[:10]) if proxies is None else set(proxies[q])
        slack = scores[:10] - scores[10]
        relevant = np.array([r in proxy for r in rows[:10]])
        if np.any(relevant & (slack > 2 * radius)):
            continue  # A true relevant proxy can also make the query safe.
        eligible = relevant & ~fidelity[rows[:10]] & (slack > radius) & (slack <= 2 * radius)
        candidates = set(map(int, rows[:10][eligible]))
        if candidates:
            result[q] = (candidates, float(weights[q]))
    return result


def marginal_gain(doc_row, covered_queries, candidates):
    return sum(weight for q, (rows, weight) in candidates.items() if q not in covered_queries and doc_row in rows)


def select_random(mapped_mask, cap, rng):
    eligible = np.flatnonzero(mapped_mask)
    if cap < 0 or cap > len(eligible):
        raise ValueError("Random batch exceeds mapped population")
    return rng.choice(eligible, cap, replace=False).tolist()


def select_greedy(candidates, cap, mapped_mask, rng, ids, lazy=True):
    if cap < 0 or cap > int(mapped_mask.sum()):
        raise ValueError("Greedy batch exceeds mapped population")
    reverse = {}
    weights = {}
    for query, (rows, weight) in candidates.items():
        if weight < 0 or not np.isfinite(weight):
            raise ValueError("Invalid coverage weight")
        weights[query] = weight
        for row in rows:
            if mapped_mask[row]:
                reverse.setdefault(row, set()).add(query)
    covered, selected = set(), []
    def gain(row):
        return sum(weights[q] for q in reverse[row] - covered)
    if lazy:
        heap = [(-gain(row), str(ids[row]), row) for row in reverse]
        heapq.heapify(heap)
        while heap and len(selected) < cap:
            _, doc_id, row = heapq.heappop(heap)
            current = gain(row)
            key = (-current, doc_id, row)
            if heap and key > heap[0]:
                heapq.heappush(heap, key)
                continue
            if current <= 0:
                break
            selected.append(row)
            covered |= reverse[row]
    else:
        remaining = set(reverse)
        while remaining and len(selected) < cap:
            row = min(remaining, key=lambda r: (-gain(r), str(ids[r])))
            if gain(row) <= 0:
                break
            selected.append(row)
            covered |= reverse[row]
            remaining.remove(row)
    greedy_count = len(selected)
    available = np.array(mapped_mask, copy=True)
    available[selected] = False
    selected += select_random(available, cap - len(selected), rng)
    return selected, {"greedy_count": greedy_count, "fallback_count": cap - greedy_count,
                      "reason": "positive_gain_exhausted" if greedy_count < cap else "coverage"}


def select_degree(schedule_edges, mapped_mask, cap, ids):
    neighbors = {}
    for query, row in schedule_edges:
        if mapped_mask[row]:
            neighbors.setdefault(row, set()).add(query)
    eligible = np.flatnonzero(mapped_mask)
    return sorted(eligible, key=lambda row: (-len(neighbors.get(row, ())), str(ids[row])))[:cap]


def choose_batch_cap(n, paid, backfilled, target, refit_interval, batch_fraction=0.01):
    next_refit = (backfilled // refit_interval + 1) * refit_interval
    return max(0, min(int(np.ceil(batch_fraction * n)), n - paid, target - paid,
                      next_refit - backfilled))
