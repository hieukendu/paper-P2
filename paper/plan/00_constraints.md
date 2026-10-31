# Ràng buộc viết paper

Các quy tắc dưới đây là bắt buộc cho tác giả và mọi lượt hỗ trợ viết tiếp theo.

1. **Chỉ báo cáo khái niệm, phương pháp và kết quả khoa học.** Không kể quy trình chạy máy, queue, retry, upload, auto-sync, checklist, worker, receipt, catalog, content hash, profile hash, source snapshot, tên run hoặc mã quản lý thí nghiệm. Chỉ giữ chi tiết triển khai cần hiểu thuật toán, ngân sách hoặc phép đo.
2. Tên dataset, cặp encoder, seed, kích thước mẫu, query split, thuật toán, cutoff, search parameters và phần cứng là thông tin phương pháp cần thiết. Không bỏ chúng vì nhầm với provenance. Dùng tên khoa học dễ đọc trong bảng; không dùng tên thư mục cấu hình hay ID nội bộ.
3. Mỗi số trong manuscript phải lấy từ kết quả đã tổng hợp và kiểm tra. Sổ nguồn chỉ phục vụ người viết ở `result/`; manuscript không trưng bày các mã tra cứu đó. Không lấy số từ phần minh họa của bản thảo cũ làm kết quả.
4. Không biến kết quả bất lợi thành lỗi kỹ thuật; cũng không biến thiếu phép đo thành kết quả âm. Báo đầy đủ mapping/scheduler/case đã định trong phạm vi nghiên cứu. Không chọn seed/corpus/checkpoint đẹp rồi gọi là primary.
5. Không hứa greedy thắng phổ quát, relevance giữ trên một tỷ lệ cao chưa được đo, near-zero downtime, giảm memory một nửa, tiết kiệm GPU theo phần trăm hoặc triển khai ở quy mô triệu/tỷ vector. Các số đo hiện có không hỗ trợ những câu này.
6. Corpus 50.000 tài liệu phải được ghi là corpus con ngay caption, setup và abstract nếu được nhắc. FiQA 57.638 và TREC-COVID 171.332 là full corpus; không gọi toàn bộ nghiên cứu là full MS MARCO/full BEIR.
7. Phân biệt **ngân sách truy cập target vectors**, **tài liệu backfill thêm**, **tỷ lệ vector true**, **chi phí encoder thật** và **cached execution time**. Mốc 10% static bao gồm bootstrap. Temporal thực tế là 7,002% accessed và 3,502% backfill thêm; không viết thành 7% scheduled.
8. ARR@10 là overlap với top10 full-new exact, không phải judged Recall@10 hay relevance. Luôn giữ absolute nDCG của hệ cũ và full-new trong thí nghiệm có judgments. Full-new là reference, không mặc nhiên là relevance upper bound.
9. Với corpus con thiếu judgments, không công bố số nDCG đã tính như BEIR score chuẩn. Với không có scheduling queries hoặc không có gain, ghi N/A/fallback và mô tả cơ chế thật; không gọi đó là thắng/hòa của một scheduler có thông tin.
10. Không tuyên bố mixed mapped/true embeddings, OP/LA/MLP, ridge, score calibration hay greedy coverage là phát minh mới riêng lẻ. Related work đã có embedding conversion và mixed embeddings. Chỉ khẳng định phần khác biệt được tài liệu và số đo hiện có hỗ trợ.
11. Không biến radius quantile 95% thành certificate cho mọi query. Không gán bảo đảm fixed coverage objective cho adaptive retrieval/nDCG/ARR, ANN hoặc cả tiến trình migration.
12. Giữ bất định, uncertainty unit và giới hạn thiết kế. Seed ranges không phải confidence intervals; các case thiếu query controls không dùng cho causal attribution. Không nói “equivalent” chỉ vì CI cắt 0.
13. Hạn chế phần phương pháp vào những thành phần thật sự cần để hiểu thí nghiệm. Không thêm framework, dashboard, service, orchestration layer hay tên gọi cầu kỳ để tạo cảm giác đóng góp. Một schematic, một mô tả state và một thuật toán ngắn là đủ.
14. Bản nộp viết **tiếng Anh**, theo template LNCS chính thức, tối đa **16 trang gồm cả references/appendices**, abstract tối đa **200 từ**, double blind. Không nén margin/font hay đẩy nội dung thiết yếu ra supplement không được CFP bảo đảm.
15. Chưa thực hiện baseline thì không tạo dòng kết quả, số mô phỏng hoặc tuyên bố vượt nó. Thảo luận công trình liên quan không thay cho đánh giá thực nghiệm cùng budget.

Ví dụ câu viết đúng: “At 10% target-vector access, read-prioritized backfill increased agreement on the observed workload, while its relevance advantage over random backfill was not resolved on FiQA.” Khi viết chi tiết phải kèm giá trị và scope tương ứng. Không dùng số within-workload để khẳng định generalization.

Trước khi chốt từng section, kiểm ba điều: người đọc hiểu câu hỏi khoa học; số liệu thực sự trả lời câu hỏi đó; caption không mở rộng phạm vi quá phép đo.
