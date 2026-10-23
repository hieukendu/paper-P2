# E5-E7 scale override: `e567_scale_v2_50k`

## Status and scope

This file is the active **server-execution override** for E5, E6 and E7. It
changes data/workload scale, not the number of independent run cells.

- Base run policy: `compact_v1`.
- Scale variant: `e567_scale_v2_50k`.
- Scope: E5, E6 and E7 only.
- E4 is unchanged and is a mandatory predecessor. E4 must reach compute
  complete plus sync verified before this variant opens.
- If E4 is already complete, reuse it; do not rerun E4 merely for this 50k
  variant.
- The existing E4 artifact, profile and hashes are immutable parent inputs for
  E5-E7. The server run registry must record their IDs and hashes.

The variant is a reduced-scale comparative pilot. It can support comparisons
inside the declared reduced workloads, but it must not be reported as a
full-corpus MS MARCO/BEIR/AOL replication.

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

When a run uses a reduced corpus, `full_rebuild` means a full rebuild **of that
reduced corpus**. It does not mean the original full MS MARCO or BEIR corpus.

## E5: static MS MARCO/ORCAS

Keep the 12-cell matrix and use the exact frozen scale artifacts from
`T0.scale`:

- MS MARCO document pool: a deterministic 50,000-document child manifest
  derived from the frozen T0/E4 100,000-document IDs. Do not select a new
  subset after seeing results.
- ORCAS: a deterministic child of the frozen T0 group manifest, capped at
  5,000 scheduling groups. Do not create a new post-hoc group split after
  seeing results.
- Checkpoints: bootstrap, 5%, 10%, 25%, 50% and 100% accessed relative to the
  50,000-document pool; 100% true remains in the same run.
- Primary endpoint: `ARR@10` at 10% accessed. Judged-dev nDCG/Hit/NFR are
  reported only when the manifest's judged-coverage check passes; otherwise
  they are explicitly `N/A_REDUCED_COVERAGE`.
- Report actual encoder work, tokens, GPU time, graph/update time, RAM/VRAM,
  and latency for this reduced workload. Do not extrapolate these values to
  3.21M documents.

E5 must load a 50k subset view or manifest derived from the frozen E4
artifacts. It must not materialize the full E4 graph and filter it afterwards
if the goal is to reduce memory use. Any E5-side induced index/view build must
be recorded as setup cost; it is not an E4 rerun.

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

Every E5-E7 summary must include:

```text
run_budget_policy: compact_v1
scale_variant: e567_scale_v2_50k
parent_e4_artifact_id: <server E4 run/artifact ID>
parent_e4_artifact_hash: <verified hash>
subset_manifest_hash: <verified hash>
claim_scope: reduced_scale_pilot
```

Results from `e567_scale_v2_50k` must not be mixed with full-scale or unqualified
`compact_v1` aggregates. The valid claim is comparative behavior within the
fixed reduced workload. Full-corpus quality, production-scale cost, and
population-wide traffic generalization remain unestablished.

## Execution gate

1. Run or verify the unchanged E4 tasks first. Do not open E5-E7 until E4 is
   `COMPUTE_COMPLETE` and `SYNC_VERIFIED`.
2. Verify the E4 artifact/profile/hash and the relevant T0/case manifests on
   the server.
3. Freeze the E5/E6/E7 50k child manifests and record their hashes.
4. Run the unchanged 12 + 4 + 20 cell matrix under `e567_scale_v2_50k`.
5. Keep compute and sync status separate; a missing or invalid manifest blocks
   the affected stage and never silently substitutes for E4 completion.
