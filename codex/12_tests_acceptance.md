# M12 — Test cần thiết và acceptance

Code tests tập trung vào lỗi làm sai nghiên cứu hoặc mất run/sync. Không đặt mục tiêu coverage100%, không mock hết công thức rồi gọi implementation đúng. Không training/full-download trong unit tests; model smoke và live tiny upload là integration checks riêng.

## Test files nên có

| File | Các case phải chứng minh |
|---|---|
| `tests/test_data_splits.py` | duplicate normalized query khác ID cùng group; doc/qrel joins; train/val/cal/test disjoint; ORCAS edge không là event; AOL multi-click1 event/time cutoff |
| `tests/test_accessor.py` | denied target không bị đọc, paid union counts đúng, cal/val không vào train, cap trước read, repeated encode charge unique/cost đúng |
| `tests/test_maps_calibration.py` | OP known rotation, tăng chiều và query-side giảm chiều, row/column convention; float64 incremental stats khớp full fit; M0 freeze; r units/quantile/identity fallback |
| `tests/test_index.py` | exact calibrated top11/ties, HNSW distance conversion, same-ID/save-load/ef, failed partial commit không còn served |
| `tests/test_scheduler.py` | A(q) đúng band `(r,2r]`, safe query exclusion, true doc exclusion, eager=lazy IDs với ties; reset coverage/heap giữa snapshots; random fallback/empty batch |
| `tests/test_migration_resume.py` | bootstrap true flags, cadence theo backfill không accessed; remap chỉ mapped touched regions; resume prefix/RNG/stats đúng uninterrupted;100% true exact reference |
| `tests/test_evaluation.py` | known qrels ndcg/hit/nfr, ARR1 at reference, zero denominator, query grouping in bootstrap, raw/candidate/serving recall phân biệt |
| `tests/test_queue_sync.py` | cgroup vs physical limits, max2 admission, exclusive mode, PID birth reconciliation, idempotent upload, rollover, account quota no repo loop, verify-before-complete/checklist |
| `tests/test_presetup.py` | LR chọn đúng theo P_val/tie rule, sentinel test evaluator không bị gọi trong T0, finite bounded grid/stop, scope/profile mismatch chặn execution, allowed ablation override, graph không cycle, development cells không vào official aggregate |

## Numerical checks

- Unit-norm float32 vectors: abs(norm−1)≤1e-4; finite/zero errors fail. Tolerance này là numerical check, không radius score/certificate.
- Float64 incremental ridge/full ridge compare `rtol=1e-7, atol=1e-9` trên well-conditioned toy fixture; nếu source/platform sai khác không nằm tolerance phải kiểm thuật toán, không tăng tolerance tùy ý để pass.
- Completion exact dùng **cùng target vectors và tie-break** nên IDs/rank phải trùng, ARR1. Live re-encode có numerical variation thì check embedding tolerance và ties separately, không quy mọi mismatch là ANN.
- Brute-force weighted max coverage trên toy nhỏ≤12 docs dùng enumerate; lazy/eager phải cùng selection với deterministic tie. Guarantee objective của fixed F, không test nDCG phải tăng mọi batch.

## Integration gates theo thứ tự

1. **Environment:** server GPU visible đúng H10080 hoặc báo discrepancy; CPU/RAM effective limits; dependency/model pooling smoke.
2. **HF tiny sync:** private test bundle có config + tiny safetensors + npz→upload→verify→restore/load; mock test không thay live result. Giữ tiny repo trong pool, không tự xóa để dọn.
3. **FiQA exact:** small subset, accessor audit, complete100% exact, learned map saved/loaded và resumed cùng batch IDs.
4. **T0.core:** core M05–M08 implementation + bounded lr validation/CAL/INDEX/RUNTIME theo M14; profile local-verified trước official. ANN ≥0.99 trên Q_tune/cùng stored snapshot; gate fail chặn ANN branch, exact branch có thể tiếp tục. Calibration thiếu giữ N/A/fallback đúng rule.
5. **FiQA full/TREC/E3:** official output per-query sau scope tương thích, không test leakage; fidelity/update/lock/cadence/cost measurements với settings freeze. Không yêu cầu positive-effect để pass.
6. **T0.scale và E4:** download/ingest/model validation → 100k one-seed timing/estimate → freeze common 50k/5k manifest → reduced-pool probe → actual reduced-pool bootstrap stored-graph fidelity/footprint trước E5. Không tự cho full scale PASS từ subset.
7. **E6/E7 case readiness:** validate inputs, scope T0/runtime đúng pair/corpus; temporal tuning chỉ tuần1, no-Q_tune transfer/N/A ghi rõ. Không đòi một seed/model probe đại diện toàn matrix.
8. **Full/temporal/matrix:** required cells count + endpoint/split + synced artifacts; không chỉ one passing run chứng minh whole stage.

## Checklist update contract

Code `progress.py`:

```python
def update_checklist(project_root, task_id, result) -> None: ...
def mark_module_complete(project_root, module_id, verification_summary) -> None: ...
def reconcile_stage_checkboxes(project_root, stage_id, run_registry) -> None: ...
```

Resolve **PROJECT_ROOT/checklist.md**, một writer lock, read/replace đúng ID markers, temp file+atomic rename. Giữ text user ngoài block managed. Không hard-code user drive cho server. Mỗi finalized run cập nhật compute checkbox và trạng thái sync trên dòng của nó; verified callback cập nhật sync URL/revision. Stage có hai checkbox compute/sync tổng; chỉ tick khi toàn required cells/gates tương ứng đã xong. Có thể thêm `<details>` cho nhiều run rows, nhưng một file root vẫn là nguồn user theo dõi.

Module M01…M14 tick sau khi code và test liên quan đã pass. E0…E7/T0/SMOKE-TIME chưa chạy thì để `[ ]`. T0.core và T0.scale riêng; T0.compute tổng chỉ khi required core+scale đủ, T0.case bổ sung theo run registry. Negative scientific result vẫn compute complete nếu technically valid; missing E6 data để blocked chứ không tick. Queued/pending/uploading không tick synced.

## Kết thúc từng lượt agent

Agent báo ngắn: module/run đã xong, test/gate thật, số compute/synced cells, task tiếp theo. Không tạo report/evidence Markdown riêng sau mỗi test. Lỗi blocking chỉ ghi reason ngắn và file/log cần xem; không log token/raw private query text.
