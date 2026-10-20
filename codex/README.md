# Hướng dẫn cho Codex triển khai thí nghiệm MixIndex

Bộ tài liệu này là đặc tả để **agent ở phiên sau viết code và chạy thí nghiệm**. Hiện chỉ soạn Markdown; chưa tải dữ liệu/model, chưa có implementation và chưa upload Hugging Face. Target chạy từ E0 đến E7 là **server A100 80GB**. Windows chỉ dùng đọc tài liệu, chỉnh code và chuẩn bị cấu hình.

**Agent bắt đầu tại file này**, rồi đọc đầy đủ report/expect và các file nền bên dưới. Luồng bắt buộc: inputs đã validate → E0/E1 correctness → T0 tuning/timing trong phạm vi hữu hạn → freeze profile → official experiments. T0 làm theo từng dataset/model; FiQA PASS không tự chứng nhận Arctic, BGE, Nomic hoặc full MS MARCO.

## Đọc theo thứ tự

1. **Bắt buộc đọc [report.md](../report.md) và [expect.md](../expect.md) trước khi code**: hiểu bài toán paper, các giới hạn bằng chứng, pipeline, baseline, primary endpoints và expected outputs của E0–E7. Không chỉ đọc tên thí nghiệm hoặc tóm tắt trong plan. Protocol chính nằm ở report mục8.3/15.
2. Đọc [constraints.md](constraints.md): giới hạn phạm vi, provenance tối thiểu và việc không được làm.
3. Đọc [structure.md](structure.md), [contracts.md](contracts.md), [plan.md](plan.md) và [14_presetup_tuning.md](14_presetup_tuning.md): cấu trúc, tên hàm, scoped gates, quy tắc chọn tham số, freeze và điểm dừng.
4. Sau đó chỉ mở thêm module đang triển khai trong bảng dưới; quay lại report/expect khi có lựa chọn ảnh hưởng phương pháp hoặc cách kết luận.
5. Sau mỗi module hoặc run hoàn tất, cập nhật [checklist.md](../checklist.md) ở **gốc project**, bên ngoài `codex/`. Khi checkout trên server, dùng đường dẫn tương đối `PROJECT_ROOT/checklist.md`, không hard-code ổ D.

| File | Công việc được giao |
|---|---|
| [01_environment.md](01_environment.md) | Linux/A100, dependency lock, config, `.env`, probe tài nguyên |
| [02_download_data.md](02_download_data.md) | Tải đúng BEIR, MS MARCO documents, ORCAS, AOL-IA và kiểm file |
| [03_preprocess_splits.md](03_preprocess_splits.md) | Parse, ID joins, text, query grouping, pools/splits và timeline |
| [04_models_embeddings.md](04_models_embeddings.md) | Tải 8 checkpoints, adapter, vector cache và encoder accessor |
| [05_maps_calibration.md](05_maps_calibration.md) | OP/LA/MLP, region, sufficient statistics, a/b/r |
| [06_index_serving.md](06_index_serving.md) | Exact/HNSW, calibrated top11, update và lock |
| [07_scheduler_migration.md](07_scheduler_migration.md) | A(q), gain, greedy/baselines, backfill/refit/remap |
| [08_evaluation_baselines.md](08_evaluation_baselines.md) | References, metrics, baseline adapters, statistics và cost |
| [09_experiments.md](09_experiments.md) | E0–E7, matrix, ablations, endpoints và gates |
| [10_queue_resources_resume.md](10_queue_resources_resume.md) | Queue tối đa 2 compute jobs, tài nguyên và resume |
| [11_huggingface_sync.md](11_huggingface_sync.md) | Auto-sync, nhiều repo, verify, retry và restore |
| [12_tests_acceptance.md](12_tests_acceptance.md) | Các test cần thiết và điều kiện nhận module |
| [13_runbook.md](13_runbook.md) | Chuỗi lệnh dự kiến để setup, chạy, resume và restore |
| [14_presetup_tuning.md](14_presetup_tuning.md) | T0.core/scale/case, validation selection, smoke timing, forecast và freeze profile trước official |

## Nguồn quyết định

- User đã chốt A100 **80GB**, không đổi target về Windows hoặc H100-MIG từ attachment cũ. Các giới hạn host phải đo trên chính server A100.
- Phương pháp chính theo `report.md` mục 8.3 và 15; `expect.md` giải thích mục tiêu từng E. T0 cụ thể hóa yêu cầu mới tối ưu trước official và lr grid validation đã có ở report15.3. E0–E7 vẫn là **8 milestone**; T0 là prep gate bổ sung.
- Các tài liệu ở đây cụ thể hóa implementation, không được thay đổi primary chỉ vì ablation thắng trên test. Nếu có chỗ chưa rõ, ghi một quyết định ngắn trong config/module đang làm; không tạo thêm chuỗi báo cáo audit.
- User đã yêu cầu auto-upload artifacts và tự tạo các repo tiếp theo. Khi triển khai có thể thực hiện trong namespace có quyền của `HF_TOKEN`; mặc định repo **private**. Hiện chưa có hành động external nào.

## Điểm vào cho phiên tiếp theo

Đọc theo thứ tự trên, kiểm trạng thái hiện tại bằng file thật và checklist; chưa có implementation thì triển khai M01/P1 trong plan. Không chạy một lượt download/training dài trước E1/T0 tương ứng. Không đánh dấu checklist hoàn thành thí nghiệm chỉ vì đã viết code hoặc tài liệu. Mỗi run có compute, sync và scientific outcome riêng.
