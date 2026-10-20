# Tiến độ setup và chạy thí nghiệm MixIndex

Checklist ở gốc project, bên ngoài `codex/`; dùng `PROJECT_ROOT/checklist.md` trên server. Target corrected by the user: **H100 80GB in this workspace**; A100 was a typo. Cgroup limit: 250GiB RAM / 16 CPU cores. FiQA and TREC-COVID validated releases and run bundles are public. E0, E1 và T0.core correctness/profile gates đã qua trên H100; shared-device timing vẫn không phải exclusive performance claim. Ma trận chính đã khóa thành `compact_v1`; queue E2 factorial cũ đã dừng và được đánh dấu superseded, queue compact mới đã lập nhưng chưa mở worker mới.

## Chuẩn bị tài liệu và đọc protocol

- [x] DOC — Bộ hướng dẫn module trong `codex/`, structure, constraints, plan và expected outputs đã được viết.
- [x] READ — Bắt đầu `codex/README.md`; đọc đầy đủ report/expect, constraints, structure, contracts, plan và M14 trước khi code.

## Modules cần agent triển khai

- [x] M01 — Environment, config/CLI, H100/cgroup/storage probes và dependency lock.
- [ ] M02 — Download đúng datasets/release và validate raw files.
- [ ] M03 — Preprocess/lookup/ID joins/splits, calibration pools và AOL timeline.
- [ ] M04 — Model snapshots/adapters, vectors và paid accessor.
- [x] M05 — OP/LA/MLP, regions/statistics, calibration a/b/r.
- [x] M06 — Exact/HNSW, top11/rerank, same-ID update/lock/save-load.
- [ ] M07 — Scheduler/baselines, bootstrap/backfill/refit/remap/resume.
- [ ] M08 — Evaluation, baseline adapters, metrics/statistics/cost.
- [ ] M09 — E0–E7 runner/config matrix và finalize hooks.
- [ ] M10 — Dynamic queue, tối đa2 compute jobs khi đủ resource, isolated measurement.
- [x] M11 — HF auto-sync/configured-visibility repo rollover/verify/restore, live tiny round-trip.
- [ ] M12 — Meaningful tests và acceptance gates.
- [ ] M13 — CLI wiring/runbook end-to-end; progress.py cập nhật đúng file này.
- [ ] M14 — Scoped pre-setup, bounded tuning/forecast, immutable profiles và gate trước official.
- [x] M15 — `compact_v1` run budget đã được khóa trong `codex/15_run_budget.md`, runner và jobs manifest.

## Pre-setup và tuning trước nhóm thí nghiệm phụ thuộc

Chi tiết chuẩn ở [codex/14_presetup_tuning.md](codex/14_presetup_tuning.md), thứ tự ở [codex/plan.md](codex/plan.md). Tuning không lặp đến khi thắng baseline: chọn trong grid đã khai báo trên development splits rồi freeze; không dùng test/future để chọn.

- [x] PREP.core — MiniLM/MPNet pinned và FiQA download → full validation/preprocess/splits → document/query model smoke đã đạt.
- [x] T0.core.compute — Sau E0/E1 và code core M05–M08/HNSW/tests: lr chọn bằng P_val, cal đúng roles, runtime/profile local-verified; ANN tasks còn cần ANN_PASS.
- [x] T0.core.sync — Selected profile và development outputs core đã remote-verified.
- [ ] PREP.scale — Arctic pinned, MS MARCO document v1/ORCAS full ingest/count/join/split validation và model smoke đã đạt.
- [ ] T0.scale.compute — Sau E3: tuning trên đúng paid train/val pools; subset100k timing một seed và forecast; đủ để mở E4, chưa phải full-corpus gate.
- [ ] T0.scale.sync — Profile/timing/forecast scale đã remote-verified.
- [ ] T0.compute — Required core+scale scopes đã hoàn tất compute; T0.case E2 bổ sung/E6/E7 ghi riêng trong managed run block trước từng case.
- [ ] T0.sync — Required core+scale bundles đã remote-verified; pending sync không bắt retrain hoặc chặn local compute hợp lệ.

T0.core mở E2 FiQA/E3, không chờ T0.scale/AOL. Dataset/model bổ sung chỉ execute sau T0.case tương thích. Lr/search/runtime được chọn có profile hash riêng; run hash khác theo seed/method là đúng. R/ridge/P95/cadence/budget giữ protocol; ablations được khai báo trước và có variant ID.

## Smoke timing một seed và dự báo thời gian

- [ ] SMOKE-TIME.compute — E1 flow timing + T0.scale timing thật đã sinh `timing.json`, encoder/storage probes và `estimate.json`; giữ measured/estimated/unmeasured rõ.
- [ ] SMOKE-TIME.sync — Các artifacts timing/forecast đã upload và remote-verify.

Seed cố định: `master_seed=20261020`, `map_seed=17`, `traffic_seed=101`; timing repeats dùng cùng seed. Reuse E1 FiQA2,000 exact completion/resume khi config/code không đổi. T0.scale dùng MS MARCO subset100,000 uniform và ORCAS tối đa10,000 groups từ scheduling pool; bốn scheduler tới10% total accessed, locked greedy tiếp tục25% để đo nhiều refit/remap. Fallback phải ghi rõ, không gọi timing random-fill là measured greedy với gain thật.

Đo riêng encode/query/search/heap/backfill/refit/remap/HNSW/checkpoint, docs/tokens/s, RSS/VRAM, bytes và stalls; upload/verify đo sau measurement window. E4 còn probe tới100k scheduling groups và actual full bootstrap graph trước E5. Không ngoại suy HNSW tuyến tính từ subset hoặc chia đôi thời gian chỉ vì cho phép2 jobs.

Runner cập nhật dự báo từ số đo thực tế. FiQA đã có timing development; thời điểm kết thúc toàn bộ E2–E7 chưa đủ bằng chứng để chốt. Không nhân timing prefix với toàn bộ cells hoặc ngoại suy100% như một số đo đã có:

| Phạm vi | Trạng thái dự báo |
|---|---|
| E2 FiQA greedy development, bootstrap→10% accessed | ĐÃ ĐO:375.42s ≈6 phút15 giây; cùng57,638 docs/4,400 scheduling queries, shared H100 |
| E2 FiQA greedy development,10%→25% accessed | ĐÃ ĐO:844.38s ≈14 phút04 giây; tổng hai chặng≈20 phút19 giây, chưa gồm full100%/official evaluation/upload |
| E2 compact preflight + cell đầu tiên | ĐÃ DỪNG để đổi policy; artifact pilot cũ vẫn giữ local/HF nhưng không tính vào compact aggregate. Preflight compact mới chưa chạy. |
| E2 compact_v1:24 required cells | ĐÃ LẬP QUEUE: FiQA mapping9 + FiQA scheduler12 + TREC mapping3; 1 preflight diagnostic mới và TREC giữ dependency T0.case. Worker E2 cũ đã dừng; ETA chưa chốt vì cell compact mới chưa có timing. |
| E2 TREC/E3/T0.scale | CHƯA ĐO; cần đúng-case gates và implementation tương ứng |
| E5:12 primary cells tới10% accessed (+ tối đa4 sensitivity) | CHƯA ĐO; shared encode/cache + per-cell costs, refine tại E4 full bootstrap |
| E5:continuation25/50/100% true | CHƯA ĐO; forecast riêng refit/remap/update/checkpoint, không cộng thêm100% scheduled |
| E7:20 dataset/model cases và eligible schedulers | CHƯA ĐO; cần đúng-case token/runtime profiles và actual task counts |
| E6:AOL recovery + temporal replay | CHƯA ĐO; source/recovery time riêng, unavailable ghi BLOCKED_DATA |
| Download và HF upload/verify/restore | CHƯA ĐO; tách compute time, cộng vào lịch wall-time theo overlap thực tế |

Không dùng các placeholder470 docs/s/1.9 GPU-hour. Timing smoke không tự tick E1/E4 hoặc mọi T0.case; primary/continuation và compute/sync là các gate riêng.

## Thí nghiệm — compute và sync là hai trạng thái riêng

Tick compute khi mọi required cells/gates đã hoàn tất hợp lệ. Tick sync khi tất cả artifact bắt buộc của stage đã remote-verified. Kết quả âm vẫn hợp lệ; thiếu dữ liệu/technical failure không được tick hoàn tất stage.

- [x] E0.compute — Protocol/env/accessor và setup gate đã chạy.
- [x] E0.sync — Setup outputs + tiny round-trip đã verified trên HF.
- [x] E1.compute — Exact smoke, budget/leakage/resume và100% true agreement.
- [x] E1.sync — Run outputs/learned states đã sync verified.
- [ ] E2.compute — `compact_v1`: FiQA mapping9 + FiQA scheduler12 + TREC mapping3 hoàn tất; preflight/gates chưa chạy lại.
- [ ] E2.sync — Pilot outputs/weights/checkpoints đã sync verified.
- [ ] E3.compute — 6 systems tasks theo `compact_v1`: exact/HNSW, cadence, synchronized serving và save/load recovery.
- [ ] E3.sync — Config/measurements/index artifacts cần thiết đã sync verified.
- [ ] E4.compute — 3 tasks theo `compact_v1`: subset probe, actual full-bootstrap stored-graph gate và restore/footprint.
- [ ] E4.sync — Subset IDs/probes/outputs đã sync verified.
- [ ] E5.compute — Full-corpus 12 primary cells và required checkpoints tới100% true hoàn tất; sensitivity không chặn stage.
- [ ] E5.sync — All required primary states/results đã sync verified.
- [ ] E6.compute — Recovered AOL temporal study8 tuần/7 decisions và coverage hợp lệ.
- [ ] E6.sync — Temporal states/metrics/coverage artifacts đã sync verified.
- [ ] E7.compute —20 representative compact cells theo M15 và required baselines hoàn tất.
- [ ] E7.sync — Matrix weights/results/aggregate tables đã sync verified.

## Run đang chạy và run đã xong

Agent/runner cập nhật block sau mỗi run hoặc sync transition. Checkbox của từng run nghĩa là **compute hoàn tất hợp lệ**; cột sync/text riêng cho biết pending hay verified. Không tick E tổng từ một run đơn lẻ. Dòng `N/A` không được biến thành successful measurement.

<!-- progress:begin -->












- [x] E1-debug-fiqa-e690dfc90eb5 — compute=COMPUTE_DONE; sync=VERIFIED; outcome=diagnostic; HF=https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/fd22a0a96e1a3c652a40186072f61aa6ead3585b/runs/E1-debug-fiqa-e690dfc90eb5/4c7aba85abcbf74d3f6c2037b0709ea6742c0b48816243875ea24f35bc3898ab
- [x] E1-debug-fiqa-182b57d9b856 — compute=COMPUTE_DONE; sync=VERIFIED; outcome=diagnostic; HF=https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/948532f0f5a98bd5fcd9f24814969cc1650025aa/runs/E1-debug-fiqa-182b57d9b856/85ab2017880d55da613d1a6dfa415953e073a4fc9d28b68a7158285cfeefd5c0
- [x] CORE_SMOKE-debug-fiqa-f661ce715552 — compute=COMPUTE_DONE; sync=VERIFIED; outcome=diagnostic; HF=https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/95570d2f2f91d5e22b86ffff8b06dd91c3e2439d/runs/CORE_SMOKE-debug-fiqa-f661ce715552/a03c1418cfb58ac955b4f6e937da2ca8220b358dabd95637ad4ec6031cdd2c99
- [x] E0-fiqa-93d6f570216b — compute=COMPUTE_DONE; sync=VERIFIED; outcome=diagnostic; HF=https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/e2c8a6a910e16d57b8d89151bf5068ac4238a05b/runs/E0-fiqa-93d6f570216b/0c619da2768d0bf09326b1daec65e0934aa2e96c1afd4277c7cb4f8ae8e6e9b6
- [x] E1-fiqa-b68e354ee3f3 — compute=COMPUTE_DONE; sync=VERIFIED; outcome=diagnostic; HF=https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/78c06322e334dd5228146f92ae3817c0f7bc454f/runs/E1-fiqa-b68e354ee3f3/6f522e5545e90d33bea1def7ebd5d2f11651a402e8050c783ff098d30e74d0ca
- [x] CORE_SMOKE-fiqa-3db596c22bef — compute=COMPUTE_DONE; sync=VERIFIED; outcome=diagnostic; HF=https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/cb4c5f99784c096260b41505f3dce3b92cf78877/runs/CORE_SMOKE-fiqa-3db596c22bef/fe3771fe1461028285a3912ca96d22e53441a84b4379004cf061b39abdc7a8fb
- [x] RUNTIME_PROBE-fiqa-minilm_mpnet-fb16c618c9df — compute=COMPUTE_DONE; sync=VERIFIED; outcome=diagnostic; HF=https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/c0c4ee043c2cfeb6408301d4dc7a35f4d0db2da6/runs/RUNTIME_PROBE-fiqa-minilm_mpnet-fb16c618c9df/307b6d81a413f3cbfcaad2941596367be1f3bb5acb991fbaaaf29e2a3479672d
- [x] E0-fiqa-d766450f861d — compute=COMPUTE_DONE; sync=VERIFIED; outcome=diagnostic; HF=https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/1ccdc8f509328bebb753d7c0e0968e6244a1b13e/runs/E0-fiqa-d766450f861d/003ca54c50bbc1e62acbe16d3b1091c75fe40977d18a77ff530c6e0a62c19cde
- [x] E1-fiqa-65e9ba9de35d — compute=COMPUTE_DONE; sync=VERIFIED; outcome=diagnostic; HF=https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/7e137e8791f36802ab14bf62e561e65e15dafd94/runs/E1-fiqa-65e9ba9de35d/e014c0890b4ba90527ee75f0a0b6528d7b5f021b68b08488b38e7e535f31d0fd
- [x] CORE_SMOKE-fiqa-04985698e65b — compute=COMPUTE_DONE; sync=VERIFIED; outcome=diagnostic; HF=https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/9103f78a6944a6f1b88c2501e14a68a0c830a62b/runs/CORE_SMOKE-fiqa-04985698e65b/01533d0572b302b6596ffa9cf168fa53f44e899fd3e39b7e1bffc5ef377f0cc0
- [x] RUNTIME_PROBE-fiqa-minilm_mpnet-80c49dd823f1 — compute=COMPUTE_DONE; sync=VERIFIED; outcome=diagnostic; HF=https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/1d0d33e09676772e0bcf00e9921f7cf0615b2336/runs/RUNTIME_PROBE-fiqa-minilm_mpnet-80c49dd823f1/7209256bb4a77465a93821272a57a6180aeb0973b83927f5ac5a55af6ab6bf21
- [x] T0-core-fiqa-b9698dc39c17 — compute=COMPUTE_DONE; sync=VERIFIED; outcome=diagnostic; HF=https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/713b740869cbd2d695a2386abfbbffd2cb270764/runs/T0-core-fiqa-b9698dc39c17/b70b9f54756ecb6e157b800273ed3940d9ad03ff93c224de098593f804c9a61c
- [x] E2_PREFLIGHT-fiqa-3a0a1a13deb8 — compute=COMPUTE_DONE; sync=VERIFIED; expect=KHỚP (technical/provenance/scope gates PASS); outcome=diagnostic; HF=https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/8c97069ed483efb9c58eaee6ebf3c1c0a299c230/runs/E2_PREFLIGHT-fiqa-3a0a1a13deb8/0bb283a5afc0a6414b8255b46a891daa929d8d59e6d74ef27f5fbace8f4a2c70
<!-- progress:end -->

<!-- expect-audit-policy:begin -->
Expectation-audit rule (2026-10-20 17:08 UTC+7, updated 2026-10-20 17:49 UTC+7): a terminal run is compared with the matching section of `expect.md`, and only a run that passes the required correctness, provenance, scope and metric gates is entered as a result in this checklist. **KHỚP** means the expected gate passes and the output has the role expected by the protocol. **YẾU HƠN KỲ VỌNG** is reserved for a valid terminal run that passes correctness gates but is below a preregistered quality/performance direction. Non-pass and in-progress attempts remain in local state/worker evidence for reproducibility and are not published or reported as results here.
<!-- expect-audit-policy:end -->

<!-- expect-audit:begin -->
Completed-run expectation audit against `expect.md`:

- `E0-fiqa-93d6f570216b` and `E0-fiqa-d766450f861d`: input validation, accessor isolation, model smoke and target-hardware gates all `PASS`; compute/sync are complete and verified. Classification: **KHỚP** with E0's manifest/environment gate. E0 has no quality claim.
- `CORE_SMOKE-debug-fiqa-f661ce715552`, `CORE_SMOKE-fiqa-04985698e65b`, and `CORE_SMOKE-fiqa-3db596c22bef`: exact completion agreement `1.0`, budget isolation `PASS`, resume prefix `PASS`, six checkpoints, 1,930 fallback selections; calibration pairs were below the fixed positive-gain minimum, so fallback was correctly recorded. Classification: **KHỚP** as a diagnostic fallback/correctness run; no scheduler-quality claim.
- `E1-fiqa-b68e354ee3f3` and `E1-fiqa-65e9ba9de35d`: see the detailed E1 report above. Classification: **KHỚP** for E1 correctness; the restricted-subset quality numbers are diagnostic only.
- `E1-debug-fiqa-e690dfc90eb5` and `E1-debug-fiqa-182b57d9b856`: exact completion/budget/resume diagnostics pass on development hardware, but `official_gate=false`. Classification: **KHỚP** with the debug-run role; not evidence for the H100 official gate.
- `RUNTIME_PROBE-fiqa-minilm_mpnet-fb16c618c9df` and `RUNTIME_PROBE-fiqa-minilm_mpnet-80c49dd823f1`: finite/norm/agreement/headroom checks and target-hardware checks pass; exclusivity is explicitly unverified. Classification: **KHỚP** with the development timing-probe expectation, not an exclusive performance claim.
- `T0-core-fiqa-b9698dc39c17`: bounded core tuning, restore and ANN fidelity pass; selected profile is frozen and remotely verified. Classification: **KHỚP** within T0.core scope; full T0 and scale/case gates remain open.
- `E2_PREFLIGHT-fiqa-889d06a882c6`: historical preflight with 45 exact bootstrap variants passed and is preserved as a superseded diagnostic artifact. It is not counted in `compact_v1`; the replacement compact preflight has 9 mapping checks and is still pending.
- `E2-fiqa-residual_mlp-primary-greedy-m17-t101-0b0e24d75fc0`: terminal compute and remote bundle verification pass; 57,638/57,638 documents were completed with exact agreement 1.0, 57,638 unique paid IDs, six checkpoints, 5,184 finite metric rows over 648 evaluation queries, and no zero-IDCG rows. The run has 39 greedy selections and 55,579 fallback selections, so its quality outcome is `inconclusive` and `performance_claim=false`; classification **KHỚP** with E2's valid pilot/correctness role, without a positive scheduler-quality claim.
- `msmarco-docs-v1` validated release `200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68`: `status=VALIDATED`; counts are 3,213,835 documents, 5,193 grouped judged-dev queries and 5,193 qrels, with zero duplicate documents/qrels and every qrel joined to the document store. The source archive SHA256 values and split hash are recorded in `data/processed/msmarco-docs-v1/manifest.json`. Classification: **KHỚP** for the MS MARCO input-validation subgate in `expect.md`; E4 timing/throughput and ORCAS gates remain separate.
<!-- expect-audit:end -->

## Ghi chú ngắn

Không cleanup local ở giai đoạn này. Không log HF_TOKEN hoặc raw AOL query/user text tại đây. Thiếu token/quota giữ sync pending, không chạy lại thí nghiệm để sửa upload.

Setup hiện tại: `.venv` Python3.11/PyTorch2.6.0+cu124, hnswlib0.9.0 commit `d9b3608c83d83b46c96e25088cb1d729b29dcfe9`; CUDA/cgroup/storage smoke thật đã ghi `state/environment.json`. FiQA có57,638 docs/648 test queries/1,706 test qrels, source MD5 match, full joins và query roles disjoint. MiniLM/MPNet revisions và document/query smoke đã lưu; không dùng random vectors để chứng nhận model.

FiQA processed release `584640e32aecdf4ce3517078a50ac7e771025e768c8c21fd3ae824d0699c5058` đã publish public và kiểm từng artifact tại [HF dataset](https://huggingface.co/datasets/deadgod3005/mixindex-data-fiqa), payload revision `238e68330fb99d2d1046f94f92c60dcc898d26c1`. Run bundles và tiny safetensors/npz restore nằm trong [HF runs](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001).

66 tests local đã pass: ID/split/accessor, OP khác chiều, learned-map load, float64 regional statistics, calibration/radius, exact/HNSW update/save-load, eager/lazy, complete/resume/corruption, standard metrics, scoped profile gates, immutable/sharded bundles, quota/partial/retry và source snapshot. Các modules còn partial giữ ô trống. Queue, primary calibration proposals, runtime probes and T0.core are now wired and tested. Scale/temporal adapters and official E2–E7 remain incomplete. Diagnostic H100 E1 không tick E0/E1/T0 official; chỉ run có snapshot/hash khớp mới được tính validated.

Code đã push ở branch `codex/mixindex-setup`, [draft PR #1](https://github.com/hieukendu/paper-P2/pull/1). GitHub token thiếu workflow scope, nên CI config nằm ở `scripts/ci-tests.yml` dưới dạng template chưa kích hoạt; không coi local tests là GitHub CI đã chạy. T0.core compute is complete on the corrected H100 target. Keep required scale and official experiment checkboxes open until their actual gates/cells complete.

Current setup revision `T0.core.51c554987c48` (supersedes `2012c977849c` before profile freeze): validated data and model smoke complete; E0 verified on HF; E1 and regional/calibration/greedy smoke compute complete. The first E0/E1/core-smoke and encoder grid are verified. The corrected revision has passed current-source E0/E1/core-smoke and verified their uploads. Its encoder batch probes are compute-done (MiniLM64 / MPNet64), with source-consistent live-encoding metadata and raw/effective token-length statistics; the probe bundle is remotely verified. Full-corpus `T0-core-fiqa-b9698dc39c17` is complete: the complete 57,638 × 384 old-vector cache is written and verified; the LR grid is complete and selects 0.001 for LA and residual MLP. All five candidates passed finite checks; exactly 2,020 unique document embeddings were paid. Bootstrap restore and ANN fidelity have passed. Core profile `a38d8e8b5b27686edceb4d80ab4822d3164545b1327bc29a35db0f687b87a0e3` is frozen and remotely VERIFIED. All 66 tests and lint pass. RAM admission counts only reclaimable inactive file cache in addition to cgroup headroom, preserves the 25GiB safety reserve, and still checks free VRAM before each worker.

The 2,000-document core smoke produced 112 cal-fit / 105 cal-check pairs, below the fixed 200-pair minimum. It correctly recorded `insufficient_calibration`, radius N/A and 1,930 fallback selections; this is correctness evidence for fallback, not a measurement of positive-gain greedy scheduling. Full-corpus T0 uses separate fixed calibration pools.

Before T0 profile freeze, corrected inherited `cached_access` labeling to `live_encode` for actual paid bootstrap encoding. Added sampled raw/effective token-length statistics. The source revision changed deliberately; the strict source guard will preserve/reject affected in-flight outputs, then a fresh setup revision will run. No profile is frozen from mismatched metadata.

First encoder grid `RUNTIME_PROBE-fiqa-minilm_mpnet-fb16c618c9df` completed: all seven batch sizes passed finite/norm/agreement/headroom checks for both encoders. Selected MiniLM batch64 / MPNet batch32 on the shared H100. A new source revision repeats setup/probes to include the corrected live-encoding label and token-length statistics before freeze. Current task prefixes: `T0.core.2012c977849c`, `T0.core.51c554987c48`.

Corrected encoder probe `RUNTIME_PROBE-fiqa-minilm_mpnet-80c49dd823f1` completed successfully and selected batch64 for both models. The 128-document sample has raw token median108.5 / max795; effective lengths retain the native caps256/384. All output agreement/headroom checks passed. These are shared-device development measurements, not exclusive latency evidence.

User notification requirement: announce explicitly when the relevant T0 optimization/profile gates finish and again when the first official experiment starts, including its run ID/configuration. The first official FiQA E2 cell has started and was announced; E3–E7 have not started.

FiQA core optimization compute finished: batch64 both encoders, LR0.001 LA/MLP, HNSW L50/ef200. Worst mean candidate recall@11 across OP/LA/MLP is0.996545; worst serving recall@10 is0.997. All local bootstrap restores passed. The development preflight passed and the first official FiQA E2 cell is now running against this immutable profile. T0.scale/case remain pending.

The compact E2 runner now passes its matrix-planning checks. `configs/jobs-compact.yaml` contains 1 compact preflight plus 24 required cells: FiQA mapping9, FiQA scheduler12 and TREC mapping3. The old 102-cell queue was canceled as `SUPERSEDED_BY_COMPACT_V1`; completed old artifacts remain on disk/HF and are excluded from the new aggregate.

Completed historical readiness run: `E2_PREFLIGHT-fiqa-889d06a882c6` / task `E2.exact.preflight.5c3d3b7c2746` completed45 exact bootstrap cells, fixed25% restore and no-test-label checks, and is remotely VERIFIED. It is retained as superseded evidence; the new compact preflight must be run under the new source/policy revision.

Historical preflight complete: all45 exact bootstrap cells passed across seeds17/29/43 and five variants, with fixed 25% restore and no test relevance opened. It is preserved as superseded evidence; compact_v1 requires a new 9-cell mapping preflight under the new source/policy revision.

Scale input preparation has started independently: Arctic model snapshots are downloaded and revision-pinned; the streaming MS MARCO/ORCAS adapter now has fixture coverage and is isolated in the input worktree. MS MARCO documents v1 + ORCAS raw downloads and gzip/checksum checks are complete; full ingest/join/split validation and scale readiness remain pending.

Public-access verification: anonymous HF API reads succeed for `mixindex-data-fiqa`, `mixindex-data-trec-covid` and `mixindex-runs-001`; all report `private=false`.

Additional BGE/Nomic snapshots and NQ/HotpotQA/FEVER archives are downloaded and pinned/verified. NQ is fully validated/published; HotpotQA/FEVER full validation is running. BGE CPU adapter smoke passed, while Nomic adapter review and model/case-specific H100 tuning remain pending.

BGE download inspection: bge-base snapshot is pinned. Original BGE-M3 revision `5617a9f61b028005a4858fdac845db406aefb181` publishes `pytorch_model.bin` only; the current safetensors-only resolver rejected it as designed. Pinned binary weights are downloaded and recorded by SHA256; restricted-format conversion/adapter review is still pending. BGE real CPU document/query and manual dense CLS smoke passed after conversion; H100 tuning remains incomplete. FiQA uses the validated MiniLM/MPNet adapters.

<!-- health:begin -->
Latest resource check (2026-10-20 16:17 UTC+7): first official FiQA run `E2-fiqa-residual_mlp-primary-greedy-m17-t101-0b0e24d75fc0` is active. Disk free5.35TiB; container-effective RAM available82.4GiB including reclaimable inactive file cache (250GiB limit); H100 free VRAM8.6GiB on the shared device. No OOM/OOM kills recorded. Additional input workers use no GPU and reduced CPU/IO priority. Evidence: `state/health-latest.json`.
<!-- health:end -->

<!-- t0-download-check:begin -->
T0 download round-trip confirmed (2026-10-20 16:01 UTC+7): downloaded the complete `T0-core-fiqa-b9698dc39c17` bundle anonymously from pinned public HF revisions into a separate restore directory. All81 payload files (887,113,489 bytes) match the recorded SHA256 manifest; completion marker/manifest, summary and frozen tuning profile agree. Profile integrity validation passes; existing T0 ANN/local-restore gates remain PASS. Evidence: `state/t0-remote-restore-check.json`. This certifies the FiQA/MiniLM–MPNet core profile; scale and other cases remain pending.

Additional data: NQ raw ZIP integrity/SHA256 verification passed (`state/beir-downloads.json`); full ingest/count/join/split validation is now running (`state/nq-prepare.json`) at reduced CPU/IO priority with one CPU thread and no GPU. Publication remains pending validation and source-specific attribution review. MS MARCO raw files have completed transfer and initial gzip checks; the independent raw-file verification pass is running before ORCAS. HotpotQA download is active.
<!-- t0-download-check:end -->

<!-- current-execution:begin -->
Current execution (2026-10-20 12:25 UTC): the previous compact revisions are stopped and their records are `CANCELLED` as superseded queue revisions; their valid artifacts are preserved but excluded because the source revision changed. Compact revision `c68c145789e2` is running its 9-cell preflight under verified-sync and serial cell gates; 21 FiQA cells wait for its terminal verified artifact, while 3 TREC cells remain dependency-gated. Existing bundles are preserved but excluded from the new aggregate.

Measured shared-host preflight timing: to10% accessed375.42s; continuation10%→25%844.38s. Full100% cell remains unmeasured. Immutable profile stays `a38d8e8b5b27686edceb4d80ab4822d3164545b1327bc29a35db0f687b87a0e3`.

Independent input preparation: MS MARCO document-v1/ORCAS raw transfer plus gzip/checksum checks are complete (`state/scale-download.json`); full ingest/count/join/split validation is pending. NQ full validation passed with2,681,468 docs,3,452 eval-only query groups and4,201 test qrels (`state/nq-prepare.json`); no independent scheduling/calibration/tune queries exist in this downloaded release, so primary greedy is N/A for that case. Public NQ publication is remotely VERIFIED, with full document semantic round-trip and anonymous shard access checks passed. BGE-M3 restricted conversion and real CPU document/query dense-CLS reference smoke passed; H100 runtime/tuning remains pending. New code is isolated in `/root/paper-P2-inputs`, branch `codex/input-adapters` (73 tests pass, Ruff/compile pass); the active official cell keeps its original code/configuration. FEVER validation and public semantic publication are VERIFIED; MS MARCO full ingest remains running.
<!-- current-execution:end -->

<!-- additional-input-progress:begin -->
Input extension update (2026-10-20 16:17 UTC+7): NQ is fully validated and publicly published at https://huggingface.co/datasets/deadgod3005/mixindex-data-nq . All uploaded artifacts are remotely checksum-verified. Reading every exported Parquet row reconstructs the exact canonical source document SHA256 across2,681,468 rows; anonymous repository access and downloaded-shard SHA256 pass (`state/nq-publication-semantic-check.json`). No independent development queries exist in this release; no test query is reassigned.

BGE base/M3 real document/query CPU smoke and manual dense CLS reference comparisons PASS (`state/model-smoke-fiqa-bge-cpu.json`). The converted M3 tensors exactly match pinned upstream binary weights. This proves adapter correctness on CPU; matching H100 runtime/tuning remains required. Nomic v1/v1.5 snapshots are downloaded/pinned and their reviewed local adapter now passes both CPU smokes (`state/nomic-download.json`, `state/nomic-code-review.json`, `state/nomic-smoke.json`); H100 runtime/tuning remains a separate case gate. All five BEIR raw archives plus MS MARCO document-v1/ORCAS are downloaded and archive-verified; FEVER validation and public semantic upload are VERIFIED at `deadgod3005/mixindex-data-fever`, while MS MARCO full ingest runs at low CPU/IO priority.

Input extension commit `1e00855` on `codex/input-adapters`:74 tests, Ruff and compile pass. It adds the pinned Nomic v1/v1.5 adapter, streaming MS MARCO/ORCAS preparation with fixture validation (including the 11 source records with empty query text), and the gated validated-scale publisher. Original active official FiQA source/config remain unchanged. HotpotQA and FEVER are validated and their public dataset uploads are remotely verified; MS MARCO validation is PASS/KHỚP and its gated publication is running while ORCAS prepares against the validated document release. Current effective RAM available is≈78.0GiB including reclaimable inactive file cache; free H100 VRAM is≈11.0GiB on the shared device; disk free is≈5.4TiB. No OOM/OOM kills have been recorded in cgroup memory events.
<!-- additional-input-progress:end -->

Input extension is reviewable in [draft PR #2](https://github.com/hieukendu/paper-P2/pull/2), stacked on #1; head `1e00855` adds the validated MS MARCO/ORCAS scale publisher with source rechecks, bounded Parquet/traffic layouts, completion markers and remote checksum verification, plus the explicit empty-query source policy. The input branch passes 74 tests, Ruff and compile; reviewed large-BEIR publication, BGE-M3 conversion and Nomic adapters remain included. Active FiQA code remains on the immutable setup revision. The publisher is prepared but will not mark a scale release uploaded until the live MS MARCO and ORCAS manifests are `VALIDATED` and remote checksums verify.

<!-- live-official-check:begin -->
Live check (2026-10-20 12:25 UTC): compact revision `c68c145789e2` preflight is RUNNING under one H100 worker; downstream cells remain blocked until `COMPUTE_DONE + sync=VERIFIED + worker exit`, and each later cell is chained to the immediately preceding pass. Prior FiQA pilots/preflights are retained only as historical diagnostic evidence; no failed orchestration attempt is reported as an experiment result. Cgroup memory events remain `oom=0` and `oom_kill=0`. Scale preparation is independent.

HotpotQA full validation PASSED:5,233,329 documents,97,844 unique query groups from97,852 source IDs,7,405 test queries and14,810 test qrels; all joins and train/dev/test query roles validated. Its source-order Parquet semantic round-trip and public upload are remotely verified at `deadgod3005/mixindex-data-hotpotqa`. FEVER full validation PASSED with5,416,568 documents,6,666 test queries and7,937 test qrels; its public semantic upload is remotely VERIFIED at `deadgod3005/mixindex-data-fever` revision `f1f326e3ca213dc7ca93357492473d137769b1eb`. NQ public release is verified with complete semantic round-trip and anonymous access; BGE base/M3 CPU adapter and Nomic v1/v1.5 CPU adapter checks pass; MS MARCO/ORCAS scale ingest remains in progress.
<!-- live-official-check:end -->

<!-- live-scale-check:begin -->
Live scale check (2026-10-20 11:30 UTC): MS MARCO document-v1 validation remains **PASS/KHỚP** at release `200a19df9868ff31a18cf860cf4e05ff71e8ff76db8b671b229cba117374ce68` with 3,213,835 documents, 5,193 judged-dev queries and 5,193 qrels. The scale publisher currently reports `FAILED` with `Source count mismatch for test_qrels`; no HF scale release is marked uploaded. ORCAS preparation has no live worker after the previous watcher exited and must be reconciled before claiming `VALIDATED` or publishing it.
<!-- live-scale-check:end -->

<!-- e1-verification:begin -->
E1 expectation audit against `expect.md`: **KHỚP** for the required correctness role. H100-target development runs `E1-fiqa-b68e354ee3f3` and `E1-fiqa-65e9ba9de35d` are `COMPUTE_DONE` with `official_gate=true`, `completion_exact_agreement=1.0`, budget isolation `PASS`, resume prefix `PASS`, six complete checkpoints, 2,000 documents and 32 queries; both run bundles are remotely `VERIFIED`. Observed diagnostic means are `nDCG@10=0.054811`, `Hit@10=0.0625`, `NFR@1=0.046875`, `ARR@10=0.371875`; these are not E1 acceptance gates. The restricted-subset evaluator has `zero_idcg=true` on 162/192 metric rows because qrels are restricted to the 2,000-document diagnostic subset, so the low quality values are expected rather than weaker E1 correctness. `expect.md` requires exact completion agreement, finite/budget-safe execution, no leakage, locked tie-breaks and lazy/eager consistency; those technical gates pass.
<!-- e1-verification:end -->

<!-- t0-threshold:begin -->
T099% threshold clarification: **mean candidate recall@11 ≥0.99 AND serving recall@10 ≥0.99** are HNSW fidelity gates against exact retrieval over the same stored-vector snapshot on the case's Q_tune. FiQA selectedL50/ef200 achieves worst mean candidate recall@11=0.99654545 (99.65%) and worst serving recall@10=0.997 (99.70%) across OP/LA/MLP primary bootstrap snapshots. This is an ANN correctness/fidelity gate, not99% NDCG/ARR/model accuracy or proof of beating baselines. T0.core also requires finite map/validation selection, held-out/calibration/budget checks, runtime/hardware admission, checkpoint restore and immutable-profile checks; those core gates pass. Scale/other cases require their own gates; full T0 remains unticked.
<!-- t0-threshold:end -->

<!-- visibility-audit:begin -->
Visibility audit (2026-10-20 17:33 UTC+7): all six Hugging Face datasets for this project report `private=false`, including the verified FEVER revision `f1f326e3ca213dc7ca93357492473d137769b1eb`. GitHub owner audit found 11 public repositories including `hieukendu/paper-P2`; a recheck using `gh repo edit --visibility public` confirms `hieukendu/safety-rag-chatbot` is still private and the current PAT receives HTTP403 on the visibility update even though the API reports admin repository permission. A GitHub connector or token with the required visibility scope is still needed; no connector connection is confirmed yet.
<!-- visibility-audit:end -->
