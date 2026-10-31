# Kết quả thực nghiệm đã tổng hợp

Ngày đối chiếu: **30/10/2026, Asia/Saigon**. Đây là kho tổng hợp nghiên cứu nội bộ; kế hoạch viết ở [paper/plan](../paper/plan/README.md).

Đã kiểm kê cả **13 kho Hugging Face** của dự án (8 dữ liệu, 5 kết quả), tất cả thư mục/tệp trong các cây kho, **166 bundle có summary**, toàn bộ bảng chỉ số và báo cáo số học ở cấp bundle. Tập so sánh hiện hành có **69 cấu hình/tác vụ E2–E7**: 24 + 6 + 3 + 12 + 4 + 20. E0, E1 và phát triển được lưu riêng. Các bản chạy lại lịch sử không phải các lần lặp độc lập.

| Tài liệu | Nội dung |
|---|---|
| [01_data_scope.md](01_data_scope.md) | Quy mô thực sự được đánh giá, query roles, coverage |
| [02_E0_E1.md](02_E0_E1.md) | Kiểm tra đầu vào, ngân sách, hoàn tất và khôi phục |
| [03_E2.md](03_E2.md) | Toàn bộ 24 cấu hình hiện hành, chất lượng, đường cong |
| [04_E3_E4.md](04_E3_E4.md) | Fidelity, update probes, footprint và giới hạn systems |
| [05_E5.md](05_E5.md) | 12 cấu hình MS MARCO/ORCAS, ARR và chi phí |
| [06_E6.md](06_E6.md) | AOL theo thời gian, 4 chính sách và ngân sách thực tế |
| [07_E7.md](07_E7.md) | 20 cấu hình trên 8 trường hợp dataset/model |
| [08_statistics.md](08_statistics.md) | Tính lại thống kê paired từ kết quả đã có |
| [09_all_recorded_results.md](09_all_recorded_results.md) | Tất cả 166 bản kết quả, gồm phát triển/lịch sử/lỗi |
| [10_sources_and_coverage.md](10_sources_and_coverage.md) | Liên kết nguồn cố định và phạm vi kiểm tra |
| [11_code_method_notes.md](11_code_method_notes.md) | Phương pháp code thực thi và khác biệt với kế hoạch cũ |

Kết luận dẫn đường: dữ liệu phù hợp nhất với **nghiên cứu thực nghiệm về chất lượng, agreement và lựa chọn backfill khi nâng cấp embedding dưới ngân sách hạn chế**. Chưa có cơ sở cho tuyên bố greedy thắng phổ quát, near-zero downtime, tiết kiệm GPU theo tỷ lệ hay full-corpus MS MARCO/BEIR.

Các con số ở bảng là số đo được tải/tính lại. Nhận định phương pháp và khuyến nghị viết được ghi bằng lời. Tên run, hash, trạng thái truyền tệp và đường dẫn máy chỉ dùng trong sổ nguồn nội bộ; không sao chép sang manuscript. Việc một cấu hình có kết quả không tự chứng minh mọi baseline và mọi thí nghiệm từng dự kiến đã được thực hiện.
