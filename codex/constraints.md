# Constraints: giữ đúng thí nghiệm và code vừa đủ

## Phạm vi

- Viết implementation cho protocol trong `report.md`/`expect.md`, T0 scoped prep theo [M14](14_presetup_tuning.md), chạy E0–E7 trên server A100 80GB, lưu kết quả và auto-sync HF. Encoder g/h giữ cố định; học map/calibration, scheduler không dùng RL.
- Giai đoạn hiện tại chỉ có tài liệu Markdown. Agent lần sau mới tạo code, config và thực hiện network/download/upload.
- Không viết lại paper; không thay placeholder trong PDF bằng số tự đặt. Không coi tài liệu thiết kế là bằng chứng đã chạy.
- Windows là máy chuẩn bị; pilot, encoder inference và benchmark đều chạy trên server. CPU fallback chỉ phục vụ debug có nhãn, không đại diện performance A100.
- Giữ dirty worktree và file người dùng. Không reset/clean, xóa corpus hoặc dọn checkpoints ở giai đoạn này. Upload trước; cleanup là việc riêng sau này.

## Không overengineering

- Một Python package `mixindex`, một CLI, YAML configs, subprocess queue một host. Dùng thư viện phổ biến; không Airflow/Ray/Celery/Kubernetes orchestration, web app, database theo dõi thí nghiệm, plugin framework hoặc event bus.
- SQLite của stdlib được phép dùng làm **index tra document/query trên disk** để không nạp corpus vào RAM; không dùng nó làm hệ thống provenance.
- Không viết class abstract cho mỗi thuật toán: dataclass cho state, hàm thuần cho công thức, một interface mỏng cho encoder/index/scheduler là đủ.
- Xây exact FiQA flow trước khi tối ưu. Không custom HNSW graph repair, distributed training, multi-node scheduler hay LLM generator trong primary.
- Một hàm chỉ có trách nhiệm rõ; không tách file chỉ có vài dòng nếu không giúp đọc hoặc kiểm tra. Tên hàm trong module docs là contract cần nối, không phải lý do để tạo hàng trăm wrapper.

## Provenance tối thiểu bắt buộc

Không tạo Material Passport cho từng module/run. Không lặp nhiều bản audit/evidence/provenance giống nhau. Chỉ giữ:

| Artifact | Nội dung và tần suất |
|---|---|
| `data/processed/<dataset>/manifest.json` | Một bản/release: source, checksum file tải, schema/counts, policy, split IDs/hash, license/source link |
| `cache/models/models.lock.json` | Một record/model revision: repo SHA, tokenizer/pooling/prefix/limit/dtype/dimension |
| `state/environment.json` | Một bản/môi trường: package versions, driver/CUDA, GPU, CPU/RAM cgroup; không dump hostname/UUID/SSH/env |
| `runs/<id>/config.lock.json` | Config đã resolve, seed, input references và code snapshot SHA; không secret |
| `runs/<id>/summary.json` | Status, gates, metric aggregates, costs, error reason; thay cho provenance.json riêng |
| `runs/<id>/metrics.parquet` và `retrieval.trec.gz` | Per-query/per-seed/checkpoint outputs đủ tính lại kết quả; không duplicate JSON/CSV cùng một bảng |
| `runs/<id>/events.jsonl` và `accessed_ids.npz` | Một dòng/batch hoặc map epoch, selection/refit/cost summary; ID pools và thứ tự backfill bằng mảng gọn |
| `runs/<id>/checkpoints/` | Learned state và checkpoint restart cần thiết; không lưu toàn bộ mọi minibatch |
| `runs/<id>/sync.json` | Manifest hash, repo/path/revision, file counts, verified/pending; một receipt, không copy token |
| `configs/locked/tuning.lock.yaml` và `state/tuning_manifest.json` | Một policy + immutable scoped profiles; reference index tới run T0. Selection/timing/estimate là outputs T0, không audit reports riêng |

`artifact_manifest.json` của gói upload chỉ liệt kê path/bytes/SHA256 cần kiểm upload; nó không phải hệ thống evidence mới. `stdout.log` có giới hạn dung lượng/rotate, chỉ ghi tiến độ batch/epoch/lỗi. Không ghi từng tensor, toàn top-L của 100k queries, toàn văn bản corpus hoặc mỗi HTTP request. Per-query metrics là dữ liệu kết quả nghiên cứu cần giữ; không cắt chúng để giảm provenance.

## Quyền truy cập và fairness

- Migration chỉ lấy vector mới qua `PaidEmbeddingAccessor`. Không truyền `Y_full`, test qrels hoặc future logs vào map/scheduler. Full-new references thuộc evaluator.
- So scheduler trên cùng bootstrap state, budget, map/refit/index policy, query split và evaluation IDs. Baseline chỉ chạy overhead nó cần; không ép random xây greedy heap.
- Global M0/regions đóng băng sau bootstrap. Primary chỉ refit regional mỗi 5% N newly backfilled, remap phần vẫn mapped của region nhận pair mới.
- Không đổi R, radius, seed, cutoff hoặc data window sau khi xem test để cứu kết quả. Negative result vẫn hoàn thành run nếu correctness/gates hợp lệ.
- Chọn checkpoint/lr MLP và LA bằng P_val theo grid/rule M14, giữ residual MLP là primary. a/b fit trên cal-fit; r tính trên cal-check; không dùng cal-check/test để chọn map hoặc bỏ regional/calibration. Các fallback chỉ vì điều kiện dữ liệu/số học đã khóa.
- Tuning có grid và điểm dừng trước official; development outputs không vào official aggregates. Queue/worker kiểm đúng T0 profile/input/policy hash; run hashes được phép khác theo seed/method/variant. Không cần tìm optimum hoặc bắt greedy thắng để chuyển bước.
- Hạ VRAM bằng batching/shard/cache được phép. Đổi dtype, token limit hoặc thuật toán là config variant, phải so quality trước khi dùng; primary float32 theo report.

## Secrets và upload

- Đọc `.env` đúng project root bằng `load_dotenv(..., override=False)`. `HF_TOKEN` là một biến trong `.env`, không phải tên file chứa token. Không in, ghi, yêu cầu dán lại hoặc upload nội dung token.
- `.env`, credential caches, SSH files, raw AOL event/query text và full upstream model/dataset copies không thuộc gói auto-upload mặc định. Upload learned map weights, configs, splits/IDs được phép, outputs và code cần tái lập.
- Dùng private HF dataset repos cho run bundles. Không tự public, đổi billing plan hoặc thuê GPU. Không tạo repo mới để né quota tổng tài khoản.
- Mọi run/checkpoint hoàn thành đều enqueue auto-sync; thiếu token/quyền/quota thì ghi pending, giữ file local, cho biết lỗi cụ thể. Không coi upload request thành công là verified trước khi kiểm remote files.
- Sau khi sync verified vẫn **không xóa local** trong đợt này. Không rewrite HF history hoặc xóa repo để giải phóng quota.

## Theo dõi hoàn thành

Checklist duy nhất là `PROJECT_ROOT/checklist.md` (ở Windows: `D:/paper-P2/checklist.md`, bên ngoài `codex/`). Runner cập nhật các marker có ID cố định và bảng run; không tạo một checklist khác ở ổ D hoặc thư mục typo `aper-p2`.

Một run có thể `COMPUTE_DONE` nhưng `SYNC_PENDING`; chỉ tick ô **đã sync** sau verify. Outcome `positive/negative/inconclusive` không quyết định tick compute. E6 unavailable ghi `BLOCKED_DATA` và để milestone chưa hoàn thành. Không dùng checkbox đã code để thay cho checkbox đã chạy.
