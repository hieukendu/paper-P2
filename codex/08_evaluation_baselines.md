# M08 — Evaluation, baselines và thống kê

Code `evaluation.py`, `baselines.py`; đọc bắt buộc `report.md` mục9/10/15.7 và `expect.md`. Không dùng test metrics để chọn scheduler/map/siêu tham số.

## Evaluation functions

| Hàm | Logic cần code |
|---|---|
| `build_reference(data, h_vectors, eval_query_vectors, cfg)` | Full-new **exact** top10 bằng evaluator-owned targets, plus old/old reference; research cost riêng |
| `evaluate_snapshot(snapshot_reader, eval_inputs, reference_reader, cfg)` | Score đúng eval IDs, lưu per-query metrics và retrieval run; không chuyển labels/reference về migration |
| `ndcg_hit_nfr(rankings, qrels, reference)` | Absolute nDCG@10, Hit@10, unconditional NFR@1; denominator policy bên dưới |
| `agreement_at_10(rankings, full_new_exact, weights=None)` | overlap set/10, weighted normalized mean khi temporal |
| `ann_fidelity(ann_output, exact_stored_output)` | Raw ANN recall, candidate recall@11 và serving recall@10 riêng |
| `quality_auc(checkpoint_metrics, x_bounds)` | Trapezoid theo accessed, explicit bounds; retained% chia100, ARR đã0..1 thì không chia100 lần nữa |
| `paired_analysis(per_query, contrast_spec)` | Query-average qua seed cells, paired bootstrap/sign-flip, Holm đúng family |
| `theory_diagnostics(snapshots, evaluator_targets, cfg)` | Slack residual/exceedance, rescue precision/coverage; chỉ evaluator offline, không feedback scheduler |
| `aggregate_runs(run_dirs, output)` | Official tables chỉ lấy phase=official, đúng case/profile/variant/endpoint; thiếu cells/failed ghi rõ. Development/timing bảng riêng, không trộn T0 vào quality evidence |

Dùng evaluator chuẩn `pytrec_eval` (dependency được lock; có thể dùng distribution `pytrec-eval-terrier` cung cấp import này) cho nDCG; test khớp hand-computed case/standard fixture. Query IDCG=0 giữ nDCG0 và báo count. So metric theo **ranking đã tie-break ID**, có thể truyền monotonic rank scores cho evaluator để không đảo tie. `retrieval.trec.gz` ghi score `-rank` nếu dùng cách này và khai báo là rank score, không giả đó là cosine.

```text
retained_nDCG = 100 * mean(ndcg_mix) / mean(ndcg_full_new)
ARR@10 = mean(|top10_mix intersect top10_full_new_exact| / 10)
NFR@1 = count(full_new_top1 relevant AND mix_top1 nonrelevant) / all_eval_queries
```

Mean reference0 thì retained=N/A, không drop query để né mẫu số. Retained>100% hợp lệ, không clip hoặc ép curve tăng. Full-new là target reference, **không bảo đảm là upper bound relevance**; old/old cũng không bảo đảm thấp nhất. At100% true, exact ranking phải khớp full-new; HNSW graph có thể khác fresh HNSW và cần đo riêng.

## Baseline adapters

So representation trước backfill và so scheduler trong migration là hai bảng khác nhau.

| Hàm/baseline | Input/output và implementation |
|---|---|
| `run_old_reference` | g(q) với old X, không map; báo absolute old quality |
| `run_full_new_reference` | h(q) với true Y full exact; khi so **migration cost** tính đầy đủ encode/build |
| `run_misaligned` | h(q) với old X chỉ khi dim bằng nhau; dim khác ghi N/A, không dot product sai chiều |
| `fit_query_side_adapter(kind, paired_XY, validation)` | Fit chiều ngược Y→X, src_dim=d_new/target_dim=d_old cho OP/LA/MLP; OP dùng padding/cropping hai phía ở M05, learned maps đổi input/output shapes; h(q)→old-space, không lấy inverse forward MLP |
| `run_forward_mapping(kind, regional, calibration)` | M0(X)→new-space; cùng bootstrap paid docs true và map/refit/index policy |
| `run_dual_index` | g(q)/old index + h(q)/migrated new docs, merge calibrated candidate union; hai query encoders và cả2 index cost ghi riêng |
| `run_hindsight_oracle` | Evaluator biết future ranking/residual; diagnostic label; không đưa oracle vào online pipeline, không gọi optimum retrieval |
| `run_qdc_adaptation` | Chỉ dim-compatible hoặc adaptation có công thức/source rõ; log adaptation, không tuyên bố nguyên bản khi tự thêm projection |
| `fit_minivec2vec_baseline` | Published unpaired method, cả new vectors60k phải charge; tách published-budget khỏi matched-budget |
| `fit_relative_representation_baseline` | Published anchor method, charge anchors và query transforms; anchor IDs/selection freeze |

Đối với QDC/mini-vec2vec/relative representations, agent phải đọc implementation/paper gốc được dẫn trong report/PDF rồi khóa recipe: input spaces, objective, anchors/unpaired count, training split, inference transform. Việc này là một task cụ thể của E7 baseline module; không thay bằng một MLP giả chỉ để đủ tên hàng. Nếu chưa xác minh recipe/source, giữ cell `UNIMPLEMENTED_SOURCE_RECIPE` và **không tick complete-baselines**. Chỉ các core OP/LA/MLP + schedulers cần để E1–E5 hoạt động; không block smoke vì baseline phụ chưa làm.

Drift-Adapter published recipe dùng20k pairs khác primary allocation: matched-budget dùng đúng pools chung; published reproduction là bảng riêng. Raw baseline results không cùng ngân sách không được gộp một ranking “best”.

## Statistics đã khóa

- Map seeds17/29/43; traffic101/103/107/109/113; eligible scheduler study đủ3×5 cells. Pilot1 seed17 chỉ debug; không gọi15 cells là15 iid replications.
- Static primary greedy−random, greedy−degree, greedy−re-embed-on-read ở **10% total accessed**. ORCAS ARR@10; BEIR eligible scheduler case absolute nDCG@10. Mapping-only/no-traffic cases không có scheduler contrast.
- Fixed eval IDs. Tính mean per-query method score qua seed cells rồi bootstrap10k query-group draws, seed20261020, CI95% paired difference; ratios phải recompute tử/mẫu mỗi draw.
- Two-sided paired sign-flip10k draws, p=(1+count(|T_random|≥|T_observed|))/10001; Holm correction trong3 contrasts của **một dataset/model/endpoint**. Báo p raw/adjusted, effect và CI. Không chọn contrast có lợi sau test.
- AOL dùng block user (opaque cluster IDs) và day sensitivity, event-weighted metrics;7 future weeks chưa là bằng chứng dài hạn.
- Claim “greedy thắng cả3 baselines” cần cả3 contrasts hỗ trợ; chỉ thắng random thì kết luận đúng phạm vi đó. Significance không thay thực dụng: không có practical-effect margin đã khóa thì báo effect/cost, không tự đặt ngưỡng sau khi xem kết quả.

Không cần tạo statistical audit riêng 11 trang khi chưa có runs. Per-query output, một contrasts table và seed variation table đủ để phân tích; checklist bias thiết kế trong report là nguồn đọc, không nhân bản thành provenance.

## Costs và systems workload

`cost_scope` aggregate bootstrap/kmeans/maps/build, query encode/search, heap, live h, regional solve/remap/graph writes, checkpoint I/O và lock waits. Unique docs không bằng total tokens/GPU time. Evaluator/reference cost và migration cost tách nhau; encoder cache lookup là cached, không GPU time measured.

Old corpus encoding/index được giả định đã tồn tại trước migration: nếu phải tạo để nghiên cứu thì ghi setup/research cost, không charge lại mỗi scheduler như chi phí upgrade. Đồng hồ migration bắt đầu **trước** sample/OP proposal/train/calibration/bootstrap và chỉ dùng các component thật của migration. Full-new evaluator và offline metric computation có timer riêng; query encoding phục vụ/scheduling thuộc migration cost dù không tăng document-accessed fraction. Full-rebuild comparison vẫn tính new-corpus encoding/build đầy đủ.

E3 systems:16 workers là client concurrency, không phải16 CPU cores được cấp. Open-loop Poisson arrival schedule độc lập service time; warmup30s, measure120s,3 repeats; loads25/50/75/90% measured no-update capacity,110% riêng stress. Deadline1s, queue cap10k. Report offered/achieved QPS, queue/service/end-to-end latency, timeouts/rejected/stall và success denominators. Primary performance chạy **exclusive**, không vừa sync HF hoặc chạy job khác.

Nhận module khi metric fixtures, same-reference ARR1, ratio-zero policy, grouping/paired stats và source recipe status đều rõ. Kết quả âm hợp lệ được giữ và sync như kết quả dương.
