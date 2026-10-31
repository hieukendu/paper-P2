# Thiếu hụt và dự kiến phản biện

## Đánh giá khả năng acceptance

**Hướng empirical study khả thi và phù hợp số liệu hơn hướng thuật toán thắng phổ quát. Với dữ liệu giữ nguyên, rủi ro bị từ chối ở DASFAA Research Track còn cao.** Chưa có cơ sở để đưa phần trăm acceptance. Viết tốt giúp người đọc đánh giá contribution rõ hơn; nó không thay đối chứng khoa học còn thiếu.

Điểm đáng theo đuổi là policy ranking reversal giữa relevance và agreement, degradation ở giai đoạn đầu dù full-new tốt hơn old, cùng phân tích selection signal thực có. Nguy cơ lớn nhất là reviewer thấy đây là phép đánh giá hẹp của một pipeline riêng, với kết luận metric mismatch vốn đã biết. Vì vậy phải thể hiện mức độ và hệ quả thực tế bằng controls, tránh nâng phản ví dụ thành nguyên lý mới.

| Ưu tiên | Phản biện có thể gặp | Hiện có gì | Cách xử lý trung thực |
|---|---|---|---|
| 1 | Novelty so với conversion/mixed embeddings đã công bố là gì? | Budget curves, scheduler comparison, gain/fallback, quality–agreement reversal | Thừa nhận prior art; thu hẹp contribution vào study và empirical findings; thêm nearest baseline nếu làm được |
| 2 | Vì sao không giữ old index bằng query-side adapter? | Old/old reference, chưa có matched query adaptation | Bổ sung query-side OP ở FiQA có khả năng dùng cached vectors; chưa chạy thì không nhận thắng baseline |
| 3 | Có thực sự giúp user relevance không? | Partial FiQA/TREC ở 10% kém old; Read chủ yếu tăng ARR | Báo degradation và quality curves trước khi báo scheduler gains; không quảng bá early upgrade |
| 4 | Study có generalize không? | Full FiQA/TREC, các 50k cases và một chronology | Phân biệt supporting cases và primary evidence; không gọi full-scale benchmark |
| 5 | Query-derived policy có dùng chính evaluation workload? | FiQA held-out; MS MARCO trùng scheduling/eval queries | Gắn nhãn within-workload; held-out ORCAS là bổ sung có ích nhất cho workload generalization |
| 6 | Cơ chế regional/calibration nào gây hiệu ứng? | Cùng settings giữa policies, chưa có controlled ablations | Không suy nhân quả; có thể thêm regional-off/calibration-off trên FiQA nhỏ nếu còn tài nguyên |
| 7 | Greedy có được thực sự kích hoạt? | Gain rất ít hoặc bằng 0; phần còn lại fallback | Hiện rõ counts và fallback; thiếu signal không phải bằng chứng greedy tương đương khi có signal |
| 8 | Cost/downtime claims có thật không? | Cached timers, fidelity probes, có graph rebuild | Bỏ GPU savings/zero-downtime claims; chỉ báo phạm vi đã đo |
| 9 | Thống kê có quá lạc quan? | Ba map seeds, một traffic seed; E5 aggregate-only | Conditional query CI, user-block temporal CI; không pseudoreplication |

## Bổ sung tối thiểu, không mở rộng phạm vi quá sức

**Ưu tiên A:** query-side OP adapter và forward OP trên FiQA, dùng cùng paid paired pool, giữ 648 test queries độc lập. So old/old, query adapter, forward mixed pipeline và full-new trên cả relevance/agreement. Mục tiêu là xem gradual backfill có thêm giá trị so với phương án giữ index cũ; không buộc kết quả phải thuận lợi.

**Ưu tiên B:** đánh giá snapshots MS MARCO trên ORCAS held-out đã được phân vai, nếu đủ văn bản/vector query. Không retrain scheduling trên held-out. So cả within-workload và held-out curves. Nếu chưa có vectors thì phải ước lượng tài nguyên trước, không coi đó là bước “miễn phí”.

**Ưu tiên C:** nếu A/B đã ổn, làm một ablation nhỏ của local correction và score calibration trên FiQA với common seeds/budgets. Thiết kế để giải thích degradation, không tạo full factorial mới trên mọi corpus.

Đây là đề xuất cho vòng revise, chưa phải thí nghiệm đã thực hiện. Không thêm số chưa đo vào manuscript. Không ưu tiên corpus lớn thứ tư hay thứ năm khi baseline gần nhất còn thiếu.

## Khi không có thêm compute

Vẫn viết được bản empirical paper đầy đủ, có limitations rõ ràng. Giảm trọng lượng các case ít judgment; dùng FiQA làm backbone; không tuyên bố superiority hay production readiness. Submission như vậy có contribution có thể đánh giá, nhưng chưa nên tự coi là mạnh chỉ vì có nhiều bảng. Tác giả có thể dùng bản đầu để quyết định mức bổ sung trước khi nộp.
