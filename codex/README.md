# Hướng dẫn cho Codex triển khai thí nghiệm MixIndex

Bộ tài liệu này là đặc tả để **agent ở phiên sau viết code và chạy thí nghiệm**. Implementation, prepared inputs, accepted E0–E7 bundles và verified uploads hiện đã có; xem checklist ở gốc project để biết evidence hiện hành. T0.core, T0.scale, các T0.case bắt buộc và các runner scale/temporal/representative đã được chạy qua gate trong phạm vi protocol hiện tại. E4–E7 dùng reduced-scale pilot `e4e567_scale_v3_50k`, nên không được diễn giải là full-corpus replication hay positive performance claim tổng quát. Target chạy từ E0 đến E7 là **server H100 80GB**. Windows chỉ dùng đọc tài liệu, chỉnh code và chuẩn bị cấu hình.

**Công việc hiện hành — reviewer revision (31/10/2026):** đọc [17_reviewer_experiments.md](17_reviewer_experiments.md), phần bổ sung của plan chính, và mục `REV` trong [checklist gốc](../checklist.md). Kế hoạch bao phủ toàn bộ PDF reviewer, cả P0/P1/P2 và Q1–Q7; chỉ loại mở rộng corpus. Kết quả cũ lấy từ HF bằng `HF_TOKEN` trong `.env`, pin revision và verify trước reuse. REV-01 raw + extra feasibility, REV-02 đã có đủ raw cells, REV-03 đã chạy đủ 18/18 sensitivity cells, REV-04 depth20 + E5 post-hoc/REV-05 TREC đã verified, REV-06 cost và REV-08 held-out contrasts đã có receipt `VERIFIED`; REV-07, aggregate cuối, wording và Git vẫn mở. Khi triển khai: mỗi kết quả xong sync HF; toàn bộ thí nghiệm xong mới commit/push và tạo hoặc cập nhật **một PR từ một branch duy nhất**. Quy tắc mới này ưu tiên hơn hướng dẫn cũ về thời điểm commit/PR.

Đã rà soát đủ **9 nhóm thí nghiệm/đo,11 clarification và Q1–Q7** trong [bảng đối chiếu M17 mục10](17_reviewer_experiments.md#10-đối-chiếu-đầy-đủ-với-pdf-reviewer). TREC dùng ba map/backfill seed tuples, không chỉ thay map seed; counts core vẫn là54 configurations mới nếu reuse đủ9 historical cells, tối đa63 nếu không reuse. Mỗi mục có gate/checklist riêng; đủ plan chưa phải đủ kết quả.

**Agent bắt đầu tại file này**, rồi đọc đầy đủ report/expect và các file nền bên dưới. Luồng bắt buộc: inputs đã validate → E0/E1 correctness → T0 tuning/timing trong phạm vi hữu hạn → freeze profile → official experiments. T0 làm theo từng dataset/model; FiQA PASS không tự chứng nhận Arctic, BGE, Nomic hoặc full MS MARCO.

## Đọc theo thứ tự

1. **Bắt buộc đọc [report.md](../report.md) và [expect.md](../expect.md) trước khi code**: hiểu bài toán paper, các giới hạn bằng chứng, pipeline, baseline, primary endpoints và expected outputs của E0–E7. Không chỉ đọc tên thí nghiệm hoặc tóm tắt trong plan. Protocol chính nằm ở report mục8.3/15.
2. Đọc [constraints.md](constraints.md): giới hạn phạm vi, provenance tối thiểu và việc không được làm.
3. Đọc [structure.md](structure.md), [contracts.md](contracts.md), [plan.md](plan.md) và [14_presetup_tuning.md](14_presetup_tuning.md): cấu trúc, tên hàm, scoped gates, quy tắc chọn tham số, freeze và điểm dừng.
4. Sau đó chỉ mở thêm module đang triển khai trong bảng dưới; quay lại report/expect khi có lựa chọn ảnh hưởng phương pháp hoặc cách kết luận.
5. Sau mỗi module hoặc run hoàn tất, cập nhật [checklist.md](../checklist.md) ở **gốc project**, bên ngoài `codex/`. Khi checkout trên server, dùng đường dẫn tương đối `PROJECT_ROOT/checklist.md`, không hard-code ổ D.

| File | Công việc được giao |
|---|---|
| [01_environment.md](01_environment.md) | Linux/H100, dependency lock, config, `.env`, probe tài nguyên |
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
| [15_run_budget.md](15_run_budget.md) | Ma trận lịch sử `compact_v1`, không tự mở rộng official E2–E7 |
| [16_e567_downscale.md](16_e567_downscale.md) | Common manifest 50k/5k và phạm vi reduced-scale đã khóa |
| [17_reviewer_experiments.md](17_reviewer_experiments.md) | Kế hoạch bổ sung đầy đủ theo reviewer; baseline, ablation, sensitivity, metrics, seeds, cost, transitions, held-out, AOL proxy; HF và một branch/PR |

## Nguồn quyết định

- User corrected the earlier A100 typo: the target is **H100 80GB in this workspace**. Measure the visible device and current CPU/RAM/storage limits here; the historical 40GB MIG inventory is not a readiness measurement.
- Phương pháp chính theo `report.md` mục 8.3 và 15; `expect.md` giải thích mục tiêu từng E. T0 cụ thể hóa yêu cầu mới tối ưu trước official và lr grid validation đã có ở report15.3. E0–E7 vẫn là **8 milestone**; T0 là prep gate bổ sung.
- Các tài liệu ở đây cụ thể hóa implementation, không được thay đổi primary chỉ vì ablation thắng trên test. Nếu có chỗ chưa rõ, ghi một quyết định ngắn trong config/module đang làm; không tạo thêm chuỗi báo cáo audit.
- User đã yêu cầu auto-upload artifacts và tự tạo các repo tiếp theo. Khi triển khai có thể thực hiện trong namespace có quyền của `HF_TOKEN`; repo **public** theo yêu cầu hiện hành của user. GitHub PR và các HF releases được theo dõi trong checklist gốc.

## Điểm vào cho phiên tiếp theo

Đọc theo thứ tự trên, kiểm trạng thái hiện tại bằng file thật và checklist; chỉ triển khai phần còn thiếu sau khi đối chiếu state, artifact và remote receipt. Không chạy một lượt download/training dài trước E1/T0 tương ứng. Không đánh dấu checklist hoàn thành thí nghiệm chỉ vì đã viết code hoặc tài liệu. Mỗi run có compute, sync và scientific outcome riêng; accepted result phải có đủ gate và remote verification.

Với vòng reviewer, dùng ma trận supplemental M17 thay vì chạy lại toàn bộ E0–E7. Các đoạn trạng thái cũ trong module docs không thay thế [result](../result/README.md), receipts và checklist thực tế; việc cũ đã hoàn tất không chứng minh yêu cầu reviewer mới đã được đáp ứng.
