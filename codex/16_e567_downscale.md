# E4-E7 scale override: `e4e567_scale_v3_50k`

## Status and scope

This file is the active **server-execution override** for E4, E5, E6 and E7.
It changes data/workload scale, not the number of independent run cells.

- Base run policy: `compact_v1`.
- Scale variant: `e4e567_scale_v3_50k`.
- Scope: E4, E5, E6 and E7.
- E4 remains a mandatory predecessor, but its official readiness workload is
  also 50,000 documents and 5,000 ORCAS groups. Keep the three E4 tasks and
  their gates unchanged; only their data/workload scale is reduced.
- E4 must reach `COMPUTE_COMPLETE` plus `SYNC_VERIFIED` before E5-E7 open.
- Reuse an E4 artifact only when its manifest, profile, config and scale
  variant hashes exactly match `e4e567_scale_v3_50k`. An older full-scale,
  100k-scale or E5-E7-only E4 artifact is not a parent for this variant.
- The server run registry must record the E4 artifact ID, hashes and the
  common 50k scale-manifest ID.

The variant is a reduced-scale comparative pilot. It can support E4 readiness
and comparisons inside the declared reduced workloads, but it must not be
reported as a full-corpus MS MARCO/BEIR/AOL replication.

## Common scale contract

E4-E7 must use one common, deterministic scale manifest frozen before any
official quality result is inspected:

- MS MARCO document pool: exactly 50,000 documents.
- ORCAS scheduling pool: at most 5,000 groups.
- The pool must contain a fixed uniform/background component and must not be
  selected only from clicked, judged-relevant or qrel-positive documents.
- Document IDs, group IDs, query IDs, selection rule, source revision and
  manifest hash are immutable across E4-E7.
- If an already-frozen `T0.scale` timing artifact uses 100,000 documents, it is
  diagnostic/forecast evidence only; it does not authorize a 100k E4 run or
  replace the official 50k manifest.

For a reduced corpus, `full_rebuild` means a full rebuild of the 50,000-document
corpus. It does not mean rebuilding or filtering the original full MS MARCO or
BEIR corpus.

## Invariants

The following remain unchanged from `compact_v1`:

- E5 has 12 primary cells: four schedulers, map seeds `{17,29,43}`, and
  traffic seed `101`.
- E6 has four cells: the four schedulers, map seed `17`, one chronology, and
  seven weekly decisions.
- E7 has 20 cells: the eight representative cases, MLP random/greedy cells,
  and the four OP+greedy cross-check cells.
- Scheduler definitions, model revisions, map/refit rules, paid budget,
  evaluator, metrics, checkpoint semantics, and run-count accounting remain
  unchanged.
- Every reduced input is selected and hashed before official quality results
  are inspected. A subset made only from clicked or judged-relevant documents
  is not allowed.

## E4: reduced static readiness gate

Keep the three E4 tasks from `compact_v1`, but run all of them on the common
50k/5k manifest:

- Subset/greedy readiness probe on the frozen 50,000-document pool.
- Actual bootstrap stored-graph fidelity, profile and footprint gate for the
  50,000-document pool. This is a full bootstrap **of the reduced pool**, not
  a full-corpus readiness claim.
- Checkpoint/restore and footprint probe using the same reduced graph and
  manifest.

E4 must publish the profile, graph/restore artifacts and manifest hash consumed
by E5-E7. It must not read official E5-E7 quality results to choose the profile.
If the current E4 job was launched with the older scale, do not relabel it as
this variant or mix its output; the new 50k E4 gate needs an exact v3 manifest
and config.

## E5: static MS MARCO/ORCAS

Keep the 12-cell matrix and use the exact frozen common 50k/5k artifacts from
E4 and `T0.scale`:

- MS MARCO document pool: the exact 50,000-document manifest used by E4. Do
  not create a new child subset after seeing results.
- ORCAS: the exact frozen manifest used by E4, capped at 5,000 scheduling
  groups. Do not create a new post-hoc group split after seeing results.
- Checkpoints: bootstrap, 5%, 10%, 25%, 50% and 100% accessed relative to the
  50,000-document pool; 100% true remains in the same run.
- Primary endpoint: `ARR@10` at 10% accessed. Judged-dev nDCG/Hit/NFR are
  reported only when the manifest's judged-coverage check passes; otherwise
  they are explicitly `N/A_REDUCED_COVERAGE`.
- Report actual encoder work, tokens, GPU time, graph/update time, RAM/VRAM,
  and latency for this reduced workload. Do not extrapolate these values to
  3.21M documents.

E5 must reference the exact 50k manifest and E4 artifact hashes. It must not
materialize a larger graph and filter it afterwards. Any E5-side induced
index/view build must be recorded as setup cost; it is not an E4 rerun.

## E6: chronological AOL-IA pilot

Keep the four schedulers, eight-week chronology and seven decisions. Reduce the
workload as follows:

- Document pool cap: 50,000 recovered documents, selected by a deterministic
  pre-run manifest.
- Event cap: 50,000 events per week. Sampling is performed within each week
  with a stable hash/stratification rule while preserving timestamps, user or
  session blocks, and week boundaries.
- The scheduler can read only history available at week `t`; no future event,
  weight or label may enter the decision.
- Primary endpoint remains week-8 weighted ARR at the declared scheduled
  budget, with recovery and coverage counts reported.

If the real AOL-IA recovery is unavailable or coverage fails, E6 remains
`BLOCKED_DATA`; synthetic timestamps are not a substitute.

## E7: reduced BEIR/model cases

Keep the existing 20 cells and per-case reporting. Apply the following scale
rule before any model result is inspected:

- Large cases (NQ, HotpotQA, FEVER): fixed 50,000-document pool and a fixed
  500-query evaluation sample selected deterministically from the validated
  query split.
- Small cases (FiQA and TREC-COVID): reuse the validated corpus/query scope
  when its exact hash matches the existing case artifact; do not enlarge it.
- Record qrel coverage for every case. If the reduced pool cannot support a
  valid judged metric, report the case as reduced-corpus diagnostic evidence,
  not as a standard full BEIR score.

The document pool must include a fixed uniform background and must not be built
only from qrel-positive or clicked documents. Query IDs and document IDs are
frozen in the case manifest before the first E7 cell.

## Required metadata and reporting

Every E4-E7 summary must include:

```text
run_budget_policy: compact_v1
scale_variant: e4e567_scale_v3_50k
official_doc_pool: 50000
orcas_group_cap: 5000
e4_artifact_id: <server E4 run/artifact ID>
e4_artifact_hash: <verified hash>
common_scale_manifest_hash: <verified hash>
parent_e4_artifact_id: <same E4 artifact ID; required for E5-E7>
parent_e4_artifact_hash: <same verified hash; required for E5-E7>
claim_scope: reduced_scale_pilot
```

Results from `e4e567_scale_v3_50k` must not be mixed with full-scale, older
`e567_scale_v2_50k`, or unqualified `compact_v1` aggregates. The valid claim is
comparative behavior within the fixed reduced workload. Full-corpus quality,
production-scale cost, and population-wide traffic generalization remain
unestablished.

## Execution gate

1. Freeze and hash the common 50k document/5k ORCAS manifests before any
   official E4-E7 quality result is inspected.
2. Run the unchanged three E4 tasks on that common reduced manifest. Do not
   open E5-E7 until E4 is `COMPUTE_COMPLETE` and `SYNC_VERIFIED`.
3. Verify the E4 artifact/profile/config/hash and confirm that E5-E7 reference
   the exact same common manifest hash.
4. Run the unchanged 12 + 4 + 20 E5-E7 cells under
   `e4e567_scale_v3_50k`.
5. Keep compute and sync status separate; a missing or invalid manifest blocks
   the affected stage and never silently substitutes for E4 completion.
