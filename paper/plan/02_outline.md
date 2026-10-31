# Dàn bài chi tiết

Mục tiêu: **15,5 trang LNCS**, chừa 0,5 trang đệm trong giới hạn 16 trang gồm references. Đây là ngân sách biên tập, không phải quy định mỗi section của hội nghị. Khoảng 5.000–6.000 từ phần thân tùy kích thước hình/bảng; phải kiểm PDF thực tế khi draft.

| Phần | Trang mục tiêu | Vai trò |
|---|---:|---|
| Title + Abstract | 0,5 | Câu hỏi, thiết kế và hai phát hiện có giới hạn |
| 1 Introduction | 1,5 | Vấn đề migration và nghiên cứu muốn làm rõ |
| 2 Background and Related Work | 1,5 | Conversion, compatibility và backfill; chỉ rõ phần kế thừa |
| 3 Problem and Migration Procedure | 2,0 | Representation, budget, mapping, scoring và bốn policies |
| 4 Experimental Design | 2,0 | Dữ liệu, scopes, metrics, controls, statistics |
| 5 Results | 4,5 | Ba RQs, relevance–agreement và case limits |
| 6 Discussion and Limitations | 1,0 | Quyết định thực hành, giới hạn và điều chưa biết |
| 7 Conclusion | 0,5 | Điều học được trong phạm vi dữ liệu |
| References | 2,0 | Công trình trực tiếp và nguồn dữ liệu/phần mềm |
| **Tổng** | **15,5** | Không dành thêm phụ lục ngoài hạn mức |

## Abstract: 170–190 từ tiếng Anh

Một câu nêu chi phí/gián đoạn logic khi thay encoder; một câu đặt câu hỏi partial re-embedding có giữ chất lượng hay chỉ giữ ranking agreement; hai câu mô tả comparison với old/full-new, mapping và backfill policies. Báo rõ có full small corpora và các corpus con 50k. Chọn tối đa hai con số: FiQA partial-vs-old hoặc contrast relevance–agreement, và temporal difference có scope. Kết câu bằng insight thực dụng đã chứng minh, không hứa một hệ thống production mới.

Không mở bằng “We solve”, “first”, “universal” hay số savings. Không đưa tên run, trạng thái kiểm chứng, checklist hoặc workflow nội bộ vào abstract. Giới hạn hội nghị là 200 từ, ưu tiên thấp hơn để có đệm.

## 1. Introduction

**Mục đích:** làm người đọc thấy đây là bài toán quản lý vector khi model thay đổi và câu hỏi chất lượng trong giai đoạn chuyển tiếp.

Đoạn 1 giải thích old/new spaces và vì sao query mới không so trực tiếp với document cũ. Đoạn 2 tóm lược conversion và gradual replacement, thừa nhận prior work đã hỗ trợ converted/true mixture. Đoạn 3 đặt câu hỏi: budget nhỏ cho quality nào, và agreement có đủ để quyết định migration không? Đoạn 4 dùng một finding thật trên FiQA làm motivation, ghi rõ corpus/budget. Đoạn 5 nêu ba đóng góp thực nghiệm và giới hạn scale.

**Dữ liệu:** bảng mapping/scheduler, old/full-new; related work conversion. **Chuyển đoạn:** trước khi xem kết quả cần định nghĩa vectors, access budget và backfill.

## 2. Background and Related Work

### 2.1. Representation conversion and compatible retrieval

Phân biệt query→old-space adapters với document→new-space conversion; encoder training-time compatibility với frozen-encoder post-hoc mapping. Dành trọng lượng chính cho Drift-Adapter và Embedding-Converter; nêu rõ mixed embeddings đã được đánh giá trong prior work.

### 2.2. Incremental replacement and index maintenance

Giải thích backfill, query-derived selection và stock index updates. Embedding Surgery/DGM có mục tiêu khác; không dùng số của họ để so trực tiếp budgeted partial quality. Kết bằng gap hẹp cần kiểm chứng: **đường cong relevance và agreement khi tiếp tục thay dần ở cùng access budget, với khả năng thiếu scheduling signal**.

**Chuyển đoạn:** đặt notation cho study, không dựng lý thuyết mới từ các thành phần quen thuộc.

## 3. Problem and Migration Procedure

### 3.1. State and budget

Định nghĩa old x, target y, stored z và fidelity flag. Query dùng target encoder. Budget là union target document accesses, gồm train/validation/calibration và backfill; true fraction sau commit bằng accessed fraction. Phân biệt scheduled fraction. Một schematic minh họa state và luồng, không có số hiệu năng minh họa.

### 3.2. Mapping and mixed scoring

Mô tả ngắn OP/LA/MLP, regional ridge correction và positive score calibration. Học từ pools đã khóa; giữ M0/regions cố định sau bootstrap; refit local theo lượng backfill. Nêu điều kiện radius thiếu và identity fallback. Không gán novelty hay guarantee thống kê cho empirical radius.

### 3.3. Backfill policies

Trình bày random, degree, read-prioritized và coverage-greedy trong một bảng cùng một pseudocode tối đa khoảng 12–18 dòng. Coverage surrogate fixed-snapshot và random fill phải hiện rõ. Mô tả read query order đã thực thi, không gọi là actual live request arrival.

**Nguồn phương pháp:** code được diễn giải trong `result/11_code_method_notes.md`; đây là tài liệu người viết, không dẫn path này trong paper. **Chuyển đoạn:** cùng procedure cần các test populations và metrics tách biệt.

## 4. Experimental Design

### 4.1. Collections, model transitions and evaluation populations

Một bảng chứa corpus thực dùng, test queries, schedule availability, judged coverage, search backend và seeds. Các dòng corpus con ghi 50k ngay trong nhãn. FiQA/TREC full; NQ/HotpotQA/FEVER reduced; MS MARCO query workload known; AOL real chronology sampled by user block, đo log rows.

### 4.2. Controls, metrics and budgets

Old/old và full-new exact; OP/LA/MLP controls; bốn scheduler; common bootstrap và frozen hyperparameters. Định nghĩa nDCG, ARR và NFR. Nói rõ full-new là target reference, không chất lượng upper bound. Tách ANN fidelity từ ARR, cached vectors từ live encoder costs.

### 4.3. Uncertainty and analysis scope

Mean qua map seeds trong mỗi query trước paired analysis; conditional query bootstrap, sign-flip và contrast family. Temporal user-block weights và exploratory paired reanalysis. E5 chỉ seed ranges. Không dùng checkpoint/case/bản chạy lại như iid replicate.

**Chuyển đoạn:** bắt đầu bằng chất lượng tuyệt đối trước khi bàn scheduler.

## 5. Results

### 5.1. Does partial replacement improve quality at small budgets?

Đường cong FiQA OP/LA/MLP với old/full-new horizontal reference; bảng TREC mapping. Dẫn finding partial nDCG có thể thấp hơn old, mapping ranking đổi giữa corpus. Chỉ nói “first observed checkpoint above old” nếu dùng lưới đã đo; không nội suy budget threshold chính xác hay gọi CI cắt 0 là không thua kém.

### 5.2. Agreement and relevance favor different priorities

Bảng bốn scheduler FiQA có nDCG/ARR/Hit/NFR, effect và uncertainty cần thiết. Highlight Degree cải thiện ARR nhưng relevance thấp; greedy không tách khỏi random/read về nDCG. Có thể ghép scatter ARR–nDCG với hai trục đơn vị rõ, tránh biểu đồ một scalar “quality”.

### 5.3. Known-workload and future-workload behavior

MS MARCO50k mean curves, scope within schedule workload, gain/fallback và cached overhead. AOL weekly curves, actual accessed/scheduled budgets và paired user-block difference tuần cuối. Giữ temporal result một chronology, không đồng nhất phương pháp read với live on-demand embedding.

### 5.4. Transfer across model transitions and available signals

Heatmap/table tám case, ARR + qrel/schedule availability; nDCG chỉ full judged cases. Giải thích những hàng greedy thực chất fallback. Nomic FiQA nhắc target quality không tự cao hơn old. Giữ tất cả case thuận/nghịch, không đưa mỗi mean gộp.

Đoạn cuối hỗ trợ đo lường: exact completion, HNSW fidelity đã quan sát và rebuild behavior. Không dành một section lớn cho restore/engineering gates.

## 6. Discussion and Limitations

Nêu quy tắc thực hành có điều kiện: đánh giá old/new relevance trước khi cutover query encoder; giữ ARR và nDCG riêng; kiểm tra scheduling-signal availability và fallback; không xem indexed vector fraction là inference savings. Chỉ đề xuất policy mới như hướng nghiên cứu, không thêm “adaptive winner selection” chưa đánh giá vào method.

Giới hạn phải hiện diện: reduced corpora/coverage, partial factorial, ba map seeds hoặc một seed theo case, E5 in-sample queries, một temporal timeline, log-row weights, missing matched prior baselines, thiếu controlled calibration/regional ablations và production latency/live-cost measurement. Vị trí limitations không che mất kết quả âm trong Results.

## 7. Conclusion

Một đoạn trả lời ba RQs trong scope đã đo: khả năng mất relevance sớm, agreement không đủ để chọn scheduler, và ích lợi scheduling phụ thuộc workload/tín hiệu thực có. Không hứa tiết kiệm compute toàn hệ hay universal algorithmic superiority. Chỉ thêm một câu về nhu cầu held-out workload và baseline comparison tiếp theo.
