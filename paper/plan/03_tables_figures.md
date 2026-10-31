# Kế hoạch bảng và hình

Tối đa khoảng **4 bảng + 4 hình** trong bản 16 trang; ghép panels khi có ý nghĩa. Ưu tiên số đo trả lời RQ. Không đưa bảng completion markers, artifact counts, revisions, hashes, run IDs hay task lifecycle vào paper.

| Mục | Nội dung | Dữ liệu | Thông điệp/caption bắt buộc |
|---|---|---|---|
| Figure 1 | Schematic old→mapped/true→retrieval và budgeted backfill | Procedure thực thi | Không có số performance giả; paid bootstrap cũng là true |
| Table 1 | Dataset/model cases, docs thực dùng, eval groups, schedule groups, judged coverage, backend, seeds | `result/01_data_scope.md`, `07_E7.md` | Full corpus và 50k subcorpus viết ngay trong rows |
| Figure 2 | FiQA mapping curves: nDCG và ARR hai panels | `03_E2.md` | Trục x total target-vector access; bắt đầu bootstrap, không giả 0%; old/full-new refs |
| Table 2 | FiQA bốn scheduler tại 10%: nDCG, ARR, Hit/NFR và dispersion/paired contrasts | `03_E2.md`, `08_statistics.md` | n=648 queries, ba map seeds, một traffic order; CI unit chính xác |
| Figure 3 | MS MARCO50k known-workload ARR và AOL future-week ARR hai panels | `05_E5.md`, `06_E6.md` | Hai populations và x-axis khác nhau; E5 seed range, E6 user-block CI |
| Table 3 | Tám representative cases, random/greedy ARR, OP cross-check và availability | `07_E7.md` | N/A scheduler-specific khi fallback; nDCG chỉ judged scope đủ |
| Figure 4 | Gain-selected vs fallback share; một panel overhead components nếu còn chỗ | events/costs đã tổng hợp | Mechanism descriptive, không suy causal do sparse click coverage |
| Table 4, tùy chỗ | TREC mapping + compact index-fidelity/footprint panel | `03_E2.md`, `04_E3_E4.md` | HNSW fidelity cùng stored snapshot; synthetic update probes gắn nhãn |

Nếu vượt trang: gộp TREC vào Table 2 một panel mapping; gộp fidelity vào một đoạn trong setup/results; bỏ overhead panel trước khi bỏ old/full-new quality references. Không giấu baseline kém hoặc case âm chỉ để tăng vẻ đẹp của paper.

## Công thức xuất số và uncertainty

- Mean metric = mean per-query, sau đó mean qua đúng map seeds trong group. Mapping MLP/random và scheduler MLP/random trùng dữ liệu không được đếm hai lần.
- Không lấy nDCG từ bảng corpus con thiếu positive coverage rồi đổi nhãn thành BEIR score. Trong Table 3, nDCG missing ghi “not evaluated under complete judgments”; ARR ghi “agreement on reduced corpus”.
- Static x = unique target vectors / actual corpus size. FiQA 10% là 5.763/57.638; TREC 17.133/171.332; MS MARCO50k 5.000/50.000. Với bootstrap, x≈0,03505 hoặc 0,02500 tùy case; không nối đường từ x=0.
- E5 endpoint cuối của curve phục vụ HNSW **không ép về 1**. Exact target reference kiểm tra cuối bằng 1 là một phép đo khác.
- Seed min–max bands ghi đúng tên, không dùng ký hiệu CI95%. FiQA CI paired dùng query groups conditional on seed grid. Temporal paired CI dùng user blocks, không lấy riêng CI method rồi so bằng mắt.
- Nếu báo retained nDCG: ratio of corpus/query aggregate means; phải hiển thị absolute values old/new kèm theo. Nomic new có thể không tốt hơn old; retained gần 100% không chứng minh upgrade hữu ích.
- AUC chỉ tích phân trên khoảng checkpoint đã quan sát, normalize bằng độ dài khoảng và ghi bounds. Không báo AUC[0,1] khi không đo phần trước bootstrap, không nội suy chất lượng/chi phí từ giả định tuyến tính.

## Hình thức và khả năng đọc

Dùng plotting chuẩn khi bước viết bắt đầu: matplotlib hoặc công cụ plotting tương đương, xuất PDF/SVG vector cho line plots/diagrams. Không dùng image generation cho scientific plots. Một hệ màu thân thiện colorblind cho bốn scheduler, line style khác nhau khi in grayscale. Axes/captions ghi units; decimals thống nhất 3–4 chữ số, uncertainty đủ precision. Table captions phía trên, figure captions phía dưới theo LNCS.

Tiêu đề/legend dùng OP, LA, MLP, Random, Degree, Read-prioritized, Coverage-greedy và tên encoder dễ đọc. Bảng/hình không có chuỗi tên run, code cấu hình hay ngày chạy. Caption nêu quần thể đánh giá, ngân sách và điều kiện hỗ trợ diễn giải; không kể các bước xác minh artifact.
