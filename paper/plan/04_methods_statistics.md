# Đặc tả phương pháp và thống kê khi viết

Tài liệu này cố định cách diễn giải code đã chạy. Xem [ghi chú code](../../result/11_code_method_notes.md) và [thống kê tính lại](../../result/08_statistics.md) để tra chi tiết. Không thêm phương pháp chưa thực nghiệm vào phần Method.

## Representation và ngân sách

Với tài liệu i, x_i là embedding cũ, y_i là embedding đích đã chuẩn hóa. Khi chưa trả chi phí lấy y_i, lưu z_i = normalize(A_region M_0(x_i) + c_region); sau backfill lưu y_i thật. Query dùng encoder đích. Các pools bootstrap phục vụ fit, validation và calibration đều tính vào số tài liệu có target vector; chúng cũng được phục vụ bằng vector thật.

Định nghĩa b = |A|/N, A là union các document IDs đã truy cập vector đích. Phân biệt b với số tài liệu backfill thêm chia N. FiQA bắt đầu ở 2.020/57.638, điểm gần 10% là 5.763/57.638. MS MARCO50k bắt đầu ở 1.750/50.000, điểm 10% có 3.250 backfill bổ sung. AOL cuối replay có 3.501/50.000 accessed và 1.751/50.000 backfilled. Không viết AOL là “7% incremental backfill”.

Budget là mô phỏng quyền truy cập vector đã cache. Nó không đo số GPU-seconds, chi phí tiền, hay tốc độ encode online. Old/full-new là references về kết quả truy hồi; full-new không phải relevance upper bound.

## Mapping, scoring và lựa chọn backfill

| Thành phần | Cách mô tả phù hợp |
|---|---|
| OP | Orthogonal Procrustes; zero padding khi khác chiều |
| LA | Low-rank affine map, rank 64 |
| MLP | OP-initialized residual MLP, hidden width 256; chọn validation loss |
| Local correction | Regional ridge regression, regularization 10; số regions theo lượng paired data |
| Refit | Global map và regions giữ cố định; local correction cập nhật theo bước 5% corpus được backfill |
| Calibration | Positive affine score calibration; radius là quantile residual thực nghiệm, có fallback khi thiếu dữ liệu |
| Random | Thứ tự giả ngẫu nhiên cố định, bỏ tài liệu đã accessed |
| Degree | Ưu tiên số láng giềng query duy nhất trong graph đã xây |
| Read-prioritized | Duyệt top-10 mapped results theo query order thực thi và cursor; không gọi là live request arrival |
| Coverage-greedy | Tối đa hóa surrogate coverage có gain dương trong snapshot; phần quota còn lại random fill |

FiQA dùng 8 regions, TREC 32, các case 50k dùng 8. Không chép số regions của cấu hình dự kiến full-scale. Radius 95% không phải bảo đảm đồng thời cho mọi query. Một bảo đảm cho fixed-set coverage objective, nếu trình bày, không chuyển thành bảo đảm nDCG, ARR hay adaptive migration.

Index exact ở phần quality chính giúp tách ANN approximation. HNSW giữ cùng ID khi update; code có đường rebuild khi truy vấn gặp lỗi. Các bản MS MARCO hiện hành ghi nhận tổng 22 rebuild trên 12 cấu hình tới cuối migration. Không mô tả hệ thống là “never rebuild”.

## Quần thể và metric

ARR@10 = |top10(method) ∩ top10(exact full-new)|/10. Đây là agreement với một reference ranking, không phải recall theo relevance judgments. nDCG@10 dùng quy ước gain tuyến tính của evaluator đã chạy. Hit@10 là có ít nhất một judged-relevant document trong top 10. NFR@1 là tỷ lệ trên **toàn bộ query** mà top-1 của full-new relevant còn top-1 của phương pháp không relevant; không đổi mẫu số sang riêng query full-new thành công.

FiQA 648 test queries là phân tích chính; các query scheduling độc lập với test. TREC chỉ 50 test queries và mapping comparison. MS MARCO hiện đánh giá đúng 5.000 query groups dùng scheduling: kết luận within-workload. Các corpus con có 4–14/500 query còn positive qrel không cung cấp BEIR relevance comparison chuẩn. AOL dùng dòng log được nhóm theo user; không gọi mọi dòng là một independent query event.

Các fidelity probes FiQA dùng 1.600 development queries gộp calibration và tuning; không mô tả đó là 500 tune queries độc lập. Chúng cũng bắt đầu từ full-true snapshot và perturb vector, không cô lập regional-refit behavior trong migration.

## Thống kê

1. Với FiQA, lấy mean qua ba mapping seeds cho từng query trước khi tính paired contrast giữa policies. Giữ cùng query trong resampling. Không nhân n thành 648 × 3 hoặc đếm lại MLP/random trùng vai trò.
2. Báo effect size, paired query-bootstrap 95% CI với 10.000 draws; sign-flip p và Holm adjustment cho ba greedy-vs-baseline contrasts trong mỗi metric nếu cần. Những so sánh chọn sau khi đọc dữ liệu ghi exploratory. CI này conditional on seed grid, không bao quát mọi retraining/workload realization.
3. OP–MLP, partial–old và FiQA/Nomic new–old là contrast bổ sung; không gắn lại nhãn primary. CI cắt 0 không chứng minh tương đương hay noninferiority.
4. MS MARCO chỉ có aggregate metrics và ba seeds; dùng mean và min–max, không tạo query-level CI hoặc giả significance từ ba con số.
5. AOL giữ user blocks khi bootstrap và log-row weighting trong mỗi draw. Read–Random tuần cuối có paired CI riêng; không suy significance từ hai marginal CIs. Một chronology không thành nhiều temporal replications nhờ tám tuần.
6. Không xem checkpoints, corpus/model cases hoặc retry là iid observations. Giữ tất cả case thuận/nghịch; không tạo một grand mean trộn các populations khác nhau.

Phân tích cơ chế phải tách quan sát và giả thuyết: gain-selected ít là quan sát; “do radius quá bảo thủ”, “do query graph thưa” hoặc “do calibration gây giảm relevance” vẫn cần ablation để xác định nguyên nhân.
