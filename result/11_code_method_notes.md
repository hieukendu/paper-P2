# Phương pháp thực thi và cách diễn giải

## Pipeline khoa học

Encoder cũ/new đều frozen; vectors dense float32, unit norm. Học forward global map từ old→new bằng document pairs: OP, low-rank affine rank 64, residual MLP hidden 256. MLP có nhánh linear OP-init và residual GELU, last residual zero-init; LA có diagonal/cross-dimension padding và rank factors. Train bằng squared vector loss trước normalize; chọn checkpoint/lr từ document validation, lr grid {1e-4,1e-3}, max 50 epochs, patience 5. Không có RL hay fine-tune encoder.

Document train = min(10.000, ceil(2%N)); validation = min(2.000, ceil(0,5%N)); mỗi cal pool tối đa min(1.000, ceil(0,5%N)). Pool disjoint, tất cả vector true đã trả phí phục vụ ngay từ bootstrap. Vì vậy 0% scheduled không phải 0% new-encoder access.

M0 và region assignments frozen sau bootstrap. Region count là power of two không vượt min(256,max(1,n_train//100)); FiQA 8, TREC 32, các pool 50k có train 1.000 nên 8, không lấy R=64/256 của full-scale design. Ridge 10, đủ ít nhất 20 train/backfill pairs mỗi vùng. Regional map refit sau mỗi 5%N backfilled, remap các vectors vẫn mapped trong vùng chạm tới; validation/cal pairs không vào fitting stats.

Cal-fit fit positive affine score a*s+b; cal-check lấy quantile residual 95%, empirical radius không phải uniform/worst-case certificate. True vectors giữ raw cosine. Thiếu data giữ identity/radius-unavailable theo quy tắc; không thay r để làm greedy thắng. Candidate greedy dùng relevant proxy trong top10 có slack trong (r,2r], loại query đã có proxy chắc hơn 2r; chỉ fixed-snapshot weighted coverage có classical greedy guarantee, không có guarantee nDCG/ARR adaptive toàn migration.

Random chọn uniformly without replacement. Degree xếp số query neighbors độc lập, tie theo original doc ID. Read duyệt top10 của query order đã khóa và backfill first occurrence; đọc hết thì random fill. Greedy refresh toàn schedule pool rồi chọn gain dương; cạn gain thì random fill. Không đổi định nghĩa để các hàng fallback thành algorithm wins.

Exact index tie-break ID gốc. HNSW dùng hnswlib stock same-ID updates, không phải custom/frozen-edge graph repair. Code có rebuild graph khi thư viện không trả được contiguous candidate matrix; cần tính chi phí rebuild nếu benchmark. One serving index không đồng nghĩa chỉ giữ một bản vectors hay memory tổng giảm một nửa.

## Khác biệt quan trọng giữa đặc tả và dữ liệu

| Nội dung cũ | Code/kết quả thực thi | Cách viết đúng |
|---|---|---|
| MS MARCO/ORCAS held-out ARR | E5 dùng scheduling queries làm evaluation | Within-workload ARR, chưa đo generalization |
| E6 7% scheduled | 7,002% total accessed, 3,502% scheduled | Báo cả bootstrap và backfill fractions |
| E6 400k query events | Parser giữ từng raw log row, có thể nhiều clicked items/query | 400k log rows; chưa gộp event instances |
| E3 cadence refit chất lượng | Noise 1e-5, cuối E2 100% true | Synthetic index-update probe |
| E3 production p99/downtime | 4 readers/3 commits và failure restore | Correctness probe; không có latency SLO |
| Greedy trên TREC/NQ | Không schedule/cal query độc lập; random fallback | N/A cho scheduler-specific claim |
| E5 completion ARR=1 | Exact target self-reference=1; serving HNSW ~0,991–0,995 | Tách serving và exact reference |
| Full BEIR trên case lớn | 50k corpus, 500 queries, 0,8–2,8% qrel coverage | Reduced-corpus agreement diagnostic |
| New encoder tốt hơn | FiQA/Nomic new mean nDCG thấp hơn old, CI delta cắt 0 | New version không tự là quality upgrade |
| Regional/calibration hữu ích độc lập | Không có balanced ablation đầy đủ trong 69 primary tasks | Thành phần implementation, hiệu ứng chưa cô lập |
| Drift-Adapter/dual-index đã so | Không có kết quả baseline tương ứng trong bundles | Related work; không ghi thắng chúng |

Mã scientific core trong snapshots của E2/E5/E6/E7 khớp code local dùng để diễn giải. Các sửa đổi bookkeeping/admission E3/E4 không đổi số đo đã lưu. Các tài liệu README/report/codex có đoạn trạng thái cũ trái checklist; không dùng câu “chưa implementation” hay “mọi E hoàn tất” của tài liệu làm phép kiểm scientific endpoint.

## Metric và chi phí

ARR@10 = mean(|top10_current ∩ top10_full-new-exact|/10), không phải judged Recall@10. nDCG@10 là relevance gain tuyến tính theo pytrec_eval, có query IDCG=0 giữ điểm 0 và phải báo số lượng. NFR@1 là tỷ lệ trên toàn query mà target top1 relevant nhưng current top1 không relevant; không phải old→new negative flip conditional. Retained nDCG = ratio of aggregate means, không mean per-query ratios; full-new không nhất thiết là relevance upper bound.

Quality cells truy cập vectors target qua accessor từ evaluator cache. Unique paid docs là ngân sách mô phỏng truy cập target; lookup_seconds không phải GPU inference. Encoder/runtime probes có thật nhưng sample lengths, cache status, thiết bị chia sẻ và scope khác nhau. Không dùng một hệ số docs/s để tạo claim full-corpus savings. Không cộng timer parent/child, không lấy CPU wall-time thành GPU time, không suy latency từ batch/search duration.

## Việc chưa được chứng minh

Chưa có reproduced Drift-Adapter/Embedding-Converter trên chính splits/budget; không có full dual-index benchmark, theory rescue certificate validation, full regional/calibration/fixed-map ablation, corpus-scale sweep giữ coverage, hay isolated live migration cost/latency study. Không tự chuyển các thiếu hụt này thành kết quả âm; chúng là chưa đo. Kế hoạch viết đã thu hẹp contribution khoa học và nêu rõ những bổ sung tối thiểu nếu muốn tăng sức thuyết phục.

## Chi tiết state và correction cần giữ đúng

Regional correction là affine map trên output global: normalize(A_region M_0(x) + c_region), ridge prior về identity; không phải cộng một residual map trực tiếp lên x. HNSW counters tới cuối 12 cấu hình E5 ghi tổng 22 rebuild; E4 subset probe có 1. Systems probes FiQA sử dụng 1.600 development queries gộp calibration/tune, không phải 500 tune queries độc lập.
