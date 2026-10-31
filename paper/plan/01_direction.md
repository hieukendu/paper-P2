# Hướng paper được chọn

## Quyết định

Viết **empirical database/vector-retrieval study** về quá trình thay thế dần vector khi thay embedding model. Trọng tâm là điều kiện và giới hạn của partial re-embedding; pipeline MixIndex là phương tiện nghiên cứu. Không lấy chiến thắng của coverage-greedy làm premise.

Tiêu đề chính đề xuất: **Partial Re-Embedding for Vector Index Migration: An Empirical Study of Quality and Agreement**.

Tiêu đề thay thế nếu cần nêu hệ thống: **MixIndex: Quality and Agreement during Budgeted Embedding Migration**. Tránh “near-zero downtime”, “scalable”, “optimal”, “universal” hoặc từ ngữ hứa cải thiện toàn diện.

Luận điểm dự kiến: **trong các phép nâng cấp đã khảo sát, tiến gần ranking của encoder đích và giữ relevance cho người dùng là hai mục tiêu có thể khác nhau; lựa chọn mapping và tín hiệu scheduling quyết định liệu partial re-embedding có hữu ích ở ngân sách nhỏ hay không.** Vế “quyết định” khi viết kết quả phải dùng ngôn ngữ quan sát, không coi nghiên cứu hiện tại đã cô lập nhân quả của từng thành phần.

## Vì sao chọn hướng này

| Hướng | Số liệu hiện có | Điểm yếu | Quyết định |
|---|---|---|---|
| Thuật toán greedy tốt hơn mọi baseline | Không được FiQA/MS MARCO/AOL hỗ trợ nhất quán | Sai premise, gain rất thưa, fallback lớn | Không dùng |
| Hệ migration production quy mô lớn/zero downtime | Có fidelity và restore probes nhỏ | Thiếu live cost, latency workload và corpus-scale replication | Không dùng |
| Một embedding map mới | OP/LA/MLP và regional/calibration đã triển khai | Thành phần quen thuộc, thiếu matched prior baselines/ablation | Không lấy làm novelty chính |
| Nghiên cứu quality–agreement–budget và vai trò scheduling | Full FiQA/TREC, bốn cặp encoder, đường cong, case thời gian | Cần thu hẹp claims và đối chiếu prior work kỹ | **Chọn** |

Đây là hướng có thể viết từ phép đo đã có, không phụ thuộc mua compute lớn. So với những hướng còn lại, nó tránh đặt kết luận vào giả thuyết đã bị dữ liệu phản đối. Điều này tăng tính thuyết phục của lập luận, không bảo đảm một mức acceptance cụ thể.

## Câu hỏi nghiên cứu

**RQ1 — Chất lượng trong quá trình nâng cấp:** Với cùng ngân sách target-vector access, partial re-embedding giữ relevance và agreement đến mức nào so với old/old và full-new? OP-, LA- và MLP-based pipelines khác nhau ra sao?

**RQ2 — Giá trị của backfill ưu tiên:** Khi giữ bootstrap/budget/mapping/refit policy cố định, random, degree, read-prioritized và coverage-greedy cho đường cong khác nhau ra sao? Khi nào kết luận đổi nếu nhìn ARR thay nDCG?

**RQ3 — Phạm vi khái quát và tín hiệu:** Các xu hướng có còn xuất hiện qua cặp encoder, corpus con và replay có thời gian không? Scheduling có bao nhiêu lựa chọn gain dương thực tế, và những trường hợp nào chỉ chạy fallback?

Systems fidelity là kiểm tra hỗ trợ độ tin cậy của phép đo, không mở thêm RQ “production performance” vì chưa có bằng chứng đủ mạnh.

## Những phát hiện có thể đặt vào câu chuyện

| Phát hiện | Số hiện có | Diễn giải được phép |
|---|---|---|
| Partial migration có thể kém hệ cũ | FiQA MLP/random nDCG 0,280003 tại 10%; old 0,368671; target 0,499633 | Không xem chuyển sang query encoder mới là upgrade relevance miễn phí |
| Không có map thắng mọi corpus | FiQA OP 0,292782 > MLP 0,280003; TREC MLP 0,450328 > OP 0,441190 | So các pipeline under matched settings; TREC chỉ 50 queries |
| ARR và relevance cho kết luận khác nhau | FiQA Degree ARR ~0,405710, Random ~0,386574; nDCG Degree ~0,233201 < Random ~0,280003 | Cần cả hai loại metric; không dùng agreement làm proxy relevance |
| Read có ích cho agreement ở một số workload | FiQA Read ARR ~0,416975; MS MARCO 50k Read ~0,288333, Random ~0,265653 | FiQA held-out; MS MARCO within-workload, không gộp hai population |
| Temporal advantage có phạm vi hẹp | AOL tuần 8 Read 0,163158, Random 0,153740; paired user-block CI delta [0,006696; 0,012306] | Exploratory, một chronology, log-row weights, ngân sách thực tế 7,002% accessed |
| Cặp encoder ảnh hưởng mạnh tính tương thích | FiQA/Nomic random ARR 0,753549 tại 10%, MiniLM→MPNet ~0,386574 | Dataset/scope này; token limits/training/model cùng khác nên không quy nhân quả cho drift riêng |
| Greedy thường cạn gain | E5 chỉ 18–20/3.250 lựa chọn tới 10%; AOL 0/1.751 | Mô tả coverage proxy và fallback thực tế; chưa chứng minh nguyên nhân duy nhất |

Số đầy đủ và uncertainty nằm trong [kết quả](../../result/README.md). Những phát hiện phụ được chọn sau khi đọc dữ liệu phải được ghi là exploratory; không đổi primary endpoint cũ để tạo kết quả dương.

## Đóng góp dự kiến, tối đa ba ý

1. Một thiết kế đánh giá rõ ngân sách cho gradual vector replacement, tách **agreement với target**, **judged relevance** và **incremental backfill** trong cùng tiến trình migration.
2. Một so sánh thực nghiệm có controls cho thấy khác biệt giữa các mapping/backfill policies và phản ví dụ cho việc coi agreement hoặc phiên bản encoder mới là bảo đảm relevance.
3. Một phân tích giới hạn sử dụng query-derived scheduling trong các corpus/workload đã khảo sát, kết hợp gain/fallback counts, scope của nhãn và replay tương lai có thời gian.

Không gọi đây là benchmark đầu tiên, thuật toán đầu tiên hay định luật tổng quát khi chưa hoàn tất literature coverage. Một bài thực nghiệm cần insight cụ thể và controls đủ tốt; việc gom nhiều số đo tự nó chưa là contribution.

## Phạm vi phần thực nghiệm chính

Đặt **FiQA exact** làm xương sống vì có full corpus, 648 test queries, ba map seeds và đủ bốn scheduler. TREC là mapping-only supporting case; không dùng làm scheduler evidence. E7 giải thích variability và giới hạn theo từng case. MS MARCO 50k là within-workload case bổ trợ; AOL là temporal case có giới hạn. HNSW/fidelity/restore gói trong một đoạn hoặc bảng nhỏ.

Đừng biến phần kết quả thành nhật ký tám stage thực thi. Sắp theo RQs và findings, còn tên nội bộ của các nhóm thí nghiệm chỉ dùng để người viết tra kết quả.
