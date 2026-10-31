# Trình tự viết và lịch thực hiện

Viết từ bảng kết quả và experimental design trước, rồi mới viết introduction/abstract. Không chờ có thêm compute để tạo bản đầu. Theo yêu cầu tiếp theo của tác giả, tạo luôn bản thảo tiếng Anh có thể revise, kèm nguồn LaTeX và PDF; không tự nộp conference.

| Giai đoạn | Thời gian mục tiêu | Đầu ra và điều kiện hoàn thành |
|---|---|---|
| Chốt phạm vi và soạn bản đầu | 30/10–03/11/2026 | Plan, bảng từ số đã có, Methods/Results/Limitations và manuscript hoàn chỉnh vòng đầu |
| Tác giả revise câu hỏi và contributions | 04–07/11 | Chốt empirical framing; mỗi contribution có finding và control tương ứng |
| Bổ sung đối chứng có giá trị cao nếu khả thi | 05–13/11 | Query-side mapping trên FiQA; held-out ORCAS nếu query vectors đã sẵn; không mở grid corpus lớn |
| Viết lại theo kết quả cuối | 14–18/11 | Tất cả claims/captions đồng nhất, related work trực tiếp, loại số không đủ scope |
| Review khoa học và kiểm PDF | 19–22/11 | Kiểm novelty, statistical unit, anonymous PDF, references và giới hạn 16 trang |
| Đóng nội dung | 23/11 | PDF ≤16 trang, abstract ≤200 từ, không missing citations, không lẫn số minh họa cũ |
| Tác giả nộp | Trước deadline 25/11 AoE | Tác giả kiểm metadata và upload; hạn quy đổi là 18:59 ngày 26/11 tại Việt Nam |

Các mốc là kế hoạch nội bộ, không phải lịch bổ sung do conference công bố. Không tự chạy GPU experiments, tải toàn corpus lại hay thay pipeline như một phần của việc viết.

## Bản đầu phải có

Một câu hỏi xuyên suốt: khi chỉ thay được một phần vector, chất lượng có được giữ và mục tiêu agreement có dẫn tới lựa chọn phù hợp không? Giữ ba RQs đã chốt, corpus/model scopes cụ thể, old/full-new references, bốn policies, uncertainty và kết quả âm. Các systems probes chỉ hỗ trợ đo lường.

Tạo các hình bằng plotting chuẩn từ bảng đã tải; không vẽ con số minh họa. Caption phải tự chỉ rõ population, budget, exact/ANN và band là seed range hay CI. Có một ghi chú riêng cho tác giả về việc cần revise; không chèn TODO hay lời hướng dẫn nội bộ vào nội dung manuscript.

## Khi tác giả revise

Ưu tiên sửa question/contributions trước câu chữ. Sau đó quyết định có bổ sung baseline gần nhất hay chấp nhận limitations của bản chỉ dùng dữ liệu hiện có. Nếu kết quả đối chứng yếu đi, sửa claim và giữ số; không chuyển endpoint hoặc bỏ case để bảo vệ narrative.

Sau mỗi thay đổi số liệu: cập nhật đúng bảng/hình liên quan, caption, abstract và conclusion; biên dịch lại, kiểm references và PDF. Không chạy lại mọi thí nghiệm khi chỉ sửa văn phong.
