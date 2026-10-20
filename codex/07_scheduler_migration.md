# M07 — Scheduler, bootstrap và backfill loop

Code `scheduling.py`, `migration.py`. Đây là module nối dữ liệu, models, maps, calibration, index và evaluator. Không RL, không reward training.

## Công thức cần giữ

Với một snapshot cố định, query scheduling q có top10 và rank11 đã calibrated:

```text
beta(q,d) = score(q,d) - score(q,rank11)
A(q) = mapped, relevant-proxy docs trong top10 và r < beta <= 2*r
R = queries có A(q) khác rỗng và không có relevant-proxy doc top10 slack > 2*r
F(T) = sum_{q in R} w_q * 1[A(q) intersects T]
gain(d | T) = sum_{q in R: d in A(q), A(q) intersects T empty} w_q
```

Proxy từ click/qrels **training/scheduling side**. Nếu không có click proxy thì served-top10 fallback phải có nhãn, không dùng evaluator qrels. True docs không được chọn; nhưng một true relevant-proxy có slack>2r vẫn có thể khiến query không thuộc R. `T` chỉ là documents đang chọn trong batch, reset sau mỗi snapshot. r/a/b/A/weights không đổi giữa lúc chọn một batch.

## Hàm scheduler

| Hàm | Cần code |
|---|---|
| `build_candidate_sets(search_results, proxies, fidelity, r, weights)` | Tính beta, A/R, reverse doc→queries bằng array/list gọn; không lưu mọi topL ra disk |
| `marginal_gain(doc_row, covered_queries, candidates) -> float` | Đúng weighted coverage, không cộng query đã covered |
| `select_greedy(candidates, cap, mapped_mask, rng, lazy=True)` | Eager correctness trước; lazy heap dùng key(-gain,original_doc_id), recheck upper bounds trong fixed snapshot; gain>0 rồi random fill |
| `select_random(mapped_mask, cap, rng)` | Seeded permutation không hoàn lại; state/RNG resume được |
| `select_degree(schedule_edges, mapped_mask, cap)` | Rank số neighbors unique trong scheduling sample, tie ID; không đọc heldout |
| `select_on_read(ordered_queries, search_fn, cap, queue_state)` | Traverse query order khóa, enqueue mapped top10 lần xuất hiện đầu, dedup và cap; exhausted fallback có reason |
| `select_uncertainty(global_map, regional, eligible_rows, cap)` | Disagreement global/regional theo config paper; không nhìn true residual chưa paid |
| `choose_batch_cap(state, checkpoints, refit_boundary) -> int` | Min1%N, mapped_remaining, remaining paid budget, distance tới checkpoint và refit boundary |

Không thể dùng gain chỉ theo tần suất doc rồi gọi coverage greedy. Example test A(q1)={d1,d2}, A(q2)={d1}, A(q3)={d3}: chọn d1 phủ q1/q2 thì gain d2=0, d3 vẫn phủ q3. Sau commit/search snapshot mới, phải tính lại; q1/q2 không được coi được cứu vĩnh viễn.

## Hàm orchestration

| Hàm | Thực hiện / gọi tới |
|---|---|
| `bootstrap_migration(data, splits, X_old, accessor, cfg)` | Allocate train/val→request y→common OP cal proposal→request cal targets→freeze pools; fit M0/regions/regional/cal; paid docs true, còn lại mapped; build index |
| `refresh_scheduling_snapshot(state, traffic)` | Cache h(q) đã biết, search **toàn bộ Q_schedule của run**, tạo A/R/gain mới; không chỉ affected queries |
| `prepare_backfill(state, selected_rows, accessor)` | Validate eligible/cap→live/cached request→prepare true vector writes, pair deltas; encode không phải remap |
| `commit_backfill(state, prepared)` | Index writer commit, vectors/fidelity/epoch thống nhất; update paid/backfill IDs và regional pairs hợp lệ |
| `maybe_refit_and_remap(state)` | Sau mỗi5%N mới backfill, fit touched regions, remap **mọi vẫn-mapped doc trong vùng**, rescore/refit cal fixed pairs, writer commit |
| `emit_checkpoint(state, target, evaluator_callback)` | Atomic complete checkpoint, metrics/cost evaluation, enqueue auto-sync; không đổi scheduler từ test metric |
| `run_migration(state, traffic, checkpoint_targets, evaluator_callback, cfg)` | Main loop, lựa chọn scheduler, batch/refit/checkpoint/stop; trả RunResult để M09 finalize một lần |
| `restore_migration(checkpoint, immutable_inputs, cfg)` | Validate config/cache IDs, load RNG/pending stats/index; tiếp tục đúng boundary |

Bootstrap pools do data module chọn IDs, OP proposal do map/calibration module tính; migration giữ thứ tự để không có dependency vòng data→map→data. `SplitBundle` ban đầu chỉ train/val và query pools; cal pair/doc IDs được finalize một lần khi OP proposal có vectors rồi freeze chung cho variants/seeds.

## Main loop cần code

```python
state = bootstrap_migration(...)
emit_checkpoint(state, "bootstrap", evaluator)
while not complete_or_budget_exhausted(state):
    cap = choose_batch_cap(state, targets, next_regional_boundary)
    if cap <= 0:
        process_reached_boundary_or_stop(state)
        continue  # chỉ khi boundary/count thật sự tiến lên
    if scheduler == "greedy" and radius_is_valid(state):
        candidates = refresh_scheduling_snapshot(state, traffic)
        selected = select_greedy(candidates, cap, ...)
    else:
        selected = select_locked_baseline_or_labeled_fallback(...)
    prepared = prepare_backfill(state, selected, accessor)
    commit_backfill(state, prepared)
    maybe_refit_and_remap(state)
    if checkpoint_reached(state):
        emit_checkpoint(state, target, evaluator)
return migration_result(...)  # M09 sở hữu finalize_run và cuối-run sync/checklist hooks
```

Boundary xử lý một lần và advance marker; batch rỗng/no progress → stop reason, không continue vô hạn. Refit kiểm theo **backfilled count** chứ không accessed count/bootstrap hoặc số loop. Regional H/B không nhận lại train pairs lúc mỗi refit; validation/calibration tuyệt đối không thêm vào train.

Checkpoint primary: bootstrap,5/10/25/50% total accessed và100% true; target=floor(f*N), bỏ checkpoint thấp hơn bootstrap. Batch có thể nhỏ hơn1% để chạm đúng target. Primary10% accessed không phải10% scheduled cộng thêm bootstrap. f_true=f_accessed sau commit thành công; log cả3 trục.

Ở refit, M0/region freeze. Remap tính từ old x, không encode h; write amplification có thể lớn dù batch1%. Primary không final-flush ngoài lịch ở25%/10%; pending sufficient stats phải nằm trong resume state. True docs không bị remap ghi đè.

## Temporal branch

`run_temporal_replay` dùng cùng bootstrap/map/update primitives. Tuần t xây traffic từ history≤cutoff, thêm tối đa1%N scheduled, đánh giá future tuần t+1. Có7 decisions cho8 tuần; primary tuần8 ở7% scheduled. Weights/gain không thấy future event hoặc cold query text trước thời điểm. Scheduler selection phụ thuộc lịch sử, evaluator đọc future riêng.

Cost được tách bootstrap/search/heap/encode/refit/remap/graph/lock/checkpoint. Baseline random không phải refresh heap100k queries vô ích; measurement tính overhead thực sự cần. Coverage guarantee1−1/e chỉ cho fixed F/count budget toy; không gán cho adaptive retrieval hay toàn migration.
