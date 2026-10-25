"""Splits depend on IDs and normalized text, never on relevance or test outcomes."""

import hashlib
import math
import unicodedata

import numpy as np

from ..io import digest


def normalize_query(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def stable_key(seed, purpose, value):
    return hashlib.sha256(f"{seed}\0{purpose}\0{value}".encode()).hexdigest()


def group_queries(records):
    groups, by_id = {}, {}
    for qid, text in records:
        if qid in by_id and by_id[qid] != text:
            raise ValueError("Conflicting duplicate query ID")
        by_id[qid] = text
        normalized = normalize_query(text)
        gid = hashlib.sha256(normalized.encode()).hexdigest()
        group = groups.setdefault(gid, {"group_id": gid, "normalized_text": normalized,
                                       "text": text, "representative_id": qid, "query_ids": []})
        if qid not in group["query_ids"]:
            group["query_ids"].append(qid)
        if qid < group["representative_id"]:
            group.update(text=text, representative_id=qid)
    for group in groups.values():
        group["query_ids"].sort()
    return groups


def build_static_splits(groups, split_qids, seed=20261020):
    roles = {"eval": [], "tune": [], "schedule": [], "cal_fit": [], "cal_check": []}
    claimed = set()
    overlap = {}
    for source, role in (("test", "eval"), ("dev", "tune"), ("train", "train")):
        eligible = {gid for gid, group in groups.items() if set(group["query_ids"]) & split_qids.get(source, set())}
        overlap[source] = len(eligible & claimed)
        eligible -= claimed
        claimed |= eligible
        if role != "train":
            roles[role] = sorted(eligible)
            continue
        ordered = sorted(eligible, key=lambda gid: stable_key(seed, "query-roles", gid))
        if not roles["tune"]:
            size = math.floor(0.1 * len(ordered))
            roles["tune"], ordered = ordered[:size], ordered[size:]
        n = len(ordered)
        first, second = math.floor(0.8 * n), math.floor(0.9 * n)
        roles["schedule"] = sorted(ordered[:first])
        roles["cal_fit"] = sorted(ordered[first:second])
        roles["cal_check"] = sorted(ordered[second:])
    flattened = [gid for values in roles.values() for gid in values]
    if len(flattened) != len(set(flattened)):
        raise ValueError("Query groups cross split roles")
    return {"seed": seed, "roles": roles, "removed_overlap_groups": overlap,
            "calibration_available": bool(roles["cal_fit"] and roles["cal_check"]),
            "query_policy": "NFKC-casefold-whitespace-v1", "hash": digest(roles)}


def sample_document_pools(doc_ids, cfg):
    n = len(doc_ids)
    seed = cfg["splits"]["master_seed"]
    budget = cfg["budget"]
    rows = sorted(range(n), key=lambda r: stable_key(seed, "document-pools", doc_ids[r]))
    train = min(budget["train_cap"], math.ceil(budget["train_fraction"] * n))
    val = min(budget["val_cap"], math.ceil(budget["val_fraction"] * n))
    if train + val > n:
        raise ValueError("Insufficient documents for disjoint pools")
    return {"train": np.array(rows[:train], dtype=np.int64),
            "validation": np.array(rows[train:train + val], dtype=np.int64),
            "cal_cap": min(budget["cal_cap"], math.ceil(budget["cal_fraction"] * n))}


def finalize_calibration_pools(proposals, reserved, caps, max_pairs=1000, per_query=4):
    used = set(map(int, reserved))
    result = {}
    for role in ("cal_fit", "cal_check"):
        docs, pairs, counts = set(), [], {}
        seen_pairs = set()
        for qid, row in proposals[role]:
            row = int(row)
            if (qid, row) in seen_pairs or row in used or counts.get(qid, 0) >= per_query:
                continue
            if row not in docs and len(docs) >= caps[role]:
                continue
            docs.add(row)
            seen_pairs.add((qid, row))
            pairs.append((qid, row))
            counts[qid] = counts.get(qid, 0) + 1
            if len(pairs) == max_pairs:
                break
        used |= docs
        result[role] = {"rows": sorted(docs), "pairs": pairs}
    return result
