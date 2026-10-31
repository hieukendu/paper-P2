# Kế hoạch viết paper DASFAA 2027

Hướng chọn: **nghiên cứu thực nghiệm về relevance, agreement và chính sách backfill khi nâng cấp embedding dưới ngân sách hạn chế**. Tiêu đề làm việc: **“Partial Re-Embedding for Vector Index Migration: An Empirical Study of Quality and Agreement.”**

Đây là kế hoạch viết từ số liệu đã chạy, không kế thừa các con số minh họa hoặc lời hứa full-scale trong bản thảo cũ. Đã tổng hợp dữ liệu trước khi lập dàn bài: xem [kết quả](../../result/README.md).

Theo yêu cầu tiếp theo của tác giả, đã viết bản đầu để revise: [PDF](../main.pdf), [nguồn LaTeX](../main.tex). Các đối chứng còn thiếu được nêu trong limitations và trong kế hoạch bổ sung; chưa chạy thêm thí nghiệm GPU.

| Đọc theo thứ tự | Mục đích |
|---|---|
| [00_constraints.md](00_constraints.md) | Quy tắc bắt buộc cho mọi phần của manuscript |
| [01_direction.md](01_direction.md) | Hướng chọn, RQs, đóng góp và phạm vi kết luận |
| [02_outline.md](02_outline.md) | Dàn bài, thông điệp từng phần, ngân sách trang |
| [03_tables_figures.md](03_tables_figures.md) | Bảng/hình cần làm và số liệu dùng được |
| [04_methods_statistics.md](04_methods_statistics.md) | Đặc tả phương pháp và phân tích đúng với code đã chạy |
| [05_related_work.md](05_related_work.md) | Vị trí so với nghiên cứu gần nhất đã xác minh |
| [06_writing_plan.md](06_writing_plan.md) | Trình tự viết, đầu ra cụ thể và lịch khả thi |
| [07_gaps_and_review.md](07_gaps_and_review.md) | Thiếu hụt còn lại, bổ sung tối thiểu, phản biện dự kiến |
| [08_dasfaa_format.md](08_dasfaa_format.md) | Quy định hội nghị và template Springer hiện hành |

Ba phát hiện dẫn đường đã có số liệu: chất lượng giai đoạn đầu có thể thấp hơn hệ cũ; tăng agreement có thể đi cùng giảm relevance; coverage-greedy thường sử dụng rất ít lựa chọn có gain và không thắng các baseline đơn giản một cách ổn định. Đây là nền cho một bài đánh giá có giới hạn rõ, không phải bài khẳng định một thuật toán mới luôn tốt hơn.

Mục tiêu là bản Research Track rõ câu hỏi khoa học, có phương pháp và so sánh kiểm chứng được. Khả năng được nhận còn phụ thuộc novelty và baseline coverage; không có dữ liệu để gán xác suất acceptance. Kế hoạch này hoàn tất công việc chuẩn bị; nó không tuyên bố manuscript đã sẵn sàng nộp.
