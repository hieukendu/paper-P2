# Bản thảo đầu để revise

Hướng: **Partial Re-Embedding for Vector Index Migration: An Empirical Study of Quality and Agreement**.

Bản đầu hiện có **14 trang**, abstract **171 từ**, 4 hình vector và 3 bảng. Đã kiểm bố cục PDF, citations/references, font nhúng và số liệu trong bảng; không có unresolved references hoặc nội dung tràn ngang trong log biên dịch.

- [main.pdf](main.pdf): bản đọc đã biên dịch theo LNCS, anonymous.
- [main.tex](main.tex): nguồn nội dung tiếng Anh.
- [references.bib](references.bib): tài liệu tham khảo; hai bài gần nhất lấy metadata từ ACL Anthology.
- [plan/README.md](plan/README.md): constraints, hướng viết, outline, kế hoạch và gaps.
- [../result/README.md](../result/README.md): tổng hợp kết quả E0–E7 và phạm vi dữ liệu.
- `data/`: bảng số khoa học dùng tạo hình; `make_figures.py` tạo lại bốn hình vector trong `figures/`.

Bản thảo này dùng số liệu đã có và có phần limitations đầy đủ; chưa phải bản được tác giả chốt để nộp. Không chạy thêm thí nghiệm GPU và không tạo số baseline còn thiếu. File `../main.pdf` của bản tham khảo cũ được giữ nguyên.

Ưu tiên revise: contribution có đủ khác prior work không; bổ sung query-side adapter có khả thi không; MS MARCO có thể đánh giá held-out queries không. Xem [gaps](plan/07_gaps_and_review.md). Các tên run, nguồn kiểm tra và lịch sử thực thi chỉ ở tài liệu nội bộ `result/`, không đưa vào manuscript.

Template `llncs.cls` và `splncs04.bst` được giữ từ ZIP chính thức của Springer. PDF đầu đã biên dịch bằng Tectonic với bibliography; có thể dùng pdfLaTeX và BibTeX trên hệ có đầy đủ font. Không sửa margin/font/layout để đạt giới hạn trang. Kiểm tra lại CFP trước bản nộp cuối.
