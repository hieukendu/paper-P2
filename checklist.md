# Tiến độ setup và chạy thí nghiệm MixIndex

Checklist ở gốc project, bên ngoài `codex/`; dùng `PROJECT_ROOT/checklist.md` trên server. Target official vẫn là **A100 80GB**. Đã triển khai nền setup/core và publish FiQA đã validate; chưa hoàn tất toàn pipeline hoặc các E official. Host development hiện tại là H100 80GB, cgroup RAM250GiB/CPU16 cores; không dùng host này chứng nhận A100/T0 hoặc performance official.

## Chuẩn bị tài liệu và đọc protocol

- [x] DOC — Bộ hướng dẫn module trong `codex/`, structure, constraints, plan và expected outputs đã được viết.
- [x] READ — Bắt đầu `codex/README.md`; đọc đầy đủ report/expect, constraints, structure, contracts, plan và M14 trước khi code.

## Modules cần agent triển khai

- [ ] M01 — Environment, config/CLI, A100/cgroup/storage probes và dependency lock.
- [ ] M02 — Download đúng datasets/release và validate raw files.
- [ ] M03 — Preprocess/lookup/ID joins/splits, calibration pools và AOL timeline.
- [ ] M04 — Model snapshots/adapters, vectors và paid accessor.
- [ ] M05 — OP/LA/MLP, regions/statistics, calibration a/b/r.
- [ ] M06 — Exact/HNSW, top11/rerank, same-ID update/lock/save-load.
- [ ] M07 — Scheduler/baselines, bootstrap/backfill/refit/remap/resume.
- [ ] M08 — Evaluation, baseline adapters, metrics/statistics/cost.
- [ ] M09 — E0–E7 runner/config matrix và finalize hooks.
- [ ] M10 — Dynamic queue, tối đa2 compute jobs khi đủ resource, isolated measurement.
- [x] M11 — HF auto-sync/private repo rollover/verify/restore, live tiny round-trip.
- [ ] M12 — Meaningful tests và acceptance gates.
- [ ] M13 — CLI wiring/runbook end-to-end; progress.py cập nhật đúng file này.
- [ ] M14 — Scoped pre-setup, bounded tuning/forecast, immutable profiles và gate trước official.

## Pre-setup và tuning trước nhóm thí nghiệm phụ thuộc

Chi tiết chuẩn ở [codex/14_presetup_tuning.md](codex/14_presetup_tuning.md), thứ tự ở [codex/plan.md](codex/plan.md). Tuning không lặp đến khi thắng baseline: chọn trong grid đã khai báo trên development splits rồi freeze; không dùng test/future để chọn.

- [x] PREP.core — MiniLM/MPNet pinned và FiQA download → full validation/preprocess/splits → document/query model smoke đã đạt.
- [ ] T0.core.compute — Sau E0/E1 và code core M05–M08/HNSW/tests: lr chọn bằng P_val, cal đúng roles, runtime/profile local-verified; ANN tasks còn cần ANN_PASS.
- [ ] T0.core.sync — Selected profile và development outputs core đã remote-verified.
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

Runner cập nhật dự báo gọn tại đây sau khi có số đo, kèm link tới `estimate.json`; hiện không có thời gian đã đo:

| Phạm vi | Trạng thái dự báo |
|---|---|
| E5:60 cells tới10% accessed | CHƯA ĐO; shared encode/cache + per-cell costs, refine tại E4 full bootstrap |
| E5:continuation25/50/100% true | CHƯA ĐO; forecast riêng refit/remap/update/checkpoint, không cộng thêm100% scheduled |
| E7:20 dataset/model cases và eligible schedulers | CHƯA ĐO; cần đúng-case token/runtime profiles và actual task counts |
| E6:AOL recovery + temporal replay | CHƯA ĐO; source/recovery time riêng, unavailable ghi BLOCKED_DATA |
| Download và HF upload/verify/restore | CHƯA ĐO; tách compute time, cộng vào lịch wall-time theo overlap thực tế |

Không dùng các placeholder470 docs/s/1.9 GPU-hour. Timing smoke không tự tick E1/E4 hoặc mọi T0.case; primary/continuation và compute/sync là các gate riêng.

## Thí nghiệm — compute và sync là hai trạng thái riêng

Tick compute khi mọi required cells/gates đã hoàn tất hợp lệ. Tick sync khi tất cả artifact bắt buộc của stage đã remote-verified. Kết quả âm vẫn hợp lệ; thiếu dữ liệu/technical failure không được tick hoàn tất stage.

- [ ] E0.compute — Protocol/env/accessor và setup gate đã chạy.
- [ ] E0.sync — Setup outputs + tiny round-trip đã verified trên HF.
- [ ] E1.compute — Exact smoke, budget/leakage/resume và100% true agreement.
- [ ] E1.sync — Run outputs/learned states đã sync verified.
- [ ] E2.compute — FiQA/TREC mapping/pilot và required seed cells hoàn tất.
- [ ] E2.sync — Pilot outputs/weights/checkpoints đã sync verified.
- [ ] E3.compute — HNSW fidelity/update/lock/cadence/systems measurements hoàn tất.
- [ ] E3.sync — Config/measurements/index artifacts cần thiết đã sync verified.
- [ ] E4.compute — MS MARCO subset/ORCAS probes + actual full-bootstrap stored-graph fidelity/footprint và forecast qua scale gate.
- [ ] E4.sync — Subset IDs/probes/outputs đã sync verified.
- [ ] E5.compute — Full-corpus static cells/contrasts và required checkpoints tới100% true hoàn tất.
- [ ] E5.sync — All required primary states/results đã sync verified.
- [ ] E6.compute — Recovered AOL temporal study8 tuần/7 decisions và coverage hợp lệ.
- [ ] E6.sync — Temporal states/metrics/coverage artifacts đã sync verified.
- [ ] E7.compute —20 BEIR/model mapping cases, eligible schedulers và required baselines hoàn tất.
- [ ] E7.sync — Matrix weights/results/aggregate tables đã sync verified.

## Run đang chạy và run đã xong

Agent/runner cập nhật block sau mỗi run hoặc sync transition. Checkbox của từng run nghĩa là **compute hoàn tất hợp lệ**; cột sync/text riêng cho biết pending hay verified. Không tick E tổng từ một run đơn lẻ. Dòng `N/A` không được biến thành successful measurement.

<!-- progress:begin -->
- [ ] E1-debug-fiqa-0658190b91b1 — compute=FAILED; sync=VERIFIED; outcome=diagnostic; HF=https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/a43e8476600f4b5acda60b4d6a54d91760205d20/runs/E1-debug-fiqa-0658190b91b1/1b99114d578ed006271c5ccab63a06b9d098a9375cc18b993c43680786a491b8
- [x] E1-debug-fiqa-e690dfc90eb5 — compute=COMPUTE_DONE; sync=VERIFIED; outcome=diagnostic; HF=https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/fd22a0a96e1a3c652a40186072f61aa6ead3585b/runs/E1-debug-fiqa-e690dfc90eb5/4c7aba85abcbf74d3f6c2037b0709ea6742c0b48816243875ea24f35bc3898ab
- [x] E1-debug-fiqa-182b57d9b856 — compute=COMPUTE_DONE; sync=VERIFIED; outcome=diagnostic; HF=https://huggingface.co/datasets/deadgod3005/mixindex-runs-001/tree/948532f0f5a98bd5fcd9f24814969cc1650025aa/runs/E1-debug-fiqa-182b57d9b856/85ab2017880d55da613d1a6dfa415953e073a4fc9d28b68a7158285cfeefd5c0
<!-- progress:end -->

## Ghi chú ngắn

Không cleanup local ở giai đoạn này. Không log HF_TOKEN hoặc raw AOL query/user text tại đây. Thiếu token/quota giữ sync pending, không chạy lại thí nghiệm để sửa upload.

Setup hiện tại: `.venv` Python3.11/PyTorch2.6.0+cu124, hnswlib0.9.0 commit `d9b3608c83d83b46c96e25088cb1d729b29dcfe9`; CUDA/cgroup/storage smoke thật đã ghi `state/environment.json`. FiQA có57,638 docs/648 test queries/1,706 test qrels, source MD5 match, full joins và query roles disjoint. MiniLM/MPNet revisions và document/query smoke đã lưu; không dùng random vectors để chứng nhận model.

FiQA processed release `584640e32aecdf4ce3517078a50ac7e771025e768c8c21fd3ae824d0699c5058` đã publish private và kiểm từng artifact tại [HF dataset](https://huggingface.co/datasets/deadgod3005/mixindex-data-fiqa), payload revision `238e68330fb99d2d1046f94f92c60dcc898d26c1`. Run bundles và tiny safetensors/npz restore nằm trong [HF runs](https://huggingface.co/datasets/deadgod3005/mixindex-runs-001).

35 tests local đã pass: ID/split/accessor, OP khác chiều, learned-map load, float64 regional statistics, calibration/radius, exact/HNSW update/save-load, eager/lazy, complete/resume/corruption, standard metrics, scoped profile gates, immutable/sharded bundles, quota/partial/retry và source snapshot. Các modules còn partial giữ ô trống. Chưa có queue/matrix/T0 runtime/profile chính thức; primary calibration proposals và các scale/temporal adapters còn phải nối theo plan. Diagnostic H100 E1 không tick E0/E1/T0 official. Run prototype có source-snapshot mismatch được giữ với FAILED; chỉ run có snapshot/hash khớp mới được tính validated.

Code đã push ở branch `codex/mixindex-setup`, [draft PR #1](https://github.com/hieukendu/paper-P2/pull/1). GitHub token thiếu workflow scope, nên CI config nằm ở `scripts/ci-tests.yml` dưới dạng template chưa kích hoạt; không coi local tests là GitHub CI đã chạy. Tiếp tục primary calibration/bootstrap, queue và bounded T0 wiring theo P3b/M14; giữ goal chưa hoàn tất và chưa freeze profile A100 từ host H100.
