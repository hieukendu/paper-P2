# M14 — Pre-setup, tuning có giới hạn và khóa cấu hình

Đây là đặc tả **cần code và chạy**, chưa phải kết quả tối ưu đã đo. T0 chuẩn bị pipeline trước từng nhóm thí nghiệm; không đổi giả thuyết E0–E7. Tối ưu ở đây là chọn trong một grid phát triển có giới hạn và đạt các gate kỹ thuật, không phải tìm optimum toàn cục hoặc lặp đến khi greedy thắng.

Đọc `report.md`, `expect.md`, M03–M08 và M10–M12 trước khi triển khai. Code các hàm dưới trong `experiments.py`, `config.py`, `runtime.py` hiện có; không tạo tuning service, Optuna framework hoặc một bản migration loop khác.

## Thứ tự và phạm vi T0

Mọi case phải đi qua: **tải model → tải dữ liệu → validate/preprocess/splits → model smoke → development tuning/timing → freeze profile → thí nghiệm chính thức**. Model/data downloads có thể overlap; validation phải hoàn tất trước mọi inference/tuning phụ thuộc chúng. Chuẩn bị từng nhóm dưới, không bắt tải cả tám checkpoint/năm BEIR/AOL trước smoke đầu tiên.

| Scope/task ID | Inputs phải sẵn sàng | Cho phép mở bước nào |
|---|---|---|
| `T0.core` | FiQA đầy đủ và MiniLM/MPNet; E0/E1 đã qua; LA/MLP, regional/calibration, scheduler, HNSW và acceptance code đã có | E2 exact trên FiQA; E2 ANN/E3 cần thêm ANN profile PASS |
| `T0.scale` | E3 correctness; Arctic snapshots; MS MARCO documents v1 + ORCAS đã ingest/validate; subset 100k cố định | E4 trên subset; E5 còn cần gate full-corpus tại E4 |
| `T0.case.<dataset>.<pair>` | Inputs thật của case E2 bổ sung/E6/E7 đã validate; core code dùng lại | Case tương ứng, sau các dependency E3/E4 nếu có |

`T0.core` không phụ thuộc E2/E3/E4; nó dùng implementation M05–M08 đã code trước khi chạy các E đó. `T0.scale` không phụ thuộc E4, và T0.case không phụ thuộc chính E đang chuẩn bị. T0 cho TREC dùng document train/validation để chọn lr; không có Q_tune thì search kế thừa FiQA cùng pair với nhãn `UNTUNED_TRANSFER`. AOL chỉ dùng document pools và query/history tuần1. Case thiếu corpus thật là `BLOCKED_DATA`; không block các case độc lập đã đủ inputs.

## Quyền sử dụng dữ liệu

- Mỗi scope dùng `master_seed=20261020`, `map_seed=17`, `traffic_seed=101`; không tìm seed đẹp. Repeats timing dùng cùng seed, không được gọi là nhiều seed độc lập.
- Chỉ `P_train` fit map; `P_val` chọn checkpoint/lr; `cal-fit` fit a/b; `cal-check` tính r; `Q_tune` chọn search fidelity. Không chọn lr hoặc bỏ regional/calibration theo cal-check, test qrels, held-out ARR/nDCG hay future events.
- Map tuning của một case dùng đúng train/val IDs theo N thật của case, qua paid accessor. Tất cả lr candidates dùng cùng pairs; không thêm target ngoài bootstrap để chọn lr. Validation không nhập train sau khi chọn. Subset timing là probe runtime riêng, không dùng quality trên subset để chọn map cho full corpus.
- Nếu chưa có old corpus cache, map-grid chỉ encode old rows cần cho train/val. Full old-corpus encode chỉ bắt đầu sau encoder batch smoke/probe khả thi, dùng streaming một lần; không bắt encode hàng triệu rows trước khi biết adapter/batch đúng. Subset runtime có pools/state riêng theo N subset, được ghi research cost và không chọn hyperparameter khoa học cho full case.
- Test text có thể được data layer đọc để loại query overlap theo quy tắc đã khóa; test relevance/results chỉ evaluator đọc sau freeze. T0 không xuất test comparison rồi quay lại tuning.

## T0-MAP và T0-CAL

1. Fit OP control một lần. Với residual MLP và LA, thử đúng `lr={1e-4,1e-3}`; giữ kiến trúc, batch256, tối đa50 epoch, patience5, min_delta1e-5, loss mean của tổng squared vector error **trước normalize** theo M05. Encoder frozen. Reset cùng initialization/RNG cho hai lr; lr là biến duy nhất thay đổi trong mỗi map kind.
2. Với từng map kind, lấy checkpoint có validation loss thấp nhất của mỗi lr; chọn lr có loss thấp nhất trên **cùng P_val**. Tie số học trong min_delta1e-5 ưu tiên default1e-3. Candidate nonfinite/zero output bị đánh FAIL, không nhận điểm giả. Nếu không có learned candidate hợp lệ, sửa lỗi và giữ scope chưa PASS.
3. Lưu lr đã chọn theo dataset/pair/map kind. Official seeds17/29/43 dùng **cùng lr đã chọn**, nhưng fit weights/checkpoint của chính seed đó; không chạy grid lại để chọn riêng cho mỗi seed/scheduler. OP/LA là controls; primary vẫn residual MLP. Ghi `lr_selection=validation_grid_v1` để phân biệt với bản default1e-3 lịch sử trong report.
4. Giữ R theo công thức, ridge10, nmin20, refit mỗi5% N mới backfill, radius quantile P95 và batch backfill tối đa1% N. R256/lambda sweep/P90/P99/cadence1%/10% là ablations đã khai báo, không dùng test để chọn primary. M0/region assignment chỉ được freeze sau bootstrap của từng run.
5. Fit a/b trên cal-fit, tính r trên cal-check bằng shadow mapped vectors của paid docs. Giữ nguyên rules sample-count/numerical fallback ở M05. `insufficient_calibration`, r=N/A hoặc rescue band rỗng là trạng thái dữ liệu cần báo, không sửa r/pool/seed để có gain. Không yêu cầu greedy thắng hoặc loss phải dưới một ngưỡng quality tự đặt để T0 PASS.

## T0-INDEX

Chạy grid `(50,200),(100,200),(500,1000),(1000,2000)` trên Q_tune và bootstrap stored snapshot của **đúng case/corpus**. Chọn L nhỏ nhất đạt mean candidate recall@11 và serving recall@10 ≥0.99; tie chọn ef nhỏ hơn. M16/efC200 giữ nguyên. Các scheduler trong cùng comparison dùng chung search profile; nếu comparison có nhiều map variants, cặp chọn phải đạt trên các bootstrap variant đã khai báo, không cấp L riêng cho variant thuận lợi.

HNSW trên FiQA/subset 100k không chứng nhận recall cho full MS MARCO hoặc model pair khác. E4 phải build actual full bootstrap graph rồi kiểm Q_tune trên snapshot đó trước E5; exact reference ở gate này dùng **stored vectors**, không target chưa paid. Những map seed còn lại được kiểm với settings đã freeze trước khi đọc test; gate fail không được âm thầm đổi settings riêng cho seed đó. Một sửa đổi development cần profile/version mới cho toàn comparison liên quan.

E4 readiness tasks chỉ cần T0.scale input/lr/runtime/subset profile và resource reservation cho target size; **không yêu cầu full-corpus ANN profile mà E4 đang tạo**. E4 không đọc official quality để chọn; sau full-bootstrap gate nó publish một search profile entry mới cho full corpus, giữ nguyên subset entry. E5 mới bắt buộc full entry PASS. Preflight các bootstrap map seeds/variants trong comparison trước khi mở test của comparison đó; lỗi sau khi đã xem test không được dùng để retune rồi thay kết quả cũ.

Không có Q_tune hợp lệ: kế thừa profile FiQA cùng pair như M06, ghi `UNTUNED_TRANSFER`; exact evaluation vẫn hợp lệ, ANN fidelity của case chưa được chứng nhận. Không coi N/A/transfer là PASS0.99. ANN_GATE_FAILED chặn task ANN phụ thuộc; exact tasks đã qua correctness vẫn được chạy với nhãn exact. Không mở rộng grid/M/efC sau khi xem test để cứu kết quả.

## T0-RUNTIME / SMOKE-TIME

- Dùng E1 FiQA2,000 completion/resume output cho timing flow, không bắt chạy lại cùng E1 nếu code/config không đổi. Không tự tick E1 chỉ từ một benchmark primitive.
- Với `T0.scale`, cố định uniform100,000 document IDs seed20261020; ORCAS lấy uniform tối đa10,000 groups trong **scheduling pool**, không held-out. Restrict edges vào subset, báo join/candidate-empty/calibration sufficiency và số group thật; không chọn chỉ query có gain cao để làm probe thuận lợi.
- Bốn scheduler greedy/random/degree/read chạy độc lập từ cùng bootstrap với seed17/101 đến10% **total accessed**. Tiếp tục **greedy đã định trước** đến25% accessed để đo nhiều refit/remap, giữ nguyên prefix/RNG. Nếu greedy bị fallback do r/candidate thiếu, ghi rõ probe đo fallback; chưa được coi là đo chi phí greedy với gain thật.
- Probe encoder g/h bằng sample uniform cố định của corpus thật, gồm short/median/long lengths; đúng native limit, prefix, pooling và float32. Thử batch `[1,2,4,8,16,32,64]` trong headroom M10; bắt đầu8, giảm khi OOM, không cắt token limit để vừa VRAM. Batch OOM chỉ là probe failure, giải phóng resources trước candidate sau.
- Sau warm-up, đo cùng sample ba lượt mỗi candidate khả thi. Chọn median throughput cao nhất trong các candidate qua finite/norm/tolerance và headroom; tie chọn working set nhỏ hơn. Worker/thread grid `[1,2,4,8]` bị chặn bởi CPU quota; chunk/shard từ default1GiB, chỉ thử thêm khi I/O/RAM probe chỉ ra bottleneck. Không tuning mọi tổ hợp Cartesian.
- Runtime tối ưu padding/bucketing/batching phải giữ ID alignment và embedding agreement trong tolerance đã khóa. Khác dtype, max tokens hoặc pooling là variant riêng, không tự đổi primary. Official performance dùng profile đã freeze và measurement exclusive.
- Tách timer download/ingest, old/new encode, map/calibration, index build, query encode/search, gain/heap, direct backfill, regional solve/remap, HNSW update, lock/stall và checkpoint. Đo VRAM/RSS, docs/s, nonpad/padded tokens/s, actual length distribution và bytes written. Upload/verify/restore đo riêng sau compute window; không bỏ chúng khỏi wall-time hoạch định.
- Default concurrency1. Chỉ cho2 sau probe memory/CPU/disk và joint throughput thực sự; không lấy thời gian một job chia2 để giả speedup. Systems/cost measurements vẫn exclusive.

## Ngoại suy thời gian và điểm dừng

`estimate.json` dùng số đo từ `timing.json` và encoder/storage probes, ghi nguồn từng hệ số và nhãn `measured`/`estimated`/`unmeasured`. Một seed chỉ tạo estimate sơ bộ, không CI đáng tin cậy cho toàn seed grid.

```text
T_shared = download + ingest + sum_encoder(length-bucket tokens / measured tokens_per_second)
           + query/reference preparation dùng chung
T_cell   = bootstrap_fit + mapped_build + sum_batch(search + select + backfill_encode_or_lookup + direct_update)
           + sum_epoch(regional_solve + remap + graph_update) + checkpoint + evaluation
T_serial = T_shared + sum(required_cells T_cell) + final_upload_verify
```

Không tính full target cache/old encode lại60 lần nếu cache dùng chung; cũng không bỏ mọi build/mutable-index copy hay100k-query refresh của từng run. E5 có60 primary cells (`4×3×5`), cần forecast riêng đến10% accessed và phần continuation25/50/100% true. Graph build/update và regional solves không được mặc định scale tuyến tính từ100k đến3.21M; E4 cập nhật bằng full-bootstrap measurements trước khi launch60 cells. Dùng ranges từ repeats/length buckets và ghi phần chưa đo, không bịa một hệ số an toàn hay GPU-hour.

Nếu reuse immutable bootstrap templates theo map seed, training/build chuẩn bị chung được đếm đúng số lần trong T_shared; T_cell dùng clone/load/copy cost thật. Per-run migration comparison vẫn báo bootstrap cost theo cost mode đã khai báo; không gọi clone lookup là measured fit/encode. Live h(d) của từng backfill được tính trong T_cell; cached-access chỉ có lookup cost và estimated live cost ghi riêng.

E7 cần sample encoder/runtime của **mỗi pair trên từng corpus thật**, và actual TaskSpecs để đếm mapping/scheduler/ablations; không nhân thời gian Arctic cho cả20 cases. Có thể reuse đúng profile/input hash. E6 recovery time ghi riêng; chưa có source thì `BLOCKED_DATA`, không đặt một deadline giả. Scheduling forecast cho concurrency2 chỉ dùng throughput đã co-schedule đo được; nếu chưa đo, dùng serial estimate.

Dừng tuning khi grid hợp lệ đã được đánh giá, chọn được candidate finite/feasible theo quy tắc trên, correctness/resume/restore pass và đủ timing/estimate cho scope. Không chạy thêm search chỉ vì quality chưa đẹp. Nếu sửa bug hoặc đổi inputs/hardware/adapter làm profile mất hiệu lực, tạo T0 scope revision mới; giữ outputs cũ và rerun phần bị ảnh hưởng. Sau khi đã xem test, thay đổi khoa học thuộc một study revision/exploratory riêng, không thay thế âm thầm kết quả official cũ.

## Freeze, API và wiring

`configs/locked/tuning.lock.yaml` chứa policy/version/hash và các **profile entries** theo dataset/pair/map kind/runtime/search corpus. `state/tuning_manifest.json` chỉ là index tới run/profile/hash/gate status; metrics nằm trong summary/tables của run T0, không sao chép thành evidence reports. Thêm profile mới không sửa nội dung/hash profile đã freeze. Dùng writer lock + atomic merge để hai scoped tasks không ghi đè entries của nhau. Official task tham chiếu entry hash, không phụ thuộc whole-file hash sẽ đổi khi thêm case mới.

T0 run ID sinh từ inputs/policy/grid/seed trước selection; profile hash sinh sau selection, không hash chính trường hash của nó. Official run ID sinh từ resolved config và profile reference. Không tạo vòng tham chiếu T0 run ID ↔ selected profile hash.

| Hàm cần code | Input → output và nơi gọi |
|---|---|
| `build_presetup_tasks(scope, cfg)` | Tạo T0 TaskSpecs với model/data/validation dependencies và không có cycle; M09 gọi |
| `run_presetup(task, inputs, cfg)` | Gọi M05 fit, M06 fidelity, M01/M10 runtime probes; ghi result/timers rồi dùng finalize/sync chung |
| `select_map_hyperparameters(train, val, grid, seed)` | Fit candidates và trả selected lr + table loss/status; chỉ nhận paid train/val, không evaluator |
| `estimate_experiment_time(task_specs, probes)` | Đếm required cells, shared cost, primary/continuation, measured/estimated parts; không chạy test để tối ưu |
| `freeze_tuning_profile(scope, selections, input_refs)` | Publish immutable profile entry và reference index sau local gate; trả profile hash |
| `load_tuning_profiles(path) -> dict` | Đọc lock, xác minh policy/profile hashes và references trước khi worker dùng; config.py sở hữu |
| `validate_tuning_profile(task, cfg, profiles)` | Cả queue admission và run_single kiểm input/policy/profile hash, allowed overrides và gate của đúng branch |

Phân biệt **policy hash** (quy tắc chung), **profile hash** (lr/search/runtime đã chọn cho case) và **run config hash** (dataset, seed, method, endpoint, mode…). Run config hashes phải khác khi đổi seed/scheduler; chỉ phần settings dùng chung trong cùng comparison phải khớp. Ablation overrides được allowlist trước, có variant ID và hash riêng; không bị từ chối chỉ vì khác primary trên đúng tham số đang ablate. Weights M0/a/b/r và map epochs vẫn fit/cập nhật trong mỗi run, không đóng băng tất cả weights từ T0 cho mọi E.

Mỗi official task phụ thuộc **task ID T0 tương thích cụ thể**, ví dụ `T0.core` hoặc `T0.case.fever.bge`, cùng các E gates đã quy định. Enqueue được phép trước khi dependency xong nhưng admission/worker phải chặn execution; public run không bypass. Development outputs có `phase=development`, official có `phase=official`; aggregate kết quả khoa học chỉ lấy official cells.

Tick `T0.compute` tổng khi core+scale scopes bắt buộc đã compute-done; scopes E7/E6 được thêm và theo dõi trong managed run block khi inputs sẵn sàng. Task E2 chỉ cần core/case tương ứng, không chờ AOL hay full E7. Tick `T0.sync` khi mọi bundle T0 bắt buộc đã verified; pending upload không làm mất local gate hoặc bắt retrain. Tick M14 sau khi các hàm/gates/test có implementation, không tick chỉ vì tài liệu này đã viết.
