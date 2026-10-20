# M06 — Exact index, HNSW và serving

Code `index.py`; input stored vectors/fidelity/calibration từ migration. Exact search phải hoạt động trước HNSW. Đây là dense search; không có LLM generation.

## API chung

| Hàm/method | Logic cần code |
|---|---|
| `ExactIndex.build(vectors, ids, fidelity, calibration)` | Vectors thuộc stored snapshot, không Y_full; chunked inner products theo corpus để tránh Q×N full matrix |
| `ExactIndex.search(query_vectors, k=10) -> SearchResult` | Calibrate theo fidelity trên **tất cả stored docs**, lấy top11 theo score giảm/ID tăng; return top10 + cutoff rank11 |
| `HnswIndex.build(vectors, labels, cfg)` | hnswlib pinned v0.9.0, `space='ip'`, dim new, M16/ef_construction200, seed khóa; labels int row IDs |
| `HnswIndex.search(query_vectors, L, ef)` | ef≥L; distance1-dot→raw score1-distance; fetch fidelity/vectors, calibrate candidates, rerank top11/top10 |
| `commit_index_update(rows, new_vectors, fidelity_updates, cal, epoch)` | Same-ID add_items stock graph update; writer lock cả vector/fidelity/cal/epoch, publish version cuối |
| `save_index(path)` / `load_index(path, metadata)` | HNSW binary và đúng labels/flags/cal/epoch; sau load **set ef lại**; verify vector counts/dim |
| `validate_ann_snapshot(index, exact_index, Q_tune)` | Candidate recall@11 + calibrated serving recall@10, raw ANN recall riêng |
| `select_search_config(snapshot, tune_ids, grid)` | Gate và freeze config theo rules bên dưới |

Exact top-k phải xử lý tie across chunks bằng ID gốc. Nếu corpus<11 docs, cutoff diagnostic unavailable thay vì index out-of-range; E1 toy có≥11 khi kiểm slack. Search nhiều queries thì batch Q nhỏ, không nạp full Q×corpus scores. Raw-score topL không đảm bảo calibrated top10 khi true/mapped scale khác, nên cần candidate gate.

## HNSW gate

Grid primary: `(L,ef)=(50,200),(100,200),(500,1000),(1000,2000)`; bắt đầu100/200. So trên cùng bootstrap stored-vector snapshot và Q_tune độc lập. Chọn L nhỏ nhất có **candidate recall@11≥0.99 và serving recall@10≥0.99 trung bình**, tie ef nhỏ hơn. Không có cặp đạt thì `ANN_GATE_FAILED`; exact pilot vẫn báo kết quả, không chuyển largest pair thành PASS.

T0 chọn/freeze search profile cho **đúng dataset/model/bootstrap snapshot**, dùng chung cho các schedulers trong comparison. Nếu so nhiều mapping variants, dùng cặp đạt gate trên các snapshot đã khai báo; không cấp search budget thuận lợi riêng từng method. Kiểm lại ở10/25/50% accessed nhưng không retune test khi quality thấp. TREC-COVID/no-Q_tune kế thừa FiQA cùng model pair; chưa có config thì fixed100/200 label UNTUNED_TRANSFER. Diagnostic trên test chỉ sau khi khóa, không dùng để chọn settings hoặc gọi transfer là PASS0.99.

Subset100k PASS không chứng nhận full3.21M. E4 build actual full bootstrap stored graph, kiểm Q_tune/exact stored và peak footprint, freeze search profile full corpus trước E5. Task ANN bị chặn khi ANN_GATE_FAILED; task exact đã qua T0 correctness vẫn được chạy. M14 định nghĩa policy/profile/run hashes và không cho đổi settings riêng mỗi seed sau khi thấy test.

Raw recall so ANN raw với exact raw trên **cùng snapshot**. Serving recall so top10 sau calibration với exact calibrated snapshot. ARR so ranking migration với full-new exact reference. Ba metric không thay thế nhau.

## Synchronization

- Query giữ read lock từ candidate search đến lấy fidelity/vectors/cal và rerank; trả epoch trong result.
- Encode và chuẩn bị remap ở ngoài lock với input snapshot khóa rõ. Commit giữ writer lock cho cả logical update; hnswlib query không được chạy đồng thời same object add_items.
- Refit đổi global mapped class a/b cũng ảnh hưởng docs ngoài touched regions; publish cal cùng epoch và refresh scheduling toàn bộ theo M07.
- Stock same-ID update có sửa graph neighbors, không gọi frozen topology hay custom repair. Fresh-build graph cùng vectors là control riêng.
- Commit lỗi nửa chừng: mark FAILED_SNAPSHOT, ngừng serving, load last complete checkpoint; không continue state hỏng. Cần test một lỗi inject giữa vector và metadata update.

Lock có thể gây stall lớn khi remap vùng rộng. E3 phải đo lock wait/queue/timeout, không coi lock là bằng chứng zero downtime. Các benchmark cost/latency độc quyền tài nguyên theo M10; không upload nền trong lúc đo.

## Output và tests

Save binary index ở checkpoint measurement quan trọng, kèm metadata tối thiểu. Không tạo dump toàn graph/candidate mỗi batch. Test ID population giữ nguyên, true/mapped calibrated ranking, save-load/ef, same-ID update, failed partial commit và exact100% trùng full-new.

Nguồn implementation: [hnswlib v0.9.0](https://github.com/nmslib/hnswlib/blob/v0.9.0/README.md). Agent phải pin commit thực tế khi cài, không chỉ ghi tên tag trong README.
